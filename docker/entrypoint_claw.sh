#!/bin/bash
# Shared entrypoint for non-OpenClaw agents (IronClaw, PicoClaw, ZeroClaw, CoPaw, Hermes, etc.)
#
# Tier 3 agents use SKILL.md + curl to interact with mock services.
# Agent reads SKILL.md → understands available APIs → uses curl via bash/exec.
#
# Required env vars (set in Dockerfile):
#   AGENT_NAME   — ironclaw, picoclaw, zeroclaw, copaw, hermes, nanoclaw, nemoclaw
#   AGENT_HOME   — agent's home/config dir, e.g. /root/.ironclaw
#   SKILL_DIR    — where to write SKILL.md
#
# Required env vars (set at runtime — pick ONE):
#   ANTHROPIC_API_KEY  — Anthropic models directly (recommended)
#   OPENROUTER_API_KEY — any model via OpenRouter
#   OPENAI_API_KEY     — OpenAI models directly
#   MODEL (optional, default: claude-sonnet-4-6)

set -e

TASK_YAML="${TASK_YAML:-/opt/clawenvkit/task.yaml}"
MOCK_DIR="/opt/clawenvkit/mock_services"
LOGS_DIR="/logs"
PORT="${PORT:-9100}"
MODEL="${MODEL:-claude-sonnet-4-6}"

# Keep original MODEL for Anthropic-direct harnesses (CoPaw, Hermes, Claude Code).
# Create OPENROUTER_MODEL with mapped short IDs for OpenRouter-based harnesses.
OPENROUTER_MODEL="$MODEL"
case "${MODEL##*/}" in
  claude-haiku-4-5-20251001) OPENROUTER_MODEL="${MODEL%/*}/claude-haiku-4.5" ;;
  claude-sonnet-4-20250514)  OPENROUTER_MODEL="${MODEL%/*}/claude-sonnet-4" ;;
  claude-opus-4-20250514)    OPENROUTER_MODEL="${MODEL%/*}/claude-opus-4" ;;
esac
export MODEL OPENROUTER_MODEL

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
    candidates = [src, os.path.join(str(__import__('pathlib').Path(os.environ.get('TASK_YAML','/opt/clawenvkit/task.yaml')).parent), src), f'/opt/clawenvkit/{src}', f'/workspace/{src}']
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
echo "[harness] Services: $SERVICES | Agent: $AGENT_NAME | Port: $PORT | Model: $MODEL" >&2

# --- Extract fixtures (per-service) ---
python3 -c "
import yaml, json
config = yaml.safe_load(open('$TASK_YAML'))
fixtures = config.get('fixtures', {})
if isinstance(fixtures, dict):
    import os as _os
    services = _os.environ.get('SERVICES', '').split(',')
    # Map: resource name → service (with ambiguity handling)
    resource_to_services = {
        'inbox': ['gmail'], 'messages': ['gmail'], 'drafts': ['gmail'],
        'events': ['calendar'], 'tasks': ['todo'], 'contacts': ['contacts'],
        'tickets': ['helpdesk'], 'notes': ['notes'], 'customers': ['crm'],
        'products': ['inventory'], 'transactions': ['finance'],
        'jobs': ['scheduler'], 'feeds': ['rss'],
        'articles': ['rss', 'kb'],  # ambiguous: both use 'articles'
        'integrations': ['config'], 'images': ['ocr'], 'documents': ['documents'],
        'pages': ['web'], 'search_results': ['web'],
        'tracks': ['spotify'], 'playlists': ['spotify'],
    }
    for key, data in fixtures.items():
        if isinstance(data, dict) and len(data) == 1:
            fixture_data = list(data.values())[0]
        elif isinstance(data, (list, dict)):
            fixture_data = data
        else:
            fixture_data = [data]
        with open(f'/tmp/fixtures_{key}.json', 'w') as f:
            json.dump(fixture_data, f)
        candidates = resource_to_services.get(key, [])
        if key in services:
            candidates = [key]
        for svc in candidates:
            if svc in services:
                with open(f'/tmp/fixtures_{svc}.json', 'w') as f:
                    json.dump(fixture_data, f)
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
# Set fixture env vars — use per-service file if available, else fallback
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
        echo "[harness] No server for $SERVICE_NAME (file-dependent task, no mock API needed)" >&2
        SERVICE_PID=""
    fi
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

    md += "```bash\n"
    md += f"curl -s -X {t.get('method', 'POST')} http://localhost:{port}{t['endpoint']} \\\n"
    md += "  -H 'Content-Type: application/json' \\\n"

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

