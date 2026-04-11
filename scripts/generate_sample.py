"""Generate a random sample of 10 tasks for validation.

Quick test before full 153-task generation.

Usage:
    python scripts/generate_sample.py
    python scripts/generate_sample.py --count 5
    python scripts/generate_sample.py --api-only
"""

from __future__ import annotations

import json
import os
import random
import sys
import time
import yaml
from pathlib import Path
from collections import defaultdict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.generate_dataset import (
    build_plan, generate_api_tasks, generate_file_tasks,
    FORMAT_HINT, FILE_FORMAT_HINT, verify,
)
from clawenvkit.llm_client import detect_provider, call_llm
from clawenvkit.generate.task_generator import (
    SERVICE_DEFINITIONS, generate_task_config_prompt, ingest_task_config,
)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Generate sample tasks for validation")
    parser.add_argument("--count", type=int, default=10, help="Number of tasks to sample")
    parser.add_argument("--api-only", action="store_true", help="Only API tasks")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--output", default="dataset_sample", help="Output directory")
    args = parser.parse_args()

    plan = build_plan(api_only=args.api_only)

    api_tasks = [p for p in plan if p["source"] != "file-dep"]
    file_tasks = [p for p in plan if p["source"] == "file-dep"]

    random.seed(args.seed)

    if args.api_only or not file_tasks:
        sample = random.sample(api_tasks, min(args.count, len(api_tasks)))
    else:
        # Mix: ~80% API, ~20% file
        n_file = max(1, args.count // 5)
        n_api = args.count - n_file
        sample = (
            random.sample(api_tasks, min(n_api, len(api_tasks)))
            + random.sample(file_tasks, min(n_file, len(file_tasks)))
        )

    print(f"=== Sample Generation ({len(sample)} tasks) ===")
    for i, p in enumerate(sample):
        svcs = ",".join(p["services"]) if p["services"] else "(file)"
        print(f"  {i+1}. [{p['source']:10s}] {p['claw_eval_id']:40s} {svcs}")

    output_dir = Path(args.output)
    if output_dir.exists():
        import shutil
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    provider, api_key, base_url, model = detect_provider()
    print(f"\nProvider: {provider} | Model: {model}\n")

    # Generate API tasks from sample
    api_sample = [p for p in sample if p["source"] != "file-dep"]
    file_sample = [p for p in sample if p["source"] == "file-dep"]

    api_ok = 0
    for i, item in enumerate(api_sample):
        svc_list = item["services"]
        dir_name = "_".join(svc_list) if len(svc_list) > 1 else svc_list[0]
        out = output_dir / dir_name
        out.mkdir(parents=True, exist_ok=True)
        task_id = f"{dir_name}-sample-{i+1:02d}"

        all_actions = []
        for svc in svc_list:
            svc_def = SERVICE_DEFINITIONS.get(svc, {})
            all_actions.extend(svc_def.get("actions", []))
        focus = all_actions[i % len(all_actions)] if all_actions else ""

        base_prompt = generate_task_config_prompt(
            services=svc_list, difficulty="medium",
            task_number=i + 1, focus_action=focus,
        ) + FORMAT_HINT

        last_error = ""
        for attempt in range(5):
            try:
                prompt = base_prompt
                if last_error:
                    prompt += (
                        f"\n\n## PREVIOUS ATTEMPT FAILED — FIX THESE ERRORS:\n"
                        f"{last_error}\n"
                        f"Generate a corrected YAML that fixes ALL the above issues."
                    )
                response = call_llm(
                    prompt, max_tokens=4096,
                    provider=provider, api_key=api_key,
                    base_url=base_url, model=model,
                )
                config = ingest_task_config(response, services=svc_list, task_number=i + 1)
                config["task_id"] = task_id
                config["category"] = item["category"]
                config["claw_eval_id"] = item["claw_eval_id"]

                out_path = out / f"{task_id}.yaml"
                with open(out_path, "w") as f:
                    yaml.dump(config, f, default_flow_style=False, allow_unicode=True)

                print(f"  ✅ [{i+1}/{len(api_sample)}] {config.get('task_name', '')[:50]}")
                api_ok += 1
                break
            except Exception as e:
                last_error = str(e)
                if attempt < 4:
                    print(f"  ⚠️  [{i+1}/{len(api_sample)}] retry {attempt+1}: {last_error[:60]}")
                    time.sleep(1)
                else:
                    print(f"  ❌ [{i+1}/{len(api_sample)}] FAILED: {last_error[:80]}")
        time.sleep(0.5)

    # Generate file tasks from sample
    file_ok = generate_file_tasks(
        file_sample, output_dir, dry_run=False,
        provider=provider, api_key=api_key,
        base_url=base_url, model=model,
    )

    total = api_ok + file_ok
    print(f"\n=== Done: {total}/{len(sample)} (API: {api_ok}, File: {file_ok}) ===")

    verify(output_dir)

    # Show generated files
    print(f"\nGenerated files:")
    for f in sorted(output_dir.rglob("*.yaml")):
        c = yaml.safe_load(open(f))
        if isinstance(c, dict) and "task_name" in c:
            n_comps = len(c.get("scoring_components", []))
            n_safety = len(c.get("safety_checks", []))
            has_files = "📁" if c.get("files") else "🔌"
            print(f"  {has_files} {f.name:40s} {n_comps} checks, {n_safety} safety")


if __name__ == "__main__":
    main()
