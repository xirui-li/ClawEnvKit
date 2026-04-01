"""Experiment 1: Task Quality — Metric 1 (Validity) + Metric 5 (Clarity)

No agent needed. Compares auto-generated tasks vs Claw-Eval tasks.

Metric 1: Validity Rate — % of configs that pass structural validation
Metric 5: Task Clarity — LLM judges each prompt on a 1-5 scale

Usage:
    python paper_experiments/exp1_task_quality/run_clarity.py
    python paper_experiments/exp1_task_quality/run_clarity.py --skip-clarity  # validity only
"""

import json
import os
import re
import sys
import time
import yaml
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from clawharness.generate.task_generator import validate_task_config, SERVICE_DEFINITIONS

RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
# Metric 1: Validity Rate
# ---------------------------------------------------------------------------

def check_validity_ours() -> dict:
    """Validate all our auto-generated tasks."""
    tasks_dir = PROJECT_ROOT / "dataset_v2"
    results = {"valid": 0, "invalid": 0, "total": 0, "issues": []}

    for f in sorted(tasks_dir.rglob("*.yaml")):
        config = yaml.safe_load(open(f))
        results["total"] += 1

        # Extract services from tools
        tools = config.get("tools", [])
        services = sorted(set(t.get("service", "") for t in tools if t.get("service")))
        if not services:
            services = [config.get("task_id", "").split("-")[0]]

        issues = validate_task_config(config, services=services)
        if issues:
            results["invalid"] += 1
            results["issues"].append({"task": config.get("task_id", f.name), "issues": issues})
        else:
            results["valid"] += 1

    return results


def check_validity_claweval() -> dict:
    """Check Claw-Eval task validity (structural check on their config)."""
    baseline = PROJECT_ROOT / "claw_eval_baseline" / "general.json"
    tasks = json.load(open(baseline))

    results = {"valid": 0, "invalid": 0, "total": 0, "issues": []}
    for t in tasks:
        results["total"] += 1
        issues = []

        if not t.get("query", "").strip():
            issues.append("Empty query/prompt")
        if not t.get("rubric", "").strip():
            issues.append("Empty rubric")
        if not t.get("task_id", "").strip():
            issues.append("Missing task_id")

        if issues:
            results["invalid"] += 1
            results["issues"].append({"task": t.get("task_id", "?"), "issues": issues})
        else:
            results["valid"] += 1

    return results


# ---------------------------------------------------------------------------
# Metric 5: Task Clarity (LLM judge rates each prompt 1-5)
# ---------------------------------------------------------------------------

CLARITY_RUBRIC = """Rate the following task prompt for an AI agent on a 1-5 scale:

1 = Incomprehensible — cannot understand what the agent should do
2 = Vague — general direction but missing key details (what, where, how much)
3 = Ambiguous — understandable but multiple valid interpretations exist
4 = Clear — one clear interpretation, minor details could be more specific
5 = Excellent — unambiguous, specific, actionable, all necessary details present

Task prompt:
{prompt}

Respond with JSON only: {{"score": <int 1-5>, "reasoning": "<brief explanation>"}}"""


