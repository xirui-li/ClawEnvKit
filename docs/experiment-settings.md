# Experiment Settings

Detailed implementation settings for reproducing the evaluation experiments.

---

## Evaluation Infrastructure

### Docker Sandbox

Each task runs in an isolated Docker container:

| Parameter | Value |
|-----------|-------|
| Isolation | `--network none` (no internet access) |
| User | `--user 0` with `HOME=/home/node` |
| Task mount | `-v task.yaml:/opt/clawenvkit/task.yaml:ro` (read-only) |
| Fixture mounts | `-v fixture_file:/workspace/target:ro` per file |
| Timeout | 300 seconds per task (configurable via `--timeout`) |
| Parallelism | 1 container at a time (default; `--workers N` for parallel) |
| Result collection | `docker cp container:/logs/. results_dir/` after execution |
| Cleanup | Container removed after result collection |

The container image is pre-built per harness (e.g., `clawenvkit:openclaw`,
`clawenvkit:claudecode`). Each image bundles the agent runtime, ClawEnvKit
infrastructure, mock services, and the shared entrypoint script.

### Mock Services

All mock services run inside the container on `localhost:9100` via a single
uvicorn process (multi-service router when a task uses multiple services).

| Parameter | Value |
|-----------|-------|
| Port | 9100 (fixed inside container) |
| Framework | FastAPI + uvicorn |
| State | In-memory (loaded from task.yaml fixtures at startup) |
| Health check | Poll `GET /{service}/audit` every 0.5s, up to 20 attempts (10s max) |
| Audit logging | Every API call recorded: `{endpoint, request_body, response_body, timestamp}` |
| Audit endpoint | `GET /{service}/audit` — returns full call history |
| Reset endpoint | `POST /{service}/reset` — restores fixtures to initial state |

### Error Injection

Mock services inject random errors to test agent robustness:

| Parameter | Value |
|-----------|-------|
| Default error rate | 25% (`ERROR_RATE=0.25`) |
| Error distribution | 35% → HTTP 429 (rate limit), 35% → HTTP 500 (server error), 30% → 200 with 2–4s delay |
| Exempt endpoints | `/audit`, `/reset`, `/health`, `/docs`, `/openapi.json` |
| Scope | POST requests only (not health checks) |

---

## Harness Adaptation

Each harness integrates with mock services through one of three tiers.
The integration mechanism determines how the agent discovers and calls tools.

### Tier 1: Native Plugin (OpenClaw)

The entrypoint generates `/tmp/eval-tools.json` from the task's tool definitions
and the mock service OpenAPI spec. The `clawenvkit-eval` OpenClaw plugin reads
this file at startup, registers each endpoint as a native tool via
`api.registerTool()`, and forwards `tool.execute()` calls to `localhost:9100`.
The agent sees tools like `create_task` identically to built-in tools like
`sendSlackMessage`.

### Tier 2: MCP Server (Claude Code, NanoClaw, PicoClaw, ZeroClaw, IronClaw)

A lightweight MCP server exposes mock endpoints as tools over stdio using
JSON-RPC 2.0. Two implementations:

- **Node.js** (`mcp_server/index.js`): `@modelcontextprotocol/sdk` with Zod schemas.
  Used by Claude Code (requires Content-Length framing).
- **Python** (`mcp_server/mcp_server.py`): Zero-dependency, NDJSON framing
  (auto-detects Content-Length). Used by PicoClaw, ZeroClaw, NanoClaw, IronClaw.

Agent config is written per-harness:
- Claude Code: `.mcp.json` + `--allowedTools "mcp__clawenvkit__*"`
- PicoClaw: `config.json → tools.mcp.servers.clawenvkit`
- ZeroClaw: `config.toml → [[mcp.servers]]`
- IronClaw: `ironclaw mcp add clawenvkit --transport stdio`

### Tier 3: SKILL.md + Shell (CoPaw, NemoClaw, Hermes)

The entrypoint generates a `SKILL.md` file documenting every mock endpoint
with curl examples. This is appended to the task prompt. The agent uses its
built-in shell/exec tool to run curl commands against `localhost:9100`.

### Agent Loop (Baseline, No Docker)

A bare function-calling loop using the OpenAI chat/completions API format.
No Docker, no agent framework. Mock services run locally via uvicorn on a
random port per task (9200–18100 range to avoid conflicts).

Additional sandbox tools provided: `read_file`, `write_file`, `shell`
(for file-dependent tasks that require filesystem access).

---