# Also copy to /workspace so agents can find it easily
with open('/workspace/SKILL.md', 'w') as f:
    f.write(md)

print(f'[harness] Generated skill with {len(tools)} tools at {skill_dir}', flush=True)
SKILL_EOF

# --- Generate tool definitions (for MCP-capable agents) ---
echo "[harness] Generating tool definitions..." >&2
python3 << 'TOOLGEN_EOF'
import json, yaml, os, urllib.request

task_yaml = os.environ.get('TASK_YAML', '/opt/clawenvkit/task.yaml')
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

# --- Configure agent ---
echo "[harness] Configuring $AGENT_NAME..." >&2
python3 << 'AGENT_CONFIG_EOF'
import json, os, sys

agent = os.environ.get('AGENT_NAME', '')
home = os.environ.get('AGENT_HOME', '')
model = os.environ.get('MODEL', 'claude-sonnet-4-6')

# Map Anthropic date-stamped model IDs to OpenRouter short IDs
OPENROUTER_MODEL_MAP = {
    'claude-haiku-4-5-20251001': 'claude-haiku-4.5',
    'claude-sonnet-4-6': 'claude-sonnet-4.6',
    'claude-sonnet-4-20250514': 'claude-sonnet-4',
    'claude-opus-4-6': 'claude-opus-4.6',
    'claude-opus-4-20250514': 'claude-opus-4',
}

def to_openrouter_model(m):
    bare = m.split('/')[-1] if '/' in m else m
    mapped = OPENROUTER_MODEL_MAP.get(bare, bare)
    return f'anthropic/{mapped}'

# Detect provider from env vars
# Priority: ANTHROPIC_API_KEY > OPENROUTER_API_KEY > OPENAI_API_KEY
anthropic_key = os.environ.get('ANTHROPIC_API_KEY', '')
openrouter_key = os.environ.get('OPENROUTER_API_KEY', '')
openai_key = os.environ.get('OPENAI_API_KEY', '')

if anthropic_key:
    provider = 'anthropic'
    api_key = anthropic_key
    base_url = ''
    # Strip provider prefix if present (anthropic/claude-sonnet-4-6 → claude-sonnet-4-6)
    anthropic_model = model.split('/')[-1] if '/' in model else model
    print(f'[harness] Using Anthropic direct (model={anthropic_model})', flush=True)
elif openrouter_key:
    provider = 'openrouter'
    api_key = openrouter_key
    base_url = 'https://openrouter.ai/api/v1'
    anthropic_model = model.split('/')[-1] if '/' in model else model
    if '/' not in model:
        model = f'anthropic/{model}'
    print(f'[harness] Using OpenRouter (model={model})', flush=True)
elif openai_key:
    provider = 'openai'
    api_key = openai_key
    base_url = ''
    anthropic_model = model
    print(f'[harness] Using OpenAI (model={model})', flush=True)
else:
    print('[harness] ERROR: No API key set', flush=True)
    sys.exit(1)

use_openrouter = provider == 'openrouter'
os.makedirs(home, exist_ok=True)

# ── IronClaw (Rust) ──
# Config: ~/.ironclaw/.env
# CLI: ironclaw --cli-only --no-db --auto-approve -m "prompt"
if agent == 'ironclaw':
    env_path = os.path.join(home, '.env')
    with open(env_path, 'w') as f:
        if use_openrouter:
            f.write(f'LLM_BACKEND=openai_compatible\n')
            f.write(f'LLM_BASE_URL={base_url}\n')
            f.write(f'LLM_API_KEY={api_key}\n')
            f.write(f'LLM_MODEL={model}\n')
        elif provider == 'anthropic':
            f.write(f'LLM_BACKEND=anthropic\n')
            f.write(f'ANTHROPIC_API_KEY={api_key}\n')
            f.write(f'ANTHROPIC_MODEL={anthropic_model}\n')
        else:
            f.write(f'LLM_BACKEND=openai\n')
            f.write(f'OPENAI_API_KEY={api_key}\n')
            f.write(f'OPENAI_MODEL={anthropic_model}\n')
        f.write('AGENT_USE_PLANNING=false\n')
        f.write('SAFETY_INJECTION_CHECK_ENABLED=false\n')
        f.write('LLM_REQUEST_TIMEOUT_SECS=120\n')
        # MCP server for mock service tools
        mcp_cmd = 'python3'
        mcp_args = ['/opt/clawenvkit/mcp_server/mcp_server.py']
        f.write(f'MCP_SERVERS=[{{"name":"clawenvkit","transport":"stdio","command":"{mcp_cmd}","args":{json.dumps(mcp_args)}}}]\n')
    print(f'[harness] Wrote {env_path} (with MCP)', flush=True)

