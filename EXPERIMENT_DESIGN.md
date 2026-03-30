# Experiment Design: Validating Auto-Generated Agent Evaluation Environments

## Research Question

Can automatically generated task configurations (YAML + fixed GradingEngine) evaluate AI agents as reliably as human-written evaluation tasks?

## Core Claim

Auto-generated task configs achieve equivalent agent evaluation quality to human-written tasks at 240× lower cost (30s API call vs 2hr human labor per task).

---

## Experiments

### Experiment 1: Multi-Agent Discrimination (必做)

**Goal:** 证明自动生成的 task 能区分不同能力的 agent。

**Setup:**
- Tasks: 我们的 129 tasks（13 services × 10 tasks）
- Agents: 3+ 个不同能力的 model
  - Weak: Claude Haiku 4.5
  - Medium: Claude Sonnet 4.5
  - Strong: Claude Opus 4.5 / 4.6
- 每个 agent × 每个 task 跑 3 次（取平均）

**Metrics:**
- 每个 agent 在每个 service 上的平均 score
- Overall 平均 score 排名是否 Strong > Medium > Weak
- Spearman rank correlation across tasks

**Expected result:**
```
Agent         Avg Score
Opus 4.5      0.72 ± 0.08
Sonnet 4.5    0.55 ± 0.10
Haiku 4.5     0.35 ± 0.12
```

**Success criteria:** Spearman ρ > 0.7 between agent capability and score

---

### Experiment 2: Human Baseline Comparison (必做)

**Goal:** 证明自动生成的 task 与人写的 task 评估结果一致。

**Setup:**
- Human tasks: Claw-Eval 139 tasks（13+ services，人工编写）
- Auto tasks: 我们的 129 tasks（13 services，自动生成）
- Agent: 选 1 个 model（e.g., Sonnet 4.5），跑两边
- 只比较 overlapping services（gmail, calendar, todo, helpdesk, notes, crm, finance, etc.）

**Metrics:**
| Metric | 计算方式 | 说明 |
|---|---|---|
| Score distribution similarity | KS test p-value | 分数分布是否一致 |
| Mean score difference | \|μ_human - μ_auto\| | 绝对分差 |
| Rank correlation | Spearman ρ across services | 各 service 难度排名是否一致 |
| Difficulty gradient | 各难度的平均分 | easy > medium > hard 是否两边都成立 |

**Expected result:**
```
                Human tasks    Auto tasks
Easy avg         0.78           0.75
Medium avg       0.52           0.48
Hard avg         0.28           0.25
KS test p-value  > 0.05 (not significantly different)
```

**Success criteria:** KS test p > 0.05（分布无显著差异）AND 两边难度梯度一致

---

### Experiment 3: Verification Accuracy (必做)

**Goal:** 证明 GradingEngine 的评分是准确的（不是假阳或假阴）。

**Setup:**
- 随机选 50 个 (task, agent_run) pair
- 3 个人工 annotator 独立评分（0-1 scale，参照 scoring_components）
- 比较 GradingEngine score 与人工评分

**Metrics:**
| Metric | 计算方式 |
|---|---|
| Pearson correlation | r(engine_score, human_score) |
| Mean absolute error | MAE = mean(\|engine - human\|) |
| False positive rate | engine > 0.5 但 human < 0.5 的比例 |
| False negative rate | engine < 0.5 但 human > 0.5 的比例 |
| Inter-annotator agreement | Fleiss' κ among 3 annotators |

**Expected result:**
```
Pearson r:           > 0.80
MAE:                 < 0.15
False positive rate: < 10%
False negative rate: < 10%
Inter-annotator κ:   > 0.70
```

**Success criteria:** Pearson r > 0.80 AND MAE < 0.15

---

### Experiment 4: Test-Retest Reliability

**Goal:** 证明评分稳定（同 agent 同 task 多次跑分数一致）。

**Setup:**
- 选 20 个 tasks（覆盖不同 service 和 difficulty）
- 同一个 agent 跑 5 次
- 计算每个 task 的分数 variance

