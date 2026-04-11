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

Each harness has its own Dockerfile:

```bash
# Build (once per harness, requires base image)
docker build -t picoclaw:latest <path-to-picoclaw>  # Build base image first
docker build -f docker/Dockerfile.picoclaw -t clawenvkit:picoclaw .

# Run any task
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