# ── PicoClaw (Go) ──
# Config: ~/.picoclaw/config.json
# CLI: picoclaw agent -m "prompt"
elif agent == 'picoclaw':
    config_path = os.path.join(home, 'config.json')
    # PicoClaw routes by model prefix: "anthropic/" → Anthropic SDK, "openrouter/" → OpenAI-compat.
    # Use "openrouter/" prefix so it sends OpenAI chat/completions format to OpenRouter.
    or_key = os.environ.get('OPENROUTER_API_KEY', '')
    if or_key:
        or_model = to_openrouter_model(anthropic_model)  # anthropic/claude-haiku-4.5
        model_entry = {
            'model_name': anthropic_model,
            'model': f'openrouter/{or_model}',  # openrouter/anthropic/claude-haiku-4.5
            'api_key': or_key,
            'api_base': 'https://openrouter.ai/api/v1',
        }
    elif use_openrouter:
        model_entry = {
            'model_name': anthropic_model,
            'model': to_openrouter_model(anthropic_model),
            'api_key': api_key,
            'api_base': base_url,
        }
    elif provider == 'anthropic':
        model_entry = {
            'model_name': anthropic_model,
            'model': f'anthropic/{anthropic_model}',
            'api_key': api_key,
        }
    else:
        model_entry = {
            'model_name': anthropic_model,
            'model': f'openai/{anthropic_model}',
            'api_key': api_key,
        }
    config = {
        'agents': {
            'defaults': {
                'model_name': anthropic_model,
                'max_tool_iterations': 20,
            }
        },
        'model_list': [model_entry],
        'tools': {
            'mcp': {
                'enabled': True,
                'servers': {
                    'clawenvkit': {
                        'enabled': True,
                        'command': 'python3',
                        'args': ['/opt/clawenvkit/mcp_server/mcp_server.py'],
                        'env': {'EVAL_TOOLS_FILE': '/tmp/eval-tools.json'},
                    }
                }
            }
        },
    }
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=2)
    print(f'[harness] Wrote {config_path} (with MCP)', flush=True)

# ── ZeroClaw (Rust) ──
# Config: ~/.zeroclaw/config.toml
# CLI: zeroclaw agent -m "prompt"
elif agent == 'zeroclaw':
    config_path = os.path.join(home, 'config.toml')
    # ZeroClaw's Anthropic provider prepends "anthropic/" to model name,
    # causing 404. Force OpenRouter provider (ZeroClaw supports it natively).
    or_key = os.environ.get('OPENROUTER_API_KEY', '')
    or_model = to_openrouter_model(anthropic_model)
    with open(config_path, 'w') as f:
        if or_key:
            f.write(f'default_provider = "openrouter"\n')
            f.write(f'default_model = "{or_model}"\n')
        elif use_openrouter:
            f.write(f'default_provider = "openrouter"\n')
            f.write(f'default_model = "{model}"\n')
        else:
            f.write(f'default_provider = "anthropic"\n')
            f.write(f'default_model = "{anthropic_model}"\n')
        f.write(f'\n[autonomy]\nlevel = "full"\n')
        f.write(f'provider_timeout_secs = 120\n')
        # MCP server for mock service tools
        f.write('\n[mcp]\nenabled = true\n\n[[mcp.servers]]\n')
        f.write('name = "clawenvkit"\ntransport = "stdio"\n')
        f.write('command = "python3"\nargs = ["/opt/clawenvkit/mcp_server/mcp_server.py"]\n')
    print(f'[harness] Wrote {config_path} (with MCP)', flush=True)

# ── CoPaw (Python/AgentScope) ──
# Config handled in case statement (copaw init creates proper structure)
elif agent == 'copaw':
    print('[harness] CoPaw config deferred to case statement', flush=True)

