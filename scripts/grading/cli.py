#!/usr/bin/env python3
"""Unified CLI for Claw Harnessing v2.

Usage:
    # Generate task configs for a service
    python -m scripts.grading.cli generate --service gmail --count 5 --difficulty medium

    # Validate generated configs (self-validation)
    python -m scripts.grading.cli validate --input tasks/gmail/

    # Grade an agent run against a task
    python -m scripts.grading.cli grade --task tasks/gmail/gmail-001.yaml --audit audit.json

    # Full pipeline: generate → validate → export
    python -m scripts.grading.cli pipeline --service gmail --count 10 --output ~/tasks/
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import yaml
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.grading.task_config_generator import (
    SERVICE_DEFINITIONS,
    generate_task_config_prompt,
    ingest_task_config,
    validate_task_config,
)
from scripts.grading.engine import GradingEngine


def _load_api_key() -> str:
    config_path = PROJECT_ROOT / "config.json"
    if config_path.exists():
        config = json.load(open(config_path))
        return config.get("ANTHROPIC_API_KEY") or config.get("claude") or ""
    return os.environ.get("ANTHROPIC_API_KEY", "")


def _call_llm(prompt: str, api_key: str) -> str:
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    model = os.environ.get("CLAWHARNESS_MODEL", "claude-sonnet-4-6")
    response = client.messages.create(
        model=model,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


FORMAT_HINT = """

IMPORTANT: Each scoring_component MUST have this exact structure:
- name: <string>
  weight: <float>
  check:
    type: <one of: audit_action_exists, audit_field_equals, audit_field_contains, audit_count_gte, audit_count_equals, audit_sequence, keywords_present, keywords_absent, llm_judge>
    <type-specific fields>

Example:
- name: inbox_checked
  weight: 0.2
  check:
    type: audit_action_exists
    service: gmail
    action: list_inbox

safety_checks must use:
- type: tool_not_called
  tool_name: <action_name>
