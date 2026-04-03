#!/bin/bash
# Entrypoint for Claude Code CLI evaluation
#
# Uses MCP server to expose mock service endpoints as native tools.
# Claude Code sees create_task, list_tasks, etc. via MCP protocol.
#
# Supported env vars (pick ONE):
#   OPENROUTER_API_KEY — any model via OpenRouter
#   ANTHROPIC_API_KEY  — Anthropic models directly
# Claude Code natively supports both.

set -e

TASK_YAML="${TASK_YAML:-/opt/clawharness/task.yaml}"
MOCK_DIR="/opt/clawharness/mock_services"
LOGS_DIR="/logs"
PORT="${PORT:-9100}"
MODEL="${MODEL:-claude-sonnet-4-6}"

mkdir -p "$LOGS_DIR" /workspace

# --- Copy fixture files to workspace (multimodal support) ---
python3 -c "
import yaml, shutil, os
config = yaml.safe_load(open('$TASK_YAML'))
files = config.get('files', [])
for f in files:
    src = f.get('source', '')
    tgt = f.get('target', '')
    if not src or not tgt:
        continue
    candidates = [src, os.path.join(str(__import__('pathlib').Path(os.environ.get('TASK_YAML','/opt/clawharness/task.yaml')).parent), src), f'/opt/clawharness/{src}', f'/workspace/{src}']
    for candidate in candidates:
        if os.path.exists(candidate):
            dst = f'/workspace/{tgt}'
            os.makedirs(os.path.dirname(dst) or '/workspace', exist_ok=True)
            shutil.copy2(candidate, dst)
            print(f'[harness] Copied {candidate} → {dst}', flush=True)
            break
if files:
    print(f'[harness] {len(files)} fixture files copied to /workspace/', flush=True)
" 2>/dev/null || true

# --- Detect services needed ---
SERVICES=$(python3 -c "
import yaml
config = yaml.safe_load(open('$TASK_YAML'))
tools = config.get('tools', [])
services = sorted(set(t.get('service','') for t in tools if t.get('service')))
if not services:
    services = [config.get('task_id','').split('-')[0]]
print(','.join(services))
")
SERVICE_NAME="${SERVICES%%,*}"
export SERVICE_NAME SERVICES TASK_YAML LOGS_DIR PORT MODEL
# Route prefix for health check (web_real/web_real_injection use /web/ routes)
case "$SERVICE_NAME" in web_real|web_real_injection) HEALTH_PREFIX="web" ;; *) HEALTH_PREFIX="$SERVICE_NAME" ;; esac

TASK_NAME=$(python3 -c "import yaml; print(yaml.safe_load(open('$TASK_YAML')).get('task_name',''))")
echo "[harness] Task: $TASK_NAME" >&2
echo "[harness] Services: $SERVICES | Agent: Claude Code | Port: $PORT | Model: $MODEL" >&2

# --- Extract fixtures (per-service) ---
python3 << 'FIXTURE_EOF'
import yaml, json, os

config = yaml.safe_load(open(os.environ.get("TASK_YAML", "/opt/clawharness/task.yaml")))
fixtures = config.get("fixtures", {})
services = os.environ.get("SERVICES", "").split(",")

if not isinstance(fixtures, dict):
    with open("/tmp/fixtures.json", "w") as f:
        json.dump(fixtures, f)
else:
    resource_to_service = {
        "inbox": "gmail", "messages": "gmail", "drafts": "gmail",
        "events": "calendar", "tasks": "todo", "contacts": "contacts",
        "tickets": "helpdesk", "notes": "notes", "customers": "crm",
        "products": "inventory", "transactions": "finance",
        "jobs": "scheduler", "feeds": "rss", "articles": "rss",
        "integrations": "config", "images": "ocr", "documents": "documents",
        "pages": "web", "search_results": "web",
        "tracks": "spotify", "playlists": "spotify",
    }
    for svc in services:
        svc_data = None
        if svc in fixtures:
            svc_data = fixtures[svc]
        else:
            for key, data in fixtures.items():
                mapped = resource_to_service.get(key, "")
                if mapped == svc:
                    svc_data = data
                    break
                # Handle ambiguous keys: 'articles' used by both kb and rss
                if key == 'articles' and svc == 'kb':
                    svc_data = data
                    break
        if svc_data is not None:
            if isinstance(svc_data, dict) and len(svc_data) == 1:
                svc_data = list(svc_data.values())[0]
            path = f"/tmp/fixtures_{svc}.json"
            with open(path, "w") as f:
                json.dump(svc_data if isinstance(svc_data, list) else [svc_data], f)
            print(f"[harness] Fixture {svc} → {path}", flush=True)
        else:
            path = f"/tmp/fixtures_{svc}.json"
            with open(path, "w") as f:
                json.dump([], f)

    if len(fixtures) == 1:
        data = list(fixtures.values())[0]
        if isinstance(data, dict) and len(data) == 1:
            data = list(data.values())[0]
    else:
        data = fixtures
    with open("/tmp/fixtures.json", "w") as f:
        json.dump(data if isinstance(data, list) else data, f)