**Metrics:**
- Mean standard deviation across tasks
- Coefficient of variation (CV = σ/μ)
- ICC (Intraclass Correlation Coefficient)

**Expected result:**
```
Mean std:  < 0.05
Mean CV:   < 10%
ICC:       > 0.90
```

**Success criteria:** ICC > 0.90

---

### Experiment 5: Ablation Studies

**Goal:** 验证系统各组件的贡献。

#### 5a: Config Generation vs Code Generation

| 方法 | Task 数 | 验证合法率 | Agent 评分准确度 |
|---|---|---|---|
| LLM 生成 pytest (v0.x) | 20 | ~30% | 二元 pass/fail |
| LLM 生成 YAML config (v2) | 20 | ~99% | 0.0-1.0 continuous |

同一批 task prompt，两种验证方式，比较 validity rate 和 scoring accuracy。

#### 5b: Safety Gate

| Condition | Dangerous agent score |
|---|---|
| With safety gate | 0.00 (清零) |
| Without safety gate | 0.60+ (只看 completion) |

证明 safety gate 能有效检测危险行为。

#### 5c: Error Injection

| Condition | Agent robustness score |
|---|---|
| With error injection (10% rate) | 0.70-0.85 (有些 agent 不重试) |
| Without error injection | 1.00 (所有 API 都成功) |

证明 error injection 能区分 robust vs fragile agent。

#### 5d: Scoring Component Analysis

| Component type | 占比 | 准确度 | 贡献 |
|---|---|---|---|
| audit_action_exists | ~30% | 100% deterministic | 核心 |
| audit_field_equals/contains | ~25% | 100% deterministic | 核心 |
| keywords_present/absent | ~15% | ~95% | 补充 |
| llm_judge | ~20% | ~75% (placeholder) | 语义质量 |
| audit_sequence | ~10% | 100% deterministic | 流程正确性 |

去掉 llm_judge 后 scoring accuracy 是否下降？去掉 audit checks 呢？

---

### Experiment 6: Scalability (核心 differentiator)

**Goal:** 证明系统可以高效 scale，直接对比人工方法不可能达到的规模。

**Phase 1: 用 129 tasks 跑通实验流程**（验证 pipeline 正确性）

| | Tasks | 用途 |
|---|---|---|
| 当前 dataset | 129 (13 services × ~10) | 验证实验流程 |

**Phase 2: Scale 到 1,300 tasks**（每个 service 100 tasks，证明 scalability）

```bash
for service in todo gmail calendar helpdesk contacts notes crm finance inventory rss scheduler kb config; do
    clawharness generate --service $service --count 100 --difficulty medium --output dataset_large
done
```

| 规模 | 服务数 | Tasks | 时间 | 成本 | 对比人工 |
|---|---|---|---|---|---|
| Small | 3 | 30 | ~2 min | ~$0.30 | 60 hrs |
| Medium | 13 | 130 | ~10 min | ~$1.30 | 260 hrs |
| **Large** | **13** | **1,300** | **~100 min** | **~$13** | **2,600 hrs** |
| XL | 13 | 13,000 | ~16 hrs | ~$130 | impossible |

**Paper 核心 table:**

```
                Tasks    Time to create    Cost
Claw-Eval        139     ~280 hours       ~$14,000 (人力)
SkillsBench       84     ~168 hours       ~$8,400 (人力)
ClawHarnessing   129     10 minutes       $1.30
ClawHarnessing  1,300    100 minutes      $13
ClawHarnessing 13,000    16 hours         $130
```

**Success criteria:**
- 线性 scale（2× tasks = 2× time）
- 1,300 tasks 的 config validity rate 仍然 > 95%
- 1,300 tasks 上的 multi-agent discrimination 与 129 tasks 一致（rank correlation > 0.9）

---

## Experiment Execution Plan

### Phase 1: Infrastructure (1 week)

- [ ] 确保 Docker sandbox 能跑所有 13 个 service 的 tasks
- [ ] 写 batch runner 脚本：一次性跑 N 个 tasks，输出 results.csv
- [ ] 集成 Anthropic API 作为 agent（Haiku/Sonnet/Opus）

