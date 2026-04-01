#!/bin/bash
# Shared entrypoint for non-OpenClaw agents (NanoClaw, IronClaw, CoPaw, etc.)
#
# These agents use Skill Markdown + curl to interact with mock services.
# Agent reads SKILL.md → understands available APIs → uses curl via bash/exec.
#
# Required env vars (set in Dockerfile):
#   AGENT_NAME   — nanoclaw, ironclaw, copaw, picoclaw, zeroclaw, nemoclaw, hermes
#   AGENT_CMD    — CLI command template, e.g. "nanoclaw agent --local --json"
#   SKILL_DIR    — where to write SKILL.md, e.g. /home/user/.nanoclaw/workspace/skills/eval-task
#   AGENT_HOME   — agent's home/config dir, e.g. /home/user/.nanoclaw
#
# Required env vars (set at runtime):
#   ANTHROPIC_API_KEY or OPENAI_API_KEY
#   MODEL (optional, default: claude-sonnet-4-6)

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
    for candidate in [src, f'/opt/clawharness/{src}', f'/opt/clawharness/dataset/{src}']:
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

TASK_NAME=$(python3 -c "import yaml; print(yaml.safe_load(open('$TASK_YAML')).get('task_name',''))")
echo "[harness] Task: $TASK_NAME" >&2
echo "[harness] Services: $SERVICES | Agent: $AGENT_NAME | Port: $PORT | Model: $MODEL" >&2

# --- Extract fixtures (per-service) ---
python3 -c "
import yaml, json
config = yaml.safe_load(open('$TASK_YAML'))
fixtures = config.get('fixtures', {})
if isinstance(fixtures, dict):
    for key, data in fixtures.items():
        path = f'/tmp/fixtures_{key}.json'
        with open(path, 'w') as f:
            json.dump(data if isinstance(data, list) else [data], f)
    if len(fixtures) == 1:
        data = list(fixtures.values())[0]
    else:
        data = fixtures
    with open('/tmp/fixtures.json', 'w') as f:
        json.dump(data if isinstance(data, list) else data, f)
else:
    with open('/tmp/fixtures.json', 'w') as f:
        json.dump(fixtures, f)
"
for svc in $(echo "$SERVICES" | tr ',' ' '); do
    export "${svc^^}_FIXTURES=/tmp/fixtures.json"
done

# --- Start mock service(s) ---
if echo "$SERVICES" | grep -q ","; then
    echo "[harness] Starting multi-service: $SERVICES..." >&2
    SERVICES=$SERVICES PORT=$PORT python3 "$MOCK_DIR/multi_server.py" --services "$SERVICES" &
    SERVICE_PID=$!
    for i in $(seq 1 20); do
        if curl -s "http://localhost:$PORT/$SERVICE_NAME/audit" > /dev/null 2>&1; then
            echo "[harness] $SERVICE_NAME ready" >&2
            break
        fi
        sleep 0.5
    done
fi

# --- Generate SKILL.md with API documentation ---
echo "[harness] Generating skill markdown..." >&2
python3 << 'SKILL_EOF'
import yaml, json, os, urllib.request

task = yaml.safe_load(open(os.environ['TASK_YAML']))
tools = task.get('tools', [])
port = os.environ.get('PORT', '9100')
service = os.environ.get('SERVICE_NAME', '')

if not tools:
    print('[harness] No tools in task.yaml, skipping skill generation', flush=True)
    import sys; sys.exit(0)

# Try to get parameter info from OpenAPI spec
params_info = {}
try:
    openapi = json.loads(urllib.request.urlopen(
        f'http://localhost:{port}/openapi.json', timeout=5).read())

    def resolve_ref(ref, spec):
        parts = ref.lstrip('#/').split('/')
        obj = spec
        for p in parts:
            obj = obj[p]
        return obj

    for t in tools:
        endpoint = t['endpoint']
        method = t.get('method', 'POST').lower()
        path_item = openapi.get('paths', {}).get(endpoint, {})
        operation = path_item.get(method, {})
        if 'requestBody' in operation:
            content = operation['requestBody'].get('content', {})
            schema = content.get('application/json', {}).get('schema', {})
            if '$ref' in schema:
                schema = resolve_ref(schema['$ref'], openapi)
            props = schema.get('properties', {})
            required = schema.get('required', [])
            params_info[t['name']] = (props, required)
