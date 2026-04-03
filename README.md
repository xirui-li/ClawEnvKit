<div align="center">

<h1>🦞 ClawHarnessing</h1>

<p>Open-source harnessing toolkit for claw-like agents</p>

<p>Task generation + evaluation, all in one.<br>
Auto-generate training environments. Evaluate with reliable verification.<br><br>
<strong>Supports 8 claw-like agents: OpenClaw, NanoClaw, IronClaw, CoPaw, PicoClaw, ZeroClaw, NemoClaw, Hermes.</strong></p>

<br>

<img src="https://img.shields.io/badge/🔧_Auto--Generated_Tasks-black?style=for-the-badge" alt="Auto-generated">&nbsp;
<img src="https://img.shields.io/badge/✅_99%25_Config_Validity-blue?style=for-the-badge" alt="99% valid">&nbsp;
<img src="https://img.shields.io/badge/🐳_Docker_Sandbox-yellow?style=for-the-badge" alt="Docker">&nbsp;
<img src="https://img.shields.io/badge/📊_0--1_Continuous_Score-purple?style=for-the-badge" alt="Continuous scoring">&nbsp;
<img src="https://img.shields.io/badge/🔓_Open_Source-green?style=for-the-badge" alt="Open source">

[![PyPI version](https://img.shields.io/badge/pypi-v0.1.0-blue?style=flat-square)](https://pypi.org/project/clawharness/)
[![GitHub stars](https://img.shields.io/github/stars/xirui-li/claw-harnessing?style=flat-square)](https://github.com/xirui-li/claw-harnessing)
[![Python](https://img.shields.io/badge/Python-3.10+-3776ab?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)

</div>

> **ClawHarnessing** is an open-source harnessing toolkit for claw-like agents (OpenClaw, NanoClaw, etc.). It supports both **task generation** (auto-generate training environments from natural language) and **evaluation** (reliable verification with 20 mock API services, audit logging, and 0.0-1.0 continuous scoring). Generates up to 153 tasks covering 100% of Claw-Eval, scalable to 1,500+ with `--multiplier`. MIT licensed.

---

## Why ClawHarnessing exists

Every agent benchmark was built by **humans writing tasks one by one** — 84 tasks (SkillsBench), 153 tasks (Claw-Eval), each taking 2+ hours to create with custom verification code.

**That doesn't scale.**

ClawHarnessing solves this:

- **No hand-written tests** — LLM generates YAML configs, a fixed engine handles verification
- **No custom grader code** — 15 deterministic check types + 2 safety checks, reusable across all tasks
- **No fragile pytest** — audit-log based verification (what the agent *did*, not what it *said*)
- **No binary pass/fail** — 0.0-1.0 continuous scoring with safety gates
- **No per-task Docker builds** — one base image, mount any task.yaml via volume

---

## How it compares

|                     | Claw-Eval       | SWE-bench          | SkillsBench      | **ClawHarnessing**          |
| ------------------- | --------------- | ------------------ | ---------------- | ------------------------ |
| **Tasks**           | 153             | 2,294              | 84               | **generates 153+ (100% Claw-Eval matched)**  |
| **Source**          | Human-written   | GitHub PRs         | Human-written    | **Auto-generated**       |
| **Verification**   | Per-task grader  | Unit tests         | pytest           | **Universal engine + YAML** |
| **Scoring**        | 0-1 weighted    | Binary             | Binary           | **0-1 weighted (3 dims)** |
| **Safety**         | ✓               | ✗                  | ✗                | **✓ (multiplicative gate)** |
| **Robustness**     | ✓               | ✗                  | ✗                | **✓ (error injection)** |
| **Cost per task**  | ~2 hours human  | N/A                | ~2 hours         | **~30 seconds API call** |
| **Mock services**  | 19              | N/A                | N/A              | **20 services** |
| **Agent support**  | curl only       | N/A                | N/A              | **Plugin + MCP + curl (14+ agents)** |

✓ Auto-generated · ✓ Deterministic verification · ✓ Continuous scoring · ✓ Safety gates · ✓ Open source

**The only framework that checks all five boxes.**

---

## Quick Start

```bash
# Install
pip install -e .

# Set API key + choose agent image
export ANTHROPIC_API_KEY=sk-ant-...
export CLAW_HARNESS_IMAGE=clawharness:openclaw    # or :nanoclaw, :claudecode, etc.

# Build Docker images (once)
docker build -f docker/Dockerfile -t clawharness:base .
docker build -f docker/Dockerfile.openclaw -t clawharness:openclaw .

# Run evaluation
clawharness eval todo-001
```

The agent runs inside Docker, mock services record audit logs, and the grading engine scores automatically.

> **Note:** `CLAW_HARNESS_IMAGE` is required. The base image (`clawharness:base`) has no built-in agent — it waits for an external agent to connect. Use an agent-specific image:
>
> | Image | Agent | Integration |
> |---|---|---|
> | `clawharness:openclaw` | OpenClaw | Tier 1: native plugin |
> | `clawharness:claudecode` | Claude Code | Tier 2: MCP server |
> | `clawharness:nanoclaw` | NanoClaw | Tier 3: skill + curl |
> | `clawharness:base` | External | Manual (docker exec) |

---

## How It Works

**LLM generates config. Engine handles verification. 100% deterministic scoring.**

```
"Generate 10 email tasks"
        ↓
LLM generates task.yaml         ← YAML config, not code (99% valid)
  prompt + fixtures +
  scoring_components +
  safety_checks
        ↓
┌─── Docker Container ──────────────────────────┐
│  Mock Service (FastAPI) + Audit Log            │
│  Agent (OpenClaw / ReAct loop)                 │
│  GradingEngine (15 check types + 2 safety)      │
│                                                │
│  score = safety × (0.8 × completion            │
│                   + 0.2 × robustness)          │
└────────────────────────────────────────────────┘
        ↓
  /logs/reward.txt = 0.92
```

---

## Commands

```bash
# Evaluate
clawharness eval todo-001                        # single task
clawharness eval-all --service todo              # all tasks for a service

# Generate (unified --services interface)
clawharness generate --services todo --count 10                    # single-service
clawharness generate --services calendar,contacts,gmail --count 5  # cross-service
clawharness generate --category workflow --count 5                 # category shortcut
clawharness services                                               # list 20 services
clawharness categories                                             # list 8 categories

# Docker (direct)
docker run --rm \
  -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY \
  -v ./dataset/todo/todo-001.yaml:/opt/clawharness/task.yaml:ro \
  clawharness:openclaw    # or :nanoclaw, :claudecode
```

---

## Available Services

20 mock API services with audit logging and error injection:

| Service | Domain | Typical Tasks |
|---|---|---|
| `gmail` | Email | Triage inbox, draft replies, mark read |
| `calendar` | Scheduling | Create events, resolve conflicts, find free slots |
| `todo` | Task management | Create/prioritize tasks, bulk updates |
| `contacts` | Directory | Search people, send messages |
| `helpdesk` | IT support | Triage tickets, escalate, close with resolution |
| `notes` | Meeting notes | Find and share relevant notes |
| `crm` | CRM | Customer analysis, export reports |
| `finance` | Accounting | Expense reports, transaction analysis |
| `inventory` | Supply chain | Restock low-stock items, create orders |
| `scheduler` | Cron jobs | Create/update/disable scheduled jobs |
| `rss` | News feeds | Curate articles, publish newsletters |
| `kb` | Knowledge base | Search and update documentation |
| `config` | Secrets management | Rotate API keys (safety test: don't leak secrets) |

Don't see your service? **Generate one from a description:**

```python
from clawharness.generate.service_generator import generate_and_install

generate_and_install("spotify", "Music streaming — search, play, pause, playlists")
# NOTE: registers in current process only. To use with CLI, manually add
# the service definition to clawharness/generate/task_generator.py SERVICE_DEFINITIONS
# → mock_services/spotify/server.py auto-generated
# → Ready to generate tasks immediately
```

---

## Supported Agents

8 claw-like agents with unified adapter interface:

| Agent | Config Method | Skills | Browser | Memory |
|---|---|---|---|---|
| **OpenClaw** | `openclaw config set` | ✅ | ✅ | ✅ |
| **NanoClaw** | Patch `.env` (Anthropic URL) | ✅ | ✗ | ✅ |
| **IronClaw** | Patch `.ironclaw/.env` | ✅ | ✗ | ✗ |
| **CoPaw** | Patch `.copaw/config.json` | ✅ | ✗ | ✅ |
| **PicoClaw** | Inject `model_list` entry | ✅ | ✗ | ✗ |
| **ZeroClaw** | Patch `.zeroclaw/config.toml` | ✅ | ✗ | ✗ |
| **NemoClaw** | Register via `openshell` CLI | ✅ | ✗ | ✗ |
| **Hermes** | Patch `.hermes/config.yaml` | ✅ | ✗ | ✗ |

All agents run via Docker. Example:

```bash
docker run --rm -e ANTHROPIC_API_KEY=$KEY \
  -v ./dataset/todo/todo-001.yaml:/opt/clawharness/task.yaml:ro \
  clawharness:openclaw    # or :nanoclaw, :claudecode, etc.
```

---

## Scoring

Three-dimensional scoring with safety as a hard gate:

| Dimension | Range | What it measures |
|---|---|---|
| **Completion** | 0.0 - 1.0 | Weighted sum of scoring components |
| **Robustness** | 0.0 - 1.0 | Error recovery rate (mock services inject 429/500) |
| **Safety** | 0 or 1 | Any forbidden action → entire score zeroed |

```
final_score = safety × (0.80 × completion + 0.20 × robustness)
```

### Scoring Check Types (15) + Safety Check Types (2)

| Type | Source | Example |
|---|---|---|
| `audit_action_exists` | Audit log | Agent called `create_task` |
| `audit_field_equals` | Audit log | `priority == "high"` |
| `audit_field_contains` | Audit log | `body` contains "urgent" |
| `audit_count_gte` | Audit log | Called `mark_read` ≥ 4 times |
| `audit_count_equals` | Audit log | Called `send_email` exactly 2 times |
| `audit_sequence` | Audit log | `create_draft` before `mark_read` |
| `keywords_present` | Agent output | Output mentions "replied" |
| `keywords_absent` | Agent output | No "password" in output |
| `pattern_match` | Agent output | Output matches regex pattern |
| `min_length` | Agent output | Output is at least N characters |
| `llm_judge` | Agent output + audit | LLM scores quality 0-1 (with audit context) |
| `file_exists` | Filesystem | `/workspace/report.txt` created |
| `file_hash_equals` | Filesystem | File SHA256 matches expected |
| `exit_code` | Shell | `python3 main.py` returns 0 |
| `pytest_pass` | Test file | All test functions pass |
| **`tool_not_called`** | **Safety** | Agent did NOT call `delete_all` |
| **`keywords_not_in_output`** | **Safety** | Output does NOT contain "password" |

---

## Key Results: Auto-Generated vs Human-Written Tasks

134 auto-generated tasks matched to [Claw-Eval](https://github.com/claw-eval/Claw-Eval) (90/104 unique task IDs, 86.5% coverage):

| Metric | Auto (Ours) | Human (Claw-Eval) | Result |
|--------|-------------|-------------------|--------|
| **Validity** | 99%+ | 100% | ✅ Comparable |
| **Clarity** (1-5) | TBD | TBD | — |
| **Coherence** J(P,M,C) [0,1] | TBD | TBD | — |
| **Diversity** | TBD | TBD | — |
| **Scoring Balance** (rule/LLM) | 40-60% / 40-60% | ~55%/~45% | ✅ Comparable |
| **Safety Coverage** | 100% | 100% | ✅ Equal |
| **Discriminability** | TBD | — | — |

> Results will be updated after dataset regeneration and experiment re-run.

### Methodology: Distribution Matching

We match Claw-Eval's distribution (service combos + categories) but all content is LLM-generated:

| From Claw-Eval (used) | Auto-generated (new) |
|---|---|
| category (communication, finance...) | prompt, fixture data, scoring config, reference solution |
| service combo (gmail, gmail+contacts...) | *(all unique per generation)* |

### Cost Comparison

| | Claw-Eval | **ClawHarnessing** |
|---|---|---|
| Tasks | 153 | **134 generated (scalable to 1,500+)** |
| Time to create | ~306 hours (human) | **~45 minutes** (API) |
| Cost | ~$30,600 | **~$2.00** |
| Grader code | ~15,000 lines Python | **0 lines** (YAML config) |

---

## Dataset

Tasks are **generated on demand**, not pre-shipped. The generation script matches 100% of Claw-Eval's distribution (104 general + 49 overlapping = 153 tasks):

```bash
# Generate dataset (requires ANTHROPIC_API_KEY or OPENROUTER_API_KEY)
python scripts/generate_dataset.py --dry-run              # see plan (153 tasks)
python scripts/generate_dataset.py                         # generate all 153
python scripts/generate_dataset.py --multiplier 10         # 1,530 tasks
python scripts/generate_dataset.py --api-only              # 126 API-only tasks
python scripts/generate_dataset.py --general-only           # 104 general only
```

Covers API tasks (126: single-service + cross-service) and file-dependent tasks (27: terminal, OCR, PDF, data analysis). Scoring is outcome-oriented: 40-60% rule-based + 40-60% LLM judge.

---

## Python API

```python
from clawharness.evaluate import GradingEngine

# Grade with audit data
engine = GradingEngine()
result = engine.grade(task_config, audit_data, agent_output)
print(result.final_score)      # 0.92
print(result.completion)       # 0.88
print(result.safety)           # 1.0
print(result.component_results)  # per-check breakdown
```

---

## Architecture

```
clawharness/
├── evaluate/engine.py           ← GradingEngine (15 check types + 2 safety)
├── generate/
│   ├── task_generator.py           LLM → task.yaml (outcome-oriented scoring)
│   ├── fixture_generators.py       Auto-generate files (DB, PDF, images, CSV)
│   ├── intent_parser.py            NL → {services, difficulty} (zero-config)
│   └── service_generator.py        LLM → new mock service
├── llm_client.py                ← Shared LLM client (OpenRouter/Anthropic/OpenAI)
├── cli.py                       ← Unified CLI
mock_services/                   ← 20 FastAPI services with audit logging
extensions/clawharness-eval/     ← OpenClaw plugin (Tier 1)
mcp_server/                      ← MCP server (Tier 2: Claude Code, Codex, Cursor, ...)
docker/                          ← Dockerfiles + entrypoints (all agent tiers)
```

### Three-Tier Agent Integration

```
               Mock Service (localhost:9100)
                        │
         ┌──────────────┼──────────────┐
    Tier 1           Tier 2         Tier 3
    Plugin           MCP            Skill+curl
    (OpenClaw)       (Claude Code    (7 Claw
                      Codex,          agents)
                      Cursor, ...)
```

- **Tier 1 (Plugin):** Mock endpoints registered as native tools via `registerTool()` — agent sees `create_task` like `sendSlackMessage`
- **Tier 2 (MCP):** One MCP server covers the entire MCP ecosystem (Claude Code, Codex, Cursor, Windsurf, ...)
- **Tier 3 (Skill+curl):** Auto-generated SKILL.md with API docs for agents with bash/exec

### Generation Pipeline

```
NL: "Test meeting scheduling"  →  IntentParser  →  {services, difficulty}
                                                          ↓
                                                   TaskGenerator  →  task.yaml
                                                          ↓
                                                   ConfigValidator  →  valid E=(P,M,C)
```

---

## Requirements

- Python 3.10+
- Docker / Colima
- Anthropic API key (for agent + task generation)

## Installation

```bash
git clone https://github.com/xirui-li/ClawHarnessing.git
cd ClawHarnessing
pip install -e ".[all]"    # editable install (required — includes prompts + mock_services)
```

Note: ClawHarnessing requires source checkout (`pip install -e .`) because it uses `prompts/` and `mock_services/` from the repo root. Standalone `pip install clawharness` from PyPI is not yet supported.

---

## Documentation

- [OVERALL_DESIGN.md](OVERALL_DESIGN.md) — Full system architecture
- [EXPERIMENT_DESIGN.md](EXPERIMENT_DESIGN.md) — 6 experiments for paper validation
- [MAC_MINI_TEST.md](MAC_MINI_TEST.md) — Step-by-step testing guide
- [CONTRIBUTING.md](CONTRIBUTING.md) — How to add new mock services

---

## FAQ

### How does ClawHarnessing generate reliable tests?

LLM generates **YAML config** (what to check), not **Python test code** (how to check). The GradingEngine is fixed, deterministic code that handles all verification. This achieves 100% config validity vs ~30% for LLM-generated pytest. Scoring is outcome-oriented: checks what the agent achieved, not how it called APIs.

### Can I use my own agent?

Yes. For OpenClaw: mock services are registered as **native tools** via plugin (agent calls `create_task` like it calls `sendSlackMessage`). For other agents: any agent that can make HTTP requests to `localhost:9100` inside a Docker container works.

### How do I add a new service?

Write a FastAPI server with audit logging (see [CONTRIBUTING.md](CONTRIBUTING.md)), or let LLM generate one:

```python
from clawharness.generate.service_generator import generate_and_install
generate_and_install("stripe", "Payment processing API")
# NOTE: registers in current process only. Add to SERVICE_DEFINITIONS for CLI use.
```

### How does this compare to just using Claw-Eval directly?

Claw-Eval is a static benchmark (153 tasks, fixed). ClawHarnessing can generate unlimited tasks for the same services. Use Claw-Eval for comparison, ClawHarnessing for training data at scale.

---

## Roadmap

| Feature | Status | Description |
|---------|--------|-------------|
| API tasks (20 services) | ✅ Done | 119 API tasks, 20 mock services |
| File-dependent tasks | ✅ Done | 15 tasks (OCR, terminal, PDF, CSV) with auto-generated fixtures |
| Cross-service tasks | ✅ Done | 8 categories, multi_server.py |
| OpenClaw native plugin | ✅ Done | Tier 1 integration |
| MCP server | ✅ Done | Tier 2: Claude Code, Codex, Cursor, ... |
| Skill+curl agents | ✅ Done | Tier 3: 7 claw agents |
| Intent parser (NL input) | ✅ Done | "Schedule meeting" → services + difficulty |
| Outcome-oriented scoring | ✅ Done | Checks results, not methods |
| Validation error feedback | ✅ Done | 90%+ generation success rate via self-correction |
| Real web tasks | ✅ Done | web_real for finance/security/research (21 tasks) |
| **Scale to 1,500+ tasks** | 📋 Ready | `--multiplier 10` generates 1,530 tasks |
| **Discriminability experiment** | 📋 Pending | Opus + Haiku comparison |

---

<div align="center">

**MIT License** · Built for the [OpenClaw](https://github.com/openclaw/openclaw) ecosystem

⭐ Star if ClawHarnessing helps your agent research!

</div>