"""


def cmd_generate(args):
    """Generate task configs."""
    api_key = _load_api_key()
    if not api_key:
        print("ERROR: No API key", file=sys.stderr)
        sys.exit(1)

    output_dir = Path(args.output) / args.service
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Generating {args.count} {args.difficulty} tasks for {args.service}...")

    valid = 0
    for i in range(args.count):
        prompt = generate_task_config_prompt(
            args.service,
            difficulty=args.difficulty,
            task_number=i + 1,
        ) + FORMAT_HINT

        for attempt in range(args.retries):
            try:
                response = _call_llm(prompt, api_key)
                config = ingest_task_config(response, args.service, task_number=i + 1)

                # Override task_id
                config["task_id"] = f"{args.service}-{i+1:03d}"

                # Save
                out_path = output_dir / f"{config['task_id']}.yaml"
                with open(out_path, "w") as f:
                    yaml.dump(config, f, default_flow_style=False, allow_unicode=True)

                print(f"  ✅ [{i+1}/{args.count}] {config.get('task_name', '')[:50]}")
                valid += 1
                break
            except Exception as e:
                if attempt < args.retries - 1:
                    print(f"  ⟳ [{i+1}/{args.count}] Retry {attempt+1}: {str(e)[:80]}", file=sys.stderr)
                    time.sleep(1)
                else:
                    print(f"  ❌ [{i+1}/{args.count}] Failed after {args.retries} tries: {str(e)[:80]}")

        time.sleep(0.5)

    print(f"\nDone: {valid}/{args.count} valid configs in {output_dir}/")


def cmd_validate(args):
    """Validate generated task configs."""
    input_dir = Path(args.input)
    files = sorted(input_dir.glob("*.yaml"))

    if not files:
        print(f"No YAML files found in {input_dir}")
        return

    print(f"Validating {len(files)} task configs...")
    valid = 0
    for f in files:
        config = yaml.safe_load(open(f))
        service = config.get("task_id", "").split("-")[0] if config.get("task_id") else ""
        issues = validate_task_config(config, service)

        if issues:
            print(f"  ❌ {f.name}: {'; '.join(issues)}")
        else:
            print(f"  ✅ {f.name}: {config.get('task_name', '')[:50]}")
            valid += 1

    print(f"\n{valid}/{len(files)} valid")


def cmd_grade(args):
    """Grade using audit data and task config."""
    config = yaml.safe_load(open(args.task))
    audit_data = json.load(open(args.audit))
    agent_output = args.agent_output or ""

    engine = GradingEngine()
    result = engine.grade(config, audit_data, agent_output)

    print(f"Task: {config.get('task_name', config.get('task_id'))}")
    print(f"Completion: {result.completion:.2f}")
    print(f"Robustness: {result.robustness:.2f}")
    print(f"Safety: {result.safety:.1f}")
    print(f"Final Score: {result.final_score:.2f}")
    print(f"\nComponents:")
    for c in result.component_results:
        print(f"  {'✅' if c.passed else '❌'} [{c.weight:.0%}] {c.name}: {c.score:.2f}")
    if result.safety_violations:
        print(f"\n🚨 Safety: {result.safety_violations}")


def cmd_pipeline(args):
    """Full pipeline: generate → validate → export."""
    # Step 1: Generate
    print(f"=== Step 1: Generate {args.count} tasks for {args.service} ===")
    args.output = args.output or "tasks"
    args.retries = 3
    cmd_generate(args)

    # Step 2: Validate
    print(f"\n=== Step 2: Validate ===")
    task_dir = Path(args.output) / args.service
    args.input = str(task_dir)
    cmd_validate(args)

    # Step 3: Export
    print(f"\n=== Step 3: Export ===")
    files = sorted(task_dir.glob("*.yaml"))
    jsonl_path = task_dir / "train.jsonl"

    with open(jsonl_path, "w") as out:
        for f in files:
            config = yaml.safe_load(open(f))
            issues = validate_task_config(config, args.service)
            if not issues:
                out.write(json.dumps(config, ensure_ascii=False) + "\n")

    lines = sum(1 for _ in open(jsonl_path))
    print(f"Exported {lines} tasks to {jsonl_path}")


def cmd_services(args):
    """List available services."""
    print(f"{'Service':<15} {'Description':<50} {'Endpoints'}")
    print("-" * 80)
    for name, svc in sorted(SERVICE_DEFINITIONS.items()):
        print(f"{name:<15} {svc['description'][:50]:<50} {len(svc['endpoints'])}")


def main():
    parser = argparse.ArgumentParser(description="Claw Harnessing v2 CLI")
    sub = parser.add_subparsers(dest="command")

    # generate
    gen = sub.add_parser("generate", help="Generate task configs")
    gen.add_argument("--service", required=True, choices=list(SERVICE_DEFINITIONS.keys()))
    gen.add_argument("--count", type=int, default=5)
    gen.add_argument("--difficulty", default="medium", choices=["easy", "medium", "hard"])
    gen.add_argument("--output", default="tasks")
    gen.add_argument("--retries", type=int, default=3)

    # validate
    val = sub.add_parser("validate", help="Validate task configs")
    val.add_argument("--input", required=True)

    # grade
    grd = sub.add_parser("grade", help="Grade an agent run")
    grd.add_argument("--task", required=True, help="Path to task.yaml")
    grd.add_argument("--audit", required=True, help="Path to audit_data.json")
    grd.add_argument("--agent-output", default="")

    # pipeline
    pipe = sub.add_parser("pipeline", help="Full pipeline: generate → validate → export")
    pipe.add_argument("--service", required=True, choices=list(SERVICE_DEFINITIONS.keys()))
    pipe.add_argument("--count", type=int, default=5)
    pipe.add_argument("--difficulty", default="medium")
    pipe.add_argument("--output", default="tasks")

    # services
    sub.add_parser("services", help="List available services")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    {"generate": cmd_generate, "validate": cmd_validate, "grade": cmd_grade,
     "pipeline": cmd_pipeline, "services": cmd_services}[args.command](args)


if __name__ == "__main__":
    main()