except Exception:
    pass  # Fallback: no param details

# Build SKILL.md
md = "# Evaluation Environment\n\n"
md += f"A mock API service is running on `http://localhost:{port}`.\n"
md += "Use `curl` to interact with the API. All endpoints accept POST with JSON body.\n\n"
md += "## Available Tools\n\n"

for t in tools:
    md += f"### {t['name']}\n\n"
    md += f"{t.get('description', '')}\n\n"

    # Show parameters if available
    if t['name'] in params_info:
        props, required = params_info[t['name']]
        if props:
            md += "**Parameters:**\n"
            for key, schema in props.items():
                ptype = schema.get('type', 'string')
                if schema.get('anyOf'):
                    non_null = [s for s in schema['anyOf'] if s.get('type') != 'null']
                    ptype = non_null[0].get('type', 'string') if non_null else 'string'
                req_marker = " **(required)**" if key in required else ""
                default = f", default: `{schema['default']}`" if 'default' in schema and schema['default'] is not None else ""
                md += f"- `{key}` ({ptype}{req_marker}{default})\n"
            md += "\n"

    # Curl example
    md += "```bash\n"
    md += f"curl -s -X {t.get('method', 'POST')} http://localhost:{port}{t['endpoint']} \\\n"
    md += "  -H 'Content-Type: application/json' \\\n"

    # Build example body
    if t['name'] in params_info:
        props, required = params_info[t['name']]
        example = {}
        for key in required:
            example[key] = "..."
        if example:
            md += f"  -d '{json.dumps(example)}'\n"
        else:
            md += "  -d '{}'\n"
    else:
        md += "  -d '{}'\n"

    md += "```\n\n"

# Write to skill directory
skill_dir = os.environ.get('SKILL_DIR', '/tmp/skills/eval-task')
os.makedirs(skill_dir, exist_ok=True)
with open(os.path.join(skill_dir, 'SKILL.md'), 'w') as f:
    f.write(md)

print(f'[harness] Generated skill with {len(tools)} tools at {skill_dir}', flush=True)
SKILL_EOF

# --- Configure agent ---
echo "[harness] Configuring $AGENT_NAME..." >&2
python3 << AGENT_CONFIG_EOF
import json, os, sys

agent = os.environ.get('AGENT_NAME', '')
home = os.environ.get('AGENT_HOME', '')
api_key = os.environ.get('ANTHROPIC_API_KEY', os.environ.get('OPENAI_API_KEY', ''))
model = os.environ.get('MODEL', 'claude-sonnet-4-6')

if not api_key:
    print('[harness] ERROR: No API key set (ANTHROPIC_API_KEY or OPENAI_API_KEY)', flush=True)
    sys.exit(1)

if agent == 'nanoclaw':
    # NanoClaw uses .env file with Anthropic-style config
    env_path = os.path.join(home, '.env')
    os.makedirs(os.path.dirname(env_path), exist_ok=True)
    with open(env_path, 'w') as f:
        f.write(f'ANTHROPIC_API_KEY={api_key}\n')
    print(f'[harness] Wrote {env_path}', flush=True)

elif agent == 'ironclaw':
    # IronClaw uses .env with LLM_BACKEND style
    env_path = os.path.join(home, '.env')
    os.makedirs(os.path.dirname(env_path), exist_ok=True)
    with open(env_path, 'w') as f:
        f.write(f'LLM_BACKEND=anthropic\n')
        f.write(f'LLM_API_KEY={api_key}\n')
        f.write(f'LLM_MODEL={model}\n')
    print(f'[harness] Wrote {env_path}', flush=True)