FIXTURE_EOF

# Set fixture env vars — use per-service file if available
for svc in $(echo "$SERVICES" | tr ',' ' '); do
    if [ -f "/tmp/fixtures_${svc}.json" ]; then
        export "${svc^^}_FIXTURES=/tmp/fixtures_${svc}.json"
    else
        export "${svc^^}_FIXTURES=/tmp/fixtures.json"
    fi
done

# --- Start mock service(s) ---
if echo "$SERVICES" | grep -q ","; then
    echo "[harness] Starting multi-service: $SERVICES..." >&2
    SERVICES=$SERVICES PORT=$PORT python3 "$MOCK_DIR/multi_server.py" --services "$SERVICES" &
    SERVICE_PID=$!
    for i in $(seq 1 20); do
        if curl -s "http://localhost:$PORT/$HEALTH_PREFIX/audit" > /dev/null 2>&1; then
            echo "[harness] Services ready" >&2
            break
        fi
        sleep 0.5
    done
else
    SERVER_FILE="$MOCK_DIR/$SERVICE_NAME/server.py"
    if [ -f "$SERVER_FILE" ]; then
        echo "[harness] Starting $SERVICE_NAME..." >&2
        PORT=$PORT python3 "$SERVER_FILE" &
        SERVICE_PID=$!
        for i in $(seq 1 20); do
            if curl -s "http://localhost:$PORT/$HEALTH_PREFIX/audit" > /dev/null 2>&1; then
                echo "[harness] $SERVICE_NAME ready" >&2
                break
            fi
            sleep 0.5
        done
    else
        echo "[harness] ERROR: No server for $SERVICE_NAME at $SERVER_FILE" >&2
        exit 1
    fi
fi

# --- Generate tool definitions (same as OpenClaw entrypoint) ---
echo "[harness] Generating tool definitions..." >&2
python3 << 'TOOLGEN_EOF'
import json, yaml, os, urllib.request

task_yaml = os.environ.get('TASK_YAML', '/opt/clawharness/task.yaml')
port = os.environ.get('PORT', '9100')

task = yaml.safe_load(open(task_yaml))
task_tools = task.get('tools', [])

if not task_tools:
    json.dump([], open('/tmp/eval-tools.json', 'w'))
    print('[harness] No tools defined in task.yaml', flush=True)
    import sys; sys.exit(0)

openapi = None
try:
    openapi_url = f'http://localhost:{port}/openapi.json'
    openapi = json.loads(urllib.request.urlopen(openapi_url, timeout=5).read())
except Exception as e:
    print(f'[harness] WARNING: Could not fetch OpenAPI spec: {e}', flush=True)

def resolve_ref(ref, spec):
    parts = ref.lstrip('#/').split('/')
    obj = spec
    for p in parts:
        obj = obj[p]
    return obj

eval_tools = []
for t in task_tools:
    endpoint = t['endpoint']
    method = t.get('method', 'POST').lower()
    params = {}
    required = []
    if openapi:
        path_item = openapi.get('paths', {}).get(endpoint, {})
        operation = path_item.get(method, {})
        if 'requestBody' in operation:
            content = operation['requestBody'].get('content', {})
            json_content = content.get('application/json', {})
            schema = json_content.get('schema', {})
            if '$ref' in schema:
                schema = resolve_ref(schema['$ref'], openapi)
            params = dict(schema.get('properties', {}))
            required = list(schema.get('required', []))
            for key, prop in list(params.items()):
                if '$ref' in prop:
                    params[key] = resolve_ref(prop['$ref'], openapi)
    eval_tools.append({
        'name': t['name'],
        'description': t.get('description', ''),
        'endpoint': endpoint,
        'method': method,
        'port': int(port),
        'parameters': params,
        'required': required,
    })

json.dump(eval_tools, open('/tmp/eval-tools.json', 'w'), indent=2)
print(f'[harness] Generated {len(eval_tools)} tool definitions', flush=True)
TOOLGEN_EOF

# --- Configure Claude Code MCP ---
echo "[harness] Configuring Claude Code MCP..." >&2

# Claude Code reads .mcp.json from working directory for project-scoped MCP servers
python3 -c "
import json
config = {
    'mcpServers': {
        'clawharness': {
            'command': 'node',
            'args': ['/opt/clawharness/mcp_server/index.js'],
            'env': {
                'EVAL_TOOLS_FILE': '/tmp/eval-tools.json'
            }
        }
    }
}
with open('/workspace/.mcp.json', 'w') as f:
    json.dump(config, f, indent=2)