elif agent == '_copaw_skip':
    # Root config
    config_path = os.path.join(home, 'config.json')
    config = {
        'agents': {
            'active_agent': 'default',
            'agent_order': ['default'],
            'profiles': {
                'default': {
                    'id': 'default',
                    'workspace_dir': os.path.join(home, 'workspaces', 'default'),
                    'enabled': True,
                }
            }
        },
        'channels': {'console': {'enabled': True}},
        'mcp': {
            'clients': {
                'clawenvkit': {
                    'name': 'clawenvkit',
                    'enabled': True,
                    'transport': 'stdio',
                    'command': 'python3',
                    'args': ['/opt/clawenvkit/mcp_server/mcp_server.py'],
                    'env': {'EVAL_TOOLS_FILE': '/tmp/eval-tools.json'},
                }
            }
        },
    }
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=2)

    # Agent config
    ws_dir = os.path.join(home, 'workspaces', 'default')
    os.makedirs(ws_dir, exist_ok=True)
    if use_openrouter:
        active_model = {'provider_id': 'openai', 'model': model}
    elif provider == 'anthropic':
        active_model = {'provider_id': 'anthropic', 'model': anthropic_model}
    else:
        active_model = {'provider_id': 'openai', 'model': anthropic_model}
    agent_config = {
        'id': 'default',
        'name': 'EvalAgent',
        'workspace_dir': ws_dir,
        'active_model': active_model,
        'running': {'max_iters': 30, 'llm_retry_enabled': True, 'llm_max_retries': 3},
        'tools': {
            'builtin_tools': {
                'execute_shell_command': {'name': 'execute_shell_command', 'enabled': True},
                'read_file': {'name': 'read_file', 'enabled': True},
                'write_file': {'name': 'write_file', 'enabled': True},
                'edit_file': {'name': 'edit_file', 'enabled': True},
                'grep_search': {'name': 'grep_search', 'enabled': True},
                'glob_search': {'name': 'glob_search', 'enabled': True},
            }
        },
        'security': {'tool_guard': {'enabled': False}, 'file_access': {'enabled': False}},
    }
    with open(os.path.join(ws_dir, 'agent.json'), 'w') as f:
        json.dump(agent_config, f, indent=2)

    # Secrets
    secret_dir = home + '.secret'
    os.makedirs(secret_dir, exist_ok=True)
    envs = {}
    if use_openrouter:
        envs['OPENAI_API_KEY'] = api_key
        envs['OPENAI_BASE_URL'] = base_url
    elif provider == 'anthropic':
        envs['ANTHROPIC_API_KEY'] = api_key
    else:
        envs['OPENAI_API_KEY'] = api_key
    with open(os.path.join(secret_dir, 'envs.json'), 'w') as f:
        json.dump(envs, f, indent=2)
    print(f'[harness] Wrote CoPaw config at {home}', flush=True)

# ── Hermes (Python) ──
# Config: ~/.hermes/config.yaml + ~/.hermes/.env
# CLI: python /opt/hermes/cli.py -q "prompt" --toolsets terminal
elif agent == 'hermes':
    import yaml as _yaml
    config_path = os.path.join(home, 'config.yaml')
    if use_openrouter:
        model_config = {'default': model, 'provider': 'openrouter'}
    elif provider == 'anthropic':
        model_config = {'default': f'anthropic/{anthropic_model}', 'provider': 'anthropic'}
    else:
        model_config = {'default': anthropic_model, 'provider': 'openai'}
    config = {
        'model': model_config,
        'terminal': {'backend': 'local', 'cwd': '/workspace', 'timeout': 120},
    }
    with open(config_path, 'w') as f:
        _yaml.dump(config, f)

    # .env file
    env_path = os.path.join(home, '.env')
    with open(env_path, 'w') as f:
        if use_openrouter:
            f.write(f'OPENROUTER_API_KEY={api_key}\n')
        elif provider == 'anthropic':
            f.write(f'ANTHROPIC_API_KEY={api_key}\n')
        else:
            f.write(f'OPENAI_API_KEY={api_key}\n')
    print(f'[harness] Wrote {config_path} + {env_path}', flush=True)

# ── NanoClaw / NemoClaw ──
elif agent in ('nanoclaw', 'nemoclaw'):
    print(f'[harness] {agent} config: setting env vars only', flush=True)

else:
    print(f'[harness] WARNING: Unknown agent {agent}', flush=True)

AGENT_CONFIG_EOF

# --- Run agent ---
echo "[harness] Running $AGENT_NAME agent..." >&2

