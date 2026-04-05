#!/bin/bash
set -e

TASK_YAML="${TASK_YAML:-/opt/clawharness/task.yaml}"
MOCK_DIR="/opt/clawharness/mock_services"
LOGS_DIR="/logs"
PORT="${PORT:-9100}"

mkdir -p "$LOGS_DIR" /workspace

# --- Copy fixture files to workspace (multimodal support) ---
python3 -c "
import yaml, shutil, os
from pathlib import Path

task_yaml = '$TASK_YAML'
task_dir = str(Path(task_yaml).parent)
config = yaml.safe_load(open(task_yaml))
files = config.get('files', [])
copied = 0
for f in files:
    src = f.get('source', '')
    tgt = f.get('target', '')
    if not src or not tgt:
        continue
    # Resolve source: task.yaml parent dir (volume mount), then container paths
    candidates = [
        src,                                    # absolute path
        os.path.join(task_dir, src),            # relative to task.yaml (volume mount)
        f'/opt/clawharness/{src}',              # container root
        f'/workspace/{src}',                    # workspace
    ]
    found = False
    for candidate in candidates:
        if os.path.exists(candidate):
            dst = f'/workspace/{tgt}'
            os.makedirs(os.path.dirname(dst) or '/workspace', exist_ok=True)
            shutil.copy2(candidate, dst)
            print(f'[harness] Copied {candidate} → {dst}', flush=True)
            copied += 1
            found = True
            break
    if not found:
        print(f'[harness] WARNING: file not found: {src} (tried {len(candidates)} paths)', flush=True)
if files:
    print(f'[harness] {copied}/{len(files)} fixture files copied to /workspace/', flush=True)
" 2>/dev/null || true

# --- Detect services needed ---
# Extract service list from task.yaml tools field, or fall back to task_id prefix
SERVICES=$(python3 -c "
import yaml
config = yaml.safe_load(open('$TASK_YAML'))
tools = config.get('tools', [])
services = sorted(set(t.get('service','') for t in tools if t.get('service')))
if not services:
    services = [config.get('task_id','').split('-')[0]]
print(','.join(services))
")
SERVICE_NAME="${SERVICES%%,*}"  # primary service (first one)
export SERVICE_NAME SERVICES TASK_YAML LOGS_DIR PORT
# Route prefix for health check (web_real/web_real_injection use /web/ routes)
case "$SERVICE_NAME" in web_real|web_real_injection) HEALTH_PREFIX="web" ;; *) HEALTH_PREFIX="$SERVICE_NAME" ;; esac

TASK_NAME=$(python3 -c "import yaml; print(yaml.safe_load(open('$TASK_YAML')).get('task_name',''))")
echo "[harness] Task: $TASK_NAME" >&2
echo "[harness] Services: $SERVICES | Agent: OpenClaw | Port: $PORT" >&2

# --- Extract fixtures (per-service) ---
# For cross-service tasks, fixtures are keyed by service name or resource type.
# Each mock service expects its OWN fixture file with a list of records.
python3 << 'FIXTURE_EOF'
import yaml, json, os

config = yaml.safe_load(open(os.environ.get("TASK_YAML", "/opt/clawharness/task.yaml")))
fixtures = config.get("fixtures", {})
services = os.environ.get("SERVICES", "").split(",")

if not isinstance(fixtures, dict):
    # Not a dict — write as-is for single service
    with open("/tmp/fixtures.json", "w") as f:
        json.dump(fixtures, f)
    for svc in services:
        os.environ[f"{svc.upper()}_FIXTURES"] = "/tmp/fixtures.json"
        print(f"fixture:{svc}:/tmp/fixtures.json", flush=True)
