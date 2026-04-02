# Experiments

## Research Question

Can automatically generated task configurations (YAML + fixed GradingEngine) evaluate AI agents as reliably as human-written evaluation tasks?

## Core Claim

Auto-generated task configs achieve equivalent agent evaluation quality to human-written tasks at **240x lower cost** (30s API call vs 2hr human labor per task).

---

## Experiment 1: Multi-Agent Discrimination

**Goal:** Auto-generated tasks can distinguish agents of different capability levels.

**Setup:**

- Tasks: auto-generated dataset (~80 supported tasks, excluding OCR/terminal)
- Agents: 2 models — Opus 4.6 (strong) + Haiku 4.5 (weak)
- 1 run per task per agent
- Docker + OpenClaw with native tool plugin

**Report:** Per-task Disc(E) = Opus - Haiku, mean Disc(E), score distributions.

---

## Experiment 2: Human Baseline Comparison (Task-Level Only)

**Goal:** Auto-generated tasks have comparable quality to human-written tasks.

**Setup:**

- Human tasks: Claw-Eval 104 general tasks
- Auto tasks: Our ~80 supported tasks
- Comparison: task-level metrics only (no agent runs on both — different grading)
- Compare overlapping services

**Success criteria:** KS test p > 0.05 (no significant distribution difference) AND consistent difficulty gradient (easy > medium > hard).

---

## Experiment 3: Verification Accuracy

**Goal:** GradingEngine scores match human judgment.

**Setup:**

- 50 random (task, agent_run) pairs
- 3 human annotators score independently (0-1)
- Compare with GradingEngine scores

**Success criteria:** Pearson r > 0.80 AND MAE < 0.15.

---

## Experiment 4: Test-Retest Reliability

**Goal:** Scores are stable across repeated runs.

**Setup:** 20 tasks x 5 runs with same agent.

**Success criteria:** ICC > 0.90.

---

## Experiment 5: Ablation Studies

### 5a: Config Generation vs Code Generation

| Method | Validity Rate | Scoring |
|--------|-------------|---------|
| LLM generates pytest (v0.x) | ~30% | Binary |
| LLM generates YAML config (v2) | **99%** | 0.0-1.0 |

### 5b: Safety Gate

| Condition | Dangerous agent score |
|-----------|----------------------|
| With safety gate | 0.00 (zeroed) |
| Without safety gate | 0.60+ (completion only) |

### 5c: Error Injection

| Condition | Robustness score |
|-----------|-----------------|
| With error injection (10%) | 0.70-0.85 |
| Without error injection | 1.00 |

### 5d: Scoring Component Analysis

What happens when we remove specific check types?

---

## Experiment 6: Scalability

**Goal:** The system scales linearly and maintains quality.

| Scale | Tasks | Time | Cost | Human equivalent |
|-------|-------|------|------|------------------|
| Small | 30 | ~2 min | ~$0.30 | 60 hrs |
| Medium | 130 | ~10 min | ~$1.30 | 260 hrs |
| **Large** | **1,300** | **~100 min** | **~$13** | **2,600 hrs** |
| XL | 13,000 | ~16 hrs | ~$130 | impossible |

**Success criteria:** Linear scale AND config validity > 95% at 1,300 tasks.

---

## Execution Timeline

| Phase | Duration | Work |
|-------|----------|------|
| Infrastructure | 1 week | Docker sandbox, batch runner, API integration |
| Exp 1: Multi-Agent | 1 week | 2 agents x 81 tasks x 1 run |
| Exp 2: Human Baseline | 1-2 weeks | Deploy Claw-Eval, comparative runs |
| Exp 3: Verification | 1 week | Human annotation, correlation analysis |
| Exp 4-6: Ablation + Scale | 1 week | Remaining experiments |
| Paper Writing | 2 weeks | Introduction, Method, Experiments, Analysis |