# Build full prompt: task prompt + SKILL.md API docs
# Agents need to know about the mock service APIs to use curl
TASK_PROMPT=$(python3 << 'PROMPT_EOF'
import yaml, os
config = yaml.safe_load(open(os.environ.get('TASK_YAML', '/opt/clawenvkit/task.yaml')))
prompt = config.get('prompt', '')

# Append SKILL.md so agents know about the mock service APIs
skill_path = '/workspace/SKILL.md'
if os.path.exists(skill_path):
    skill = open(skill_path).read()
    prompt += "\n\n---\n\n" + skill
    prompt += "\nIMPORTANT: Use the curl commands above to interact with the API. "
    prompt += "Read the SKILL.md file at /workspace/SKILL.md for full API documentation. "
    prompt += "Execute curl commands using your shell/exec tool to call the API endpoints.\n"

print(prompt)
PROMPT_EOF
)

case "$AGENT_NAME" in
  ironclaw)
    # IronClaw: Rust binary. MCP registered via CLI (database-based config).
    cd /workspace
    # Register MCP server — tools become available as native tools
    ironclaw mcp add clawenvkit \
      --transport stdio \
      --command python3 \
      --arg /opt/clawenvkit/mcp_server/mcp_server.py \
      2>&1 || true
    ironclaw --cli-only --auto-approve -m "$TASK_PROMPT" \
      2>&1 | tee /workspace/agent_output.txt || true
    ;;

  picoclaw)
    # PicoClaw: Go binary with agent -m for single message
    # Initialize workspace first (non-interactive)
    cd /workspace
    picoclaw onboard --defaults 2>&1 || true
    picoclaw agent -m "$TASK_PROMPT" -d \
      2>&1 | tee /workspace/agent_output.txt || true
    ;;

  zeroclaw)
    # ZeroClaw: Rust binary with agent -m for single message
    # Override MODEL env var with OpenRouter-mapped version (ZeroClaw reads env over config)
    export MODEL="$OPENROUTER_MODEL"
    cd /workspace
    zeroclaw agent -m "$TASK_PROMPT" \
      2>&1 | tee /workspace/agent_output.txt || true
    ;;

  copaw)
    # CoPaw: Python web server — init, inject provider config, start + chat
    echo "[harness] Initializing CoPaw..." >&2
    export COPAW_WORKING_DIR="$AGENT_HOME"
    export COPAW_SECRET_DIR="${AGENT_HOME}.secret"
    mkdir -p "$AGENT_HOME" "${AGENT_HOME}.secret"

    # Let copaw init create proper config structure
    copaw init --defaults --accept-security 2>&1 || true

    # Inject API key + model into CoPaw's secrets and config
    python3 << 'COPAW_INJECT_EOF'
import json, os, glob

home = os.environ.get('AGENT_HOME', '/root/.copaw')
secret_dir = home + '.secret'
api_key = os.environ.get('ANTHROPIC_API_KEY', '')
model = os.environ.get('MODEL', 'claude-sonnet-4-6')
anthropic_model = model.split('/')[-1] if '/' in model else model

# Inject API key into secrets
os.makedirs(secret_dir, exist_ok=True)
envs_path = os.path.join(secret_dir, 'envs.json')
envs = {}
if os.path.exists(envs_path):
    try: envs = json.load(open(envs_path))
    except: pass
envs['ANTHROPIC_API_KEY'] = api_key
with open(envs_path, 'w') as f:
    json.dump(envs, f, indent=2)

# Update agent.json model setting
for agent_json in glob.glob(f'{home}/workspaces/*/agent.json'):
    try:
        cfg = json.load(open(agent_json))
        cfg['active_model'] = {'provider_id': 'anthropic', 'model': anthropic_model}
        with open(agent_json, 'w') as f:
            json.dump(cfg, f, indent=2)
        print(f'[harness] Updated {agent_json}: model={anthropic_model}', flush=True)
    except Exception as e:
        print(f'[harness] Warning: {e}', flush=True)

# Write Anthropic provider config so CoPaw's ProviderManager finds the key
provider_dir = os.path.join(secret_dir, 'providers', 'builtin')
os.makedirs(provider_dir, exist_ok=True)
provider_cfg = {'id': 'anthropic', 'name': 'Anthropic', 'api_key': api_key}
with open(os.path.join(provider_dir, 'anthropic.json'), 'w') as f:
    json.dump(provider_cfg, f, indent=2)
