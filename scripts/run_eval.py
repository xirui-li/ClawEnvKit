"""Run evaluation on all tasks with cost tracking.

Calls the agent (via LLM API) on each task, collects responses,
grades with GradingEngine, and tracks per-model token usage + cost.

Usage:
    # Single model
    python scripts/run_eval.py --model anthropic/claude-sonnet-4.6 --dataset dataset

    # Multiple models
    python scripts/run_eval.py --model anthropic/claude-sonnet-4.6 openai/gpt-5.4 --dataset dataset

    # With parallel workers
    python scripts/run_eval.py --model anthropic/claude-sonnet-4.6 --dataset dataset --workers 4

    # Resume (skip completed)
    python scripts/run_eval.py --model anthropic/claude-sonnet-4.6 --dataset dataset --resume
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import yaml
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from dataclasses import dataclass, field, asdict
from threading import Lock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from clawharness.llm_client import detect_provider
from clawharness.evaluate.engine import GradingEngine

try:
    from tqdm import tqdm
except ImportError:
    tqdm = None

# OpenRouter pricing lookup (loaded once)
_PRICING: dict[str, tuple[float, float]] = {}
_pricing_lock = Lock()


def _load_pricing():
    """Load model pricing from OpenRouter API."""
    global _PRICING
    if _PRICING:
        return
    try:
        import urllib.request
        config_keys = {}
        for candidate in [Path.cwd() / "config.json", PROJECT_ROOT / "config.json"]:
            if candidate.exists():
                config_keys = json.load(open(candidate))
                break
        key = os.environ.get("OPENROUTER_API_KEY", config_keys.get("OPENROUTER_API_KEY", ""))
        if not key:
            return
        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/models",
            headers={"Authorization": f"Bearer {key}"},
        )
        resp = urllib.request.urlopen(req, timeout=15)
        models = json.loads(resp.read())["data"]
        for m in models:
            p = m.get("pricing", {})
            _PRICING[m["id"]] = (
                float(p.get("prompt", 0)),      # per token
                float(p.get("completion", 0)),   # per token
            )
    except Exception:
        pass


def _calc_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Calculate cost in USD for a given model and token counts."""
    _load_pricing()
    if model in _PRICING:
        inp_price, out_price = _PRICING[model]
        return input_tokens * inp_price + output_tokens * out_price
    return 0.0


@dataclass
class ModelCostTracker:
    model: str
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: float = 0.0
    total_tasks: int = 0
    total_graded: int = 0
    scores: list = field(default_factory=list)
    _lock: Lock = field(default_factory=Lock, repr=False)

    def add(self, input_tokens: int, output_tokens: int, score: float | None = None):
        cost = _calc_cost(self.model, input_tokens, output_tokens)
        with self._lock:
            self.total_input_tokens += input_tokens
            self.total_output_tokens += output_tokens
            self.total_cost_usd += cost
            self.total_tasks += 1
            if score is not None:
                self.scores.append(score)
                self.total_graded += 1

    def summary(self) -> dict:
        mean_score = sum(self.scores) / len(self.scores) if self.scores else 0
        return {
            "model": self.model,
            "total_tasks": self.total_tasks,
            "total_graded": self.total_graded,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_cost_usd": round(self.total_cost_usd, 4),
            "mean_score": round(mean_score, 4),
            "cost_per_task": round(self.total_cost_usd / self.total_tasks, 4) if self.total_tasks else 0,
        }


