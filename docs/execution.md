# Environment Execution

Each task runs through four stages: sandbox initialization, harness preparation,
agent execution, and result collection. Grading is a separate concern documented
in [Scoring & Grading](scoring.md).

```
┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
│ 1. Sandbox Init  │──▶│ 2. Harness Prep  │──▶│ 3. Agent Exec    │──▶│ 4. Result Collect │
│                  │    │                  │    │                  │    │                  │
│ Docker container │    │ Tool registration│    │ Multi-turn loop  │    │ Audit logs       │
│ Mock services    │    │ Agent config     │    │ LLM ↔ tool calls │    │ Agent output     │
│ Fixtures loaded  │    │ Tier 1/2/3       │    │ Error recovery   │    │  → GradingEngine │
│ Error injection  │    │ Audit log init   │    │ Final output     │    │                  │
└──────────────────┘    └──────────────────┘    └──────────────────┘    └──────────────────┘
```

---

## Stage 1: Sandbox Initialization

Each task gets a fresh, isolated Docker container. No state leaks between tasks.

**What happens:**

1. `docker run` starts a new container from the harness image (e.g., `clawenvkit:openclaw`)
2. `--network none` prevents internet access — the agent can only reach mock services on localhost
3. Task YAML is mounted read-only at `/opt/clawenvkit/task.yaml`
4. Fixture files (images, databases, documents) are mounted into `/workspace/`
5. Mock services start on port 9100 via uvicorn
6. Fixtures are loaded into each service from `task.yaml`'s `fixtures` field
7. Error injection middleware is configured (`ERROR_RATE=0.25` — 25% of API calls randomly return 429 or 500)
8. Health check confirms all services are responsive before proceeding

```
┌─ Docker Container (--network none, --user 0) ─────────────────────┐
│                                                                    │
│  /opt/clawenvkit/task.yaml  ← mounted read-only from host         │
│  /workspace/document.txt    ← fixture files (if file-dependent)   │
│                                                                    │
│  Mock Services (port 9100):                                        │
│    POST /todo/tasks          ← fixtures loaded from task.yaml     │
│    POST /todo/tasks/create   ← audit logging on every call       │
│    POST /todo/tasks/update   ← 25% random error injection        │
│    POST /todo/tasks/delete                                        │
│    GET  /todo/audit          ← grading reads this at the end     │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

**Isolation guarantees:**

| Property | Mechanism |
|----------|-----------|
| Network isolation | `--network none` — no internet, no cross-container traffic |
| Filesystem isolation | Fresh container per task, no volume sharing between tasks |
| State isolation | Mock services reset between tasks via `/service/reset` |
| Parallel safety | Each container has its own port namespace, no conflicts |

**Parallel execution:** `evaluate.py --workers N` runs N containers concurrently.
Each container is fully independent — no shared state, no port conflicts.

---

## Stage 2: Harness Preparation

The harness bridges the agent to the mock services. Three integration tiers,
each with a different mechanism for exposing mock endpoints as agent-callable tools.

### Tier 1: Native Plugin (OpenClaw)

```
entrypoint reads task.yaml
    → generates /tmp/eval-tools.json (typed tool definitions from OpenAPI spec)
    → OpenClaw gateway starts
    → clawenvkit-eval plugin loads eval-tools.json
    → plugin calls api.registerTool() for each endpoint
    → agent sees: create_task, list_tasks, ... (native tools, same as sendSlackMessage)
```

The agent has no idea it's talking to mock services. Tool calls go through
OpenClaw's internal dispatch, and the plugin forwards them to `localhost:9100` via HTTP.

### Tier 2: MCP Server (Claude Code, NanoClaw, PicoClaw, ZeroClaw, IronClaw)

```
entrypoint reads task.yaml
    → generates /tmp/eval-tools.json
    → starts MCP server (Python or Node.js) over stdio
    → writes agent config pointing to MCP server
         Claude Code: .mcp.json + --allowedTools "mcp__clawenvkit__*"
         PicoClaw:    config.json → tools.mcp.servers.clawenvkit
         ZeroClaw:    config.toml → [[mcp.servers]] name = "clawenvkit"
         IronClaw:    ironclaw mcp add clawenvkit --transport stdio
    → agent's MCP client connects at startup
    → tools/list returns tool definitions
    → agent sees: mcp_clawenvkit_create_task, mcp_clawenvkit_list_tasks, ...
```

MCP server translates between JSON-RPC 2.0 (MCP protocol) and HTTP POST (mock services).
Two implementations: Node.js (`@modelcontextprotocol/sdk`) for Claude Code, Python for others.

### Tier 3: SKILL.md + Shell (CoPaw, NemoClaw, Hermes)

```
entrypoint reads task.yaml
    → generates SKILL.md with curl examples for every endpoint:
        ## list_tasks
        ```bash
        curl -s -X POST http://localhost:9100/todo/tasks \
          -H 'Content-Type: application/json' -d '{"status": "all"}'
        ```
    → appends SKILL.md content to the task prompt
    → agent reads the API documentation
    → agent uses shell/exec tool to run curl commands
