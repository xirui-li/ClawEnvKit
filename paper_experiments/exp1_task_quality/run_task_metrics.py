"""Experiment 1: Task Quality — Additional Metrics (no agent needed)

Metric 6: Coherence — does the prompt align with scoring components?
Metric 7: Diversity — are tasks sufficiently different from each other?
Metric 8: Scoring Balance — rule vs LLM judge weight distribution
Metric 9: Safety Coverage — meaningful safety checks?

Usage:
    python paper_experiments/exp1_task_quality/run_task_metrics.py
    python paper_experiments/exp1_task_quality/run_task_metrics.py --skip-coherence  # skip LLM calls
"""

import json
import os
import re
import sys
import time
import yaml
from pathlib import Path
from collections import Counter

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
# Load tasks
# ---------------------------------------------------------------------------

def load_ours() -> list[dict]:
    tasks = []
    for f in sorted((PROJECT_ROOT / "dataset").rglob("*.yaml")):
        config = yaml.safe_load(open(f))
        config["_source"] = "auto"
        tasks.append(config)
    return tasks


def load_claweval() -> list[dict]:
    data = json.load(open(PROJECT_ROOT / "claw_eval_baseline" / "general.json"))
    overlap_path = PROJECT_ROOT / "claw_eval_baseline" / "overlapping.json"
    if overlap_path.exists():
        data.extend(json.load(open(overlap_path)))
    tasks = []
    for t in data:
        tasks.append({
            "task_id": t["task_id"],
            "prompt": t["query"],
            "fixture": t.get("fixture", []),
            "rubric": t["rubric"],
            "category": t["category"],
            "language": t["language"],
            "_source": "human",
        })
    return tasks


# ---------------------------------------------------------------------------
# Metric 8: Scoring Balance (rule vs LLM judge)
# ---------------------------------------------------------------------------

def compute_scoring_balance(tasks: list[dict]) -> dict:
    """Compute rule vs LLM judge weight distribution."""
    llm_weights = []
    comp_counts = []
    check_type_counts = Counter()

    for t in tasks:
        comps = t.get("scoring_components", [])
        comp_counts.append(len(comps))

        llm_w = 0
        for c in comps:
            ctype = c.get("check", {}).get("type", "")
            check_type_counts[ctype] += 1
            if ctype == "llm_judge":
                llm_w += c.get("weight", 0)
        llm_weights.append(llm_w)

    if not llm_weights:
        return {"mean_llm": 0, "mean_rule": 1, "avg_components": 0}

    mean_llm = sum(llm_weights) / len(llm_weights)
    return {
        "mean_llm_weight": round(mean_llm, 3),
        "mean_rule_weight": round(1 - mean_llm, 3),
        "min_llm": round(min(llm_weights), 2),
        "max_llm": round(max(llm_weights), 2),
        "avg_components": round(sum(comp_counts) / len(comp_counts), 1),
        "check_type_distribution": dict(check_type_counts.most_common()),
        "n_tasks": len(llm_weights),
    }


# ---------------------------------------------------------------------------
# Metric 9: Safety Coverage
# ---------------------------------------------------------------------------

def compute_safety_coverage(tasks: list[dict]) -> dict:
    """Compute safety check statistics."""
    has_safety = 0
    safety_counts = []
    safety_types = Counter()

    for t in tasks:
        checks = t.get("safety_checks", [])
        safety_counts.append(len(checks))
        if checks:
            has_safety += 1
        for c in checks:
            safety_types[c.get("type", "unknown")] += 1

    n = len(tasks)
    return {
        "tasks_with_safety": has_safety,
        "coverage_rate": round(has_safety / n, 3) if n else 0,
        "avg_checks_per_task": round(sum(safety_counts) / n, 1) if n else 0,
        "safety_types": dict(safety_types.most_common()),
        "n_tasks": n,
    }


# ---------------------------------------------------------------------------
# Metric 7: Diversity (prompt similarity)
# ---------------------------------------------------------------------------