print(f'[harness] Wrote anthropic provider config', flush=True)
COPAW_INJECT_EOF

    # Ensure API key is in environment for CoPaw's provider
    export ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY}"
    copaw app --host 127.0.0.1 --port 8088 --log-level error &
    COPAW_PID=$!
    for i in $(seq 1 30); do
      curl -s http://localhost:8088/ > /dev/null 2>&1 && break
      sleep 1
    done
    echo "[harness] CoPaw ready" >&2

    # Send task via console/chat API (AgentRequest format, streaming response)
    python3 << 'COPAW_EVAL_EOF'
import json, os, sys, urllib.request, yaml

config = yaml.safe_load(open(os.environ.get('TASK_YAML', '/opt/clawenvkit/task.yaml')))
prompt = config.get('prompt', '')
# Append SKILL.md
skill_path = '/workspace/SKILL.md'
if os.path.exists(skill_path):
    prompt += "\n\n---\n\n" + open(skill_path).read()
    prompt += "\nUse the curl commands above via your shell tool to call the API.\n"

# Send as plain dict (not AgentRequest) so CoPaw uses dict parsing branch
body = {
    "channel": "console",
    "user_id": "eval",
    "session_id": "eval-001",
    "input": [{
        "content": [{"type": "text", "text": prompt}]
    }],
}
output = ""
try:
    req = urllib.request.Request(
        "http://localhost:8088/api/console/chat",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    resp = urllib.request.urlopen(req, timeout=180)
    output = resp.read().decode()
    # Parse streaming SSE if needed
    lines = output.split('\n')
    texts = []
    for line in lines:
        line = line.strip()
        if line.startswith('data:'):
            try:
                d = json.loads(line[5:].strip())
                for msg in d.get('output', [d] if 'content' in d else []):
                    for c in msg.get('content', []):
                        if c.get('type') == 'text' and c.get('text'):
                            texts.append(c['text'])
            except: pass
        elif line.startswith('{'):
            try:
                d = json.loads(line)
                for msg in d.get('output', [d] if 'content' in d else []):
                    for c in msg.get('content', []):
                        if c.get('type') == 'text' and c.get('text'):
                            texts.append(c['text'])
            except: pass
    if texts:
        output = '\n'.join(texts)
    print(output, flush=True)
except Exception as e:
    print(f"[harness] CoPaw API error: {e}", flush=True)
    output = str(e)

with open("/workspace/agent_output.txt", "w") as f:
    f.write(output)
COPAW_EVAL_EOF

    kill $COPAW_PID 2>/dev/null || true
    ;;

  hermes)
    # Hermes: Python CLI with -q for single query, --toolsets terminal for shell access
    export HERMES_HOME="$AGENT_HOME"
    # Bootstrap config files (same as Docker entrypoint)
    mkdir -p "$AGENT_HOME"/{cron,sessions,logs,hooks,memories,skills}
    if [ -f /opt/hermes/cli-config.yaml.example ] && [ ! -f "$AGENT_HOME/config.yaml" ]; then
      cp /opt/hermes/cli-config.yaml.example "$AGENT_HOME/config.yaml"
    fi
    if [ -f /opt/hermes/.env.example ] && [ ! -f "$AGENT_HOME/.env" ]; then
      cp /opt/hermes/.env.example "$AGENT_HOME/.env"
    fi
    cd /opt/hermes
    python3 cli.py -q "$TASK_PROMPT" --toolsets terminal --quiet \
      2>&1 | tee /workspace/agent_output.txt || true
    ;;

  nanoclaw)
    # NanoClaw: has claude CLI (Claude Code) + agent-runner. Use claude CLI with MCP.
    cd /workspace
    # Configure MCP for claude CLI (same as Claude Code entrypoint)
    python3 -c "
import json
config = {'mcpServers': {'clawenvkit': {'command': 'python3', 'args': ['/opt/clawenvkit/mcp_server/mcp_server.py'], 'env': {'EVAL_TOOLS_FILE': '/tmp/eval-tools.json'}}}}
with open('/workspace/.mcp.json', 'w') as f:
    json.dump(config, f, indent=2)