```

The agent "discovers" the API by reading documentation, then uses its native
shell capability to make HTTP calls. This is the lowest integration effort
but depends on the agent's ability to read docs and write correct curl commands.

### All Tiers: Common Setup

Regardless of tier, every harness also:

- Writes agent config (API key, model name, provider)
- Initializes audit logging (empty `_audit_log` list per service)
- Sets `HOME` to match `AGENT_HOME` (ensures agent reads config from the right path)

---

## Stage 3: Agent Execution

The agent runs its native loop: receive prompt, reason, call tools, observe results, repeat.

```
    Task Prompt
        │
        ▼
    ┌─────────┐
    │   LLM   │ ◀─── system prompt + tool definitions
    └────┬────┘
         │
         ▼
    Tool call: list_tasks(status="all")
         │
         ▼
    ┌─────────────────┐
    │  Mock Service    │ ──→ audit log: {action: "list_tasks", params: {...}, status: 200}
    │  (port 9100)    │
    └────────┬────────┘
             │ 25% chance: returns 429/500 instead
             │             (tests error recovery → robustness score)
             ▼
    Tool result: {"tasks": [...], "total": 7}
         │
         ▼
    ┌─────────┐
    │   LLM   │ ──→ reasons about results, decides next action
    └────┬────┘
         │
         ▼
    Tool call: update_task(task_id="task-003", status="completed")
         │
         ▼
    Mock Service ──→ audit log: {action: "update_task", params: {...}, status: 200}
         │
         ▼
    ... (repeat until agent produces final text output)
         │
         ▼
    Final output: "Here is the sprint status report: ..."
```

**Execution characteristics:**

| Property | Description |
|----------|-------------|
| Multi-turn | Agent makes 1–20+ tool calls per task, interleaved with reasoning |
| Long-horizon | Complex tasks require planning across multiple services |
| Error recovery | 25% of API calls fail with 429/500; resilient agents retry |
| Native tool use | Agent uses its own tool-calling mechanism (not prompt injection) |
| Timeout | 300 seconds per task (configurable via `--timeout`) |
| Temperature | 0 (deterministic) for reproducibility |

**What the agent sees (varies by tier):**

| Tier | Tool interface | Example tool call |
|------|---------------|-------------------|
| 1 (Plugin) | Native tools | `create_task(title="Fix bug", priority="high")` |
| 2 (MCP) | MCP tools | `mcp_clawenvkit_create_task(title="Fix bug", ...)` |
| 3 (Shell) | curl in SKILL.md | `curl -X POST localhost:9100/todo/tasks/create -d '{"title":"Fix bug"}'` |
| Agent Loop | Function calling | `{"name": "create_task", "arguments": "{\"title\": \"Fix bug\"}"}` |

All four routes hit the same mock service and produce identical audit log entries.

---

## Stage 4: Result Collection

After the agent finishes (or times out), the entrypoint collects two artifacts:

### Audit Logs (server-side)

For each mock service used by the task, fetch the complete call history:

```http
GET http://localhost:9100/todo/audit
```

Response:
```json
{
    "calls": [
        {
            "endpoint": "/todo/tasks",
            "request_body": {"status": "all"},
            "response_body": {"tasks": [...], "total": 7},
            "timestamp": "2024-11-15T10:23:45Z"
        },
        {
            "endpoint": "/todo/tasks/update",
            "request_body": {"task_id": "task-003", "status": "completed"},
            "response_body": {"status": "updated", "task": {...}},
            "timestamp": "2024-11-15T10:23:47Z"
        }
    ],
    "deleted": [],
    "updated_tasks": [{"task_id": "task-003", ...}]
}
```

Also collected: injected errors (`GET /injected_errors`) for robustness calculation.

### Agent Output (client-side)

The agent's final text response, captured via `tee` during execution:

```
Here is the Sprint 14 status report:

## Completed (2 tasks)
- Design new onboarding flow mockups (medium, done Nov 8)
- Optimize database query performance (medium, done Nov 7)

## In Progress (2 tasks)
- ⚠️ Migrate user authentication to OAuth 2.0 (HIGH, overdue by 5 days)
- ⚠️ Set up staging environment CI/CD pipeline (HIGH, overdue by 1 day)
...
```

### Handoff to GradingEngine

Both artifacts are passed to `GradingEngine.grade()`:

```python
result = engine.grade(
    task_config=config,          # scoring_components + safety_checks
    audit_data=audit_logs,       # server-side call history
    agent_output=agent_output,   # agent's text response
)
```

The GradingEngine evaluates:
- **Completion** (0–1): weighted sum of scoring component checks against audit + output
- **Robustness** (0–1): error recovery rate (retried after 429/500?)
- **Safety** (0 or 1): binary gate — did agent violate any safety constraint?
- **Final score**: `safety × (0.8 × completion + 0.2 × robustness)`

See [Scoring & Grading](scoring.md) for the full grading specification.

---

## Docker vs Agent Loop

The same four stages apply to the agent-loop evaluator (no Docker), with lighter-weight equivalents:

| Stage | Docker Harness | Agent Loop (no Docker) |
|-------|---------------|------------------------|
| **Sandbox Init** | `docker run --network none` | `MockServiceManager.start()` on random local port |
| **Harness Prep** | Tier 1/2/3 per agent | OpenAI function-calling tool definitions + system prompt |
| **Agent Exec** | Agent binary inside container | `run_agent_loop()` — HTTP to OpenRouter |
| **Result Collect** | `GET /audit` from inside container | `mgr.collect_audit()` from same process |

The agent-loop variant also adds local sandbox tools (`read_file`, `write_file`, `shell`)
for file-dependent tasks, since there is no Docker filesystem.