else:
    # Dict — could be keyed by service name or resource type
    # Strategy: try to match fixture keys to service names
    # e.g., fixtures: {finance: {transactions: [...]}, crm: {customers: [...]}}
    # or:   fixtures: {transactions: [...], customers: [...]}

    for svc in services:
        svc_data = None

        # Case 1: fixtures keyed by service name directly
        if svc in fixtures:
            svc_data = fixtures[svc]
        else:
            # Case 2: fixtures keyed by resource type — find the one for this service
            # Map known resource types to services
            resource_to_service = {
                "inbox": "gmail", "messages": "gmail", "drafts": "gmail",
                "events": "calendar",
                "tasks": "todo",
                "contacts": "contacts",
                "tickets": "helpdesk",
                "notes": "notes",
                "customers": "crm",
                "products": "inventory",
                "transactions": "finance",
                "jobs": "scheduler",
                "feeds": "rss", "articles": "rss",
                "integrations": "config",
                "images": "ocr",
                "documents": "documents",
                "pages": "web", "search_results": "web",
                "tracks": "spotify", "playlists": "spotify",
            }
            for key, data in fixtures.items():
                mapped_svc = resource_to_service.get(key, "")
                if mapped_svc == svc:
                    svc_data = data
                    break
                # Handle ambiguous: 'articles' used by both kb and rss
                if key == "articles" and svc == "kb":
                    svc_data = data
                    break

        if svc_data is not None:
            # Write fixture for this service
            if isinstance(svc_data, dict):
                if len(svc_data) == 1:
                    # Single-key dict (e.g., {transactions: [...]}) → unwrap to list
                    svc_data = list(svc_data.values())[0]
                else:
                    # Multi-key dict (e.g., web: {search_results: [...], pages: [...]})
                    # Write as-is — the service uses load_fixtures(raw=True) to handle it
                    pass
            path = f"/tmp/fixtures_{svc}.json"
            with open(path, "w") as f:
                json.dump(svc_data if isinstance(svc_data, (list, dict)) else [svc_data], f)
            size = len(svc_data) if isinstance(svc_data, list) else len(svc_data) if isinstance(svc_data, dict) else 1
            print(f"[harness] Fixture {svc} → {path} ({size} records/keys)", flush=True)
        else:
            # No matching fixtures — write empty list
            path = f"/tmp/fixtures_{svc}.json"
            with open(path, "w") as f:
                json.dump([], f)
            print(f"[harness] Fixture {svc} → {path} (empty)", flush=True)

    # Also write combined for single-service backward compat
    if len(fixtures) == 1:
        data = list(fixtures.values())[0]
        if isinstance(data, dict) and len(data) == 1:
            data = list(data.values())[0]
    else:
        data = fixtures
    with open("/tmp/fixtures.json", "w") as f:
        json.dump(data if isinstance(data, list) else data, f)
FIXTURE_EOF

# Set fixture env vars for each service
for svc in $(echo "$SERVICES" | tr ',' ' '); do
    if [ -f "/tmp/fixtures_${svc}.json" ]; then
        export "${svc^^}_FIXTURES=/tmp/fixtures_${svc}.json"
    else
        export "${svc^^}_FIXTURES=/tmp/fixtures.json"
    fi
done

# --- Start mock service(s) ---
if echo "$SERVICES" | grep -q ","; then
    # Multi-service: use multi_server.py
    echo "[harness] Starting multi-service: $SERVICES..." >&2
    SERVICES=$SERVICES PORT=$PORT python3 "$MOCK_DIR/multi_server.py" --services "$SERVICES" &
    SERVICE_PID=$!
    # Wait for first service to be ready
    for i in $(seq 1 20); do
        if curl -s "http://localhost:$PORT/$HEALTH_PREFIX/audit" > /dev/null 2>&1; then
            echo "[harness] Services ready" >&2
            break
        fi
        sleep 0.5
    done
else
    # Single service
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
    fi
fi

# --- Generate tool definitions for the eval plugin ---
# Reads task.yaml tools + mock service OpenAPI spec → /tmp/eval-tools.json
# The clawharness-eval plugin reads this file to register native tools.
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

