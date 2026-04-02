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

> **ClawHarnessing** is an open-source harnessing toolkit for claw-like agents (OpenClaw, NanoClaw, etc.). It supports both **task generation** (auto-generate training environments from natural language) and **evaluation** (reliable verification with 20 mock API services, audit logging, and 0.0-1.0 continuous scoring). Pre-generated tasks across 20 services (100% Claw-Eval coverage). MIT licensed.

---

## Why ClawHarnessing exists

Every agent benchmark was built by **humans writing tasks one by one** — 84 tasks (SkillsBench), 139 tasks (Claw-Eval), each taking 2+ hours to create with custom verification code.

**That doesn't scale.**

ClawHarnessing solves this:

- **No hand-written tests** — LLM generates YAML configs, a fixed engine handles verification
- **No custom grader code** — 14 deterministic check types, reusable across all tasks
- **No fragile pytest** — audit-log based verification (what the agent *did*, not what it *said*)
- **No binary pass/fail** — 0.0-1.0 continuous scoring with safety gates
- **No per-task Docker builds** — one base image, mount any task.yaml via volume

---

## How it compares

|                     | Claw-Eval       | SWE-bench          | SkillsBench      | **ClawHarnessing**          |
| ------------------- | --------------- | ------------------ | ---------------- | ------------------------ |
| **Tasks**           | 139             | 2,294              | 84               | **104 (matched, scalable to ∞)**  |
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

# Set API key
export ANTHROPIC_API_KEY=sk-ant-...

# Build Docker image (once)
docker build -f docker/Dockerfile -t clawharness:base .

# Run evaluation (one command)
clawharness eval todo-001
```

Done. Agent runs inside Docker, mock service records audit, grading engine scores automatically.

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
│  GradingEngine (14 check types)                │
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
clawharness services                                               # list 13 services
clawharness categories                                             # list 8 categories

# Docker
docker run --rm \
  -e ANTHROPIC_API_KEY=$KEY \
  -v ./dataset/todo/todo-001.yaml:/opt/clawharness/task.yaml:ro \
  clawharness:base
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

```python
from clawharness.agents import list_agents, get_agent

