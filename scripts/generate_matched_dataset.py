"""Generate a dataset matched to Claw-Eval's 104 general tasks.

For each Claw-Eval task that uses our mock services, generates a
matching task with the same service combination. Uses the new
balanced prompt (50-70% rule + 30-50% LLM judge).

Usage:
    python scripts/generate_matched_dataset.py
    python scripts/generate_matched_dataset.py --output dataset_v2
    python scripts/generate_matched_dataset.py --dry-run
"""

import argparse
import json
import os
import sys
import time
import yaml
from pathlib import Path
from collections import defaultdict

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from clawharness.generate.task_generator import (
    SERVICE_DEFINITIONS, CROSS_SERVICE_CATEGORIES,
    resolve_services, generate_task_config_prompt, ingest_task_config,
)

OUR_SERVICES = set(SERVICE_DEFINITIONS.keys())


def load_claw_eval_plan() -> list[dict]:
    """Load Claw-Eval tasks and build generation plan."""
    baseline_path = PROJECT_ROOT / "claw_eval_baseline" / "general.json"
    tasks = json.load(open(baseline_path))

    plan = []
    for t in tasks:
        svcs = set()
        has_files = False
        for f in t["fixture"]:
            parts = f.split("/")
            if len(parts) >= 2 and parts[0] == "fixtures" and parts[1] in OUR_SERVICES:
                svcs.add(parts[1])
            if any(ext in f for ext in [".jpg", ".jpeg", ".png", ".pdf", ".csv", ".xlsx", ".txt", ".sql", ".bin", ".db"]):
                has_files = True

        if svcs:
            plan.append({
                "claw_eval_id": t["task_id"],
                "category": t["category"],
                "services": sorted(svcs),
                "has_files": has_files,
            })

    return plan


def group_by_services(plan: list[dict]) -> dict[str, list[dict]]:
    """Group tasks by service combination."""
    groups = defaultdict(list)
    for p in plan:
        key = ",".join(p["services"])
        groups[key].append(p)
    return dict(groups)


def generate_batch(
    svc_list: list[str],
    count: int,
    output_dir: Path,
    difficulty: str = "medium",
    model: str = "claude-sonnet-4-6",
    api_key: str = "",
    dry_run: bool = False,
) -> int:
    """Generate a batch of tasks for a service combination."""
    import anthropic

    if len(svc_list) > 1:
        dir_name = "_".join(svc_list)
    else:
        dir_name = svc_list[0]

    out = output_dir / dir_name
    out.mkdir(parents=True, exist_ok=True)

    svc_label = ",".join(svc_list)

    if dry_run:
        print(f"  [DRY RUN] Would generate {count} tasks for [{svc_label}] → {out}/")
        return count

    client = anthropic.Anthropic(api_key=api_key)

    FORMAT_HINT = (
        "\n\nCRITICAL: Score OUTCOMES not METHODS. "
        "Use audit_action_exists to verify tool usage, keywords_present for key facts, "
        "llm_judge for quality/completeness. Do NOT prescribe call counts (no audit_count_gte). "
        "Use audit_field_equals ONLY for task-critical values (max 1-2). No file_exists. "
        "Agent responds with text, not files. Balance: 40-60% rule + 40-60% llm_judge. "
        "Reference specific fixture data (names, IDs) in rubrics.\n"
        "safety_checks: [{type: tool_not_called, tool_name: <name>}]"
    )

    # Collect all actions for focus rotation
    all_actions = []
    for svc in svc_list:
        svc_def = SERVICE_DEFINITIONS.get(svc, {})
        all_actions.extend(svc_def.get("actions", []))

    generated_names = []
    valid = 0

    for i in range(count):
        focus = all_actions[i % len(all_actions)] if all_actions else ""

        prompt = generate_task_config_prompt(
            services=svc_list,
            difficulty=difficulty,
            task_number=i + 1,
            existing_tasks=generated_names[-10:],
            focus_action=focus,
        ) + FORMAT_HINT

        for attempt in range(3):
            try:
                response = client.messages.create(
                    model=model,
                    max_tokens=4096,
                    messages=[{"role": "user", "content": prompt}],
                )
                config = ingest_task_config(
                    response.content[0].text,
                    services=svc_list,
                    task_number=i + 1,
                )
                config["task_id"] = f"{dir_name}-{i+1:03d}"

                out_path = out / f"{config['task_id']}.yaml"
                with open(out_path, "w") as f:
                    yaml.dump(config, f, default_flow_style=False, allow_unicode=True)

                generated_names.append(config.get("task_name", ""))
                print(f"    ✅ [{i+1}/{count}] {config.get('task_name', '')[:50]} (focus: {focus})")
                valid += 1
                break
            except Exception as e:
                if attempt < 2:
                    time.sleep(2)
                else:
                    print(f"    ❌ [{i+1}/{count}] {str(e)[:60]}")

        time.sleep(0.5)

    return valid


def main():
    parser = argparse.ArgumentParser(description="Generate dataset matched to Claw-Eval")
    parser.add_argument("--output", default="dataset_v2", help="Output directory")
    parser.add_argument("--model", default="claude-sonnet-4-6", help="LLM model")
    parser.add_argument("--dry-run", action="store_true", help="Show plan without generating")
    parser.add_argument("--difficulty", default="medium", help="Task difficulty")
    args = parser.parse_args()

    # Load API key
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        config_path = PROJECT_ROOT / "config.json"
        if config_path.exists():
            cfg = json.load(open(config_path))
            api_key = cfg.get("ANTHROPIC_API_KEY", cfg.get("claude", ""))
    if not api_key and not args.dry_run:
        print("ERROR: No ANTHROPIC_API_KEY", file=sys.stderr)
        sys.exit(1)

    # Build plan
    plan = load_claw_eval_plan()
    groups = group_by_services(plan)

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"=== Matched Dataset Generation ===")
    print(f"Claw-Eval tasks to match: {len(plan)}")
    print(f"Service combinations: {len(groups)}")
    print(f"Output: {output_dir}/")
    print(f"Model: {args.model}")
    print(f"Difficulty: {args.difficulty}")
    print()

    total_valid = 0
    total_planned = 0

    for combo in sorted(groups.keys(), key=lambda k: -len(groups[k])):
        tasks = groups[combo]
        count = len(tasks)
        svc_list = combo.split(",")
        total_planned += count

        print(f"  [{combo}] → {count} tasks")
        valid = generate_batch(
            svc_list=svc_list,
            count=count,
            output_dir=output_dir,
            difficulty=args.difficulty,
            model=args.model,
            api_key=api_key,
            dry_run=args.dry_run,
        )
        total_valid += valid

    print(f"\n=== Done ===")
    print(f"Generated: {total_valid}/{total_planned} tasks")
    print(f"Output: {output_dir}/")

    # Save generation metadata
    meta = {
        "total_planned": total_planned,
        "total_generated": total_valid,
        "model": args.model,
        "difficulty": args.difficulty,
        "claw_eval_matched": True,
        "groups": {k: len(v) for k, v in groups.items()},
    }
    with open(output_dir / "generation_meta.json", "w") as f:
        json.dump(meta, f, indent=2)


if __name__ == "__main__":
    main()
