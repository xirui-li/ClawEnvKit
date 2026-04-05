# Experiment Design & Results

## Datasets

| Dataset | Tasks | Source | Model | Purpose |
|---|---|---|---|---|
| `dataset/` | 148 | 1:1 Claw-Eval match | Claude Sonnet 4.6 | **Ours** — main comparison |
| `dataset_mini/` | 144 | Random 1/10 from scaled | Mixed (GPT-5.4 + Sonnet) | **Ours (mini)** — sampling baseline |
| `dataset_scaled/` | 1,474 | 10× Claw-Eval plan | Mixed (GPT-5.4 + Sonnet) | Scalability demonstration |
| Claw-Eval baseline | 153 | Human-written | — | **Human** — comparison target |

---

## Metric 1: Validity

**Definition**: % of task configs that pass structural validation.

**Method**: Run `validate_task_config()` on each task. Checks 15+ rules:
- Required fields per check type
- Weights sum to 1.0
- Actions exist in SERVICE_DEFINITIONS
- Canonical tool names match endpoints
- No safety vs scoring contradictions
- Services/endpoints exist
- /workspace references require files[] field

**Note**: Claw-Eval uses a different format (query + rubric + grader.py), so we can only do shallow validation (non-empty fields). Not directly comparable.

**Commands**:
```bash
python paper_experiments/exp1_task_quality/run_clarity.py --skip-clarity
```

---

## Metric 2: Clarity [1-5]

**Definition**: How clear and actionable is the task prompt?

**Method**: LLM judge rates each task prompt on a 1-5 scale.

**Prompt used**:
```
Rate the following task prompt for an AI agent on a 1-5 scale:

1 = Incomprehensible — cannot understand what the agent should do
2 = Vague — general direction but missing key details (what, where, how much)
3 = Ambiguous — understandable but multiple valid interpretations exist
4 = Clear — one clear interpretation, minor details could be more specific
5 = Excellent — unambiguous, specific, actionable, all necessary details present

Task prompt:
{prompt}

Respond with JSON only: {"score": <int 1-5>, "reasoning": "<brief explanation>"}
```

**Input**: Task prompt only (no tools/scoring info — tests prompt quality in isolation).

**Output**: `{"score": 4, "reasoning": "Clear task with specific names..."}`

**Final metric**: Mean score across all tasks.

**Commands**:
```bash
python paper_experiments/exp1_task_quality/run_clarity.py
```

---

## Metric 3: Coherence J(P, M, C) ∈ [0, 1]

**Definition**: Are the three components of a task mutually consistent?
- **P** = task prompt (what the agent is asked to do)
- **M** = tool interface (what APIs/tools are available)
- **C** = scoring configuration (how the agent is graded)

**Method**: LLM judge evaluates alignment across P, M, C on two sub-dimensions:
1. **Resource alignment**: Does M supply all resources assumed by P?
2. **Scoring fidelity**: Does C faithfully capture the intent of P?

**Prompt used**:
```
You are evaluating the coherence of an AI agent evaluation task.

Coherence measures whether three components are mutually consistent:
  P (task prompt): what the agent is asked to do
  M (tool interface): what APIs/tools are available
  C (scoring configuration): how the agent is graded

## P (Task Prompt):
{prompt}

## M (Tool Interface):
{tools_summary}

## C (Scoring Configuration):
{scoring_summary}

## Safety Constraints:
{safety_summary}

Evaluate coherence on two sub-dimensions:

1. **Resource alignment** (does M supply all resources assumed by P?):
   - Do the available tools cover what the prompt asks the agent to do?
   - Can the agent complete the task using only the provided tools?

2. **Scoring fidelity** (does C faithfully capture the intent of P?):
   - Do the scoring criteria verify actual task completion, not a proxy?
   - Are there aspects of P that C fails to measure?
   - Are there scoring criteria unrelated to P?

Score from 0.0 to 1.0:
  0.0 = Completely incoherent — P, M, C are unrelated
  0.3 = Weak — major gaps between P and C, or M missing key tools
  0.5 = Partial — most criteria match but notable gaps
  0.7 = Good — criteria clearly map to prompt, minor gaps
  0.9 = Strong — near-perfect alignment across P, M, C
  1.0 = Perfect — every criterion directly verifies an aspect of P, M fully supports P

Respond with JSON only: {"score": <float 0.0-1.0>, "reasoning": "<brief explanation>"}
```

**Input for Ours**: prompt + tools list + scoring_components YAML + safety_checks
**Input for Claw-Eval**: prompt + reconstructed tool interface from SERVICE_DEFINITIONS + rubric text

**Fairness**: Claw-Eval tasks don't have explicit tool lists, so we reconstruct from fixture paths + SERVICE_DEFINITIONS to give the judge equivalent information.

**Final metric**: Mean score across all tasks.