agent = get_agent("openclaw")
agent.setup(workspace="/workspace", model="claude-sonnet-4-6", api_key="sk-ant-...")
result = agent.run(prompt="Create a task...", tools=[...])
print(result.output, result.wall_time_s)
```

Compatible with [MetaClaw](https://github.com/aiming-lab/MetaClaw)'s `claw_type` list.

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

### Verification Check Types (14)

| Type | Source | Example |
|---|---|---|
| `audit_action_exists` | Audit log | Agent called `create_task` |
| `audit_field_equals` | Audit log | `priority == "high"` |
| `audit_field_contains` | Audit log | `body` contains "urgent" |
| `audit_count_gte` | Audit log | Called `mark_read` ≥ 4 times |
| `audit_sequence` | Audit log | `create_draft` before `mark_read` |
| `keywords_present` | Agent output | Output mentions "replied" |
| `keywords_absent` | Agent output | No "password" in output |
| `llm_judge` | Agent output + audit | LLM scores quality 0-1 (with audit context) |
| `file_exists` | Filesystem | `/workspace/report.txt` created |
| `exit_code` | Shell | `python3 main.py` returns 0 |
| `pytest_pass` | Test file | All test functions pass |
| + 3 more | | |

---

## Key Results: Auto-Generated vs Human-Written Tasks

104 auto-generated tasks compared against 104 human-written tasks from [Claw-Eval](https://github.com/claw-eval/Claw-Eval):

| Metric | Auto (Ours) | Human (Claw-Eval) | Result |
|--------|-------------|-------------------|--------|
| **Validity** | 100% | 100% | ✅ Equal |
| **Clarity** (1-5) | 3.54 | 3.38 | ✅ Ours higher |
| **Coherence** J(P,M,C) [0,1] | **0.64** | 0.36 | ✅ Ours much higher |
| **Diversity** | 0.884 | **0.970** | Human more diverse |
| **Scoring Balance** (rule/LLM) | 60%/40% | ~55%/~45% | ✅ Comparable |
| **Safety Coverage** | 100% | 100% | ✅ Equal |
| **Discriminability** (Opus, 81 tasks) | **0.636 mean** | — | ✅ Solvable + challenging |

**5/6 task-level metrics: auto >= human.** Opus scores 0.636 mean on supported tasks (47% score >0.7). Auto tasks are more coherent (structured YAML) and equally clear, while human tasks are more diverse (bilingual).

### Cost Comparison

| | Claw-Eval | **ClawHarnessing** |
|---|---|---|
| Tasks | 104 | 104 |
| Time to create | ~208 hours (human) | **~50 minutes** (API) |
| Cost | ~$20,800 | **~$1.50** |
| Grader code | ~15,000 lines Python | **0 lines** (YAML config) |

---

## Dataset

104 tasks across 32 categories, matched 1-to-1 with Claw-Eval's 104 general tasks:

```bash
find dataset/ -name "*.yaml" | wc -l    # 104 tasks
ls dataset/                              # 32 category directories
```

Covers single-service (todo, gmail, ...) and cross-service (workflow, ops, procurement, ...) tasks. Scoring is outcome-oriented: 60% rule-based + 40% LLM judge.

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
├── evaluate/engine.py        ← GradingEngine (14 check types)
├── generate/
│   ├── task_generator.py        LLM → task.yaml (outcome-oriented scoring)
│   ├── intent_parser.py         NL → {services, difficulty} (zero-config)
│   └── service_generator.py     LLM → new mock service
├── agents/                   ← 8 agent adapters
├── mock_services/            ← 20 FastAPI services
├── extensions/clawharness-eval/  ← OpenClaw plugin (Tier 1)
├── mcp_server/               ← MCP server (Tier 2: Claude Code, Codex, Cursor, ...)
├── docker/                   ← 9 Dockerfiles (OpenClaw + Claude Code + 7 claw agents)
└── cli.py                    ← Unified CLI
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
```

### How does this compare to just using Claw-Eval directly?

Claw-Eval is a static benchmark (139 tasks, fixed). ClawHarnessing can generate unlimited tasks for the same services. Use Claw-Eval for comparison, ClawHarnessing for training data at scale.

---

## Roadmap

| Feature | Status | Description |
|---------|--------|-------------|
| Text/API tasks | ✅ Done | 20 mock services, 81 supported tasks |
| Cross-service tasks | ✅ Done | 8 categories, multi_server.py |
| OpenClaw native plugin | ✅ Done | Tier 1 integration |
| MCP server | ✅ Done | Tier 2: Claude Code, Codex, Cursor, ... |
| Skill+curl agents | ✅ Done | Tier 3: 7 claw agents |
| Intent parser (NL input) | ✅ Done | "Schedule meeting" → services + difficulty |
| Outcome-oriented scoring | ✅ Done | Checks results, not methods |
| Defensive fixture loading | ✅ Done | Handles any LLM-generated schema |
| **Multimodal tasks** | 🔧 Planned | Image (OCR/caption), PDF, video processing |
| **Real web access** | 🔧 Planned | web_real for finance/security research tasks |
| **Haiku discriminability** | 🔧 Running | Weak agent comparison for Disc(E) |
| **Scale to 1,000+ tasks** | 📋 Planned | Scalability experiment |

### Multimodal Support (Planned)

Currently, 23 tasks (OCR + terminal) score low (~0.25) because the agent can't process images or files through the JSON-based tool interface. Planned approach:

- **Image tasks:** Encode images as base64 in tool responses, or use agent's native vision capabilities
- **File tasks:** Mount files to workspace + use agent's built-in `read`/`exec` tools alongside mock service tools
- **PDF/CSV tasks:** Combine `documents` mock service with file fixtures

---

<div align="center">

**MIT License** · Built for the [OpenClaw](https://github.com/openclaw/openclaw) ecosystem

⭐ Star if ClawHarnessing helps your agent research!

</div>
