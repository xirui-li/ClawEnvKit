# Experiment Design: Validating Auto-Generated Agent Evaluation Environments

> **Note:** This is the original experiment plan. Some comparison table numbers may be outdated. See [docs/scoring.md](docs/scoring.md) for current check types and [docs/agents/index.md](docs/agents/index.md) for current harness count.

## Research Question

Can automatically generated task configurations (YAML + fixed GradingEngine) produce evaluation tasks of equivalent quality to human-written tasks?

## Core Claim

Auto-generated tasks are **as good as human-written tasks** for evaluating AI agents, at **240x lower cost** (30s API call vs 2hr human labor per task).

---

## Experiment Overview

| # | Experiment | Core Question | Priority |
|---|-----------|---------------|----------|
| **1** | **Task Quality (Human Baseline)** | auto tasks ≈ human tasks? | **核心** |
| 2 | Multi-Agent Discrimination | auto tasks 能区分 agent 能力? | 必做 |
| 3 | Verification Accuracy | GradingEngine 评分 ≈ 人工评分? | 必做 |
| 4 | Test-Retest Reliability | 评分稳定? | 补充 |
| 5 | Ablation Studies | 各组件贡献? | 补充 |
| 6 | Scalability | 线性 scale? | 核心 differentiator |

---

## Experiment 1: Task Quality — Human Baseline Comparison（核心实验）

**Goal:** 直接证明自动生成的 task 质量 ≈ 人写的 task 质量。

### Dataset Comparison

| | Claw-Eval (Human) | ClawEnvKit (Auto) |
|---|---|---|
| **Total tasks** | 139 (104 general + 35 multimodal) | 129 (general only) |
| **Services** | 13+ (同一套 mock services) | 13 (同一套 mock services) |
| **Task format** | query + rubric (自然语言) | prompt + scoring_components (结构化 YAML) |
| **Scoring** | LLM judge 读 rubric | GradingEngine 查 audit log |
| **Comparison scope** | Overlapping general services only | Same |

Note: Claw-Eval 的 35 个 multimodal tasks（网页生成、视频问答等）不在比较范围内。两边使用**同一套 mock service 代码**（FastAPI + audit log），确保 agent 执行环境完全一致。

### 5 个 Task Quality Metrics

#### Metric 1: Validity Rate（task 是否合法可执行）

| | Claw-Eval | Ours |
|---|---|---|
| **怎么算** | 100%（人工编写保证合法）| 自动验证：config validator |
| **检查项** | N/A | check types valid, weights sum=1.0, actions exist |

**Expected:** Ours ≥ 95%（实测 99%: 129/130）

#### Metric 2: Solvability Rate（好 agent 能否完成）

| | Claw-Eval | Ours |
|---|---|---|
| **怎么算** | 用 Opus 跑每个 task，score > 0.5 的比例 | 同 |

**为什么重要：** 如果一个 task 连最强 agent 都做不到 0.5，说明 task 有问题（不可解、scoring 有 bug、prompt 不清晰）。

**Report:** Solvability rate for both sides (absolute values, no statistical test).

#### Metric 3: Discriminative Power（能否区分强弱 agent）

| | Claw-Eval | Ours |
|---|---|---|
| **怎么算** | per task: Opus_score - Haiku_score | 同 |

**为什么重要：** 好的 task 应该让强 agent 得高分、弱 agent 得低分。如果所有 agent 都得 1.0 或都得 0.0，这个 task 没有区分力。

**Report:** Mean ± std of discriminative power for both sides.

#### Metric 4: Difficulty Calibration（难度标签是否准确）

| | Claw-Eval | Ours |
|---|---|---|
| **怎么算** | Spearman ρ(标注难度, 实际 agent 分数) | 同 |

**为什么重要：** 标注为 "easy" 的 task 应该比 "hard" 的 task 得分高。

**Report:** Spearman ρ value for our tasks (Claw-Eval has no difficulty labels).

#### Metric 5: Task Clarity（prompt 是否清晰无歧义）

| | Claw-Eval | Ours |
|---|---|---|
| **怎么算** | LLM judge 对每个 prompt 打 1-5 分 | 同 |
| **评分标准** | 1=不可理解, 3=有歧义, 5=清晰明确 | 同 |

**为什么重要：** 自动生成的 prompt 可能不清晰、有歧义、或要求不合理。

**Report:** Mean ± std for both sides.

### 论文核心 Table

Report absolute values. Let the reader judge whether the difference is meaningful.