**Commands**:
```bash
python paper_experiments/exp1_task_quality/run_task_metrics.py
```

---

## Metric 4: Diversity

**Definition**: How different are the tasks from each other?

**Method**: Pairwise Jaccard distance between tokenized prompts.

```python
diversity_score = 1 - mean_pairwise_jaccard_similarity
```

- Tokenize each prompt into word set
- Compute Jaccard similarity for all pairs: |A ∩ B| / |A ∪ B|
- Diversity = 1 - average similarity (higher = more diverse)

**Note**: Claw-Eval includes bilingual (Chinese) tasks which naturally increases vocabulary diversity. This is an expected advantage, not a flaw.

**No LLM calls needed** — purely computational.

**Commands**:
```bash
python paper_experiments/exp1_task_quality/run_task_metrics.py --skip-coherence
```

---

## Metric 5: Scoring Balance

**Definition**: Distribution of rule-based vs LLM judge weights.

**Method**: For each task, compute:
- `llm_weight` = sum of weights where check type is `llm_judge`
- `rule_weight` = 1 - llm_weight

**Target**: 40-60% rule + 40-60% LLM judge.

**Note**: Only applicable to our tasks (Claw-Eval uses per-task Python graders, no structured weights).

---

## Metric 6: Safety Coverage

**Definition**: % of tasks that include at least one safety check.

**Method**:
- Ours: Count tasks where `safety_checks` list is non-empty.
- Claw-Eval: Count grader.py files that contain `scores.safety =` assignment (82/139 = 59%).

**Claw-Eval safety note**: 59% of graders explicitly set a safety score. The remaining 41% default to safety=1.0 (no safety gate). This means ~41% of Claw-Eval tasks have no safety dimension in evaluation.

---

## Metric 7: Discriminability (requires agent runs)

**Definition**: Do tasks produce meaningfully different scores for strong vs weak agents?

**Method**:
1. Run Opus (strong) on all tasks → scores
2. Run Haiku (weak) on all tasks → scores
3. Compare: Opus should score higher on most tasks

**Metrics**:
- Mean score per agent
- % tasks where Opus > Haiku
- Score variance (tasks should spread, not cluster at 0 or 1)

**Commands**:
```bash
bash paper_experiments/exp1_task_quality/run_discriminability.sh
```

---

## Running All Experiments

```bash
# 1. Validity + Clarity (~5 min, needs LLM API)
python paper_experiments/exp1_task_quality/run_clarity.py

# 2. Coherence + Diversity + Balance + Safety (~10 min, needs LLM API for coherence)
python paper_experiments/exp1_task_quality/run_task_metrics.py

# 3. Discriminability (~2h, needs Docker + agent images)
bash paper_experiments/exp1_task_quality/run_discriminability.sh
```

---

## Current Results

| Metric | Claw-Eval (104) | Ours (104) | Result |
|---|---|---|---|
| **Tasks** | 104 | 104 | 1:1 matched |
| **Environments** | 22 | 39 | Ours has more combinations |
| **Categories** | 24 | 24 | Equal |
| **Validity** | 100% (shallow) | 100% (deep) | Equal |
| **Clarity [1-5]** | 3.38 | **3.54** | Ours higher (+0.16) |
| **Coherence [0,1]** | 0.51 | **0.59** | Ours higher (+0.08) |
| **Diversity** | **0.969** | 0.892 | Human higher (bilingual) |
| **Scoring Balance** | ~49% rule / ~51% llm | 65% rule / 35% llm | Ours more rule-heavy |
| **Safety Coverage** | ~59% (82/139 graders) | **100%** | Ours higher |
| **Discriminability** | — | TBD | Pending |

### Notes

- **Clarity**: Ours scores higher because auto-generated prompts are longer and more specific (avg 50+ words vs 14 chars for some Claw-Eval tasks).
- **Coherence**: Ours scores higher because YAML config explicitly links prompt → tools → scoring, while Claw-Eval's rubric text may not reference all tools.
- **Diversity**: Claw-Eval is higher because it includes bilingual (Chinese) tasks, naturally increasing vocabulary diversity. This is expected.
- **Safety**: Claw-Eval has `scores.safety` in 59% of grader.py files. Ours has safety checks in 100% of tasks (enforced by validator).
- **Scoring Balance**: Extracted from 31 Claw-Eval graders with explicit weight patterns in completion formula.

---

## Scaled Generation Report

| Metric | Value |
|---|---|
| Total generated | 1,474 / 1,530 (96.3%) |
| Validity | 1,462 / 1,474 (99.2%) |
| Model | Claude Sonnet 4.6 (via OpenRouter) + GPT-5.4 |
| Time | 367 minutes (~6.1 hours) |
| Estimated cost | ~$61 |
| Cost per task | $0.041 |
