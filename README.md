<div align="center">

<h1>🦞 ClawEnvKit</h1>

<p>Open-source environment generation toolkit for claw-like agents</p>

<p>Task generation + evaluation, all in one.<br>
Auto-generate training environments. Evaluate with reliable verification.<br><br>
<strong>Supports 10 evaluation harnesses across 3 tiers: native plugin (OpenClaw), MCP (Claude Code, NanoClaw, IronClaw, PicoClaw, ZeroClaw), SKILL.md+shell (CoPaw, NemoClaw, Hermes) + Agent Loop.</strong></p>

<br>

<img src="https://img.shields.io/badge/Quality-Human--Level_Scoring-blue?style=for-the-badge" alt="Quality">&nbsp;
<img src="https://img.shields.io/badge/Scalability-1000%2B_Tasks-black?style=for-the-badge" alt="Scalability">&nbsp;
<img src="https://img.shields.io/badge/Adaptability-On--Demand_Curation-purple?style=for-the-badge" alt="Adaptability">&nbsp;
<img src="https://img.shields.io/badge/Open_Source-MIT-green?style=for-the-badge" alt="Open source">

[![PyPI version](https://img.shields.io/badge/pypi-v1.0.0-blue?style=flat-square)](https://pypi.org/project/clawenvkit/)
[![GitHub stars](https://img.shields.io/github/stars/xirui-li/ClawEnvKit?style=flat-square)](https://github.com/xirui-li/ClawEnvKit)
[![Python](https://img.shields.io/badge/Python-3.10+-3776ab?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)
[![Auto-ClawEval](https://img.shields.io/badge/%F0%9F%A4%97-Auto--ClawEval-orange?style=flat-square)](https://huggingface.co/datasets/xirui-li/Auto-ClawEval)
[![Auto-ClawEval-mini](https://img.shields.io/badge/%F0%9F%A4%97-Auto--ClawEval--mini-orange?style=flat-square)](https://huggingface.co/datasets/xirui-li/Auto-ClawEval-mini)

</div>

> **ClawEnvKit** is an open-source environment generation toolkit for claw-like agents (OpenClaw, NanoClaw, etc.). It supports both **task generation** (auto-generate training environments from natural language) and **evaluation** (reliable verification with 20 mock API services, audit logging, and 0.0-1.0 continuous scoring). MIT licensed.

---

## Why ClawEnvKit exists

Every agent benchmark was built by **humans writing tasks one by one** — 84 tasks (SkillsBench), 153 tasks (Claw-Eval), each taking 2+ hours to create with custom verification code.

**That doesn't scale.**

ClawEnvKit solves this:

- **No hand-written tests** — LLM generates YAML configs, a fixed engine handles verification
- **No custom grader code** — 15 structured check types (14 rule-based + LLM judge) + 2 safety checks, reusable across all tasks
- **No fragile pytest** — audit-log based verification (what the agent *did*, not what it *said*)
- **No binary pass/fail** — 0.0-1.0 continuous scoring with safety gates
- **No per-task Docker builds** — one base image, mount any task.yaml via volume

---

## Requirements

- Python 3.10+
- Docker / Colima (for harness evaluation)
- API key: [OpenRouter](https://openrouter.ai/) (recommended) or Anthropic / OpenAI directly

## Installation

```bash
git clone https://github.com/xirui-li/ClawEnvKit.git
cd ClawEnvKit
pip install -e ".[all]"

# Set API key (OpenRouter recommended — unified access to all providers)
export OPENROUTER_API_KEY=sk-or-v1-...
# Or use provider keys directly:
# export ANTHROPIC_API_KEY=sk-ant-...
# export OPENAI_API_KEY=sk-...
```

> **Note:** ClawEnvKit requires source checkout (`pip install -e .`) because it uses `prompts/` and `mock_services/` from the repo root.

---

## Quick Start

### 1. Generate On Demand

Create evaluation environments from natural language — each call produces a complete `task.yaml` with prompt, fixtures, tools, scoring rubric, and safety checks:

```
"Test meeting scheduling with attendee notifications"
        ↓
    Parser.parse_intent()          NL → {services, atoms, difficulty}
        ↓
    Generator.generate_task_prompt()  →  LLM generates task.yaml (99%+ valid)
        ↓                                  prompt + fixtures +
    Validator.validate_task_config()       scoring_components +
    Validator.verify_coverage()            safety_checks
        ↓
    task.yaml ready to evaluate
```

```bash
# Generate from natural language
clawenvkit generate --request "Test if agent can triage emails and flag urgent ones"

# Generate by service
clawenvkit generate --services todo --count 10
clawenvkit generate --services calendar,contacts,gmail --count 5

# Scale up
python scripts/generate_dataset.py --multiplier 10    # 1,000+ tasks
```

### 2. Use Auto-ClawEval

Or use our pre-generated benchmark dataset directly:

```bash
# Download from HuggingFace
huggingface-cli download xirui-li/Auto-ClawEval --repo-type dataset --local-dir Auto-ClawEval
huggingface-cli download xirui-li/Auto-ClawEval-mini --repo-type dataset --local-dir Auto-ClawEval-mini
```

#### Option A: Docker Harness Evaluation

Run agents inside Docker with mock services, audit logging, and trajectory capture:

```bash
# Build Docker image (once per harness)
docker build -f docker/Dockerfile.claudecode -t clawenvkit:claudecode .

# Run a single harness on the mini benchmark (104 tasks)
bash run_harnesses.sh --harness claudecode --dataset Auto-ClawEval-mini --resume

# Run all 8 harnesses
bash run_harnesses.sh --dataset Auto-ClawEval-mini --resume
```

Available harnesses:

| Image | Agent | Integration |
|---|---|---|
| `clawenvkit:openclaw` | OpenClaw | Tier 1: native plugin |
| `clawenvkit:claudecode` | Claude Code | Tier 2: MCP server |
| `clawenvkit:nanoclaw` | NanoClaw | Tier 2: MCP server |
| `clawenvkit:picoclaw` | PicoClaw | Tier 2: MCP server |
| `clawenvkit:zeroclaw` | ZeroClaw | Tier 2: MCP server |
| `clawenvkit:copaw` | CoPaw | Tier 3: SKILL.md + shell |
| `clawenvkit:nemoclaw` | NemoClaw | Tier 3: SKILL.md + shell |
| `clawenvkit:hermes` | Hermes | Tier 3: SKILL.md + shell |

#### Option B: Agent Loop Evaluation (No Docker)

Lightweight function-calling loop — runs mock services locally, no Docker needed:

```bash
# Single model
bash run_loop.sh --dataset Auto-ClawEval-mini --model anthropic/claude-haiku-4-5-20251001 --resume

# All models
bash run_loop.sh --dataset Auto-ClawEval-mini --resume
```

For a more structured setup guide, see [docs/getting-started.md](docs/getting-started.md).

---

## Commands

```bash
# Evaluate
clawenvkit eval todo-001                        # single task
clawenvkit eval-all --service todo              # all tasks for a service

# Generate (unified --services interface)
clawenvkit generate --services todo --count 10                    # single-service
clawenvkit generate --services calendar,contacts,gmail --count 5  # cross-service
clawenvkit generate --category workflow --count 5                 # category shortcut
clawenvkit services                                               # list available services
clawenvkit service create --request "Stripe payments"             # create new mock service
clawenvkit categories                                             # list 8 categories
clawenvkit compat                                                 # compatibility gate

# Docker (direct)
docker run --rm \
  -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY \
  -v ./dataset/todo/todo-001.yaml:/opt/clawenvkit/task.yaml:ro \
  clawenvkit:claudecode    # most turnkey path
```

---

## Available Services

ClawEnvKit ships with 20 mock services spanning email, scheduling, CRM, finance, inventory, OCR, PDF, and live-web tasks. New services can be auto-generated from natural language (`clawenvkit service create --request "Slack messaging"`). Every service supports audit logging, reset endpoints, and optional error injection, and services can be combined into cross-service benchmarks.

See [Mock Services](docs/services.md) for the full catalog, API conventions, multimodal/file-backed services, and category-level service combinations.

If you want to add a new domain, see [Contributing: Adding Mock Services](docs/contributing/services.md).

---

## Supported Agents

ClawEnvKit supports three integration tiers: native plugin for OpenClaw, MCP servers for Claude Code, NanoClaw, IronClaw, PicoClaw, and ZeroClaw, and SKILL.md+shell for CoPaw, NemoClaw, and Hermes. All 10 harnesses use their native agent loops and run through the same Docker-based task runtime (plus a no-Docker Agent Loop baseline).

See [Supported Agents](docs/agents/index.md) for the integration tiers, supported runtimes, and agent-specific setup notes.

### Supported Backbone Models

ClawEnvKit works with provider-native Anthropic and OpenAI setups as well as tool-calling models routed through OpenRouter. The repo includes tested model IDs for the Claw-Eval leaderboard set, but the runtime is not limited to those examples.

See [Backbone Models](docs/models.md) for tested model IDs and routing patterns, or browse the broader [OpenRouter tool-calling collection](https://openrouter.ai/collections/tool-calling-models).

---

## Scoring

Scoring combines weighted task completion, robustness under injected failures, and safety as a hard gate. Most tasks mix audit-based checks, output-based checks, and LLM-judge components so that both action correctness and response quality matter.

```
final_score = safety × (0.80 × completion + 0.20 × robustness)
```

See [Scoring and Grading](docs/scoring.md) for the three score dimensions, all supported check types, and the full `task.yaml` scoring format.

---

## Dataset

Generate evaluation datasets on demand with the generation script:

```bash
# Generate dataset (requires ANTHROPIC_API_KEY or OPENROUTER_API_KEY)
python scripts/generate_dataset.py --dry-run              # see plan
python scripts/generate_dataset.py                         # generate base set
python scripts/generate_dataset.py --multiplier 10         # 1,000+ tasks
python scripts/generate_dataset.py --general-only           # general tasks only
```

The generated dataset is also available on [HuggingFace](https://huggingface.co/datasets/xirui-li/Auto-ClawEval). Tasks span 20 mock services, 24 categories, and include both API-based and file-dependent tasks (terminal, OCR, office QA, data analysis). Scoring is outcome-oriented: 40-60% rule-based + 40-60% LLM judge.

---

## Python API

Three module classes provide the programmatic interface:

```python
from clawenvkit.generate import Parser, Generator, Validator

# 1. Parse natural language → structured spec
parser = Parser()
intent = parser.parse_intent("Test if agent can schedule a meeting and notify attendees")
# → {services: ["calendar", "contacts", "gmail"], atoms: [...], difficulty: "medium"}

# 2. Generate task config
gen = Generator()
services = gen.resolve_services(intent["services"])
prompt = gen.generate_task_prompt(services=services, difficulty=intent["difficulty"])
config = gen.ingest_task_config(llm_response, services=services, atoms=intent["atoms"])

# 3. Validate
val = Validator()
issues = val.validate_task_config(config, services=services)  # structural checks
gaps = val.verify_coverage(config, intent["atoms"])           # semantic coverage

# 4. Grade agent output (separate class — runtime evaluation)
from clawenvkit.evaluate import GradingEngine
engine = GradingEngine()
result = engine.grade(task_config, audit_data, agent_output)
print(result.final_score)      # 0.92
print(result.completion)       # 0.88
print(result.safety)           # 1.0
```

---

## Architecture

```
clawenvkit/
├── evaluate/engine.py           ← GradingEngine (15 check types + 2 safety)
├── generate/
│   ├── task_generator.py           LLM → task.yaml (outcome-oriented scoring)
│   ├── fixture_generators.py       Auto-generate files (DB, PDF, images, CSV)
│   ├── intent_parser.py            NL → {services, difficulty} (zero-config)
│   └── service_generator.py        LLM → new mock service
├── llm_client.py                ← Shared LLM client (OpenRouter/Anthropic/OpenAI)
├── cli.py                       ← Unified CLI
mock_services/                   ← 20 FastAPI services with audit logging
extensions/clawenvkit-eval/     ← OpenClaw plugin (Tier 1)
mcp_server/                      ← MCP server (Tier 2: Claude Code, Codex, Cursor, ...)
docker/                          ← Dockerfiles + entrypoints (all agent tiers)
```

### Three-Tier Agent Integration

```
               Mock Service (localhost:9100)
                        │
         ┌──────────────┼──────────────┐
    Tier 1           Tier 2         Tier 3
    Plugin           MCP            SKILL.md+shell
    (OpenClaw)       (Claude Code    (CoPaw
                      NanoClaw        NemoClaw
                      IronClaw        Hermes
                      PicoClaw        Agent Loop)
                      ZeroClaw)
```

- **Tier 1 (Plugin):** Mock endpoints registered as native tools via `registerTool()` — agent sees `create_task` like `sendSlackMessage`
- **Tier 2 (MCP):** Python/Node.js MCP server over stdio — tools appear as native agent tools
- **Tier 3 (SKILL.md+shell):** Auto-generated API docs appended to prompt, agent uses shell/curl

### Generation Pipeline

```
NL: "Test meeting scheduling"  →  Parser.parse_intent()  →  {services, atoms, difficulty}
                                                                    ↓
                                                             Generator.ingest_task_config()  →  task.yaml
                                                                    ↓
                                                             Validator.validate_task_config()  →  structural checks
                                                             Validator.verify_coverage()       →  semantic coverage
```

---

## Documentation

**Start here:**
- [docs/getting-started.md](docs/getting-started.md) — Onboarding and first evaluation
- [docs/agents/index.md](docs/agents/index.md) — All 10 evaluation harnesses and integration tiers
- [docs/agents/others.md](docs/agents/others.md) — Per-harness config, invocation, and setup
- [docs/task-spec.md](docs/task-spec.md) — `task.yaml` schema and validation rules
- [docs/scoring.md](docs/scoring.md) — Scoring formula, 15 check types, Pass^3
- [docs/api.md](docs/api.md) — Python API reference
- [docs/cli.md](docs/cli.md) — CLI reference
- [docs/models.md](docs/models.md) — Tested model IDs and routing patterns
- [docs/compatibility-gate.md](docs/compatibility-gate.md) — Static compatibility checks
- [CONTRIBUTING.md](CONTRIBUTING.md) — How to add new mock services

---

## FAQ

### How does ClawEnvKit generate reliable tests?

LLM generates **YAML config** (what to check), not **Python test code** (how to check). The GradingEngine is fixed code that handles all verification: 14 rule-based checks are fully deterministic, while `llm_judge` checks (capped at 55% weight per task) make live LLM API calls for semantic quality evaluation. This achieves 100% config validity vs ~30% for LLM-generated pytest. Scoring is outcome-oriented: checks what the agent achieved, not how it called APIs.

### Can I use my own agent?

Yes. For OpenClaw: mock services are registered as **native tools** via plugin (agent calls `create_task` like it calls `sendSlackMessage`). For other agents: any agent that can make HTTP requests to `localhost:9100` inside a Docker container works.

### How do I add a new service?

Write a FastAPI server with audit logging (see [CONTRIBUTING.md](CONTRIBUTING.md)), or auto-generate one:

```bash
clawenvkit service create --request "Stripe payment processing"
# → LLM plans API structure → you review → generates server.py → validates → registers
# → Then: clawenvkit generate --services stripe --count 5
```

### How does this compare to just using Claw-Eval directly?

Claw-Eval is a static benchmark (153 tasks, fixed). ClawEnvKit can generate unlimited tasks for the same services. Use Claw-Eval for comparison, ClawEnvKit for training data at scale.

---

## Roadmap

| Feature | Status | Description |
|---------|--------|-------------|
| API tasks (20 services) | ✅ Done | 20 mock services, single + cross-service |
| File-dependent tasks | ✅ Done | OCR, terminal, PDF, CSV, office QA, rewriting with auto-generated fixtures |
| Cross-service tasks | ✅ Done | 8 categories, multi_server.py |
| OpenClaw native plugin | ✅ Done | Tier 1 integration |
| MCP server | ✅ Done | Tier 2: Claude Code, NanoClaw, IronClaw, PicoClaw, ZeroClaw |
| SKILL.md+shell agents | ✅ Done | Tier 3: CoPaw, NemoClaw, Hermes |
| Intent parser (NL input) | ✅ Done | "Schedule meeting" → services + difficulty |
| Outcome-oriented scoring | ✅ Done | Checks results, not methods |
| Scale to 1,000+ tasks | ✅ Done | `--multiplier 10` with 99%+ config validity |

### Next Up

- [ ] Support multilingual task generation and evaluation
- [ ] Integrate generated tasks with training pipelines

---

<div align="center">

**MIT License** · Built for the [OpenClaw](https://github.com/openclaw/openclaw) ecosystem

⭐ Star if ClawEnvKit helps your agent research!

</div>
