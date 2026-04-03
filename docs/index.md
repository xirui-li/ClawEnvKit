# ClawHarnessing

**Open-source harnessing toolkit for claw-like agents — auto-generate training environments, evaluate with reliable verification.**

Supports 8 claw-like agents: OpenClaw, NanoClaw, IronClaw, CoPaw, PicoClaw, ZeroClaw, NemoClaw, Hermes.

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

## How it compares

|                     | Claw-Eval       | SWE-bench          | SkillsBench      | **ClawHarnessing**          |
| ------------------- | --------------- | ------------------ | ---------------- | ------------------------ |
| **Tasks**           | 139             | 2,294              | 84               | **generates 153+ (100% matched, scalable to ∞)**  |
| **Source**          | Human-written   | GitHub PRs         | Human-written    | **Auto-generated**       |
| **Verification**   | Per-task grader  | Unit tests         | pytest           | **Universal engine + YAML** |
| **Scoring**        | 0-1 weighted    | Binary             | Binary           | **0-1 weighted (3 dims)** |
| **Safety**         | Yes             | No                 | No               | **Yes (multiplicative gate)** |
| **Robustness**     | Yes             | No                 | No               | **Yes (error injection)** |
| **Cost per task**  | ~2 hours human  | N/A                | ~2 hours         | **~30 seconds API call** |

## Key Results

| Metric | Value |
|--------|-------|
| Config generation success rate | **99%+** |
| Average scoring components per task | 8.4 |
| Good agent score | **0.92** |
| Bad agent score | 0.24 |
| Dangerous agent score (safety violation) | **0.00** |
| Grading correctly ranks agent quality | Good > Bad > Dangerous |

## Quick Start

```bash
pip install -e .
export ANTHROPIC_API_KEY=sk-ant-...
docker build -f docker/Dockerfile -t clawharness:base .
clawharness eval todo-001
```

See [Getting Started](getting-started.md) for the full guide.