| Task Quality Metric | Claw-Eval (Human) | ClawEnvKit (Auto) | Notes |
|---------------------|-------------------|-----------------------|-------|
| Validity Rate | 100% (shallow check) | ?% (deep check) | Different check depths — not directly comparable |
| Coherence J(P,M,C) | ? ± ? | ? ± ? | Same judge, same rubric, reconstructed tool interface |
| Solvability Rate (Opus > 0.5) | ?% | ?% | Same agent, same mock services |
| Discriminative Power (Opus - Haiku) | ? ± ? | ? ± ? | Same agent pair, same mock services |
| Task Clarity (LLM 1-5) | ? ± ? | ? ± ? | Same judge, same rubric |

---

## Discriminability (part of Experiment 1)

**Goal:** 证明自动生成的 task 能区分不同能力的 agent。

**Setup:**
- Tasks: auto-generated dataset only (no Claw-Eval — different grading mechanism)
- Agents: 2 models
  - Strong: Claude Opus 4.6
  - Weak: Claude Haiku 4.5
- 1 run per task per agent (single pass, no averaging)
- Docker + OpenClaw with native tool plugin

**What we measure:**
- Per-task: Disc(E) = Opus_score - Haiku_score
- Set-level: mean Disc(E), and whether Opus consistently > Haiku
- Score distributions for both models

**Limitations:**
- No Claw-Eval comparison (their grading uses per-task Python graders, not comparable)
- No multi-run averaging (1 run, not 3 — cost constraint)
- 2 models, not 3 (no Sonnet — cost constraint)

**Success criteria:** Spearman ρ > 0.7 between agent capability and score

---

## Experiment 3: Verification Accuracy

**Goal:** 证明 GradingEngine 的评分 ≈ 人工评分。

**Setup:**
- 随机选 50 个 (task, agent_run) pair
- 3 个人工 annotator 独立评分（0-1 scale）
- 比较 GradingEngine score 与人工评分

**Metrics:**

| Metric | 计算方式 |
|---|---|
| Pearson correlation | r(engine_score, human_score) |
| Mean absolute error | MAE = mean(\|engine - human\|) |
| False positive rate | engine > 0.5 but human < 0.5 |
| False negative rate | engine < 0.5 but human > 0.5 |
| Inter-annotator agreement | Fleiss' κ among 3 annotators |

**Success criteria:** Pearson r > 0.80 AND MAE < 0.15

---

## Experiment 4: Test-Retest Reliability

**Goal:** 证明评分稳定。

**Setup:** 20 tasks × 5 runs with same agent。

**Metrics:**
- Coefficient of variation (CV = σ/μ)
- ICC (Intraclass Correlation Coefficient)

**Success criteria:** ICC > 0.90

---

## Experiment 5: Ablation Studies

### 5a: Config Generation vs Code Generation

| 方法 | Task 数 | 验证合法率 | 评分精度 |
|---|---|---|---|
| LLM 生成 pytest (v0.x) | 20 | ~30% | 二元 pass/fail |
| LLM 生成 YAML config (v2) | 20 | ~99% | 0.0-1.0 continuous |

### 5b: Safety Gate

| Condition | Dangerous agent score |
|---|---|
| With safety gate | 0.00 (清零) |
| Without safety gate | 0.60+ (只看 completion) |

### 5c: Error Injection

| Condition | Robustness score |
|---|---|
| With error injection (10%) | 0.70-0.85 |
| Without error injection | 1.00 |

### 5d: Scoring Component Analysis

去掉 llm_judge 后 scoring accuracy 是否下降？去掉 audit checks 呢？

---

## Experiment 6: Scalability

**Goal:** 证明系统线性 scale。

| 规模 | Tasks | 时间 | 成本 | 对比人工 |
|---|---|---|---|---|
| Small | 30 | ~2 min | ~$0.30 | 60 hrs |
| Medium | 130 | ~10 min | ~$1.30 | 260 hrs |
| **Large** | **1,300** | **~100 min** | **~$13** | **2,600 hrs** |
| XL | 13,000 | ~16 hrs | ~$130 | impossible |

**Paper 核心 table:**

```
                Tasks    Time to create    Cost
Claw-Eval        139     ~280 hours       ~$14,000 (人力)
SkillsBench       84     ~168 hours       ~$8,400 (人力)
ClawEnvKit   129     10 minutes       $1.30
ClawEnvKit  1,300    100 minutes      $13
ClawEnvKit 13,000    16 hours         $130
```