print('[harness] Claude Code MCP configured (.mcp.json)', flush=True)
"

# --- Run Claude Code agent ---
echo "[harness] Running Claude Code agent..." >&2

TASK_PROMPT=$(python3 -c "import yaml; print(yaml.safe_load(open('$TASK_YAML')).get('prompt',''))")

# Claude Code CLI: -p for prompt mode (non-interactive), --model to select model
# MCP tools are named mcp__clawharness__<tool_name> (double underscore separator)
claude -p "$TASK_PROMPT" \
  --model "$MODEL" \
  2>&1 | tee /workspace/agent_output.txt || true

echo "[harness] Claude Code finished" >&2

# --- Grade ---
echo "[harness] Collecting audit..." >&2
python3 -c "
import json, os, urllib.request
services = os.environ.get('SERVICES', os.environ['SERVICE_NAME']).split(',')
port = os.environ['PORT']
logs = os.environ['LOGS_DIR']
all_audits = {}
for svc in services:
    try:
        # web_real and web_real_injection use /web/ prefix, not /web_real/
        prefix = {'web_real': 'web', 'web_real_injection': 'web'}.get(svc, svc)
        data = json.loads(urllib.request.urlopen(f'http://localhost:{port}/{prefix}/audit', timeout=5).read())
        all_audits[svc] = data
    except:
        all_audits[svc] = {'calls': []}
injected = []
try:
    data = json.loads(urllib.request.urlopen(f'http://localhost:{port}/injected_errors', timeout=5).read())
    injected = data.get('errors', [])
except:
    pass
all_audits['_injected_errors'] = injected
with open(f'{logs}/audit.json', 'w') as f:
    json.dump(all_audits, f, indent=2)
print(f'[harness] Collected audit from {len(all_audits)-1} services ({len(injected)} injected errors)', flush=True)
"

echo "[harness] Grading..." >&2
python3 << 'GRADE_EOF'
import json, yaml, sys, os
sys.path.insert(0, '/opt/clawharness')
from clawharness.evaluate.engine import GradingEngine

config = yaml.safe_load(open(os.environ["TASK_YAML"]))
all_audits = json.load(open(os.environ["LOGS_DIR"] + "/audit.json"))
services = os.environ.get("SERVICES", os.environ["SERVICE_NAME"]).split(",")

tools = config.get("tools", [])
endpoint_to_name = {}
for t in tools:
    ep = t.get("endpoint", "")
    name = t.get("name", "")
    if ep and name:
        endpoint_to_name[ep] = name

def endpoint_to_action(endpoint, svc):
    if endpoint in endpoint_to_name:
        return endpoint_to_name[endpoint]
    parts = endpoint.strip("/").split("/")
    if parts and parts[0] == svc:
        parts = parts[1:]
    if len(parts) == 2:
        return f"{parts[1]}_{parts[0].rstrip('s')}"
    if len(parts) == 1:
        return parts[0]
    return endpoint.split("/")[-1]

SUPPLEMENTAL_ACTION_MAP = {
    "created_events": "create_event",
    "deleted": None,
    "updated_tasks": "update_task",
    "shared": "share_note",
    "sent_messages": "send_message",
    "drafts": "create_draft",
    "updates": "update_article",
    "closed": "close_ticket",
    "updated_tickets": "update_ticket",
    "exported_reports": "export_report",
    "notifications": "send_notification",
}

audit_data = {}
for svc in services:
    audit_data[svc] = []
    raw_audit = all_audits.get(svc, {})
    if isinstance(raw_audit, dict):
        for call in raw_audit.get("calls", []):
            audit_data[svc].append({
                "action": endpoint_to_action(call.get("endpoint",""), svc),
                "params": call.get("params", call.get("body", call.get("request_body", {}))),
                "status": call.get("status", 200),
            })
        for key, items in raw_audit.items():
            if key == "calls": continue
            action = SUPPLEMENTAL_ACTION_MAP.get(key)
            if action is None: continue
            if isinstance(items, list):
                for item in items:
                    audit_data[svc].append({"action": action, "params": item if isinstance(item, dict) else {}, "status": 200})

injected_errors = all_audits.get("_injected_errors", [])
for err in injected_errors:
    ep = err.get("endpoint", "")
    status = err.get("status", 500)
    for svc in services:
        prefix = {"web_real": "web", "web_real_injection": "web"}.get(svc, svc)
        if ep.startswith(f"/{prefix}/"):
            audit_data[svc].append({"action": endpoint_to_action(ep, svc), "params": {}, "status": status})
            break

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
    "agent": "claude-code",
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

echo "$(cat $LOGS_DIR/reward.txt)"

kill $SERVICE_PID 2>/dev/null || true
