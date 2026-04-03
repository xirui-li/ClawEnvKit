# Supported Agents

ClawHarnessing supports 14+ agents across three integration tiers.

## Agent Comparison

| Agent | Integration | Mechanism | Tool Experience |
|-------|------------|-----------|-----------------|
| **OpenClaw** | Native Plugin | TypeScript `registerTool()` | Native tools |
| **Claude Code** | MCP Server | `@modelcontextprotocol/sdk` | Native tools |
| **Codex (OpenAI)** | MCP Server | Same MCP server | Native tools |
| **Cursor** | MCP Server | Same MCP server | Native tools |
| **NanoClaw** | Skill + curl | SKILL.md → bash curl | Curl commands |
| **IronClaw** | Skill + curl | SKILL.md → bash curl | Curl commands |
| **CoPaw** | Skill + curl | SKILL.md → bash curl | Curl commands |
| **PicoClaw** | Skill + curl | SKILL.md → bash curl | Curl commands |
| **ZeroClaw** | Skill + curl | SKILL.md → bash curl | Curl commands |
| **NemoClaw** | Skill + curl | SKILL.md → bash curl | Curl commands |
| **Hermes** | Skill + curl | SKILL.md → bash curl | Curl commands |

### Integration Tiers

```
Tier 1 — Native Plugin: OpenClaw (registerTool API)
Tier 2 — MCP Server:    Claude Code, Codex, Cursor, Windsurf, Continue, ...
Tier 3 — Skill + curl:  NanoClaw, IronClaw, CoPaw, PicoClaw, ZeroClaw, NemoClaw, Hermes
```

Tier 1 and Tier 2 agents see native tools. Tier 3 agents use curl via bash.

## Docker Images

Each agent has its own Dockerfile. Build once, run any task via volume mount:

| Agent | Dockerfile | Integration |
|-------|-----------|-------------|
| OpenClaw | `Dockerfile.openclaw` | Native Plugin |
| Claude Code | `Dockerfile.claudecode` | MCP Server |
| NanoClaw | `Dockerfile.nanoclaw` | Skill + curl |
| IronClaw | `Dockerfile.ironclaw` | Skill + curl |
| CoPaw | `Dockerfile.copaw` | Skill + curl |
| PicoClaw | `Dockerfile.picoclaw` | Skill + curl |
| ZeroClaw | `Dockerfile.zeroclaw` | Skill + curl |
| NemoClaw | `Dockerfile.nemoclaw` | Skill + curl |
| Hermes | `Dockerfile.hermes` | Skill + curl |

```bash
# Build any agent (example: Claude Code)
docker build -f docker/Dockerfile.claudecode -t clawharness:claudecode .

# Run any task
docker run --rm \
  -e ANTHROPIC_API_KEY=$KEY \
  -v ./dataset/todo/todo-001.yaml:/opt/clawharness/task.yaml:ro \
  clawharness:claudecode
```

## Python API

All agents run via Docker (no Python agent API):

```bash
docker run --rm -e ANTHROPIC_API_KEY=$KEY \
  -v ./dataset/todo/todo-001.yaml:/opt/clawharness/task.yaml:ro \
  clawharness:openclaw
```