def compute_diversity(tasks: list[dict]) -> dict:
    """Compute task diversity using word overlap between prompts."""
    prompts = [t.get("prompt", t.get("query", "")).lower() for t in tasks]

    if len(prompts) < 2:
        return {"avg_similarity": 0, "n_tasks": len(prompts)}

    # Simple Jaccard similarity between all prompt pairs
    def tokenize(text):
        return set(re.findall(r'\b\w+\b', text.lower()))

    token_sets = [tokenize(p) for p in prompts]

    similarities = []
    for i in range(len(token_sets)):
        for j in range(i + 1, len(token_sets)):
            if not token_sets[i] or not token_sets[j]:
                continue
            intersection = len(token_sets[i] & token_sets[j])
            union = len(token_sets[i] | token_sets[j])
            similarities.append(intersection / union if union else 0)

    avg_sim = sum(similarities) / len(similarities) if similarities else 0

    # Unique words coverage
    all_words = set()
    for ts in token_sets:
        all_words.update(ts)

    return {
        "avg_pairwise_similarity": round(avg_sim, 3),
        "unique_vocabulary_size": len(all_words),
        "n_pairs": len(similarities),
        "n_tasks": len(prompts),
        # Lower similarity = more diverse (good)
        "diversity_score": round(1 - avg_sim, 3),
    }


# ---------------------------------------------------------------------------
# Metric 6: Coherence (LLM judges prompt-scoring alignment)
# ---------------------------------------------------------------------------

# Coherence rubric aligned with paper Eq 2: J(P, M, C) ∈ [0, 1]
# P = task prompt, M = tool interface (mock services), C = scoring configuration
COHERENCE_RUBRIC = """You are evaluating the coherence of an AI agent evaluation task.

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

Respond with JSON only: {{"score": <float 0.0-1.0>, "reasoning": "<brief explanation>"}}"""


def summarize_tools(task: dict) -> str:
    """Summarize the tool interface M for coherence evaluation."""
    tools = task.get("tools", [])
    if not tools:
        return "  (no tools defined)"
    lines = []
    for t in tools:
        name = t.get("name", "?")
        svc = t.get("service", "?")
        desc = t.get("description", "")[:60]
        endpoint = t.get("endpoint", "")
        lines.append(f"  {name} ({svc}): {desc} [{endpoint}]")
    return "\n".join(lines)


def summarize_scoring(task: dict) -> str:
    """Summarize scoring configuration C."""
    comps = task.get("scoring_components", [])
    lines = []
    for c in comps:
        check = c.get("check", {})
        ctype = check.get("type", "?")
        weight = c.get("weight", 0)
        name = c.get("name", "?")
        if ctype == "llm_judge":
            rubric = check.get("rubric", "")[:80]
            lines.append(f"  [{weight:.0%}] {name}: llm_judge — {rubric}")
        else:
            detail = ""
            if check.get("action"):
                detail += f" action={check['action']}"
            if check.get("field"):
                detail += f" field={check['field']}"
            if check.get("value"):
                detail += f" value={str(check['value'])[:30]}"
            lines.append(f"  [{weight:.0%}] {name}: {ctype}{detail}")
    return "\n".join(lines) if lines else "  (no scoring components)"


def summarize_scoring_claweval(task: dict) -> str:
    rubric = task.get("rubric", "")
    return rubric[:500] if rubric else "(no rubric)"


def summarize_tools_claweval(task: dict) -> str:
    """Reconstruct tool interface from Claw-Eval fixtures + SERVICE_DEFINITIONS.

    To make coherence comparison fair, we give the judge the same level
    of tool information for both auto and human tasks. Since Claw-Eval
    doesn't have explicit tools, we reconstruct from fixture paths +
    our SERVICE_DEFINITIONS (same mock services).
    """
    from clawharness.generate.task_generator import SERVICE_DEFINITIONS

    fixtures = task.get("fixture", [])
    if not fixtures:
        return "  (no fixtures — tool interface unknown)"

    services = set()
    for f in fixtures:
        parts = f.split("/")
        if len(parts) >= 2 and parts[0] == "fixtures":
            services.add(parts[1])

    if not services:
        return f"  Fixtures: {', '.join(fixtures[:5])}"

    # Reconstruct tool list from SERVICE_DEFINITIONS (same mock services)
    lines = []
    for svc in sorted(services):
        svc_def = SERVICE_DEFINITIONS.get(svc)
        if svc_def:
            lines.append(f"  [{svc}] {svc_def['description']}")
            for ep in svc_def["endpoints"]:
                lines.append(f"    {ep}")
        else:
            lines.append(f"  [{svc}] (no definition available)")

    return "\n".join(lines)


