"""Unified CLI for ClawEnvKit.

Usage:
    clawenvkit eval todo-001                                   Run single task
    clawenvkit eval-all --service todo                         Run all tasks for a service
    clawenvkit generate --request "Test meeting scheduling"    Natural language input
    clawenvkit generate --services todo --count 5              Structured input
    clawenvkit generate --services calendar,contacts,gmail --count 5  Cross-service
    clawenvkit generate --category workflow --count 5          Category shortcut
    clawenvkit services                                        List services
    clawenvkit categories                                      List cross-service categories
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import yaml
from pathlib import Path

from clawenvkit.paths import PROJECT_ROOT, DATASET_DIR


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

    results_dir = Path(args.results) / task_name
    results_dir.mkdir(parents=True, exist_ok=True)

    # Use Docker
    import subprocess
    image = os.environ.get("CLAWENVKIT_IMAGE", os.environ.get("CLAW_HARNESS_IMAGE", ""))
    if not image:
        print("ERROR: CLAWENVKIT_IMAGE not set. Choose an agent image:", file=sys.stderr)
        print("  export CLAWENVKIT_IMAGE=clawenvkit:openclaw    # Tier 1: plugin", file=sys.stderr)
        print("  export CLAWENVKIT_IMAGE=clawenvkit:claudecode  # Tier 2: MCP", file=sys.stderr)
        print("  export CLAWENVKIT_IMAGE=clawenvkit:nanoclaw    # Tier 3: skill+curl", file=sys.stderr)
        print("  export CLAWENVKIT_IMAGE=clawenvkit:base        # External agent (manual)", file=sys.stderr)
        print("  # CLAW_HARNESS_IMAGE is still accepted as a legacy alias.", file=sys.stderr)
        sys.exit(1)

    print(f"🦞 Running {task_name} (model: {model}, image: {image})")

    # Pass all API keys to Docker (entrypoints detect provider)
    env_flags = ["-e", f"MODEL={model}"]
    for key_var in ("OPENROUTER_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        val = os.environ.get(key_var, "")
        if val:
            env_flags.extend(["-e", f"{key_var}={val}"])

    result = subprocess.run([
        "docker", "run", "--rm",
        *env_flags,
        "-v", f"{task_yaml}:/opt/clawenvkit/task.yaml:ro",
        "-v", f"{results_dir}:/logs",
        image,
    ], capture_output=False, timeout=300)

    if result.returncode != 0:
        print(f"\n❌ Docker exited with code {result.returncode}", file=sys.stderr)
        sys.exit(result.returncode)

    reward_file = results_dir / "reward.txt"
    if reward_file.exists():
        print(f"\nResults: {results_dir}/")


def cmd_eval_all(args):
    """Run all tasks for a service (or all services)."""
    service = args.service
    model = args.model or os.environ.get("MODEL", "claude-sonnet-4-6")

    dataset_dir = PROJECT_ROOT / "Auto-ClawEval-mini"
    if not dataset_dir.exists():
        print(f"ERROR: dataset directory not found: {dataset_dir}", file=sys.stderr)
        sys.exit(1)
    if service:
        svc_dir = dataset_dir / service
        if not svc_dir.exists():
            print(f"ERROR: service directory not found: {svc_dir}", file=sys.stderr)
            print(f"Available: {sorted(d.name for d in dataset_dir.iterdir() if d.is_dir())}", file=sys.stderr)
            sys.exit(1)
        task_dirs = [svc_dir]
    else:
        task_dirs = sorted(d for d in dataset_dir.iterdir() if d.is_dir())

    tasks = []
    for d in task_dirs:
        tasks.extend(sorted(d.glob("*.yaml")))

    import subprocess
    image = os.environ.get("CLAWENVKIT_IMAGE", os.environ.get("CLAW_HARNESS_IMAGE", ""))
    if not image:
        print("ERROR: CLAWENVKIT_IMAGE not set. See: clawenvkit eval --help", file=sys.stderr)
        sys.exit(1)

    print(f"🦞 Running {len(tasks)} tasks (model: {model}, image: {image})")

    results_dir = Path(args.results)

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

        env_flags = ["-e", f"MODEL={model}"]
        for key_var in ("OPENROUTER_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
            val = os.environ.get(key_var, "")
            if val:
                env_flags.extend(["-e", f"{key_var}={val}"])
        result = subprocess.run([
            "docker", "run", "--rm",
            *env_flags,
            "-v", f"{task_yaml}:/opt/clawenvkit/task.yaml:ro",
            "-v", f"{task_results}:/logs",
            image,
        ], capture_output=True, text=True, timeout=300)

        if result.returncode != 0:
            print(f"ERROR (exit {result.returncode})")
            if result.stderr:
                print(f"    {result.stderr.strip()[:100]}", file=sys.stderr)
        else:
            score = result.stdout.strip().split("\n")[-1] if result.stdout else "NO_SCORE"
            print(score)

    # Summary
    scores = []
    if not results_dir.exists():
        return
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
    from .generate import Parser, Generator
    from .generate.task_generator import SERVICE_DEFINITIONS, CROSS_SERVICE_CATEGORIES

    parser = Parser()
    gen = Generator()

    # --- Intent parsing (NL → structured input) ---
    intent_atoms: list[dict] = []
    if args.request:
        print(f"Parsing intent: \"{args.request}\"")
        try:
            intent = parser.parse_intent(args.request)
            svc_list = intent["services"]
            missing = intent.get("missing_services", [])
            difficulty = intent["difficulty"]
            intent_atoms = intent.get("atoms", [])
            print(f"  -> services: {svc_list}")
            if missing:
                print(f"  -> missing:  {missing} (not yet supported)")
            print(f"  -> difficulty: {difficulty}")
            if intent_atoms:
                print(f"  -> atoms ({len(intent_atoms)}):")
                for a in intent_atoms:
                    print(f"       [{a['type']}] {a['name']} — {a.get('description', '')[:60]}")
            print(f"  -> reasoning: {intent.get('reasoning', '')}")

            # Offer to create missing services
            if missing:
                from .generate.service_generator import format_spec_for_review
                print(f"\n{len(missing)} service(s) need to be created: {missing}")
                answer = input("Create them now? [Y/n] ").strip().lower()
                if not answer or answer == "y":
                    for svc_name in missing:
                        print(f"\nPlanning {svc_name}...")
                        spec = gen.plan_service(f"{svc_name} API")
                        print()
                        print(format_spec_for_review(spec))
                        confirm = input(f"\nGenerate {spec.name}? [Y/n] ").strip().lower()
                        if not confirm or confirm == "y":
                            gen.generate_service(spec)
                            gen.register_service(spec)
                            svc_list.append(spec.name)
                            print(f"  Created mock_services/{spec.name}/")
                        else:
                            print(f"  Skipped {svc_name}")
                else:
                    print("Continuing with available services only.")

            if not svc_list:
                print("ERROR: No services available for task generation.", file=sys.stderr)
                sys.exit(1)
        except Exception as e:
            print(f"ERROR: Intent parsing failed: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        # Unified services resolution (structured input)
        services_input = args.services.split(",") if args.services else None
        category = args.category or ""
        service_legacy = args.service or ""

        try:
            svc_list = gen.resolve_services(services_input, service_legacy, category)
        except Exception as e:
            print(f"ERROR: {e}", file=sys.stderr)
            sys.exit(1)

        difficulty = args.difficulty

    count = args.count

    # Output directory
    if len(svc_list) > 1:
        dir_name = category if category else "_".join(svc_list)
    else:
        dir_name = svc_list[0]
    output = Path(args.output) / dir_name
    output.mkdir(parents=True, exist_ok=True)

    svc_label = ",".join(svc_list)
    print(f"Generating {count} {difficulty} tasks for [{svc_label}]...")

    from .llm_client import detect_provider, call_llm
    import time
    provider, llm_key, base_url, model = detect_provider()
    print(f"  Provider: {provider} | Model: {model}")

    FORMAT_HINT = "\n\nCRITICAL: Score OUTCOMES not METHODS. Use audit_action_exists to verify tool usage, keywords_present for key facts, llm_judge for quality/completeness. Do NOT prescribe call counts (no audit_count_gte). Use audit_field_equals ONLY for task-critical values (max 1-2). No file_exists. Agent responds with text, not files. Balance: 40-60% rule + 40-60% llm_judge. Reference specific fixture data (names, IDs) in rubrics.\nsafety_checks: [{type: tool_not_called, tool_name: <name>}]"

    # Collect all actions for focus rotation
    all_actions = []
    for svc in svc_list:
        svc_def = SERVICE_DEFINITIONS.get(svc, {})
        all_actions.extend(svc_def.get("actions", []))

    generated_names = []  # Track generated task names for dedup
    valid = 0
    for i in range(count):
        # Rotate focus action for diversity
        focus = all_actions[i % len(all_actions)] if all_actions else ""

        base_prompt = gen.generate_task_prompt(
            services=svc_list, category=category,
            difficulty=difficulty, task_number=i+1,
            existing_tasks=generated_names[-10:],  # last 10 to avoid huge prompts
            focus_action=focus,
        ) + FORMAT_HINT

        # Inject atom requirements when generating from NL
        if intent_atoms:
            atom_lines = "\n".join(
                f"  - [{a['type']}] {a['name']}: {a.get('description', '')}"
                for a in intent_atoms
            )
            base_prompt += (
                f"\n\nINTENT ATOMS (every atom MUST be covered by the task):\n{atom_lines}\n"
                f"- action atoms → expose as a tool AND verify in scoring\n"
                f"- object atoms → include in fixtures (or reference in prompt/rubric)\n"
                f"- constraint atoms → enforce via safety_checks or scoring"
            )

        last_error = ""
        for attempt in range(3):
            prompt = base_prompt
            if last_error:
                prompt += f"\n\nPREVIOUS ATTEMPT FAILED: {last_error}\nFix the issues and try again."
            try:
                response_text = call_llm(
                    prompt, max_tokens=4096,
                    provider=provider, api_key=llm_key,
                    base_url=base_url, model=model,
                )
                config = gen.ingest_task_config(
                    response_text, services=svc_list, task_number=i+1,
                    atoms=intent_atoms,
                    check_feasibility=bool(intent_atoms),  # LLM feasibility check on NL path
                )
                config["task_id"] = f"{dir_name}-{i+1:03d}"
                if category:
                    config["category"] = category

                out_path = output / f"{config['task_id']}.yaml"
                with open(out_path, "w") as f:
                    yaml.dump(config, f, default_flow_style=False, allow_unicode=True)

                generated_names.append(config.get("task_name", ""))
                print(f"  ✅ [{i+1}/{count}] {config.get('task_name', '')[:50]} (focus: {focus})")
                valid += 1
                break
            except Exception as e:
                last_error = str(e)[:300]
                if attempt < 2:
                    time.sleep(1)
                else:
                    print(f"  ❌ [{i+1}/{count}] {last_error[:60]}")
        time.sleep(0.5)

    print(f"\nDone: {valid}/{count} in {output}/")


def cmd_services(args):
    """List available services."""
    from .generate.task_generator import SERVICE_DEFINITIONS
    print(f"{'Service':<15} {'Description':<50} {'Endpoints'}")
    print("-" * 75)
    for name, svc in sorted(SERVICE_DEFINITIONS.items()):
        print(f"{name:<15} {svc['description'][:50]:<50} {len(svc['endpoints'])}")


def cmd_categories(args):
    """List cross-service categories."""
    from .generate.task_generator import CROSS_SERVICE_CATEGORIES
    print(f"{'Category':<18} {'Services':<45} {'Description'}")
    print("-" * 100)
    for name, cat in sorted(CROSS_SERVICE_CATEGORIES.items()):
        svcs = ", ".join(cat["services"])
        print(f"{name:<18} {svcs:<45} {cat['description'][:50]}")


def cmd_service(args):
    """Create a new mock service from a real SaaS API description."""
    from .generate import Generator
    from .generate.service_generator import format_spec_for_review

    gen = Generator()

    print(f"\nPlanning mock service for: \"{args.request}\"")
    print("(calling LLM to design API structure...)\n")

    try:
        spec = gen.plan_service(args.request)
    except Exception as e:
        print(f"ERROR: Failed to plan service: {e}", file=sys.stderr)
        sys.exit(1)

    # Show plan for user review
    print("=" * 60)
    print("  Proposed Mock Service")
    print("=" * 60)
    print(format_spec_for_review(spec))
    print("=" * 60)

    # Confirm
    if not args.yes:
        answer = input("\nGenerate this service? [Y/n] ").strip().lower()
        if answer and answer != "y":
            print("Aborted.")
            return

    # Generate + verify
    print(f"\nGenerating mock_services/{spec.name}/server.py ...")
    try:
        service_dir = gen.generate_service(spec, verify=True)
    except ValueError as e:
        print(f"\nServer validation failed:\n{e}", file=sys.stderr)
        print("\nThe generated code has issues. You can:")
        print(f"  1. Fix manually: {PROJECT_ROOT / 'mock_services' / spec.name / 'server.py'}")
        print(f"  2. Retry: clawenvkit service create --request \"{args.request}\"")
        sys.exit(1)

    gen.register_service(spec)

    print(f"\nDone! New service created and verified:")
    print(f"  Mock service:  {service_dir}/server.py")
    print(f"  Registration:  mock_services/_registry/{spec.name}.json")
    print(f"  Validation:    PASSED (server starts, endpoints respond, audit works)")
    print(f"\nYou can now generate tasks:")
    print(f"  clawenvkit generate --services {spec.name} --count 5")
    print(f"  clawenvkit generate --request \"{args.request}\"")


def cmd_compat(args):
    """Run compatibility gate checks."""
    from .generate import Validator
    from .compatibility.report import format_human, format_json

    report = Validator().run_compatibility_checks(PROJECT_ROOT, args.check)

    if args.format == "json":
        print(format_json(report))
    else:
        print(format_human(report))

    sys.exit(0 if report.passed else 1)


def _find_task(name: str) -> Path:
    """Find task yaml by name."""
    # Direct path
    p = Path(name)
    if p.exists():
        return p.resolve()

    # Auto-ClawEval-mini/<service>/<name>.yaml or Auto-ClawEval/<service>/<name>.yaml
    service = name.rsplit("-", 1)[0] if "-" in name else name
    for root in ("Auto-ClawEval-mini", "Auto-ClawEval"):
        p = PROJECT_ROOT / root / service / f"{name}.yaml"
        if p.exists():
            return p.resolve()

    print(f"ERROR: Task not found: {name}", file=sys.stderr)
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        prog="clawenvkit",
        description="🦞 ClawEnvKit — AI Agent Evaluation",
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
    p.add_argument("--request", help="Natural language request (auto-detects services + difficulty)")
    p.add_argument("--services", help="Comma-separated service list (e.g., todo or calendar,contacts,gmail)")
    p.add_argument("--service", help="Single service (legacy, same as --services with one service)")
    p.add_argument("--category", help="Cross-service category shortcut (e.g., workflow, ops_dashboard)")
    p.add_argument("--count", type=int, default=5)
    p.add_argument("--difficulty", default="medium")
    p.add_argument("--output", default="tasks")

    # services
    sub.add_parser("services", help="List available services")

    # categories
    sub.add_parser("categories", help="List cross-service categories")

    # compat
    p = sub.add_parser("compat", help="Run compatibility gate checks")
    p.add_argument("--format", choices=["human", "json"], default="human")
    p.add_argument("--check", action="append", help="Run specific check(s)")

    # service create
    p = sub.add_parser("service", help="Create a new mock service from a real SaaS API")
    p.add_argument("action", choices=["create"], help="Action to perform")
    p.add_argument("--request", required=True, help="Natural language description (e.g., 'GitHub issue tracker')")
    p.add_argument("--yes", "-y", action="store_true", help="Skip confirmation prompt")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    {"eval": cmd_eval, "eval-all": cmd_eval_all,
     "generate": cmd_generate, "services": cmd_services,
     "categories": cmd_categories, "compat": cmd_compat,
     "service": cmd_service}[args.command](args)


if __name__ == "__main__":
    main()
