#!/bin/bash
set -e

TASK_YAML="${TASK_YAML:-/opt/clawharness/task.yaml}"
MOCK_DIR="/opt/clawharness/mock_services"
LOGS_DIR="/logs"
PORT="${PORT:-9100}"

mkdir -p "$LOGS_DIR" /workspace

# --- Check task.yaml exists ---
if [ ! -f "$TASK_YAML" ]; then
    echo "[harness] ERROR: No task.yaml found at $TASK_YAML" >&2
    echo "[harness] Mount with: -v /path/to/task.yaml:$TASK_YAML:ro" >&2
    exit 1
fi

# --- Copy to /tmp to prevent writes to mounted file ---
cp "$TASK_YAML" /tmp/task_config.yaml
TASK_YAML="/tmp/task_config.yaml"
export TASK_YAML LOGS_DIR PORT

# --- Auto-detect SERVICE_NAME from task.yaml ---
YAML_SERVICE=$(python3 -c "import yaml; print(yaml.safe_load(open('$TASK_YAML')).get('task_id','').split('-')[0])")
if [ -n "$SERVICE_NAME" ] && [ "$SERVICE_NAME" != "$YAML_SERVICE" ]; then
    echo "[harness] WARNING: SERVICE_NAME=$SERVICE_NAME but task is $YAML_SERVICE. Using $YAML_SERVICE." >&2
fi
SERVICE_NAME="$YAML_SERVICE"
export SERVICE_NAME

TASK_NAME=$(python3 -c "import yaml; print(yaml.safe_load(open('$TASK_YAML')).get('task_name',''))")
echo "[harness] Task: $TASK_NAME" >&2
echo "[harness] Service: $SERVICE_NAME | Model: ${MODEL:-default} | Port: $PORT" >&2

# --- Extract fixtures ---
python3 -c "
import yaml, json
config = yaml.safe_load(open('$TASK_YAML'))
fixtures = config.get('fixtures', {})
if isinstance(fixtures, dict) and len(fixtures) == 1:
    fixture_data = list(fixtures.values())[0]
elif isinstance(fixtures, dict):
    for v in fixtures.values():
        if isinstance(v, list):
            fixture_data = v
            break
    else:
        fixture_data = fixtures
else:
    fixture_data = fixtures
with open('/tmp/fixtures.json', 'w') as f:
    json.dump(fixture_data, f)
"
export "${SERVICE_NAME^^}_FIXTURES=/tmp/fixtures.json"

# --- Start mock service ---
SERVER_FILE="$MOCK_DIR/$SERVICE_NAME/server.py"
if [ -f "$SERVER_FILE" ]; then
    echo "[harness] Starting $SERVICE_NAME..." >&2
    PORT=$PORT python3 "$SERVER_FILE" &
    SERVICE_PID=$!
    for i in $(seq 1 20); do
        if curl -s "http://localhost:$PORT/$SERVICE_NAME/audit" > /dev/null 2>&1; then
            echo "[harness] $SERVICE_NAME ready" >&2
            break
        fi
        sleep 0.5
    done
else
    echo "[harness] ERROR: No server for $SERVICE_NAME at $SERVER_FILE" >&2
    exit 1
fi

# --- Run agent ---
echo "[harness] Starting agent (model=$MODEL, max_turns=$MAX_TURNS)..." >&2
python3 /opt/clawharness/clawharness/evaluate/agent_loop.py

# --- Grade ---
echo "[harness] Collecting audit..." >&2
curl -s "http://localhost:$PORT/$SERVICE_NAME/audit" > "$LOGS_DIR/audit.json" 2>/dev/null || echo "{}" > "$LOGS_DIR/audit.json"

echo "[harness] Grading..." >&2
python3 << 'GRADE_EOF'
import json, yaml, sys, os
sys.path.insert(0, '/opt/clawharness')
from clawharness.evaluate.engine import GradingEngine

config = yaml.safe_load(open(os.environ["TASK_YAML"]))
raw_audit = json.load(open(os.environ["LOGS_DIR"] + "/audit.json"))
service = os.environ["SERVICE_NAME"]

def endpoint_to_action(endpoint, svc):
    parts = endpoint.strip("/").split("/")
    if parts and parts[0] == svc:
        parts = parts[1:]
    if len(parts) == 2:
        return f"{parts[1]}_{parts[0].rstrip('s')}"
    if len(parts) >= 2:
        return f"{parts[-1]}_{parts[0].rstrip('s')}"
    if len(parts) == 1:
        mapping = {"tasks":"list_tasks","messages":"list_inbox","events":"list_events",
                   "tickets":"list_tickets","customers":"list_customers","products":"list_products",
                   "jobs":"list_jobs","notes":"list_notes","feeds":"list_feeds",
                   "articles":"list_articles","integrations":"list_integrations","items":"list_items"}
        return mapping.get(parts[0], f"list_{parts[0]}")
    return endpoint.split("/")[-1]

audit_data = {service: []}
if isinstance(raw_audit, dict):
    for call in raw_audit.get("calls", []):
        audit_data[service].append({
            "action": endpoint_to_action(call.get("endpoint",""), service),
            "params": call.get("params", call.get("body", call.get("request_body", {}))),
            "status": call.get("status", 200),
        })
    for key, items in raw_audit.items():
        if key == "calls": continue
        if isinstance(items, list):
            for item in items:
                audit_data[service].append({"action": key.rstrip("s"), "params": item if isinstance(item, dict) else {}, "status": 200})

agent_output = ""
if os.path.exists("/workspace/agent_output.txt"):
    agent_output = open("/workspace/agent_output.txt").read()

efficiency_data = {}
if os.path.exists(os.environ["LOGS_DIR"] + "/efficiency.json"):
    efficiency_data = json.load(open(os.environ["LOGS_DIR"] + "/efficiency.json"))

engine = GradingEngine()
result = engine.grade(config, audit_data, agent_output)

with open(os.environ["LOGS_DIR"] + "/reward.txt", "w") as f:
    f.write(f"{result.final_score:.4f}\n")

details = {
    "completion": result.completion, "robustness": result.robustness,
    "safety": result.safety, "final_score": result.final_score,
    "components": [{"name":c.name,"passed":c.passed,"score":c.score,"weight":c.weight} for c in result.component_results],
    "safety_violations": result.safety_violations,
    "efficiency": efficiency_data,
    "model": os.environ.get("MODEL", "unknown"),
}
with open(os.environ["LOGS_DIR"] + "/grading.json", "w") as f:
    json.dump(details, f, indent=2)

print(f"Score: {result.final_score:.2f}")
for c in result.component_results:
    print(f"  {'✅' if c.passed else '❌'} [{c.weight:.0%}] {c.name}: {c.score:.2f}")
if result.safety_violations:
    print(f"🚨 Safety: {result.safety_violations}")
GRADE_EOF

# --- Output score ---
SCORE=$(cat "$LOGS_DIR/reward.txt")
echo "$SCORE"

# --- Fix permissions for host user ---
chmod -R 777 "$LOGS_DIR" 2>/dev/null

# --- Cleanup ---
kill $SERVICE_PID 2>/dev/null