**Success criteria:**
- 线性 scale（2× tasks = 2× time）
- 1,300 tasks config validity rate > 95%
- 1,300 tasks discrimination 与 81 supported tasks 一致（rank correlation > 0.9）

---

## Experiment Execution Plan

### Phase 1: Infrastructure (1 week)

- [ ] 下载 Claw-Eval dataset（HuggingFace: claw-eval/Claw-Eval）
- [ ] 对齐 Claw-Eval task format 与我们的 format（overlapping services）
- [ ] 写 batch runner 脚本：一次性跑 N 个 tasks，输出 results.csv
- [ ] 确保 Docker sandbox 能跑所有 13 个 service

### Phase 2: Task Quality + Multi-Agent (Exp 1 + 2) (2 weeks)

- [ ] 跑 3 个 agent (Haiku/Sonnet/Opus) × 129 auto tasks × 3 runs
- [ ] 跑 1 个 agent (Sonnet) × Claw-Eval overlapping tasks × 3 runs
- [ ] 计算 5 个 task quality metrics
- [ ] 计算 multi-agent discrimination
- [ ] 生成 Table 1: Task Quality Comparison
- [ ] 生成 Table 2: Agent Ranking

### Phase 3: Verification + Reliability (Exp 3 + 4) (1 week)

- [ ] 随机抽 50 个 task-run pairs
- [ ] 人工 annotation（3 annotators）
- [ ] Test-retest: 20 tasks × 5 runs
- [ ] 生成 Table 3: Verification Accuracy

### Phase 4: Ablation + Scalability (Exp 5 + 6) (1 week)

- [ ] Config vs pytest ablation
- [ ] Safety gate / error injection ablation
- [ ] Scale to 1,300 tasks, verify quality holds

### Phase 5: Paper Writing (2 weeks)

- [ ] Introduction: the problem of agent evaluation at scale
- [ ] Method: config generation + fixed grading engine
- [ ] Experiments: Table 1-4, Figure 1-2
- [ ] Analysis: ablation results
- [ ] Discussion: limitations, future work

---

## Key Comparisons in Paper

### Table: System Comparison

| | Claw-Eval | SWE-bench | SkillsBench | **Ours** |
|---|---|---|---|---|
| Tasks | 139 | 2,294 | 84 | **~100 (100% Claw-Eval coverage, scalable to ∞)** |
| Source | Human | GitHub PR | Human | **Auto-generated** |
| Verification | Per-task rubric + LLM judge | Unit tests | pytest | **Universal engine + YAML** |
| Scoring | 0-1 weighted | Binary | Binary | **0-1 weighted (3D)** |
| Safety | ✅ | ❌ | ❌ | **✅** |
| Robustness | ✅ | ❌ | ❌ | **✅** |
| Cost/task | ~2hr | N/A | ~2hr | **~30s** |
| Agent integration | Curl-based | N/A | N/A | **Plugin + MCP + shell (10 harnesses)** |

---

## Potential Reviewer Questions

**Q: How do you know LLM-generated configs don't have semantic errors?**
A: Five-metric task quality evaluation (Exp 1) shows auto tasks match human tasks on solvability, discriminative power, difficulty calibration, and clarity. 99% first-try config validity rate.

**Q: The GradingEngine uses LLM-judge for some components — isn't that circular?**
A: LLM-judge weight targets 30-50% per task (capped at 55%), balanced with 50-70% deterministic audit-based checks. The LLM judge receives audit context (what the agent did) alongside agent output, matching Claw-Eval's approach. Ablation (Exp 5d) measures the contribution of each component.

**Q: Different grading mechanisms (rubric vs audit) — is the comparison fair?**
A: We compare task quality metrics (solvability, discrimination, clarity), not grading scores directly. Both use the same mock services and agent, so the comparison isolates task source (human vs auto) as the only variable.

**Q: Can you generate tasks for domains not covered by mock services?**
A: Each new service takes ~4 hours to build. The GradingEngine and config generator work unchanged. Or use `service_generator.py` to auto-generate from description.

**Q: What about multimodal tasks?**
A: Claw-Eval has 35 multimodal tasks (webpage, video, OCR). Our current scope is general tasks (104 vs 129). Multimodal is future work.

**Q: How does this compare to just using Claw-Eval directly?**
A: Claw-Eval is a static benchmark (139 tasks, fixed). We can generate unlimited tasks for the same services, enabling: (1) training data at scale, (2) task diversity to avoid overfitting, (3) dynamic difficulty adjustment.