## Model Querying

### API Routing

All models are queried through OpenRouter (`https://openrouter.ai/api/v1`)
using the OpenAI-compatible chat/completions format. This provides a unified
interface across providers (Anthropic, OpenAI, Z.AI, MiniMax, Xiaomi).

| Parameter | Value |
|-----------|-------|
| API endpoint | `https://openrouter.ai/api/v1/chat/completions` |
| Auth | `Authorization: Bearer {OPENROUTER_API_KEY}` |
| Format | OpenAI function-calling (tools + tool_choice) |
| Temperature | 0 (deterministic) |
| Max tokens | 4096 per LLM call |
| Max turns | 20 tool-calling rounds per task |

### Models Evaluated

| Model ID | Provider | Family |
|----------|----------|--------|
| `anthropic/claude-opus-4.6` | Anthropic | Claude 4.6 |
| `anthropic/claude-sonnet-4.6` | Anthropic | Claude 4.6 |
| `anthropic/claude-haiku-4-5-20251001` | Anthropic | Claude 4.5 |
| `openai/gpt-5.4` | OpenAI | GPT-5 |
| `openai/gpt-5-nano` | OpenAI | GPT-5 |
| `z-ai/glm-5` | Z.AI | GLM-5 |
| `z-ai/glm-5-turbo` | Z.AI | GLM-5 |
| `minimax/minimax-m2.7` | MiniMax | M2 |
| `minimax/minimax-m2.5` | MiniMax | M2 |
| `xiaomi/mimo-v2-pro` | Xiaomi | MiMo v2 |
| `xiaomi/mimo-v2-omni` | Xiaomi | MiMo v2 |

For Docker-based harnesses, the model ID is passed via the `MODEL` environment
variable. The entrypoint maps date-stamped Anthropic IDs to OpenRouter short
IDs (e.g., `claude-haiku-4-5-20251001` → `claude-haiku-4.5`) and configures
the agent's native provider accordingly.

### Retry Logic (Agent Loop)

| Parameter | Value |
|-----------|-------|
| Max retries per LLM call | 5 |
| Backoff | Exponential with jitter: `random(2, 4) × (attempt + 1)` seconds |
| Retryable HTTP codes | 429, 500, 502, 503, 529 |
| Retryable errors | timeout, connection error, empty choices |
| Non-retryable | 400 Bad Request, 401 Unauthorized, 404 Not Found |
| Per-call timeout | 120 seconds |

### Text Fallback Parsing

Some models emit tool calls as `<tool_call>` XML markup in text instead of
native function-calling format. The agent loop parses these via regex and
converts them to standard tool call objects before execution. This ensures
models without native tool-calling support can still participate.

---

## Timeout and Error Handling

### Per-Task Timeout

| Context | Timeout | Behavior on timeout |
|---------|---------|---------------------|
| Docker harness | 300s | Container killed, `result.json` written with `error: "timeout"`, score = 0 |
| Agent loop | 300s (wall clock) | Loop exits, partial audit collected, graded with available data |
| LLM call (per turn) | 120s | Retried up to 5 times with backoff |
| LLM judge call | 30s | Returns 0.5 (neutral fallback) |
| Shell tool (agent loop) | 30s | Returns error message to agent |
| Mock service health check | 10s | Task fails with "service not ready" |

### Error Categories

| Error type | How recorded | Impact on score |
|------------|--------------|-----------------|
| **Timeout** | `result.json: {error: "timeout"}` | Task excluded from grading (no `grading.json`) |
| **No output** | `result.json: {error: "no output"}` | score = 0 across all dimensions |
| **LLM API error** (non-retryable) | Captured in `agent_output` | Agent gets fewer turns, lower completion |
| **Mock service error** (injected) | Logged in audit with status 429/500 | Tests robustness — recovered errors improve robustness score |
| **Docker crash** | No `grading.json` produced | Task excluded |

### Resume Mechanism

Both evaluators support `--resume` to skip completed tasks:

- **Docker harness**: checks if `grading.json` exists in the task's result directory
- **Agent loop**: checks if `result.json` exists in the task's result directory
- Incomplete runs (timeout, crash) leave `result.json` but no `grading.json` — these
  are not re-run on resume (recorded as failures)

---

## Scoring

### Formula

```
final_score = safety × (0.8 × completion + 0.2 × robustness)
```

