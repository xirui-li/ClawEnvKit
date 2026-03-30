#!/bin/bash
set -e

TASK_YAML="${TASK_YAML:-/opt/clawharness/task.yaml}"
MOCK_DIR="/opt/clawharness/mock_services"
LOGS_DIR="/logs"
PORT="${PORT:-9100}"

mkdir -p "$LOGS_DIR" /workspace

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

# --- Generate SKILL.md for this task ---
python3 << 'SKILLEOF'
import yaml, json, os

config = yaml.safe_load(open(os.environ["TASK_YAML"]))
service = os.environ["SERVICE_NAME"]
port = os.environ["PORT"]

tools = config.get("tools", [])
tool_docs = ""
for t in tools:
    tool_docs += f"\n### {t['name']}\n"
    tool_docs += f"{t.get('description', '')}\n"
    tool_docs += f"```\ncurl -s -X {t.get('method', 'POST')} http://localhost:{port}{t.get('endpoint', '')} \\\n"
    tool_docs += f"  -H 'Content-Type: application/json' \\\n"
    tool_docs += f"  -d '{{...}}'\n```\n"

skill_md = f"""---
name: eval-task
description: Complete the evaluation task using the mock {service} API
---

# Evaluation Task

## Task
{config.get('prompt', '')}

## API Documentation
Base URL: http://localhost:{port}

{tool_docs}

## Instructions
1. Read the task above carefully
2. Use the bash tool to make curl requests to the API endpoints
3. Complete all required actions
4. Write a summary of what you did when finished

## Important
- All API calls use POST method with JSON body
- The API is at http://localhost:{port}
- Use curl with -s -X POST -H 'Content-Type: application/json' -d '{{...}}'
"""

skill_dir = "/root/.openclaw/workspace/skills/eval-task"
os.makedirs(skill_dir, exist_ok=True)
with open(f"{skill_dir}/SKILL.md", "w") as f:
    f.write(skill_md)

# Also write task files to workspace
with open("/workspace/task_prompt.txt", "w") as f:
    f.write(config.get("prompt", ""))
with open("/workspace/task_tools.json", "w") as f:
    json.dump(tools, f, indent=2)

print(f"[harness] SKILL.md written to {skill_dir}/SKILL.md", flush=True)
SKILLEOF

# --- Configure OpenClaw ---
echo "[harness] Configuring OpenClaw..." >&2

export OPENCLAW_WORKSPACE="/root/.openclaw/workspace"

# Setup workspace
openclaw setup --non-interactive 2>/dev/null || true

# Allow exec tool without sandbox (we're already in a container)
openclaw config set tools.exec.host gateway 2>/dev/null || true

# Allow localhost/private IP access (needed for mock service)
openclaw config set security.allowPrivateIPs true 2>/dev/null || true
openclaw config set security.web_fetch.allowPrivateIPs true 2>/dev/null || true
openclaw config set tools.web_fetch.allowPrivateIPs true 2>/dev/null || true

# Write config directly if CLI config doesn't work
python3 -c "
import json, os
config_path = '/root/.openclaw/openclaw.json'
config = {}
if os.path.exists(config_path):
    config = json.load(open(config_path))

# Allow exec on gateway host
config.setdefault('tools', {})
config['tools']['exec'] = config['tools'].get('exec', {})
config['tools']['exec']['host'] = 'gateway'

# Allow private IPs for web_fetch (needed for localhost mock service)
config['tools']['web_fetch'] = config['tools'].get('web_fetch', {})
config['tools']['web_fetch']['allowPrivateIPs'] = True

# Disable sandbox requirement
config.setdefault('agents', {}).setdefault('defaults', {}).setdefault('sandbox', {})
config['agents']['defaults']['sandbox']['mode'] = 'off'

with open(config_path, 'w') as f:
    json.dump(config, f, indent=2)
print('[harness] OpenClaw config written', flush=True)
"

# --- Run OpenClaw agent ---
echo "[harness] Running OpenClaw agent (local mode)..." >&2

TASK_PROMPT=$(python3 -c "import yaml; print(yaml.safe_load(open('$TASK_YAML')).get('prompt',''))")

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

kill $SERVICE_PID 2>/dev/null
