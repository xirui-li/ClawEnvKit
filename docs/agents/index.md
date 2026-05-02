# Supported Harnesses

ClawEnvKit supports 10 evaluation harnesses across three integration tiers.
All harnesses use their **native agent loop** — no fallback agents.

## Harness Comparison

| Harness | Tier | Tool Mechanism | Native Agent | Language | Verified |
|---------|------|---------------|-------------|----------|----------|
| **OpenClaw** | 1 - Native Plugin | TypeScript `registerTool()` | OpenClaw gateway | TypeScript | 0.82 |
| **Claude Code** | 2 - MCP | Node.js MCP server (stdio) | `claude` CLI | Node.js | 0.86 |
| **NanoClaw** | 2 - MCP | Python MCP server (stdio) | `claude` CLI (bundled) | Node.js | 0.88 |
| **IronClaw** | 2 - MCP | Python MCP server (via `ironclaw mcp add`) | `ironclaw` CLI | Rust | MCP verified |
| **PicoClaw** | 2 - MCP | Python MCP server (stdio) | `picoclaw agent` | Go | 0.52 |
| **ZeroClaw** | 2 - MCP | Python MCP server (stdio) | `zeroclaw agent` | Rust | 0.78 |
| **CoPaw** | 3 - SKILL.md + shell | curl via `execute_shell_command` | `copaw app` + REST API | Python | 0.76 |
| **NemoClaw** | 3 - SKILL.md + shell | curl via OpenClaw shell | `openclaw agent --local` | TypeScript | 0.80 |
| **Hermes** | 3 - SKILL.md + shell | curl via `terminal` toolset | `python cli.py -q` | Python | 0.68 |
| **Agent Loop** | 3 - Direct function calling | OpenAI-format tool calls (no Docker) | Python agent loop | Python | ~0.55 |

## Integration Tiers

### Tier 1 - Native Plugin
The harness provides a plugin/extension API to register custom tools.
Mock service endpoints are registered as native tools via `registerTool()`.
The agent calls `create_task(title, priority)` exactly like `sendSlackMessage`.

**Harnesses:** OpenClaw

### Tier 2 - MCP (Model Context Protocol)
A lightweight MCP server exposes mock service endpoints as tools over stdio.
The agent's MCP client connects at startup, discovers tools via `tools/list`,
and calls them via `tools/call`. Two MCP server implementations:

- **Node.js** (`mcp_server/index.js`): Full `@modelcontextprotocol/sdk` with Zod schemas.
  Used by Claude Code (requires Content-Length framing).
- **Python** (`mcp_server/mcp_server.py`): Zero-dependency JSON-RPC 2.0, NDJSON framing
  (auto-detects Content-Length). Used by NanoClaw, IronClaw, PicoClaw, ZeroClaw.

**Harnesses:** Claude Code, NanoClaw, IronClaw, PicoClaw, ZeroClaw

### Tier 3 - SKILL.md + Shell / Direct Function Calling
The entrypoint generates a `SKILL.md` file documenting all mock API endpoints
with curl examples. This is appended to the task prompt. The agent uses its
built-in shell/terminal tool to execute curl commands against localhost:9100.

Agent Loop is a variant that uses direct OpenAI-format function calling
(no Docker, no shell) as a baseline.

**Harnesses:** CoPaw, NemoClaw, Hermes, Agent Loop

## Docker Images

Each harness ships its own `Dockerfile.<agent>` in [`docker/`](https://github.com/xirui-li/ClawEnvKit/tree/main/docker).
Most of them layer ClawEnvKit's eval infrastructure (mock services, MCP server,
entrypoint) on top of an upstream **base image** that ships the agent runtime
itself. You must build (or pull) that base image first before building the
ClawEnvKit harness image.

### Base Image Sources

The harness expects each base image tagged as `<agent>:latest` by default.
Build them locally from the upstream sources:

| Harness | Upstream repo | Build the base image |
|---------|---------------|----------------------|
| OpenClaw | [openclaw/openclaw](https://github.com/openclaw/openclaw) | `docker build -f openclaw/Dockerfile -t openclaw:latest openclaw` |
| NanoClaw | [qwibitai/nanoclaw](https://github.com/qwibitai/nanoclaw) | `docker build -f nanoclaw/container/Dockerfile -t nanoclaw:latest nanoclaw/container` |
| IronClaw¹ | [nearai/ironclaw](https://github.com/nearai/ironclaw) | `docker build -f ironclaw/Dockerfile -t ironclaw:latest ironclaw` |
| CoPaw | [agentscope-ai/CoPaw](https://github.com/agentscope-ai/CoPaw) | `docker build -f copaw/deploy/Dockerfile -t copaw:latest copaw` |
| Hermes | [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent) | `docker build -f hermes/Dockerfile -t hermes:latest hermes` |
| NemoClaw | [nvidia/nemoclaw](https://github.com/nvidia/nemoclaw) | `docker build -f nemoclaw/Dockerfile -t nemoclaw:latest nemoclaw` |
| PicoClaw | [sipeed/picoclaw](https://github.com/sipeed/picoclaw) | `docker build -f picoclaw/docker/Dockerfile -t picoclaw:latest picoclaw` |
| ZeroClaw¹ | [zeroclaw-labs/zeroclaw](https://github.com/zeroclaw-labs/zeroclaw) | `docker build -f zeroclaw/Dockerfile -t zeroclaw:latest zeroclaw` |
| Claude Code | (no separate base — pulls `node:22-slim` and `npm install`s the CLI) | n/a |

¹ IronClaw is excluded by default in `run_harnesses.sh` — its native agent loop
runs 50 iterations per task and tends to time out. Build only if you need it.
ZeroClaw differs from the others structurally: its harness Dockerfile uses
`COPY --from=${BASE_IMAGE}` rather than `FROM ${BASE_IMAGE}` (only the
`zeroclaw` binary is pulled into a fresh `python:3.12-slim` runtime). The
`BASE_IMAGE` build-arg works the same way regardless.

### Overriding the Base Image

Each `Dockerfile.<agent>` declares `ARG BASE_IMAGE=<agent>:latest`, so you can
point at a fork or a registry image without editing the Dockerfile:

```bash
docker build -f docker/Dockerfile.openclaw \
  --build-arg BASE_IMAGE=ghcr.io/your-fork/openclaw:v1.2 \
  -t clawenvkit:openclaw .
```

### End-to-End Example

```bash
# 1. Build the upstream base image (once per harness)
git clone https://github.com/sipeed/picoclaw.git
docker build -f picoclaw/docker/Dockerfile -t picoclaw:latest picoclaw

# 2. Build the ClawEnvKit harness image (layers eval infra on top)
docker build -f docker/Dockerfile.picoclaw -t clawenvkit:picoclaw .

# 3. Run any task
docker run --rm \
  -e ANTHROPIC_API_KEY=$KEY \
  -v ./Auto-ClawEval-mini/todo/todo-001.yaml:/opt/clawenvkit/task.yaml:ro \
  clawenvkit:picoclaw
```

## Batch Evaluation

```bash
# All 10 harnesses with one model
bash run_harnesses.sh --model anthropic/claude-haiku-4-5-20251001 --dataset Auto-ClawEval-mini --resume

# Single harness
bash run_harnesses.sh --harness picoclaw --model anthropic/claude-sonnet-4.6 --resume

# All harnesses via Python
python3 scripts/evaluate.py --all-harnesses --model anthropic/claude-sonnet-4.6
```