def rate_coherence(prompt: str, tools_summary: str, scoring_summary: str, safety_summary: str) -> dict:
    """Rate coherence as J(P, M, C) ∈ [0, 1] per paper Eq 2."""

    msg = COHERENCE_RUBRIC.format(
        prompt=prompt[:1000],
        tools_summary=tools_summary[:800],
        scoring_summary=scoring_summary[:1000],
        safety_summary=safety_summary[:300],
    )

    from clawharness.llm_client import call_llm

    for attempt in range(3):
        try:
            content = call_llm(msg, max_tokens=300, temperature=0)

            try:
                result = json.loads(content.strip("`").strip())
                score = float(result["score"])
                return {"score": max(0.0, min(1.0, score)), "reasoning": result.get("reasoning", "")}
            except (json.JSONDecodeError, KeyError, ValueError):
                match = re.search(r'[\d.]+', content)
                if match:
                    score = float(match.group())
                    if score > 1.0:
                        score = (score - 1) / 4.0
                    return {"score": max(0.0, min(1.0, score)), "reasoning": content[:100]}
                return {"score": 0.5, "reasoning": "parse_failed"}

        except Exception as e:
            if attempt < 2:
                time.sleep(2 ** (attempt + 1))
            else:
                return {"score": 0.5, "reasoning": f"api_error: {str(e)[:50]}"}


def evaluate_coherence_ours(tasks: list[dict]) -> list[dict]:
    """Evaluate Coh(E) = J(P, M, C) for our auto-generated tasks."""
    results = []
    for t in tasks:
        prompt = t.get("prompt", "")
        tools = summarize_tools(t)
        scoring = summarize_scoring(t)
        safety_checks = t.get("safety_checks", [])
        safety = "\n".join(f"  - {c.get('type', '?')}: {c.get('tool_name', '?')}" for c in safety_checks) or "(none)"

        rating = rate_coherence(prompt, tools, scoring, safety)
        results.append({"task_id": t.get("task_id", "?"), "source": "auto", **rating})
        print(f"  [auto] {t.get('task_id', '?')}: {rating['score']:.2f}")
        time.sleep(0.3)
    return results


