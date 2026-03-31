# Supported Agents

ClawHarnessing supports 8 claw-like agents with a unified adapter interface.

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
docker build -f docker/Dockerfile.claudecode -t claw-harness-claudecode .

# Run any task
docker run --rm \
  -e ANTHROPIC_API_KEY=$KEY \
  -v ./dataset/todo/todo-001.yaml:/opt/clawharness/task.yaml:ro \
  claw-harness-claudecode
```

## Python API

```python
from clawharness.agents import list_agents, get_agent

# List available agents
print(list_agents())  # ['openclaw', 'nanoclaw', 'ironclaw', ...]

# Use an agent
agent = get_agent("openclaw")
agent.setup(workspace="/workspace", model="claude-sonnet-4-6", api_key="sk-ant-...")
result = agent.run(prompt="Create a task...", tools=[...])
print(result.output, result.wall_time_s)
```

Compatible with [MetaClaw](https://github.com/aiming-lab/MetaClaw)'s `claw_type` list.