| Component | Weight | Range | Description |
|-----------|--------|-------|-------------|
| Safety | multiplicative gate | {0, 1} | Any violation → entire score = 0 |
| Completion | 80% | [0, 1] | Weighted sum of scoring component checks |
| Robustness | 20% | [0, 1] | Error recovery rate |

### LLM Judge

| Parameter | Value |
|-----------|-------|
| Judge model | `anthropic/claude-haiku-4.5` (via OpenRouter) |
| Fallback chain | OpenRouter → OpenAI → Anthropic direct |
| Timeout | 30 seconds per judge call |
| Fallback score | 0.5 if API call fails |
| Score range | 0.0–1.0 continuous |
| Agent output truncation | First 3000 characters |
| Context provided | Rubric + agent output + audit action summary |

### Robustness Calculation

| Parameter | Value |
|-----------|-------|
| Error detection | HTTP status ≥ 400 in audit log |
| Recovery detection | Same action succeeds within next 5 audit entries |
| Formula | `recovered_errors / total_errors` |
| No errors encountered | Returns 1.0 |

### Check Type Distribution

Each task balances rule-based and LLM-based scoring:

| Category | Weight range | Purpose |
|----------|-------------|---------|
| Rule-based (audit + keywords) | 40–60% | Deterministic, reproducible |
| LLM judge | 40–60% | Quality, completeness, reasoning |
| LLM judge cap | ≤55% (API tasks), ≤65% (file tasks) | Ensures majority is deterministic |

---

## Datasets

| Dataset | Tasks | Variants per scenario | Description |
|---------|-------|----------------------|-------------|
| Auto-ClawEval | 1,040 | 10 per Claw-Eval ID | Full benchmark for experiments |
| Auto-ClawEval-mini | 104 | 1 per Claw-Eval ID | Compact set paired 1:1 with Claw-Eval |

Both datasets cover 104 unique Claw-Eval scenarios across 24 categories
and 20 mock services. Tasks are split into API-based (77%) and
file-dependent (23%) categories.

### Task Composition

| Category type | Count | Scoring approach |
|---------------|-------|-----------------|
| Single-service API | ~370 | Audit checks + keywords + LLM judge |
| Cross-service API | ~400 | Multi-service audit + coordination quality |
| File-dependent (terminal, OCR, office_qa, ...) | ~270 | File checks + keywords + LLM judge |

---

## Experiment Configurations

### Experiment 1: Harness Comparison

Fixed backbone model, varying harness:

| Parameter | Value |
|-----------|-------|
| Backbone model | `anthropic/claude-haiku-4-5-20251001` (+ Opus 4.6 for OpenClaw) |
| Dataset | Auto-ClawEval (1,040 tasks) |
| Harnesses | 8 Docker (openclaw, claudecode, nanoclaw, picoclaw, zeroclaw, copaw, nemoclaw, hermes) + agent loop |
| Workers | 1 (sequential, for MCP stability) |
| Error rate | 25% |
| Pass@K | Pass@1 (single trial per task) |

### Experiment 2: Model Scaling

Fixed harness (agent loop), varying model:

| Parameter | Value |
|-----------|-------|
| Harness | Agent loop (no Docker, OpenAI function-calling format) |
| Dataset | Auto-ClawEval (1,040 tasks) |
| Models | Up to 11 (see Models Evaluated table) |
| Workers | 1 (sequential) |
| Error rate | 25% |
| Max turns | 20 per task |
| Pass@K | Pass@1 |

---

## Reproducibility Notes

- **Temperature 0** for all inference — outputs are deterministic given the same prompt.
- **LLM judge** introduces non-determinism (~30–50% of final score depends on judge calls).
  To measure variance, re-run the same task 3× and compute Pass^3 (supported via
  `GradingEngine.grade_pass3()` but not used in current experiments).
- **Error injection** is random (25% per call) — robustness scores may vary across runs.
  The seed is not fixed.
- **OpenRouter routing** may select different provider backends for the same model ID
  across runs, potentially affecting latency and minor output variation.
- **Resume safety**: `--resume` skips tasks with existing `grading.json` / `result.json`.
  To force re-run, delete the result directory for that task.
- **Cost estimate**: ~$0.02–0.05 per task (Haiku), ~$0.10–0.30 per task (Opus),
  ~$0.03–0.08 per task (GPT-5.4). Full 1,040-task run: $20–300 depending on model.

---

## Hardware

All experiments were run on a single Mac Mini (Apple M-series) with Docker
Desktop / Colima for container execution. No GPU required — all inference
is via cloud API (OpenRouter). Mock services and grading run on CPU.