# Fetch OpenAPI spec from the running mock service (with retry)
import time as _time
openapi = None
openapi_url = f'http://localhost:{port}/openapi.json'
for _attempt in range(5):
    try:
        openapi = json.loads(urllib.request.urlopen(openapi_url, timeout=5).read())
        break
    except Exception as e:
        if _attempt < 4:
            _time.sleep(1)
        else:
            print(f'[harness] WARNING: Could not fetch OpenAPI spec after 5 attempts: {e}', flush=True)

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

    # Extract typed parameters from OpenAPI spec if available
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

            # Resolve nested $refs in properties
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

# --- Configure OpenClaw ---
echo "[harness] Configuring OpenClaw..." >&2

export OPENCLAW_WORKSPACE="/home/node/.openclaw/workspace"

# Setup workspace (creates initial config)
openclaw setup --non-interactive 2>/dev/null || true

# Overwrite config with ONLY valid keys — start fresh to avoid unrecognized key errors
python3 -c "
import json, os

openclaw_dir = '/home/node/.openclaw'
agent_dir = f'{openclaw_dir}/agents/main/agent'
config_path = f'{openclaw_dir}/openclaw.json'
auth_path = f'{agent_dir}/auth-profiles.json'
os.makedirs(openclaw_dir, exist_ok=True)
os.makedirs(agent_dir, exist_ok=True)

openrouter_key = os.environ.get('OPENROUTER_API_KEY', '')
anthropic_key = os.environ.get('ANTHROPIC_API_KEY', '')
model_name = os.environ.get('MODEL', 'claude-opus-4-6')

# --- Auth profiles (API keys) ---
auth_profiles = {}
if openrouter_key:
    auth_profiles['openrouter:manual'] = {
        'providerId': 'openrouter',
        'token': openrouter_key,
        'profileId': 'openrouter:manual',
    }
    # Model format for OpenRouter: openrouter/provider/model
    if '/' not in model_name:
        model_name = f'anthropic/{model_name}'
    if not model_name.startswith('openrouter/'):
        model_name = f'openrouter/{model_name}'
    print(f'[harness] OpenClaw using OpenRouter ({model_name})', flush=True)
elif anthropic_key:
    auth_profiles['anthropic:manual'] = {
        'providerId': 'anthropic',
        'token': anthropic_key,
        'profileId': 'anthropic:manual',
    }
    print(f'[harness] OpenClaw using Anthropic ({model_name})', flush=True)

with open(auth_path, 'w') as f:
    json.dump(auth_profiles, f, indent=2)