def rate_clarity(prompt: str, api_key: str) -> dict:
    """Rate a single prompt's clarity using LLM judge."""
    import urllib.request

    body = json.dumps({
        "model": "claude-haiku-4-5",
        "max_tokens": 200,
        "messages": [{"role": "user", "content": CLARITY_RUBRIC.format(prompt=prompt[:1500])}],
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=body,
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
    )

    resp = urllib.request.urlopen(req, timeout=30)
    data = json.loads(resp.read())
    content = data["content"][0]["text"].strip()

    try:
        # Try JSON parse
        result = json.loads(content.strip("`").strip())
        return {"score": int(result["score"]), "reasoning": result.get("reasoning", "")}
    except (json.JSONDecodeError, KeyError, ValueError):
        # Fallback: extract number
        match = re.search(r'[1-5]', content)
        if match:
            return {"score": int(match.group()), "reasoning": content[:100]}
        return {"score": 3, "reasoning": "parse_failed"}


def evaluate_clarity_ours(api_key: str) -> list[dict]:
    """Rate clarity of all our tasks."""
    tasks_dir = PROJECT_ROOT / "dataset_v2"
    results = []

    for f in sorted(tasks_dir.rglob("*.yaml")):
        config = yaml.safe_load(open(f))
        prompt = config.get("prompt", "")
        task_id = config.get("task_id", f.stem)

        rating = rate_clarity(prompt, api_key)
        results.append({"task_id": task_id, "source": "auto", **rating})
        print(f"  [auto] {task_id}: {rating['score']}/5")
        time.sleep(0.3)

    return results


def evaluate_clarity_claweval(api_key: str) -> list[dict]:
    """Rate clarity of Claw-Eval tasks."""
    baseline = PROJECT_ROOT / "claw_eval_baseline" / "general.json"
    tasks = json.load(open(baseline))
    results = []

    for t in tasks:
        prompt = t.get("query", "")
        task_id = t.get("task_id", "?")

        rating = rate_clarity(prompt, api_key)
        results.append({"task_id": task_id, "source": "human", **rating})
        print(f"  [human] {task_id}: {rating['score']}/5")
        time.sleep(0.3)

    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-clarity", action="store_true", help="Skip clarity evaluation (API calls)")
    args = parser.parse_args()

    print("=" * 60)
    print("Experiment 1: Task Quality — Metric 1 (Validity) + Metric 5 (Clarity)")
    print("=" * 60)

    # --- Metric 1: Validity ---
    print("\n--- Metric 1: Validity Rate ---")
    ours_validity = check_validity_ours()
    claweval_validity = check_validity_claweval()

    print(f"  Ours (auto):     {ours_validity['valid']}/{ours_validity['total']} = {ours_validity['valid']/ours_validity['total']:.1%}")
    print(f"  Claw-Eval (human): {claweval_validity['valid']}/{claweval_validity['total']} = {claweval_validity['valid']/claweval_validity['total']:.1%}")

    if ours_validity["issues"]:
        print(f"  Issues in our tasks:")
        for issue in ours_validity["issues"][:5]:
            print(f"    {issue['task']}: {issue['issues']}")

    # Save validity results
    validity_results = {
        "ours": ours_validity,
        "claweval": claweval_validity,
    }
    with open(RESULTS_DIR / "metric1_validity.json", "w") as f:
        json.dump(validity_results, f, indent=2)

    if args.skip_clarity:
        print("\n[Skipping clarity evaluation]")
        return

    # --- Metric 5: Clarity ---
    print("\n--- Metric 5: Task Clarity (LLM Judge 1-5) ---")

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        config_path = PROJECT_ROOT / "config.json"
        if config_path.exists():
            cfg = json.load(open(config_path))
            api_key = cfg.get("claude", cfg.get("ANTHROPIC_API_KEY", ""))
    if not api_key:
        print("ERROR: No ANTHROPIC_API_KEY")
        sys.exit(1)

    print("\n  Rating auto-generated tasks...")
    ours_clarity = evaluate_clarity_ours(api_key)

    print("\n  Rating Claw-Eval tasks...")
    claweval_clarity = evaluate_clarity_claweval(api_key)

    # Compute stats
    ours_scores = [r["score"] for r in ours_clarity]
    claweval_scores = [r["score"] for r in claweval_clarity]

    ours_mean = sum(ours_scores) / len(ours_scores)
    claweval_mean = sum(claweval_scores) / len(claweval_scores)

    print(f"\n  Results:")
    print(f"    Ours (auto):     {ours_mean:.2f} ± {(sum((s-ours_mean)**2 for s in ours_scores)/len(ours_scores))**0.5:.2f} (n={len(ours_scores)})")
    print(f"    Claw-Eval (human): {claweval_mean:.2f} ± {(sum((s-claweval_mean)**2 for s in claweval_scores)/len(claweval_scores))**0.5:.2f} (n={len(claweval_scores)})")

    # Simple t-test approximation
    diff = abs(ours_mean - claweval_mean)
    print(f"    Difference: {diff:.2f}")
    print(f"    {'PASS' if diff < 0.5 else 'FAIL'}: difference {'<' if diff < 0.5 else '>'} 0.5")

    # Distribution
    for source, scores in [("auto", ours_scores), ("human", claweval_scores)]:
        dist = {i: scores.count(i) for i in range(1, 6)}
        print(f"    {source}: " + " ".join(f"{k}★={v}" for k, v in dist.items()))

    # Save clarity results
    clarity_results = {
        "ours": {"mean": ours_mean, "scores": ours_clarity},
        "claweval": {"mean": claweval_mean, "scores": claweval_clarity},
        "difference": diff,
    }
    with open(RESULTS_DIR / "metric5_clarity.json", "w") as f:
        json.dump(clarity_results, f, indent=2)

    # --- Summary Table ---
    print("\n" + "=" * 60)
    print("EXPERIMENT 1 RESULTS (Metric 1 + 5)")
    print("=" * 60)
    print(f"{'Metric':<30} {'Ours (Auto)':<20} {'Claw-Eval (Human)':<20} {'Fair?'}")
    print("-" * 80)
    print(f"{'Validity Rate':<30} {ours_validity['valid']/ours_validity['total']:.1%}{'':<14} {claweval_validity['valid']/claweval_validity['total']:.1%}{'':<14} {'✅' if abs(ours_validity['valid']/ours_validity['total'] - 1.0) < 0.05 else '❌'}")
    print(f"{'Task Clarity (1-5)':<30} {ours_mean:.2f}{'':<16} {claweval_mean:.2f}{'':<16} {'✅' if diff < 0.5 else '❌'}")


if __name__ == "__main__":
    main()