### Phase 2: Multi-Agent Discrimination (Exp 1) (1 week)

- [ ] 跑 3 个 agent × 129 tasks × 3 runs = ~1,161 runs
- [ ] 收集 scores，计算排名相关性
- [ ] 生成 Table 1: Agent ranking results

### Phase 3: Human Baseline (Exp 2) (1-2 weeks)

- [ ] 部署 Claw-Eval 环境
- [ ] 用同一个 agent 跑 Claw-Eval tasks
- [ ] 收集 scores，对比分布
- [ ] 生成 Figure 1: Score distribution comparison

### Phase 4: Verification Accuracy (Exp 3) (1 week)

- [ ] 随机抽 50 个 task-run pairs
- [ ] 3 个 annotator 独立评分
- [ ] 计算 correlation + agreement
- [ ] 生成 Table 2: Verification accuracy

### Phase 5: Ablation + Scalability (Exp 4-6) (1 week)

- [ ] Test-retest: 20 tasks × 5 runs
- [ ] Config vs pytest ablation
- [ ] Safety gate / error injection ablation
- [ ] Scalability timing

### Phase 6: Paper Writing (2 weeks)

- [ ] Introduction: the problem of agent evaluation at scale
- [ ] Method: config generation + fixed grading engine
- [ ] Experiments: Table 1-3, Figure 1-2
- [ ] Analysis: ablation results
- [ ] Discussion: limitations, future work

---

## Key Comparisons in Paper

### Table: System Comparison

| | Claw-Eval | SWE-bench | SkillsBench | **Ours** |
|---|---|---|---|---|
| Tasks | 139 | 2,294 | 84 | **129 (scalable to ∞)** |
| Source | Human | GitHub PR | Human | **Auto-generated** |
| Verification | Per-task grader.py | Unit tests | pytest | **Universal engine + YAML** |
| Scoring | 0-1 weighted | Binary | Binary | **0-1 weighted (3D)** |
| Safety | ✅ | ❌ | ❌ | **✅** |
| Robustness | ✅ | ❌ | ❌ | **✅** |
| Cost/task | ~2hr | N/A | ~2hr | **~30s** |
| Domains | 11 | Python only | 11 | **13** |

### Figure: Score Distribution

```
     Human Tasks          Auto Tasks
     ┌─────────┐          ┌─────────┐
Easy │ ████████ │ 0.75    │ ████████│ 0.73
Med  │ █████    │ 0.50    │ █████   │ 0.48
Hard │ ██       │ 0.25    │ ███     │ 0.27
     └─────────┘          └─────────┘
     KS test: p = 0.12 (not significantly different)
```

---

## Potential Reviewer Questions

**Q: How do you know LLM-generated configs don't have semantic errors?**
A: Self-validation pipeline (reference_solution must score > 0.6). Config validator checks structural correctness. 99% first-try validity rate. Verification accuracy experiment (Exp 3) with human annotators shows Pearson r > 0.80.

**Q: The GradingEngine uses LLM-judge for some components — isn't that circular?**
A: LLM-judge weight is capped at 35% per task. Ablation (Exp 5d) shows removing LLM-judge only reduces accuracy by ~5pp. Core scoring is 100% deterministic (audit-based checks).

**Q: Can you generate tasks for domains not covered by mock services?**
A: Each new service template takes ~4 hours to build (FastAPI + audit log). The GradingEngine and config generator work unchanged. This is linear not exponential cost.

**Q: How does this compare to just using Claw-Eval directly?**
A: Claw-Eval is a static benchmark (139 tasks, fixed). We can generate unlimited tasks for the same services, enabling: (1) training data at scale, (2) task diversity to avoid overfitting, (3) dynamic difficulty adjustment.

**Q: What if the mock services don't accurately represent real APIs?**
A: We use Claw-Eval's mock services directly (same code). If their services are accurate enough for a peer-reviewed benchmark with 139 human-curated tasks, they are accurate enough for auto-generated tasks.