print('[harness] NanoClaw MCP configured', flush=True)
"
    # Map MODEL to Claude CLI model name
    # Claude CLI accepts: haiku, sonnet, opus (short names)
    case "${MODEL##*/}" in
      *haiku*)  CLAUDE_MODEL="haiku" ;;
      *opus*)   CLAUDE_MODEL="opus" ;;
      *sonnet*) CLAUDE_MODEL="sonnet" ;;
      *)        CLAUDE_MODEL="${MODEL##*/}" ;;
    esac
    claude -p "$TASK_PROMPT" \
      --model "$CLAUDE_MODEL" \
      --mcp-config /workspace/.mcp.json \
      --allowedTools "mcp__clawenvkit__*" \
      2>&1 | tee /workspace/agent_output.txt || true
    ;;

  nemoclaw)
    # NemoClaw: has openclaw binary. Use openclaw agent --local with plugin.
    cd /workspace
    # Configure OpenClaw (same approach as entrypoint_openclaw.sh)
    python3 << 'NEMO_CONFIG_EOF'
import json, os

home = '/home/node'
api_key = os.environ.get('ANTHROPIC_API_KEY', os.environ.get('OPENROUTER_API_KEY', ''))
model = os.environ.get('MODEL', 'claude-sonnet-4-6')

# Use openrouter format for OpenClaw
if os.environ.get('OPENROUTER_API_KEY'):
    model_name = f'openrouter/anthropic/{model}' if '/' not in model else f'openrouter/{model}'
    auth_key = os.environ.get('OPENROUTER_API_KEY')
else:
    model_name = f'anthropic/{model}' if '/' not in model else model
    auth_key = api_key

# OpenClaw config
config_dir = f'{home}/.openclaw'
os.makedirs(config_dir, exist_ok=True)
config = {
    'agents': {'defaults': {'model': {'primary': model_name}}},
    'gateway': {'mode': 'local'},
    'tools': {'exec': {'host': 'gateway'}},
    'plugins': {'entries': {'clawenvkit-eval': {'enabled': True}}},
}
with open(f'{config_dir}/config.json', 'w') as f:
    json.dump(config, f, indent=2)

# Auth profile
agent_dir = f'{home}/.openclaw/agents/main/agent'
os.makedirs(agent_dir, exist_ok=True)
auth = {'profiles': {'default': {'key': auth_key}}}
with open(f'{agent_dir}/auth-profiles.json', 'w') as f:
    json.dump(auth, f, indent=2)

print(f'[harness] NemoClaw/OpenClaw config: model={model_name}', flush=True)
NEMO_CONFIG_EOF

    export HOME=/home/node
    openclaw agent --local --session-id eval-001 -m "$TASK_PROMPT" --json --timeout 120 \
      2>&1 | tee /workspace/agent_output.txt || true
    ;;

  *)
    # Generic fallback: try agent -m
    ${AGENT_CMD:-echo "No AGENT_CMD set"} -m "$TASK_PROMPT" \
      2>&1 | tee /workspace/agent_output.txt || true
    ;;
esac

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
errors = len(injected)
print(f'[harness] Collected audit from {len(all_audits)-1} services ({errors} injected errors)', flush=True)
"

echo "[harness] Grading..." >&2
python3 << 'GRADE_EOF'
import json, yaml, sys, os
sys.path.insert(0, '/opt/clawenvkit')
from clawenvkit.evaluate.engine import GradingEngine

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
    "task_id": config.get("task_id", ""),
    "category": config.get("category", ""),
    "services": sorted(set(t.get("service","") for t in config.get("tools",[]) if t.get("service"))),
    "completion": result.completion, "robustness": result.robustness,
    "safety": result.safety, "final_score": result.final_score,
    "components": [{"name":c.name,"passed":c.passed,"score":c.score,"weight":c.weight} for c in result.component_results],
    "safety_violations": result.safety_violations,
    "num_tool_calls": sum(len(v) for v in audit_data.values()),
    "agent": os.environ.get("AGENT_NAME", "unknown"),
    "model": os.environ.get("MODEL", "unknown"),
    "agent_output": agent_output,
}
with open(os.environ["LOGS_DIR"] + "/grading.json", "w") as f:
    json.dump(details, f, indent=2)

print(f"Score: {result.final_score:.2f}")
for c in result.component_results:
    print(f"  {'PASS' if c.passed else 'FAIL'} [{c.weight:.0%}] {c.name}: {c.score:.2f}")
if result.safety_violations:
    print(f"Safety: {result.safety_violations}")
GRADE_EOF

echo "$(cat $LOGS_DIR/reward.txt)"

kill $SERVICE_PID 2>/dev/null || true
