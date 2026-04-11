# Agent Framework Integration Details

This document describes exactly how each agent framework connects to
ClawEnvKit's mock service endpoints, including configuration format,
tool registration mechanism, and known limitations.

All Docker-based agents share `docker/entrypoint_claw.sh` which handles:
1. Starting mock services on port 9100
2. Generating SKILL.md (API docs with curl examples)
3. Generating eval-tools.json (typed tool definitions from OpenAPI spec)
4. Configuring the agent (API key, model, MCP/tools)
5. Running the agent with the task prompt
6. Collecting audit logs and grading

---

## Tier 2: MCP-Based Agents

These agents connect to a Python MCP server (`mcp_server/mcp_server.py`)
over stdio. The server reads `eval-tools.json` and exposes each mock endpoint
as an MCP tool. Protocol: JSON-RPC 2.0 with NDJSON framing (auto-detects
Content-Length framing for Claude Code's Node.js SDK).

### Claude Code (MCP via Node.js)

**Binary:** `claude` (Claude Code CLI)

**Config:** `/workspace/.mcp.json`
```json
{
  "mcpServers": {
    "clawenvkit": {
      "command": "node",
      "args": ["/opt/clawenvkit/mcp_server/index.js"],
      "env": {
        "EVAL_TOOLS_FILE": "/tmp/eval-tools.json"
      }
    }
  }
}
```

**Invocation:**
```bash
claude -p "$TASK_PROMPT" \
  --model "sonnet" \
  --mcp-config /workspace/.mcp.json \
  --allowedTools "mcp__clawenvkit__*"
```

**Notes:**
- Uses Node.js MCP server (`mcp_server/index.js`) with `@modelcontextprotocol/sdk`
- Requires `ANTHROPIC_API_KEY` (does not support OpenRouter)
- `--allowedTools "mcp__clawenvkit__*"` pre-approves all eval tools
- Has its own entrypoint: `docker/entrypoint_claudecode.sh`

**Verified score:** 0.86 (todo-007, Sonnet 4.6)

---

### NanoClaw (MCP via Claude CLI)

**Binary:** `claude` (bundled in NanoClaw Docker image)

NanoClaw is a host orchestrator that spawns Docker containers with Claude
Agent SDK. Its Docker image includes the `claude` CLI binary, which we use
directly with the Python MCP server.

**Config:** `/workspace/.mcp.json` (same format as Claude Code)

**Invocation:**
```bash
claude -p "$TASK_PROMPT" \
  --model "sonnet" \
  --mcp-config /workspace/.mcp.json \
  --allowedTools "mcp__clawenvkit__*"
```

**Notes:**
- NanoClaw image bundles `claude` CLI + Node.js 22 + agent-runner
- Same MCP config as Claude Code but uses Python MCP server
- NanoClaw's native architecture (host → container → Claude SDK) is not used;
  we invoke the bundled `claude` CLI directly

**Verified score:** 0.88 (todo-007, Haiku 4.5)

---

### IronClaw (MCP via CLI registration)

**Binary:** `ironclaw` (single Rust binary)

IronClaw uses database-based MCP configuration. The MCP server is registered
via the `ironclaw mcp add` CLI command before running the agent.

**Config:** `~/.ironclaw/.env`
```
LLM_BACKEND=anthropic
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-sonnet-4-6
AGENT_USE_PLANNING=false
SAFETY_INJECTION_CHECK_ENABLED=false
LLM_REQUEST_TIMEOUT_SECS=120
```

**Invocation:**
```bash
# Register MCP server (stored in embedded libSQL database)
ironclaw mcp add clawenvkit \
  --transport stdio \
  --command python3 \
  --arg /opt/clawenvkit/mcp_server/mcp_server.py

# Run agent
ironclaw --cli-only --auto-approve -m "$TASK_PROMPT"
```

**Tool names seen by agent:** `clawenvkit_list_tasks`, `clawenvkit_create_task`, etc.

**Notes:**
- `--cli-only`: disable messaging channels
- `--auto-approve`: skip interactive tool approval prompts
- MCP via `.env` `MCP_SERVERS=[...]` does NOT work (IronClaw uses database)
- IronClaw's built-in HTTP tool blocks `http://localhost` (SSRF protection)
- MCP tools bypass SSRF since they use stdio IPC, not HTTP
- Agent loop can be slow (50 iteration limit)

**Verified:** MCP tool calls confirmed (`clawenvkit_list_tasks` called successfully)

---

### PicoClaw (MCP via config.json)

**Binary:** `picoclaw` (single Go binary, Alpine-based)

**Config:** `~/.picoclaw/config.json`
```json
{
  "agents": {
    "defaults": {
      "model_name": "claude-sonnet-4-6",
      "max_tool_iterations": 20
    }
  },
  "model_list": [
    {
      "model_name": "claude-sonnet-4-6",
      "model": "anthropic/claude-sonnet-4-6",
      "api_key": "sk-ant-..."
    }
  ],
  "tools": {
    "mcp": {
      "enabled": true,
      "servers": {
        "clawenvkit": {
          "enabled": true,
          "command": "python3",
          "args": ["/opt/clawenvkit/mcp_server/mcp_server.py"],
          "env": {"EVAL_TOOLS_FILE": "/tmp/eval-tools.json"}
        }
      }
    }
  }
}
```

**Tool names seen by agent:** `mcp_clawenvkit_list_tasks`, `mcp_clawenvkit_create_task`, etc.

**Invocation:**
```bash
picoclaw agent -m "$TASK_PROMPT" -d
```

**Notes:**
- Alpine image needs `bash` installed (entrypoint uses `#!/bin/bash`)
- 3 built-in tools always present: `write_file`, `reaction`, `load_image`
- MCP tools registered at startup alongside built-in tools (total 7 tools)
- `-d` flag enables debug logging

**Verified score:** 0.52 (todo-007, Sonnet 4.6)

---

### ZeroClaw (MCP via config.toml)

**Binary:** `zeroclaw` (single Rust binary, copied into python:3.12-slim)

**Config:** `~/.zeroclaw/config.toml`
```toml
api_key = "sk-ant-..."
default_provider = "anthropic"
default_model = "claude-sonnet-4-6"

[autonomy]
level = "full"
provider_timeout_secs = 120

[mcp]
enabled = true

[[mcp.servers]]
name = "clawenvkit"
transport = "stdio"
command = "python3"
args = ["/opt/clawenvkit/mcp_server/mcp_server.py"]
```

**Invocation:**
```bash
zeroclaw agent -m "$TASK_PROMPT"
```

**Notes:**
- `autonomy.level = "full"` required to skip interactive tool approval
- ZeroClaw expects NDJSON framing (not Content-Length) for MCP stdio
- Has 95+ built-in tools; MCP tools are additional
- SSRF protection blocks `http://localhost` from built-in HTTP/web_fetch tools
  (MCP bypasses this since it uses stdio IPC)

**Verified score:** 0.78 (todo-007, Sonnet 4.6)

---

## Tier 3: SKILL.md + Shell

These agents receive the SKILL.md API documentation appended to the task
prompt, then use their built-in shell/exec tools to run curl commands against
the mock service at localhost:9100.

### Hermes (Python CLI)

**Binary:** `hermes` / `python cli.py` (Python CLI with google/python-fire)

**Config:** `~/.hermes/config.yaml`
```yaml
model:
  default: anthropic/claude-sonnet-4-6
  provider: anthropic
terminal:
  backend: local
  cwd: /workspace
  timeout: 120
```

**Env:** `~/.hermes/.env`
```
ANTHROPIC_API_KEY=sk-ant-...
```

**Invocation:**
```bash
HERMES_HOME=~/.hermes python3 /opt/hermes/cli.py \
  -q "$TASK_PROMPT" --toolsets terminal --quiet
```

**How it works:**
1. SKILL.md content is appended to the task prompt
2. Hermes receives the prompt with API documentation embedded
3. Agent uses `terminal` toolset (shell commands) to execute curl
4. Curl calls hit mock service at localhost:9100
5. Agent processes API responses and generates output

**Notes:**
- `--toolsets terminal` enables shell command execution
- `--quiet` reduces terminal UI output noise
- Base image is Debian with Node.js 20, Python 3, ripgrep, ffmpeg
- `HERMES_HOME` env var sets config/data directory

**Verified score:** 0.68 (todo-007, Sonnet 4.6)

---

### CoPaw (Python web server + REST API)

**Binary:** `copaw` (Python CLI, FastAPI web server)

CoPaw has no CLI agent mode. It runs as a web server (`copaw app`) and
accepts chat messages via REST API at `POST /api/console/chat`.

**Config:** Created by `copaw init --defaults --accept-security`, then:
- `~/.copaw.secret/providers/builtin/anthropic.json` — API key injection
- `~/.copaw/workspaces/*/agent.json` — Model selection

**Provider config:** `~/.copaw.secret/providers/builtin/anthropic.json`
```json
{
  "id": "anthropic",
  "name": "Anthropic",
  "api_key": "sk-ant-..."
}
```

**Invocation:**
```bash
# Initialize
copaw init --defaults --accept-security

# Inject API key + model
# (writes provider config + updates agent.json active_model)

# Start server
copaw app --host 127.0.0.1 --port 8088 --log-level error &

# Send task via REST API (AgentRequest format)
curl -X POST http://localhost:8088/api/console/chat \
  -H "Content-Type: application/json" \
  -d '{
    "channel": "console",
    "user_id": "eval",
    "session_id": "eval-001",
    "input": [{"content": [{"type": "text", "text": "TASK_PROMPT"}]}]
  }'
```

**How it works:**
1. CoPaw app starts with Anthropic provider configured
2. Task prompt (with SKILL.md appended) sent via REST API
3. CoPaw's ReAct agent processes the prompt using AgentScope
4. Agent uses `execute_shell_command` built-in tool to run curl
5. Streaming SSE response parsed for agent output

**Notes:**
- `copaw init` must run BEFORE our config injection (creates workspace structure)
- Provider config requires `id` and `name` fields (Pydantic validation)
- REST API uses `channel: "console"` to route to console channel
- Response is Server-Sent Events (SSE) stream, parsed for text content

**Verified score:** 0.76 (todo-007, Haiku 4.5)

---

### NemoClaw (OpenClaw agent --local)

**Binary:** `openclaw` (bundled in NemoClaw Docker image)

NemoClaw is an OpenClaw plugin + NVIDIA OpenShell sandbox orchestrator.
Its Docker image includes the `openclaw` binary, which we use in local
agent mode.

**Config:** `~/.openclaw/config.json` (OpenClaw format)
```json
{
  "agents": {"defaults": {"model": {"primary": "anthropic/claude-sonnet-4-6"}}},
  "gateway": {"mode": "local"},
  "tools": {"exec": {"host": "gateway"}}
}
```

**Auth:** `~/.openclaw/agents/main/agent/auth-profiles.json`
```json
{
  "profiles": {"default": {"key": "sk-ant-..."}}
}
```

**Invocation:**
```bash
openclaw agent --local --session-id eval-001 -m "$TASK_PROMPT" --json --timeout 120
```

**How it works:**
1. OpenClaw starts in local mode (embedded gateway, no external WebSocket)
2. Task prompt (with SKILL.md appended) sent via `--message` flag
3. OpenClaw agent processes prompt using its native agent loop
4. Agent uses shell/exec tools to run curl commands
5. JSON output captured for grading

**Notes:**
- `--local` runs embedded agent without gateway server
- `--session-id eval-001` required (OpenClaw needs session routing)
- `--json` outputs structured JSON response
- OpenClaw config uses `agents.defaults.model.primary` (v2026.3.x format)
- Auth profile with API key stored in agent-specific directory

**Verified score:** 0.80 (todo-007, Haiku 4.5)

---

## Adding a New Agent

To add a new agent framework:

### Option A: MCP (Recommended)

If the agent supports MCP stdio servers:

1. Create `docker/Dockerfile.youragent`:
```dockerfile
FROM youragent:latest
USER root
RUN apt-get update && apt-get install -y python3 python3-pip curl && \
    pip3 install --break-system-packages fastapi uvicorn pyyaml httpx requests
COPY clawenvkit/ /opt/clawenvkit/clawenvkit/
COPY mock_services/ /opt/clawenvkit/mock_services/
COPY mcp_server/mcp_server.py /opt/clawenvkit/mcp_server/mcp_server.py
COPY docker/entrypoint_claw.sh /opt/clawenvkit/entrypoint.sh
RUN chmod +x /opt/clawenvkit/entrypoint.sh && mkdir -p /workspace /logs
ENV AGENT_NAME=youragent
ENV SKILL_DIR=/root/.youragent/skills/eval-task
ENV AGENT_HOME=/root/.youragent
ENV PYTHONPATH=/opt/clawenvkit
WORKDIR /workspace
ENTRYPOINT ["/opt/clawenvkit/entrypoint.sh"]
```

2. Add agent config in `entrypoint_claw.sh` (AGENT_CONFIG_EOF section):
```python
elif agent == 'youragent':
    config = {
        'mcp': {
            'servers': [{
                'name': 'clawenvkit',
                'command': 'python3',
                'args': ['/opt/clawenvkit/mcp_server/mcp_server.py'],
            }]
        },
        'model': anthropic_model,
        'api_key': api_key,
    }
    # Write to agent's config file
```

3. Add agent invocation in `entrypoint_claw.sh` (case statement):
```bash
youragent)
    cd /workspace
    youragent agent -m "$TASK_PROMPT" \
      2>&1 | tee /workspace/agent_output.txt || true
    ;;
```

4. Register in `scripts/evaluate.py`:
```python
AGENT_IMAGES["youragent"] = "clawenvkit:youragent"
```

### Option B: SKILL.md + Shell

If the agent has a shell/exec tool but no MCP:

1. Same Dockerfile setup
2. Config just needs API key + model
3. SKILL.md is auto-generated and appended to the task prompt
4. Agent uses shell to run curl commands

### Option C: simple_agent Fallback

If the agent can't be configured for tool calls in eval mode:

1. Same Dockerfile (simple_agent.py is included via clawenvkit/)
2. Add to case statement:
```bash
youragent)
    python3 /opt/clawenvkit/clawenvkit/simple_agent.py \
      2>&1 | tee /workspace/agent_output.txt || true
    ;;
```

---

## MCP Server Details

### Python MCP Server (`mcp_server/mcp_server.py`)

Minimal JSON-RPC 2.0 server, zero external dependencies:

- **Input:** Reads `eval-tools.json` (generated from OpenAPI spec)
- **Protocol:** NDJSON by default, auto-switches to Content-Length if client uses it
- **Methods:** `initialize`, `tools/list`, `tools/call`, `ping`
- **Tool execution:** `tools/call` -> HTTP POST to `localhost:9100/{endpoint}`

### Node.js MCP Server (`mcp_server/index.js`)

Full `@modelcontextprotocol/sdk` implementation with Zod schemas:

- **Used by:** Claude Code (requires Content-Length framing)
- **Dependencies:** `@modelcontextprotocol/sdk`, `zod`
- **Type mapping:** OpenAPI property types -> Zod schemas (string, number, boolean, array)

Both servers read the same `eval-tools.json` and produce identical tool behavior.
