# Other Agent Frameworks

NanoClaw, IronClaw, CoPaw, PicoClaw, ZeroClaw, NemoClaw, and Hermes all use the **Skill + curl** approach.

## How It Works

```
1. Entrypoint starts mock service (port 9100)
2. Fetches OpenAPI spec → generates SKILL.md with parameter docs + curl examples
3. Writes SKILL.md to agent's skill directory
4. Configures agent (API key, model) via framework-specific config file
5. Runs agent CLI with the task prompt
6. Agent reads SKILL.md → uses bash/curl to call mock API
7. Audit log → GradingEngine → score
```

All 7 agents share `docker/entrypoint_claw.sh`, differentiated by environment variables.

## Generated SKILL.md Example

The entrypoint auto-generates detailed API documentation from the mock service's OpenAPI spec:

```markdown
# Evaluation Environment

A mock API service is running on `http://localhost:9100`.

## Available Tools

### create_task

Create a new task with a title, description, priority, and due date.

**Parameters:**
- `title` (string **(required)**)
- `description` (string)
- `priority` (string, default: `medium`)
- `due_date` (string)

​```bash
curl -s -X POST http://localhost:9100/todo/tasks/create \
  -H 'Content-Type: application/json' \
  -d '{"title": "..."}'
​```
```

## Per-Framework Config

| Framework | Config File | Format | Key Fields |
|-----------|-------------|--------|------------|
| NanoClaw | `~/.nanoclaw/.env` | KEY=value | `ANTHROPIC_API_KEY` |
| IronClaw | `~/.ironclaw/.env` | KEY=value | `LLM_BACKEND`, `LLM_API_KEY`, `LLM_MODEL` |
| CoPaw | `~/.copaw/config.json` | JSON | `models.default.provider`, `api_key` |
| PicoClaw | `~/.picoclaw/config.json` | JSON | `model_list[].provider`, `api_key` |
| ZeroClaw | `~/.zeroclaw/config.toml` | TOML | `provider.type`, `api_key` |
| NemoClaw | `~/.nemoclaw/config.json` | JSON | `providers.default.type`, `api_key` |
| Hermes | `~/.hermes/config.yaml` | YAML | `providers.default.type`, `api_key` |

## Running

```bash
# Build (once per agent, requires base image)
docker build -f docker/Dockerfile.nanoclaw -t claw-harness-nanoclaw .

# Run any task
docker run --rm \
  -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY \
  -v ./dataset/todo/todo-001.yaml:/opt/clawharness/task.yaml:ro \
  -v /tmp/results:/logs \
  claw-harness-nanoclaw
```

Replace `nanoclaw` with any other agent name.