def _call_agent(prompt: str, model: str, provider: str, api_key: str,
                base_url: str) -> tuple[str, int, int]:
    """Call agent LLM, return (response_text, input_tokens, output_tokens)."""
    import urllib.request

    if provider == "anthropic" and not base_url:
        body = json.dumps({
            "model": model,
            "max_tokens": 4096,
            "temperature": 0,
            "messages": [{"role": "user", "content": prompt}],
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
        resp = urllib.request.urlopen(req, timeout=120)
        data = json.loads(resp.read())
        text = data["content"][0]["text"]
        usage = data.get("usage", {})
        return text, usage.get("input_tokens", 0), usage.get("output_tokens", 0)
    else:
        # OpenRouter / OpenAI compatible
        if not base_url:
            base_url = "https://openrouter.ai/api/v1"
        token_key = "max_completion_tokens" if model.startswith("gpt-5") else "max_tokens"
        body = json.dumps({
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            token_key: 4096,
            "temperature": 0,
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{base_url}/chat/completions",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
        )
        resp = urllib.request.urlopen(req, timeout=120)
        data = json.loads(resp.read())
        text = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        return text, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)


def run_task(task_path: Path, model: str, provider: str, api_key: str,
             base_url: str, results_dir: Path, tracker: ModelCostTracker,
             engine: GradingEngine, resume: bool = False) -> dict | None:
    """Run a single task and return grading result."""
    config = yaml.safe_load(open(task_path))
    if not isinstance(config, dict) or "scoring_components" not in config:
        return None

    task_id = config.get("task_id", task_path.stem)
    result_file = results_dir / task_id / "result.json"

    # Resume: skip if already done
    if resume and result_file.exists():
        try:
            existing = json.load(open(result_file))
            tracker.add(
                existing.get("input_tokens", 0),
                existing.get("output_tokens", 0),
                existing.get("final_score"),
            )
            return existing
        except Exception:
            pass

    # Build agent prompt
    prompt = config.get("prompt", "")
    fixtures = config.get("fixtures", {})
    tools = config.get("tools", [])

    # Add tool descriptions to prompt
    if tools:
        tool_desc = "\n\nAvailable tools:\n"
        for t in tools:
            tool_desc += f"- {t.get('name', '')}: {t.get('description', '')} [endpoint: {t.get('endpoint', '')}]\n"
        prompt += tool_desc

    if fixtures:
        prompt += f"\n\nData available:\n{yaml.dump(fixtures)[:1000]}"

    try:
        response, inp_tok, out_tok = _call_agent(prompt, model, provider, api_key, base_url)
    except Exception as e:
        tracker.add(0, 0, 0.0)
        return {"task_id": task_id, "error": str(e)[:200], "final_score": 0.0,
                "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}

    # Grade (simplified — no Docker audit, just output-based checks)
    # For full eval, use Docker runner. This is the lightweight API-only path.
    audit_data = {}  # No real tool calls in API-only mode
    try:
        grading = engine.grade(config, audit_data, response)
        score = grading.final_score
    except Exception:
        score = 0.0

    cost = _calc_cost(model, inp_tok, out_tok)
    tracker.add(inp_tok, out_tok, score)

    result = {
        "task_id": task_id,
        "model": model,
        "final_score": round(score, 4),
        "input_tokens": inp_tok,
        "output_tokens": out_tok,
        "cost_usd": round(cost, 6),
        "response_length": len(response),
    }

    # Save per-task result
    result_file.parent.mkdir(parents=True, exist_ok=True)
    with open(result_file, "w") as f:
        json.dump(result, f, indent=2)

    return result


def main():
    parser = argparse.ArgumentParser(description="Run evaluation with cost tracking")
    parser.add_argument("--model", nargs="+", required=True, help="OpenRouter model ID(s)")
    parser.add_argument("--dataset", default="dataset", help="Dataset directory")
    parser.add_argument("--results", default="eval_results", help="Results directory")
    parser.add_argument("--workers", type=int, default=1, help="Parallel workers")
    parser.add_argument("--resume", action="store_true", help="Skip completed tasks")
    args = parser.parse_args()

    provider, api_key, base_url, _ = detect_provider()
    engine = GradingEngine()

    tasks = sorted(Path(args.dataset).rglob("*.yaml"))
    tasks = [t for t in tasks if t.name != "generation_report.json"]

    print(f"=== Evaluation ===")
    print(f"  Dataset: {args.dataset}/ ({len(tasks)} tasks)")
    print(f"  Models: {args.model}")
    print(f"  Workers: {args.workers}")
    print(f"  Results: {args.results}/")
    print()

    all_summaries = {}

    for model in args.model:
        model_results_dir = Path(args.results) / model.replace("/", "_")
        model_results_dir.mkdir(parents=True, exist_ok=True)

        tracker = ModelCostTracker(model=model)

        print(f"--- {model} ---")

        pbar = tqdm(total=len(tasks), desc=model.split("/")[-1], unit="task") if tqdm else None

        def _run_one(task_path):
            result = run_task(
                task_path, model, provider, api_key, base_url,
                model_results_dir, tracker, engine, resume=args.resume,
            )
            if pbar:
                if result:
                    pbar.set_postfix_str(f"${tracker.total_cost_usd:.2f}")
                pbar.update(1)
            return result

        if args.workers > 1:
            with ThreadPoolExecutor(max_workers=args.workers) as executor:
                futures = [executor.submit(_run_one, t) for t in tasks]
                for future in as_completed(futures):
                    future.result()
        else:
            for t in tasks:
                _run_one(t)

        if pbar:
            pbar.close()

        summary = tracker.summary()
        all_summaries[model] = summary

        print(f"  Score: {summary['mean_score']:.3f}")
        print(f"  Tokens: {summary['total_input_tokens']:,} in / {summary['total_output_tokens']:,} out")
        print(f"  Cost: ${summary['total_cost_usd']:.2f} (${summary['cost_per_task']:.4f}/task)")
        print()

        # Save per-model summary
        with open(model_results_dir / "summary.json", "w") as f:
            json.dump(summary, f, indent=2)

    # Save combined summary
    combined = {
        "dataset": args.dataset,
        "total_tasks": len(tasks),
        "models": all_summaries,
        "total_cost_usd": round(sum(s["total_cost_usd"] for s in all_summaries.values()), 2),
    }
    with open(Path(args.results) / "eval_summary.json", "w") as f:
        json.dump(combined, f, indent=2)

    print(f"=== Total Cost: ${combined['total_cost_usd']:.2f} ===")
    print(f"Report: {args.results}/eval_summary.json")


if __name__ == "__main__":
    main()
