"""Unified CLI for Claw Harness.

Usage:
    claw-harness eval todo-001                    Run single task
    claw-harness eval-all --service todo           Run all tasks for a service
    claw-harness generate --service gmail --count 5  Generate tasks
    claw-harness services                          List services
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import yaml
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_ROOT.parent


def _load_api_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if key:
        return key
    config_path = PROJECT_ROOT / "config.json"
    if config_path.exists():
        config = json.load(open(config_path))
        return config.get("ANTHROPIC_API_KEY") or config.get("claude") or ""
    return ""


def cmd_eval(args):
    """Run evaluation on a single task."""
    from .evaluate.engine import GradingEngine

    task_name = args.task
    model = args.model or os.environ.get("MODEL", "claude-sonnet-4-6")

    # Find task yaml
    task_yaml = _find_task(task_name)
    service = _get_service(task_yaml)

    results_dir = Path(args.results) / task_name
    results_dir.mkdir(parents=True, exist_ok=True)

    print(f"🦞 Running {task_name} (model: {model})")

    # Use Docker
    import subprocess
    image = os.environ.get("CLAW_HARNESS_IMAGE", "claw-harness:base")

    result = subprocess.run([
        "docker", "run", "--rm",
        "-e", f"ANTHROPIC_API_KEY={_load_api_key()}",
        "-e", f"MODEL={model}",
        "-v", f"{task_yaml}:/opt/claw-harness/task.yaml:ro",
        "-v", f"{results_dir}:/logs",
        image,
    ], capture_output=False, timeout=300)

    reward_file = results_dir / "reward.txt"
    if reward_file.exists():
        print(f"\nResults: {results_dir}/")


def cmd_eval_all(args):
    """Run all tasks for a service (or all services)."""
    service = args.service
    model = args.model or os.environ.get("MODEL", "claude-sonnet-4-6")

    dataset_dir = PROJECT_ROOT / "dataset"
    if service:
        task_dirs = [dataset_dir / service]
    else:
        task_dirs = sorted(d for d in dataset_dir.iterdir() if d.is_dir())

    tasks = []
    for d in task_dirs:
        tasks.extend(sorted(d.glob("*.yaml")))

    print(f"🦞 Running {len(tasks)} tasks (model: {model})")

    results_dir = Path(args.results)
    import subprocess

    for i, task_yaml in enumerate(tasks):
        config = yaml.safe_load(open(task_yaml))
        task_id = config.get("task_id", task_yaml.stem)
        task_results = results_dir / task_id

        # Skip if done
        if (task_results / "reward.txt").exists() and not args.force:
            score = (task_results / "reward.txt").read_text().strip()
            print(f"  [{i+1}/{len(tasks)}] SKIP {task_id} ({score})")
            continue

        task_results.mkdir(parents=True, exist_ok=True)
        print(f"  [{i+1}/{len(tasks)}] {task_id}:", end=" ", flush=True)

        image = os.environ.get("CLAW_HARNESS_IMAGE", "claw-harness:base")
        result = subprocess.run([
            "docker", "run", "--rm",
            "-e", f"ANTHROPIC_API_KEY={_load_api_key()}",
            "-e", f"MODEL={model}",
            "-v", f"{task_yaml}:/opt/claw-harness/task.yaml:ro",
            "-v", f"{task_results}:/logs",
            image,
        ], capture_output=True, text=True, timeout=300)

        score = result.stdout.strip().split("\n")[-1] if result.stdout else "FAIL"
        print(score)

    # Summary
    scores = []
    for d in results_dir.iterdir():
        reward = d / "reward.txt"
        if reward.exists():
            try:
                scores.append(float(reward.read_text().strip()))
            except ValueError:
                pass

    if scores:
        print(f"\n=== Summary ===")
        print(f"  Tasks: {len(scores)}")
        print(f"  Average: {sum(scores)/len(scores):.2f}")
        print(f"  Min: {min(scores):.2f}, Max: {max(scores):.2f}")


def cmd_generate(args):
    """Generate task configs."""
    from .generate.task_generator import (
        SERVICE_DEFINITIONS, generate_task_config_prompt, ingest_task_config,
    )

    api_key = _load_api_key()
    if not api_key:
        print("ERROR: No API key", file=sys.stderr)
        sys.exit(1)

    service = args.service
    count = args.count
    difficulty = args.difficulty
    output = Path(args.output) / service
    output.mkdir(parents=True, exist_ok=True)

    print(f"Generating {count} {difficulty} tasks for {service}...")

    import anthropic
    import time
    client = anthropic.Anthropic(api_key=api_key)
    model = os.environ.get("MODEL", "claude-sonnet-4-6")

    FORMAT_HINT = "\n\nIMPORTANT: scoring_components must have check.type from: audit_action_exists, audit_field_equals, audit_field_contains, audit_count_gte, keywords_present, keywords_absent, llm_judge\nsafety_checks: [{type: tool_not_called, tool_name: <name>}]"

    valid = 0
    for i in range(count):
        prompt = generate_task_config_prompt(service, difficulty=difficulty, task_number=i+1) + FORMAT_HINT

        for attempt in range(3):
            try:
                response = client.messages.create(
                    model=model, max_tokens=4096,
                    messages=[{"role": "user", "content": prompt}],
                )
                config = ingest_task_config(response.content[0].text, service, task_number=i+1)
                config["task_id"] = f"{service}-{i+1:03d}"

                out_path = output / f"{config['task_id']}.yaml"
                with open(out_path, "w") as f:
                    yaml.dump(config, f, default_flow_style=False, allow_unicode=True)

                print(f"  ✅ [{i+1}/{count}] {config.get('task_name', '')[:50]}")
                valid += 1
                break
            except Exception as e:
                if attempt < 2:
                    time.sleep(1)
                else:
                    print(f"  ❌ [{i+1}/{count}] {str(e)[:60]}")
        time.sleep(0.5)

    print(f"\nDone: {valid}/{count} in {output}/")


def cmd_services(args):
    """List available services."""
    from .generate.task_generator import SERVICE_DEFINITIONS
    print(f"{'Service':<15} {'Description':<50} {'Endpoints'}")
    print("-" * 75)
    for name, svc in sorted(SERVICE_DEFINITIONS.items()):
        print(f"{name:<15} {svc['description'][:50]:<50} {len(svc['endpoints'])}")


def _find_task(name: str) -> Path:
    """Find task yaml by name."""
    # Direct path
    p = Path(name)
    if p.exists():
        return p.resolve()

    # dataset/<service>/<name>.yaml
    service = name.rsplit("-", 1)[0] if "-" in name else name
    p = PROJECT_ROOT / "dataset" / service / f"{name}.yaml"
    if p.exists():
        return p.resolve()

    print(f"ERROR: Task not found: {name}", file=sys.stderr)
    sys.exit(1)


def _get_service(task_yaml: Path) -> str:
    config = yaml.safe_load(open(task_yaml))
    return config.get("task_id", "").split("-")[0]


def main():
    parser = argparse.ArgumentParser(
        prog="claw-harness",
        description="🦞 Claw Harness — AI Agent Evaluation",
    )
    sub = parser.add_subparsers(dest="command")

    # eval
    p = sub.add_parser("eval", help="Run evaluation on a task")
    p.add_argument("task", help="Task ID (e.g., todo-001) or path to yaml")
    p.add_argument("--model", help="LLM model (default: claude-sonnet-4-6)")
    p.add_argument("--results", default=os.path.expanduser("~/claw-results"))

    # eval-all
    p = sub.add_parser("eval-all", help="Run all tasks")
    p.add_argument("--service", help="Service name (default: all)")
    p.add_argument("--model", help="LLM model")
    p.add_argument("--results", default=os.path.expanduser("~/claw-results"))
    p.add_argument("--force", action="store_true", help="Re-run completed tasks")

    # generate
    p = sub.add_parser("generate", help="Generate task configs")
    p.add_argument("--service", required=True)
    p.add_argument("--count", type=int, default=5)
    p.add_argument("--difficulty", default="medium")
    p.add_argument("--output", default="tasks")

    # services
    sub.add_parser("services", help="List available services")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    {"eval": cmd_eval, "eval-all": cmd_eval_all,
     "generate": cmd_generate, "services": cmd_services}[args.command](args)


if __name__ == "__main__":
    main()
