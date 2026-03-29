<div align="center">

<h1>🦞 ClawHarnessing</h1>

<p>The evaluation framework built for autonomous AI agents</p>

<p>Benchmarks are human-written. Benchmarks don't scale.<br>
Agents need thousands of diverse evaluation tasks, not 84.<br><br>
<strong>ClawHarnessing automatically generates evaluation environments with reliable verification.</strong></p>

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

> **ClawHarnessing** is an open-source framework that automatically generates evaluation tasks for AI agents (OpenClaw, Claude Code, etc.) with reliable, deterministic verification. It produces YAML task configs (not test code), uses 19 mock API services with audit logging, and scores agents on a 0.0-1.0 scale across completion, robustness, and safety dimensions. 129 pre-generated tasks across 13 services. MIT licensed.

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
| **Tasks**           | 139             | 2,294              | 84               | **129 (scalable to ∞)**  |
| **Source**          | Human-written   | GitHub PRs         | Human-written    | **Auto-generated**       |
| **Verification**   | Per-task grader  | Unit tests         | pytest           | **Universal engine + YAML** |
| **Scoring**        | 0-1 weighted    | Binary             | Binary           | **0-1 weighted (3 dims)** |
| **Safety**         | ✓               | ✗                  | ✗                | **✓ (multiplicative gate)** |
| **Robustness**     | ✓               | ✗                  | ✗                | **✓ (error injection)** |
| **Cost per task**  | ~2 hours human  | N/A                | ~2 hours         | **~30 seconds API call** |
| **Mock services**  | 19              | N/A                | N/A              | **19 (same as Claw-Eval)** |

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
clawharness eval todo-001 --model claude-3-haiku  # specific model
clawharness eval-all --service todo              # all tasks for a service
clawharness eval-all                              # all 129 tasks

# Generate
clawharness generate --service gmail --count 10   # new tasks
clawharness services                              # list 13 services

# Docker (alternative)
docker run --rm \
  -e ANTHROPIC_API_KEY=$KEY \
  -v ./dataset/todo/todo-001.yaml:/opt/clawharness/task.yaml:ro \
  -v ~/claw-results/todo-001:/logs \
  clawharness:base
```

---

## Available Services

19 mock API services with audit logging and error injection:

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
| `llm_judge` | Agent output | GPT-5-mini scores quality 0-1 |
| `file_exists` | Filesystem | `/workspace/report.txt` created |
| `exit_code` | Shell | `python3 main.py` returns 0 |
| `pytest_pass` | Test file | All test functions pass |
| + 3 more | | |

---

## Key Results

| Metric | Value |
|---|---|
| Config generation success rate | **99%** (129/130) |
| Average scoring components per task | 8.4 |
| Good agent score | **0.92** |
| Bad agent score | 0.24 |
| Dangerous agent score (safety violation) | **0.00** |
| LLM Judge accuracy (good vs bad) | 1.0 vs 0.0 |
| Grading correctly ranks agent quality | ✅ Good > Bad > Dangerous |

---

## Dataset

129 pre-generated tasks across 13 services (3 easy + 4 medium + 3 hard each):

```bash
ls dataset/           # 13 service directories
wc -l dataset/train.jsonl  # 129 tasks
```

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
├── evaluate/              ← Evaluation (core)
│   ├── engine.py             GradingEngine (14 check types)
│   ├── runner.py             Docker runner
│   └── agent_loop.py         Lightweight ReAct agent
├── generate/              ← Task generation
│   ├── task_generator.py     LLM → task.yaml
│   └── service_generator.py  LLM → mock service
├── mock_services/         ← 19 FastAPI services (from Claw-Eval)
└── cli.py                 ← Unified CLI
```

---

## Requirements

- Python 3.10+
- Docker / Colima
- Anthropic API key (for agent + task generation)

---

## Documentation

- [OVERALL_DESIGN.md](OVERALL_DESIGN.md) — Full system architecture
- [EXPERIMENT_DESIGN.md](EXPERIMENT_DESIGN.md) — 6 experiments for paper validation
- [MAC_MINI_TEST.md](MAC_MINI_TEST.md) — Step-by-step testing guide
- [CONTRIBUTING.md](CONTRIBUTING.md) — How to add new mock services

---

## FAQ

### How does ClawHarnessing generate reliable tests?

LLM generates **YAML config** (what to check), not **Python test code** (how to check). The GradingEngine is fixed, deterministic code that handles all verification. This achieves 99% config validity vs ~30% for LLM-generated pytest.

### Can I use my own agent?

Yes. Any agent that can make HTTP requests to `localhost:9100` inside a Docker container works. OpenClaw, Claude Code, custom agents — all supported.

### How do I add a new service?

Write a FastAPI server with audit logging (see [CONTRIBUTING.md](CONTRIBUTING.md)), or let LLM generate one:

```python
from clawharness.generate.service_generator import generate_and_install
generate_and_install("stripe", "Payment processing API")
```

### How does this compare to just using Claw-Eval directly?

Claw-Eval is a static benchmark (139 tasks, fixed). ClawHarnessing can generate unlimited tasks for the same services. Use Claw-Eval for comparison, ClawHarnessing for training data at scale.

---

<div align="center">

**MIT License** · Built for the [OpenClaw](https://github.com/openclaw/openclaw) ecosystem

⭐ Star if ClawHarnessing helps your agent research!

</div>
