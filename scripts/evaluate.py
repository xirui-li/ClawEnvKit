#!/usr/bin/env python3
"""Unified evaluation runner for ClawHarnessing.

Usage:
    # Single model
    python scripts/evaluate.py --model anthropic/claude-sonnet-4.6

    # Multiple models (paper table)
    python scripts/evaluate.py --preset paper

    # Custom
    python scripts/evaluate.py --model openai/gpt-5.4 z-ai/glm-5 --dataset dataset_x10 --workers 10

    # Resume interrupted run
    python scripts/evaluate.py --preset paper --resume

    # Different agent image
    python scripts/evaluate.py --model anthropic/claude-sonnet-4.6 --agent claudecode
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import yaml
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock

try:
    from tqdm import tqdm
except ImportError:
    tqdm = None

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ── Agent images ────────────────────────────────────────────────────

AGENT_IMAGES = {
    "openclaw":   "clawharness:openclaw",
    "claudecode": "clawharness:claudecode",
    "nanoclaw":   "clawharness:nanoclaw",
    "ironclaw":   "clawharness:ironclaw",
    "copaw":      "clawharness:copaw",
    "picoclaw":   "clawharness:picoclaw",
    "zeroclaw":   "clawharness:zeroclaw",
    "nemoclaw":   "clawharness:nemoclaw",
    "hermes":     "clawharness:hermes",
    "base":       "clawharness:base",
}

# ── Default models (all 10 backbone models) ────────────────────────

ALL_MODELS = [
    "anthropic/claude-opus-4.6",
    "anthropic/claude-sonnet-4.6",
    "openai/gpt-5.4",
    "openai/gpt-5-nano",
    "z-ai/glm-5-turbo",
    "z-ai/glm-5",
    "minimax/minimax-m2.7",
    "minimax/minimax-m2.5",
    "xiaomi/mimo-v2-pro",
    "xiaomi/mimo-v2-omni",
]

# ── API key loading ─────────────────────────────────────────────────

def load_api_keys() -> dict[str, str]:
    """Load API keys from env vars + config.json."""
    keys = {}
    config_path = PROJECT_ROOT / "config.json"
    if config_path.exists():
        try:
            cfg = json.load(open(config_path))
            keys["OPENROUTER_API_KEY"] = cfg.get("OPENROUTER_API_KEY", "")
            keys["ANTHROPIC_API_KEY"] = cfg.get("claude", cfg.get("ANTHROPIC_API_KEY", ""))
            keys["OPENAI_API_KEY"] = cfg.get("OPENAI_API_KEY", "")
        except Exception:
            pass

    # Env vars override config.json
    for k in ("OPENROUTER_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        env_val = os.environ.get(k, "")
        if env_val:
            keys[k] = env_val

    return {k: v for k, v in keys.items() if v}


# ── Evaluator ───────────────────────────────────────────────────────

@dataclass
class TaskResult:
    task_id: str
    model: str
    category: str = ""
    services: list = field(default_factory=list)
    claw_eval_id: str = ""
    safety: float = 0.0
    completion: float = 0.0
    robustness: float = 0.0
    final_score: float = 0.0
    num_tool_calls: int = 0
    safety_violations: list = field(default_factory=list)
    components: list = field(default_factory=list)
    latency_seconds: float = 0.0
    error: str = ""

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


class Evaluator:
    """Run evaluation across models and tasks using Docker containers."""

    def __init__(
        self,
        dataset: str = "dataset_x10",
        results_dir: str = "paper_results",
        agent: str = "openclaw",
        workers: int = 10,
        timeout: int = 300,
        resume: bool = False,
    ):
        self.dataset = Path(dataset)
        self.results_dir = Path(results_dir)
        self.agent = agent
        self.image = AGENT_IMAGES.get(agent, agent)
        self.workers = workers
        self.timeout = timeout
        self.resume = resume
        self.api_keys = load_api_keys()

        # Load tasks
        self.tasks = sorted(
            f for f in self.dataset.rglob("*.yaml")
            if f.name != "generation_report.json"
        )

        # Build task_id → claw_eval_id mapping
        self.task_meta = {}
        for f in self.tasks:
            try:
                c = yaml.safe_load(open(f))
                if isinstance(c, dict):
                    tid = c.get("task_id", f.stem)
                    self.task_meta[tid] = {
                        "category": c.get("category", ""),
                        "services": sorted(set(
                            t.get("service", "") for t in c.get("tools", []) if t.get("service")
                        )),
                        "claw_eval_id": c.get("claw_eval_id", ""),
                    }
            except Exception:
                pass

    def _check_prerequisites(self):
        """Verify Docker image exists and API keys available."""
        result = subprocess.run(
            ["docker", "image", "inspect", self.image],
            capture_output=True,
        )
        if result.returncode != 0:
            print(f"ERROR: Docker image '{self.image}' not found.")
            print(f"  docker build -f docker/Dockerfile.{self.agent} -t {self.image} .")
            sys.exit(1)

        if not self.api_keys:
            print("ERROR: No API keys found (config.json or env vars).")
            sys.exit(1)

    def _build_env_flags(self, model: str) -> list[str]:
        """Build Docker -e flags for API keys + model."""
        flags = ["-e", f"MODEL={model}"]
        for key, val in self.api_keys.items():
            flags.extend(["-e", f"{key}={val}"])
        return flags

    def _run_one_task(self, task_path: Path, model: str, model_dir: Path) -> TaskResult:
        """Run a single task in Docker and parse grading.json."""
        config = yaml.safe_load(open(task_path))
        if not isinstance(config, dict):
            return TaskResult(task_id=task_path.stem, model=model, error="invalid yaml")

        task_id = config.get("task_id", task_path.stem)
        task_results_dir = model_dir / task_id
        grading_file = task_results_dir / "grading.json"
        reward_file = task_results_dir / "reward.txt"

        # Resume: skip if done
        if self.resume and grading_file.exists():
            try:
                g = json.load(open(grading_file))
                meta = self.task_meta.get(g.get("task_id", task_id), {})
                return TaskResult(
                    task_id=g.get("task_id", task_id),
                    model=model,
                    category=g.get("category", meta.get("category", "")),
                    services=g.get("services", meta.get("services", [])),
                    claw_eval_id=meta.get("claw_eval_id", ""),
                    safety=g.get("safety", 0),
                    completion=g.get("completion", 0),
                    robustness=g.get("robustness", 0),
                    final_score=g.get("final_score", 0),
                    num_tool_calls=g.get("num_tool_calls", 0),
                    safety_violations=g.get("safety_violations", []),
                    components=g.get("components", []),
                )
            except Exception:
                pass

        task_results_dir.mkdir(parents=True, exist_ok=True)
        abs_yaml = str(task_path.resolve())
        container_name = f"claw-eval-{task_id}-{int(time.time()*1000) % 100000}"

        # Mount fixture files if task has files[] field
        file_mounts = []
        task_dir = task_path.parent
        for file_entry in config.get("files", []):
            src = file_entry.get("source", "")
            target = file_entry.get("target", "")
            if not src or not target:
                continue
            # Try to find fixture file relative to task dir or dataset dir
            for candidate in [
                task_dir / src,
                task_dir / "fixtures" / src,
                self.dataset / task_dir.name / "fixtures" / src,
            ]:
                if candidate.exists():
                    file_mounts.extend(["-v", f"{candidate.resolve()}:{target}:ro"])
                    break
                    break

        t0 = time.time()
        try:
            # Run container (not --rm, we need to docker cp results out)
            # Don't capture/redirect — let entrypoint's tee handle agent output
            subprocess.run(
                [
                    "docker", "run", "--name", container_name,
                    "--user", "0", "-e", "HOME=/home/node",
                    *self._build_env_flags(model),
                    "-v", f"{abs_yaml}:/opt/clawharness/task.yaml:ro",
                    *file_mounts,
                    self.image,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=self.timeout,
            )
            # Copy results from container /logs/ to host
            subprocess.run(
                ["docker", "cp", f"{container_name}:/logs/.", str(task_results_dir)],
                capture_output=True, timeout=10,
            )
            # agent_output is now inside grading.json, no separate cp needed
        except subprocess.TimeoutExpired:
            return TaskResult(task_id=task_id, model=model, error="timeout")
        except Exception as e:
            return TaskResult(task_id=task_id, model=model, error=str(e)[:100])
        finally:
            subprocess.run(["docker", "rm", "-f", container_name],
                           capture_output=True, timeout=10)

        latency = time.time() - t0
        meta = self.task_meta.get(task_id, {})

        # Parse grading.json
        if grading_file.exists():
            try:
                g = json.load(open(grading_file))
                return TaskResult(
                    task_id=g.get("task_id", task_id),
                    model=model,
                    category=g.get("category", meta.get("category", "")),
                    services=g.get("services", meta.get("services", [])),
                    claw_eval_id=meta.get("claw_eval_id", ""),
                    safety=g.get("safety", 0),
                    completion=g.get("completion", 0),
                    robustness=g.get("robustness", 0),
                    final_score=g.get("final_score", 0),
                    num_tool_calls=g.get("num_tool_calls", 0),
                    safety_violations=g.get("safety_violations", []),
                    components=g.get("components", []),
                    latency_seconds=latency,
                )
            except Exception:
                pass

        # Fallback: read reward.txt
        if reward_file.exists():
            try:
                score = float(reward_file.read_text().strip())
                return TaskResult(task_id=task_id, model=model, final_score=score,
                                  latency_seconds=latency, **meta)
            except Exception:
                pass

        return TaskResult(task_id=task_id, model=model, error="no output",
                          latency_seconds=latency)

    def run_model(self, model: str) -> dict:
        """Run all tasks for a single model. Returns summary dict."""
        model_dir_name = model.replace("/", "_")
        model_dir = self.results_dir / model_dir_name
        model_dir.mkdir(parents=True, exist_ok=True)

        # Check if already complete
        summary_file = model_dir / "summary.json"
        if self.resume and summary_file.exists():
            try:
                s = json.load(open(summary_file))
                if s.get("completed", 0) == len(self.tasks):
                    print(f"  SKIP {model} (already complete, score={s.get('mean_score', '?')})")
                    return s
            except Exception:
                pass

        results: list[TaskResult] = []
        lock = Lock()

        desc = model.split("/")[-1]
        pbar = tqdm(total=len(self.tasks), desc=desc, unit="task",
                    bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}] {postfix}") if tqdm else None

        def _worker(task_path):
            r = self._run_one_task(task_path, model, model_dir)
            with lock:
                results.append(r)
                # Save per-task result
                result_file = model_dir / r.task_id / "result.json"
                result_file.parent.mkdir(parents=True, exist_ok=True)
                with open(result_file, "w") as f:
                    json.dump(r.to_dict(), f, indent=2)
            if pbar:
                pbar.set_postfix_str(f"score={r.final_score:.2f}")
                pbar.update(1)
            return r

        with ThreadPoolExecutor(max_workers=self.workers) as executor:
            futures = [executor.submit(_worker, t) for t in self.tasks]
            for future in as_completed(futures):
                future.result()

        if pbar:
            pbar.close()

        # Compute summary
        scored = [r for r in results if not r.error]
        n = len(scored)
        mean = lambda key: round(sum(getattr(r, key) for r in scored) / n, 4) if n else 0

        summary = {
            "model": model,
            "agent": self.agent,
            "dataset": str(self.dataset),
            "total_tasks": len(self.tasks),
            "completed": n,
            "errors": len(results) - n,
            "mean_safety": mean("safety"),
            "mean_completion": mean("completion"),
            "mean_robustness": mean("robustness"),
            "mean_score": mean("final_score"),
            "mean_latency": mean("latency_seconds"),
            "safety_violation_rate": round(sum(1 for r in scored if r.safety < 1) / n, 4) if n else 0,
            "mean_tool_calls": round(sum(r.num_tool_calls for r in scored) / n, 1) if n else 0,
        }

        # Save summary (crash-safe: written after every model)
        with open(summary_file, "w") as f:
            json.dump(summary, f, indent=2)

        # Save all results for analysis
        with open(model_dir / "all_results.json", "w") as f:
            json.dump([r.to_dict() for r in results], f, indent=2)

        print(f"  {model}: score={summary['mean_score']:.3f} safety={summary['mean_safety']:.2f} "
              f"completion={summary['mean_completion']:.2f} ({n}/{len(self.tasks)} tasks)")

        return summary

    def run(self, models: list[str]) -> dict:
        """Run all models. Returns combined summary."""
        self._check_prerequisites()

        print(f"{'='*60}")
        print(f"  ClawHarnessing Evaluation")
        print(f"{'='*60}")
        print(f"  Agent:    {self.agent} ({self.image})")
        print(f"  Dataset:  {self.dataset}/ ({len(self.tasks)} tasks)")
        print(f"  Models:   {len(models)}")
        print(f"  Workers:  {self.workers} parallel containers")
        print(f"  Results:  {self.results_dir}/")
        print(f"  Resume:   {self.resume}")
        print(f"{'='*60}\n")

        start = time.time()
        all_summaries = {}

        for model in models:
            print(f"\n--- {model} ---")
            summary = self.run_model(model)
            all_summaries[model] = summary

        elapsed = time.time() - start

        # Combined summary
        combined = {
            "agent": self.agent,
            "dataset": str(self.dataset),
            "total_tasks": len(self.tasks),
            "total_models": len(models),
            "elapsed_seconds": round(elapsed),
            "elapsed_minutes": round(elapsed / 60, 1),
            "models": all_summaries,
        }
        with open(self.results_dir / "eval_combined.json", "w") as f:
            json.dump(combined, f, indent=2)

        # Generate paper table
        self._generate_paper_table(all_summaries)

        print(f"\n{'='*60}")
        print(f"  Done: {len(models)} models × {len(self.tasks)} tasks in {elapsed/60:.1f}m")
        print(f"  Results: {self.results_dir}/")
        print(f"{'='*60}")

        return combined

    def _generate_paper_table(self, summaries: dict):
        """Generate markdown table with Full (×10) and Mini (×1 per ID) columns."""
        lines = ["# Evaluation Results\n"]

        # Header
        lines.append("| Family | Model | Safety | Compl. | Robust. | Mean |")
        lines.append("|---|---|---|---|---|---|")

        family_map = {
            "anthropic": "Anthropic", "openai": "OpenAI", "z-ai": "Zhipu AI",
            "minimax": "MiniMax", "xiaomi": "Xiaomi", "google": "Google",
            "deepseek": "DeepSeek", "x-ai": "xAI", "moonshotai": "Moonshot",
            "meta-llama": "Meta", "qwen": "Alibaba", "nvidia": "NVIDIA",
            "mistralai": "Mistral", "stepfun": "StepFun",
        }

        for model, s in summaries.items():
            provider = model.split("/")[0]
            family = family_map.get(provider, provider)
            name = model.split("/")[-1]
            lines.append(
                f"| {family} | **{name}** "
                f"| {s['mean_safety']:.2f} "
                f"| {s['mean_completion']:.2f} "
                f"| {s['mean_robustness']:.2f} "
                f"| {s['mean_score']:.2f} |"
            )

        lines.append(f"\nDataset: `{self.dataset}/` ({len(self.tasks)} tasks)")
        lines.append(f"Agent: {self.agent} (`{self.image}`)")

        table_path = self.results_dir / "paper_table.md"
        with open(table_path, "w") as f:
            f.write("\n".join(lines))
        print(f"\n  Paper table: {table_path}")


# ── CLI ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="ClawHarnessing Evaluator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/evaluate.py                                   # all 10 models × 1039 tasks
  python scripts/evaluate.py --model openai/gpt-5.4            # single model
  python scripts/evaluate.py --model openai/gpt-5.4 z-ai/glm-5 # multiple models
  python scripts/evaluate.py --dataset dataset --workers 5      # 104 tasks, 5 parallel
  python scripts/evaluate.py --resume                           # resume interrupted
  python scripts/evaluate.py --agent claudecode                 # Claude Code agent
        """,
    )
    parser.add_argument("--model", nargs="+", help="OpenRouter model ID(s). Default: all 10 models")
    parser.add_argument("--dataset", default="dataset_x10", help="Dataset directory (default: dataset_x10)")
    parser.add_argument("--results", default="eval_results", help="Results directory")
    parser.add_argument("--agent", default="openclaw", choices=list(AGENT_IMAGES.keys()), help="Agent image")
    parser.add_argument("--workers", type=int, default=10, help="Parallel Docker containers")
    parser.add_argument("--timeout", type=int, default=300, help="Per-task timeout (seconds)")
    parser.add_argument("--resume", action="store_true", help="Skip completed tasks/models")
    args = parser.parse_args()

    models = args.model if args.model else ALL_MODELS

    evaluator = Evaluator(
        dataset=args.dataset,
        results_dir=args.results,
        agent=args.agent,
        workers=args.workers,
        timeout=args.timeout,
        resume=args.resume,
    )
    evaluator.run(models)


if __name__ == "__main__":
    main()
