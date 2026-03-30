#!/bin/bash
set -e

TASK_YAML="${TASK_YAML:-/opt/clawharness/task.yaml}"
MOCK_DIR="/opt/clawharness/mock_services"
LOGS_DIR="/logs"
PORT="${PORT:-9100}"

mkdir -p "$LOGS_DIR" /workspace

# Note: localhost hostname added via docker run --add-host localhost:127.0.0.1

SERVICE_NAME="${SERVICE_NAME:-$(python3 -c "import yaml; print(yaml.safe_load(open('$TASK_YAML')).get('task_id','').split('-')[0])")}"
export SERVICE_NAME TASK_YAML LOGS_DIR PORT

TASK_NAME=$(python3 -c "import yaml; print(yaml.safe_load(open('$TASK_YAML')).get('task_name',''))")
echo "[harness] Task: $TASK_NAME" >&2
echo "[harness] Service: $SERVICE_NAME | Agent: OpenClaw | Port: $PORT" >&2

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
fi

# No SKILL.md injected — fair evaluation, agent gets only the task prompt

# --- Configure OpenClaw ---
echo "[harness] Configuring OpenClaw..." >&2

export OPENCLAW_WORKSPACE="/home/node/.openclaw/workspace"

# Setup workspace (creates initial config)
openclaw setup --non-interactive 2>/dev/null || true

# Overwrite config with ONLY valid keys — start fresh to avoid unrecognized key errors
python3 -c "
import json, os

config_path = '/home/node/.openclaw/openclaw.json'

# Read existing config to preserve model provider settings
existing = {}
if os.path.exists(config_path):
    try:
        existing = json.load(open(config_path))
    except:
        existing = {}

# Build clean config with ONLY recognized keys
config = {}

# Preserve model providers if they exist
if 'models' in existing:
    config['models'] = existing['models']

# Gateway: must be set to local for container use
config['gateway'] = {
    'mode': 'local'
}

# Tools: allow exec on gateway (no sandbox in container)
config['tools'] = {
    'exec': {'host': 'gateway'}
}

# Agents: disable sandbox
config['agents'] = {
    'defaults': {
        'sandbox': {'mode': 'off'}
    }
}

# Browser: allow private network (localhost mock service)
config['browser'] = {
    'ssrfPolicy': {
        'dangerouslyAllowPrivateNetwork': True,
        'allowedHostnames': ['localhost', '127.0.0.1', 'localhost']
    }
}

with open(config_path, 'w') as f:
    json.dump(config, f, indent=2)

print('[harness] OpenClaw config written (clean)', flush=True)
"

# --- Start gateway in background ---
echo "[harness] Starting OpenClaw gateway..." >&2
openclaw gateway --force &
GATEWAY_PID=$!

# Wait for gateway to be ready
for i in $(seq 1 15); do
    if curl -s http://127.0.0.1:18789/__openclaw__/health > /dev/null 2>&1; then
        echo "[harness] Gateway ready" >&2
        break
    fi
    sleep 1
done

# --- Build task prompt with API info (part of task spec, not a hint) ---
TASK_PROMPT=$(python3 -c "
import yaml, json, os

config = yaml.safe_load(open(os.environ['TASK_YAML']))
port = os.environ['PORT']

prompt = config.get('prompt', '')
tools = config.get('tools', [])

if tools:
    prompt += '\n\nAvailable API (running at http://localhost:' + port + '):\n'
    for t in tools:
        endpoint = t.get('endpoint', '')
        method = t.get('method', 'POST')
        desc = t.get('description', '')
        prompt += f'  - {method} http://localhost:{port}{endpoint} — {desc}\n'

print(prompt)
")

echo "[harness] Running OpenClaw agent..." >&2

openclaw agent \
  --local \
  --session-id "eval-$$" \
  --message "$TASK_PROMPT" \
  --json \
  --timeout 120 \
  2>&1 | tee /workspace/agent_output.txt || true

echo "[harness] OpenClaw finished" >&2

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
        mapping = {"tasks":"list_tasks","messages":"list_inbox","events":"list_events","tickets":"list_tickets","customers":"list_customers","products":"list_products","jobs":"list_jobs","notes":"list_notes","feeds":"list_feeds","articles":"list_articles","integrations":"list_integrations"}
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

agent_output = open("/workspace/agent_output.txt").read() if os.path.exists("/workspace/agent_output.txt") else ""

engine = GradingEngine()
result = engine.grade(config, audit_data, agent_output)

with open(os.environ["LOGS_DIR"] + "/reward.txt", "w") as f:
    f.write(f"{result.final_score:.4f}\n")

details = {
    "completion": result.completion, "robustness": result.robustness,
    "safety": result.safety, "final_score": result.final_score,
    "components": [{"name":c.name,"passed":c.passed,"score":c.score,"weight":c.weight} for c in result.component_results],
    "safety_violations": result.safety_violations,
    "agent": "openclaw",
    "model": os.environ.get("MODEL", os.environ.get("OPENCLAW_MODEL", "unknown")),
}
with open(os.environ["LOGS_DIR"] + "/grading.json", "w") as f:
    json.dump(details, f, indent=2)

print(f"Score: {result.final_score:.2f}")
for c in result.component_results:
    print(f"  {'✅' if c.passed else '❌'} [{c.weight:.0%}] {c.name}: {c.score:.2f}")
if result.safety_violations:
    print(f"🚨 Safety: {result.safety_violations}")
GRADE_EOF

echo "$(cat $LOGS_DIR/reward.txt)"

kill $SERVICE_PID $GATEWAY_PID 2>/dev/null