# --- Config (agents.defaults.model.primary format) ---
config = {
    'agents': {
        'defaults': {
            'model': {
                'primary': model_name,
            },
        },
    },
    'gateway': {
        'mode': 'local',
    },
    'tools': {
        'exec': {'host': 'gateway'},
    },
    'plugins': {
        'entries': {
            'clawharness-eval': {'enabled': True},
        },
    },
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

# --- Run OpenClaw agent ---
echo "[harness] Running OpenClaw agent..." >&2

TASK_PROMPT=$(python3 -c "import yaml; print(yaml.safe_load(open('$TASK_YAML')).get('prompt',''))")

# Use --local for embedded mode (no gateway pairing needed)
# Agent sees native tools (create_task, list_tasks, etc.) via clawharness-eval plugin
openclaw agent \
  --local \
  --session-id "eval-$$" \
  --message "$TASK_PROMPT" \
  --json \
  --timeout 120 \
  2>&1 | tee /workspace/agent_output.txt || true

echo "[harness] OpenClaw finished" >&2

# Fix /logs permissions for grading output (volume mount uid mismatch)
sudo chmod 777 "$LOGS_DIR" 2>/dev/null || chmod 777 "$LOGS_DIR" 2>/dev/null || true

# --- Grade ---
echo "[harness] Collecting audit..." >&2
# Collect audit from ALL services
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

# Collect injected errors (for robustness scoring)
injected = []
try:
    data = json.loads(urllib.request.urlopen(f'http://localhost:{port}/injected_errors', timeout=5).read())
    injected = data.get('errors', [])
except:
    pass
all_audits['_injected_errors'] = injected

with open(f'{logs}/audit.json', 'w') as f:
    json.dump(all_audits, f, indent=2)
errors = len(injected)
print(f'[harness] Collected audit from {len(all_audits)-1} services ({errors} injected errors)', flush=True)
"

echo "[harness] Grading..." >&2
python3 << 'GRADE_EOF'
import json, yaml, sys, os
sys.path.insert(0, '/opt/clawharness')
from clawharness.evaluate.engine import GradingEngine

config = yaml.safe_load(open(os.environ["TASK_YAML"]))
all_audits = json.load(open(os.environ["LOGS_DIR"] + "/audit.json"))
services = os.environ.get("SERVICES", os.environ["SERVICE_NAME"]).split(",")

# Build endpoint → tool_name mapping from task.yaml (authoritative source)
tools = config.get("tools", [])
endpoint_to_name = {}
for t in tools:
    ep = t.get("endpoint", "")
    name = t.get("name", "")
    if ep and name:
        endpoint_to_name[ep] = name

def endpoint_to_action(endpoint, svc):
    # First: use task.yaml mapping (authoritative)
    if endpoint in endpoint_to_name:
        return endpoint_to_name[endpoint]
    # Fallback: parse endpoint path
    parts = endpoint.strip("/").split("/")
    if parts and parts[0] == svc:
        parts = parts[1:]
    if len(parts) == 2:
        return f"{parts[1]}_{parts[0].rstrip('s')}"
    if len(parts) == 1:
        return parts[0]
    return endpoint.split("/")[-1]

# Build audit_data for all services
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

# Add injected errors to audit_data (for robustness scoring)
# These are 429/500 responses that the middleware returned before _log_call
injected_errors = all_audits.get("_injected_errors", [])
for err in injected_errors:
    ep = err.get("endpoint", "")
    status = err.get("status", 500)
    # Find which service this endpoint belongs to
    for svc in services:
        prefix = {"web_real": "web", "web_real_injection": "web"}.get(svc, svc)
        if ep.startswith(f"/{prefix}/"):
            audit_data[svc].append({
                "action": endpoint_to_action(ep, svc),
                "params": {},
                "status": status,
            })
            break

agent_output = open("/workspace/agent_output.txt").read() if os.path.exists("/workspace/agent_output.txt") else ""

engine = GradingEngine()
result = engine.grade(config, audit_data, agent_output)

with open(os.environ["LOGS_DIR"] + "/reward.txt", "w") as f:
    f.write(f"{result.final_score:.4f}\n")

details = {
    "task_id": config.get("task_id", ""),
    "category": config.get("category", ""),
    "services": sorted(set(t.get("service","") for t in config.get("tools",[]) if t.get("service"))),
    "completion": result.completion,
    "robustness": result.robustness,
    "safety": result.safety,
    "final_score": result.final_score,
    "components": [{"name":c.name,"passed":c.passed,"score":c.score,"weight":c.weight} for c in result.component_results],
    "safety_violations": result.safety_violations,
    "num_tool_calls": sum(len(v) for v in audit_data.values()),
    "agent": "openclaw",
    "model": os.environ.get("MODEL", os.environ.get("OPENCLAW_MODEL", "unknown")),
}
with open(os.environ["LOGS_DIR"] + "/grading.json", "w") as f:
    json.dump(details, f, indent=2)

# Save agent response for analysis
import shutil
if os.path.exists("/workspace/agent_output.txt"):
    shutil.copy("/workspace/agent_output.txt", os.environ["LOGS_DIR"] + "/agent_output.txt")

print(f"Score: {result.final_score:.2f}")
for c in result.component_results:
    print(f"  {'✅' if c.passed else '❌'} [{c.weight:.0%}] {c.name}: {c.score:.2f}")
if result.safety_violations:
    print(f"🚨 Safety: {result.safety_violations}")
GRADE_EOF

echo "$(cat $LOGS_DIR/reward.txt)"

kill $SERVICE_PID $GATEWAY_PID 2>/dev/null
