# Supported Agents

ClawHarnessing supports 8 claw-like agents with a unified adapter interface.

## Agent Comparison

| Agent | Integration | Config Method | Skills | Browser | Memory |
|-------|------------|---------------|--------|---------|--------|
| **OpenClaw** | Native Plugin | TypeScript `registerTool()` | Yes | Yes | Yes |
| **NanoClaw** | Skill + curl | `.env` patch | Yes | No | Yes |
| **IronClaw** | Skill + curl | `.ironclaw/.env` patch | Yes | No | No |
| **CoPaw** | Skill + curl | `.copaw/config.json` patch | Yes | No | Yes |
| **PicoClaw** | Skill + curl | `.picoclaw/config.json` patch | Yes | No | No |
| **ZeroClaw** | Skill + curl | `.zeroclaw/config.toml` patch | Yes | No | No |
| **NemoClaw** | Skill + curl | `.nemoclaw/config.json` patch | Yes | No | No |
| **Hermes** | Skill + curl | `.hermes/config.yaml` patch | Yes | No | No |

## Docker Images

Each agent has its own Dockerfile. Build once, run any task via volume mount:

| Agent | Dockerfile | Build Command |
|-------|-----------|---------------|
| OpenClaw | `Dockerfile.openclaw` | `docker build -f docker/Dockerfile.openclaw -t claw-harness-openclaw .` |
| NanoClaw | `Dockerfile.nanoclaw` | `docker build -f docker/Dockerfile.nanoclaw -t claw-harness-nanoclaw .` |
| IronClaw | `Dockerfile.ironclaw` | `docker build -f docker/Dockerfile.ironclaw -t claw-harness-ironclaw .` |
| CoPaw | `Dockerfile.copaw` | `docker build -f docker/Dockerfile.copaw -t claw-harness-copaw .` |
| PicoClaw | `Dockerfile.picoclaw` | `docker build -f docker/Dockerfile.picoclaw -t claw-harness-picoclaw .` |
| ZeroClaw | `Dockerfile.zeroclaw` | `docker build -f docker/Dockerfile.zeroclaw -t claw-harness-zeroclaw .` |
| NemoClaw | `Dockerfile.nemoclaw` | `docker build -f docker/Dockerfile.nemoclaw -t claw-harness-nemoclaw .` |
| Hermes | `Dockerfile.hermes` | `docker build -f docker/Dockerfile.hermes -t claw-harness-hermes .` |

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