def evaluate_coherence_claweval(tasks: list[dict]) -> list[dict]:
    """Evaluate Coh(E) = J(P, M, C) for Claw-Eval human-written tasks."""
    results = []
    for t in tasks:
        prompt = t.get("prompt", t.get("query", ""))
        tools = summarize_tools_claweval(t)
        scoring = summarize_scoring_claweval(t)
        safety = "(embedded in rubric)"

        rating = rate_coherence(prompt, tools, scoring, safety)
        results.append({"task_id": t.get("task_id", "?"), "source": "human", **rating})
        print(f"  [human] {t.get('task_id', '?')}: {rating['score']:.2f}")
        time.sleep(0.3)
    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-coherence", action="store_true")
    args = parser.parse_args()

    ours = load_ours()
    claweval = load_claweval()

    print("=" * 60)
    print("Experiment 1: Additional Task Quality Metrics")
    print("  LLM judge (coherence): claude-haiku-4-5, temperature=0, single run")
    print("  Note: LLM scores may vary across runs. Input truncated (prompt 1000, tools 800, scoring 1000 chars)")
    print("=" * 60)
    print(f"  Ours: {len(ours)} tasks | Claw-Eval: {len(claweval)} tasks")

    # --- Metric 8: Scoring Balance ---
    print("\n--- Metric 8: Scoring Balance ---")
    ours_balance = compute_scoring_balance(ours)
    print(f"  Ours:  rule={ours_balance['mean_rule_weight']:.0%} llm={ours_balance['mean_llm_weight']:.0%} "
          f"(range {ours_balance['min_llm']:.0%}-{ours_balance['max_llm']:.0%}), "
          f"avg {ours_balance['avg_components']} components")
    print(f"  Claw-Eval: not computed (grading is per-task Python, not structured YAML)")
    print(f"  Check types: {ours_balance['check_type_distribution']}")

    # --- Metric 9: Safety Coverage ---
    print("\n--- Metric 9: Safety Coverage ---")
    ours_safety = compute_safety_coverage(ours)
    print(f"  Ours:  {ours_safety['coverage_rate']:.0%} tasks have safety checks "
          f"({ours_safety['avg_checks_per_task']} avg per task)")
    print(f"  Types: {ours_safety['safety_types']}")
    print(f"  Claw-Eval: not computed (safety logic embedded in per-task grader.py)")

    # --- Metric 7: Diversity ---
    print("\n--- Metric 7: Task Diversity ---")
    ours_diversity = compute_diversity(ours)
    claweval_diversity = compute_diversity(claweval)
    print(f"  Ours:     diversity={ours_diversity['diversity_score']:.3f} "
          f"(avg similarity={ours_diversity['avg_pairwise_similarity']:.3f}, "
          f"vocab={ours_diversity['unique_vocabulary_size']})")
    print(f"  Claw-Eval: diversity={claweval_diversity['diversity_score']:.3f} "
          f"(avg similarity={claweval_diversity['avg_pairwise_similarity']:.3f}, "
          f"vocab={claweval_diversity['unique_vocabulary_size']})")

    # Save non-LLM results
    results = {
        "metric8_scoring_balance": {"ours": ours_balance},
        "metric9_safety_coverage": {"ours": ours_safety},
        "metric7_diversity": {"ours": ours_diversity, "claweval": claweval_diversity},
    }
    with open(RESULTS_DIR / "metrics_7_8_9.json", "w") as f:
        json.dump(results, f, indent=2)

    if args.skip_coherence:
        print("\n[Skipping coherence evaluation]")
        return

    # --- Metric 6: Coherence ---
    print("\n--- Metric 6: Coherence (prompt ↔ scoring alignment) ---")

    # API key auto-detected by call_llm (OpenRouter > Anthropic > OpenAI)

    print("\n  Rating auto-generated tasks...")
    ours_coherence = evaluate_coherence_ours(ours)

    print("\n  Rating Claw-Eval tasks...")
    claweval_coherence = evaluate_coherence_claweval(claweval)

    ours_scores = [r["score"] for r in ours_coherence]
    claweval_scores = [r["score"] for r in claweval_coherence]

    ours_mean = sum(ours_scores) / len(ours_scores)
    claweval_mean = sum(claweval_scores) / len(claweval_scores)
    diff = abs(ours_mean - claweval_mean)

    print(f"\n  Results:")
    print(f"    Ours:     {ours_mean:.2f} ± {(sum((s-ours_mean)**2 for s in ours_scores)/len(ours_scores))**0.5:.2f}")
    print(f"    Claw-Eval: {claweval_mean:.2f} ± {(sum((s-claweval_mean)**2 for s in claweval_scores)/len(claweval_scores))**0.5:.2f}")
    print(f"    Absolute difference: {diff:.3f}")

    coherence_results = {
        "ours": {"mean": ours_mean, "scores": ours_coherence},
        "claweval": {"mean": claweval_mean, "scores": claweval_coherence},
        "difference": diff,
    }
    with open(RESULTS_DIR / "metric6_coherence.json", "w") as f:
        json.dump(coherence_results, f, indent=2)

    # --- Summary (all values from this run, nothing hardcoded) ---
    print("\n" + "=" * 60)
    print("ALL TASK-LEVEL METRICS (no agent needed)")
    print("=" * 60)
    print(f"{'Metric':<35} {'Ours':<20} {'Claw-Eval':<20}")
    print("-" * 75)
    # Validity: loaded from results file if run_clarity.py ran first
    import pathlib
    validity_path = pathlib.Path(RESULTS_DIR) / "metric1_validity.json"
    if validity_path.exists():
        vdata = json.load(open(validity_path))
        ov = vdata["ours"]
        cv = vdata["claweval"]
        print(f"{'Validity (deep/shallow)':<35} {ov['valid']}/{ov['total']:<16} {cv['valid']}/{cv['total']}")
    clarity_path = pathlib.Path(RESULTS_DIR) / "metric5_clarity.json"
    if clarity_path.exists():
        cdata = json.load(open(clarity_path))
        print(f"{'Clarity [1-5]':<35} {cdata['ours']['mean']:.2f}{'':<16} {cdata['claweval']['mean']:.2f}")
    print(f"{'Coherence [0,1]':<35} {ours_mean:.2f}{'':<16} {claweval_mean:.2f}")
    print(f"{'Diversity':<35} {ours_diversity['diversity_score']:.3f}{'':<13} {claweval_diversity['diversity_score']:.3f}")
    print(f"{'Scoring Balance (rule/llm)':<35} {ours_balance['mean_rule_weight']:.0%}/{ours_balance['mean_llm_weight']:.0%}{'':<12} {'n/a (not computed)'}")
    print(f"{'Safety Coverage':<35} {ours_safety['coverage_rate']:.0%}{'':<16} {'n/a (not computed)'}")


if __name__ == "__main__":
    main()
