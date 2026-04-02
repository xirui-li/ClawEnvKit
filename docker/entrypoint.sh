#!/bin/bash
set -e

TASK_YAML="/opt/claw-harness/task.yaml"
MOCK_DIR="/opt/claw-harness/mock_services"
LOGS_DIR="/logs"
PORT="${PORT:-9100}"

mkdir -p "$LOGS_DIR"

# --- Grade function (defined first so trap can use it) ---
grade() {
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

def endpoint_to_action(endpoint, service):
    """Map endpoint path to action name.
    /todo/tasks/create → create_task
    /todo/tasks        → list_tasks
    /gmail/messages    → list_inbox
    /gmail/send        → send_email
    /gmail/drafts/save → create_draft
    """
    # Strip service prefix: /todo/tasks/create → tasks/create
    parts = endpoint.strip("/").split("/")
    if parts and parts[0] == service:
        parts = parts[1:]

    # Common patterns
    path = "/".join(parts)

    # Resource/action pattern: tasks/create → create_task
    if len(parts) == 2:
        resource, verb = parts
        singular = resource.rstrip("s") if resource.endswith("s") else resource
        return f"{verb}_{singular}"

    # Resource/sub/action: tasks/update → update_task, drafts/save → create_draft
    if len(parts) >= 2:
        resource = parts[0]
        verb = parts[-1]
        singular = resource.rstrip("s") if resource.endswith("s") else resource
        return f"{verb}_{singular}"

    # Single resource: tasks → list_tasks, messages → list_inbox
    if len(parts) == 1:
        resource = parts[0]
        list_map = {
            "tasks": "list_tasks", "messages": "list_inbox",
            "events": "list_events", "tickets": "list_tickets",
            "customers": "list_customers", "products": "list_products",
            "jobs": "list_jobs", "notes": "list_notes",
            "feeds": "list_feeds", "articles": "list_articles",
            "integrations": "list_integrations",
        }
        return list_map.get(resource, f"list_{resource}")

    return endpoint.split("/")[-1]

audit_data = {service: []}
if isinstance(raw_audit, dict):
    for call in raw_audit.get("calls", []):
        endpoint = call.get("endpoint", "")
        action = endpoint_to_action(endpoint, service)
        audit_data[service].append({
            "action": action,
            "params": call.get("params", call.get("body", call.get("request_body", {}))),
            "status": call.get("status", 200),
        })
    for key, items in raw_audit.items():
        if key == "calls": continue
        if isinstance(items, list):
            for item in items:
                audit_data[service].append({
                    "action": key.rstrip("s"),
                    "params": item if isinstance(item, dict) else {},
                    "status": 200,
                })

agent_output = ""
if os.path.exists("/workspace/agent_output.txt"):
    agent_output = open("/workspace/agent_output.txt").read()

engine = GradingEngine()
result = engine.grade(config, audit_data, agent_output)

with open(os.environ["LOGS_DIR"] + "/reward.txt", "w") as f:
    f.write(f"{result.final_score:.4f}\n")

details = {
    "completion": result.completion,
    "robustness": result.robustness,
    "safety": result.safety,
    "final_score": result.final_score,
    "components": [
        {"name": c.name, "passed": c.passed, "score": c.score, "weight": c.weight}
        for c in result.component_results
    ],
    "safety_violations": result.safety_violations,
}
with open(os.environ["LOGS_DIR"] + "/grading.json", "w") as f:
    json.dump(details, f, indent=2)

print(f"Score: {result.final_score:.2f}")
for c in result.component_results:
    icon = "✅" if c.passed else "❌"
    print(f"  {icon} [{c.weight:.0%}] {c.name}: {c.score:.2f}")
if result.safety_violations:
    print(f"🚨 Safety: {result.safety_violations}")
GRADE_EOF
}

export TASK_YAML LOGS_DIR

# --- Parse task config ---
SERVICE_NAME="${SERVICE_NAME:-$(python3 -c "import yaml; print(yaml.safe_load(open('$TASK_YAML')).get('task_id','').split('-')[0])")}"
export SERVICE_NAME
echo "[harness] Service: $SERVICE_NAME" >&2

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
    echo "[harness] Starting $SERVICE_NAME on port $PORT..." >&2
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
    echo "[harness] WARNING: No server for $SERVICE_NAME" >&2
fi

# --- Write task info for agent ---
python3 -c "
import yaml, json
config = yaml.safe_load(open('$TASK_YAML'))
with open('/workspace/task_prompt.txt', 'w') as f:
    f.write(config.get('prompt', ''))
with open('/workspace/task_tools.json', 'w') as f:
    json.dump(config.get('tools', []), f, indent=2)
with open('/workspace/api_base_url.txt', 'w') as f:
    f.write('http://localhost:$PORT')
"

echo "[harness] Task: $(python3 -c "import yaml; print(yaml.safe_load(open('$TASK_YAML')).get('task_name',''))")" >&2

# --- Set trap to grade on exit ---
cleanup() {
    grade
    [ -n "$SERVICE_PID" ] && kill $SERVICE_PID 2>/dev/null
}
trap cleanup EXIT

# --- Wait for agent (interactive mode) ---
TIMEOUT="${TIMEOUT:-300}"
echo "[harness] Waiting for agent (timeout: ${TIMEOUT}s)..." >&2
echo "[harness] Use: docker exec <container> curl http://localhost:$PORT/$SERVICE_NAME/..." >&2
sleep "$TIMEOUT"