elif agent == 'copaw':
    # CoPaw uses config.json
    config_path = os.path.join(home, 'config.json')
    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    config = {}
    if os.path.exists(config_path):
        try: config = json.load(open(config_path))
        except: pass
    config.setdefault('models', {}).setdefault('default', {})
    config['models']['default']['provider'] = 'anthropic'
    config['models']['default']['model'] = model
    config['models']['default']['api_key'] = api_key
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=2)
    print(f'[harness] Wrote {config_path}', flush=True)

elif agent == 'picoclaw':
    # PicoClaw uses config.json with model_list
    config_path = os.path.join(home, 'config.json')
    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    config = {}
    if os.path.exists(config_path):
        try: config = json.load(open(config_path))
        except: pass
    config['model_list'] = [{
        'provider': 'anthropic',
        'model': model,
        'api_key': api_key,
    }]
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=2)
    print(f'[harness] Wrote {config_path}', flush=True)

elif agent == 'zeroclaw':
    # ZeroClaw uses config.toml
    config_path = os.path.join(home, 'config.toml')
    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    with open(config_path, 'w') as f:
        f.write('[provider]\n')
        f.write(f'type = "anthropic"\n')
        f.write(f'model = "{model}"\n')
        f.write(f'api_key = "{api_key}"\n')
    print(f'[harness] Wrote {config_path}', flush=True)

elif agent == 'nemoclaw':
    # NemoClaw uses config.json with providers section
    config_path = os.path.join(home, 'config.json')
    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    config = {}
    if os.path.exists(config_path):
        try: config = json.load(open(config_path))
        except: pass
    config.setdefault('providers', {})['default'] = {
        'type': 'anthropic',
        'model': model,
        'api_key': api_key,
    }
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=2)
    print(f'[harness] Wrote {config_path}', flush=True)

elif agent == 'hermes':
    # Hermes uses config.yaml
    config_path = os.path.join(home, 'config.yaml')
    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    import yaml
    config = {}
    if os.path.exists(config_path):
        try: config = yaml.safe_load(open(config_path)) or {}
        except: pass
    config.setdefault('providers', {})['default'] = {
        'type': 'anthropic',
        'model': model,
        'api_key': api_key,
    }
    with open(config_path, 'w') as f:
        yaml.dump(config, f)
    print(f'[harness] Wrote {config_path}', flush=True)

else:
    print(f'[harness] WARNING: Unknown agent {agent}, skipping config', flush=True)
AGENT_CONFIG_EOF

# --- Run agent ---
echo "[harness] Running $AGENT_NAME agent..." >&2

TASK_PROMPT=$(python3 -c "import yaml; print(yaml.safe_load(open('$TASK_YAML')).get('prompt',''))")

$AGENT_CMD \
  --message "$TASK_PROMPT" \
  --timeout 120 \
  2>&1 | tee /workspace/agent_output.txt || true

echo "[harness] $AGENT_NAME finished" >&2

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
        data = json.loads(urllib.request.urlopen(f'http://localhost:{port}/{svc}/audit', timeout=5).read())
        all_audits[svc] = data
    except:
        all_audits[svc] = {'calls': []}
with open(f'{logs}/audit.json', 'w') as f:
    json.dump(all_audits, f, indent=2)
print(f'[harness] Collected audit from {len(all_audits)} services', flush=True)
"

echo "[harness] Grading..." >&2
python3 << 'GRADE_EOF'
import json, yaml, sys, os
sys.path.insert(0, '/opt/clawharness')
from clawharness.evaluate.engine import GradingEngine

config = yaml.safe_load(open(os.environ["TASK_YAML"]))
all_audits = json.load(open(os.environ["LOGS_DIR"] + "/audit.json"))
services = os.environ.get("SERVICES", os.environ["SERVICE_NAME"]).split(",")

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
            if isinstance(items, list):
                for item in items:
                    audit_data[svc].append({"action": key.rstrip("s"), "params": item if isinstance(item, dict) else {}, "status": 200})

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
    "agent": os.environ.get("AGENT_NAME", "unknown"),
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
