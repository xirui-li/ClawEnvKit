#!/usr/bin/env python3
"""serve.py — State machine orchestrator for Claw Harnessing pipeline.

All JSON responses go to stdout. All logs go to stderr.
Called by the claw (via bash tool) or by mock_claw.py.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path so we can import scripts.core.*
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.core.schema import (
    GenerationSpec,
    TaskSpec,
    ValidationResult,
    BuildResult,
    ExportResult,
)
from scripts.core.intent_parser import parse as intent_parse, IntentParseError
from scripts.core.task_generator import (
    generate_instruction_prompt,
    ingest_instruction,
    generate_fs_prompt,
    ingest_fs_and_criteria,
    TaskGenerationError,
    _pick_difficulty,
)
from scripts.core.consistency_checker import check as consistency_check
from scripts.core.image_builder import build as image_build, build_batch
from scripts.core.validator import (
    validate_prompt as make_validate_prompt,
    parse_solver_response,
    validate_with_solution,
)
from scripts.core.exporter import export


VERSION = "0.1.0"


def _log(msg: str) -> None:
    """Log to stderr."""
    print(f"[serve.py] {msg}", file=sys.stderr)


def _respond_ok(data: dict) -> None:
    """Write OK response to stdout."""
    print(json.dumps({"status": "ok", "data": data}, ensure_ascii=False))


def _respond_error(error: str) -> None:
    """Write error response to stdout."""
    print(json.dumps({"status": "error", "error": error}, ensure_ascii=False))


def _respond_llm_needed(prompt: str, callback_mode: str, callback_args: dict | None = None, system: str | None = None) -> None:
    """Write llm_needed response to stdout."""
    llm_call = {
        "prompt": prompt,
        "callback_mode": callback_mode,
        "callback_args": callback_args or {},
    }
    if system:
        llm_call["system"] = system
    print(json.dumps({"status": "llm_needed", "llm_call": llm_call}, ensure_ascii=False))


# --- State file management ---


def _state_path(output_dir: str) -> Path:
    return Path(os.path.expanduser(output_dir)) / ".clawharness_state.json"


def _load_state(spec_path: str) -> dict:
    """Load state from file."""
    p = Path(os.path.expanduser(spec_path))
    if not p.exists():
        return {}
    with open(p) as f:
        return json.load(f)


def _save_state(state: dict, spec_path: str) -> None:
    """Save state to file atomically."""
    p = Path(os.path.expanduser(spec_path))
    p.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    # Write to temp file first, then rename for atomicity
    tmp = p.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    tmp.rename(p)


def _init_state(output_dir: str) -> dict:
    """Create initial state."""
    return {
        "version": VERSION,
        "spec": None,
        "tasks": [],
        "pipeline_stage": "init",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


# --- Mode handlers ---


def handle_parse(args: argparse.Namespace) -> None:
    """Parse NL description → return LLM prompt."""
    output_dir = args.output or "~/clawharness-tasks"
    spec_path = str(_state_path(output_dir))

    result = intent_parse(args.input)

    if result.state == "needs_clarification":
        # Initialize state file
        state = _init_state(output_dir)
        state["_input"] = args.input
        state["_output_dir"] = output_dir
        _save_state(state, spec_path)

        _respond_llm_needed(
            prompt=result.clarification_prompt,
            callback_mode="parse_ingest",
            callback_args={"spec": spec_path},
        )
    else:
        # Shouldn't happen on first call, but handle it
        _respond_ok({"spec": result.spec.model_dump()})


def handle_parse_ingest(args: argparse.Namespace) -> None:
    """Ingest LLM response → build GenerationSpec."""
    state = _load_state(args.spec)
    description = state.get("_input", "")
    output_dir = state.get("_output_dir", "~/clawharness-tasks")

    try:
        result = intent_parse(description, llm_response=args.llm_response)
    except IntentParseError as e:
        _respond_error(str(e))
        return

    if result.state == "ready":
        # Override output_dir if it was in the parsed spec
        spec = result.spec
        if spec.output_dir == "~/clawharness-tasks" and output_dir != "~/clawharness-tasks":
            spec = spec.model_copy(update={"output_dir": output_dir})

        state["spec"] = spec.model_dump()
        state["pipeline_stage"] = "parsed"
        state["tasks"] = []
        _save_state(state, args.spec)
        _respond_ok({"pipeline_stage": "parsed", "spec": spec.model_dump()})
    else:
        _respond_error("Intent parsing did not produce a ready spec")


def handle_task_prompt(args: argparse.Namespace) -> None:
    """Generate instruction prompt for task at index."""
    state = _load_state(args.spec)
    spec = GenerationSpec(**state["spec"])
    index = args.index

    # Collect prior instructions
    prior = [t["instruction"] for t in state["tasks"] if t.get("instruction")]

    prompt = generate_instruction_prompt(spec, index, prior_instructions=prior)

    _respond_llm_needed(
        prompt=prompt,
        callback_mode="task_ingest",
        callback_args={"spec": args.spec, "index": index},
    )


def handle_task_ingest(args: argparse.Namespace) -> None:
    """Ingest LLM instruction response."""
    state = _load_state(args.spec)
    spec = GenerationSpec(**state["spec"])
    index = args.index

    prior = [t["instruction"] for t in state["tasks"] if t.get("instruction")]

    try:
        instruction = ingest_instruction(spec, index, args.llm_response, prior_instructions=prior)
    except TaskGenerationError as e:
        _respond_error(str(e))
        return

    # Ensure tasks list is long enough
    while len(state["tasks"]) <= index:
        state["tasks"].append({})

    difficulty = _pick_difficulty(spec, index)
    skill_target = spec.skill_targets[index % len(spec.skill_targets)] if spec.skill_targets else spec.domain
    task_id = f"{spec.domain}-{index + 1:03d}"

    state["tasks"][index] = {
        "task_id": task_id,
        "stage": "instruction_generated",
        "instruction": instruction,
        "difficulty": difficulty,
        "skill_target": skill_target,
    }
    state["pipeline_stage"] = "generating"
    _save_state(state, args.spec)
    _respond_ok({"task_id": task_id, "instruction": instruction})


def handle_fs_prompt(args: argparse.Namespace) -> None:
    """Generate fs+criteria prompt for task at index."""
    state = _load_state(args.spec)
    spec = GenerationSpec(**state["spec"])
    index = args.index

    instruction = state["tasks"][index]["instruction"]
    prompt = generate_fs_prompt(spec, instruction)

    _respond_llm_needed(
        prompt=prompt,
        callback_mode="fs_ingest",
        callback_args={"spec": args.spec, "index": index},
    )


def handle_fs_ingest(args: argparse.Namespace) -> None:
    """Ingest LLM fs+criteria response → build TaskSpec."""
    state = _load_state(args.spec)
    spec = GenerationSpec(**state["spec"])
    index = args.index

    instruction = state["tasks"][index]["instruction"]

    try:
        task = ingest_fs_and_criteria(spec, index, instruction, args.llm_response)
    except TaskGenerationError as e:
        _respond_error(str(e))
        return

    # Update task in state
    state["tasks"][index].update({
        "stage": "fs_generated",
        "initial_fs": task.initial_fs,
        "base_tools": task.base_tools,
        "success_criteria": [c.model_dump() for c in task.success_criteria],
        "domain": task.domain,
        "task_type": task.task_type,
    })
    _save_state(state, args.spec)
    _respond_ok({"task_id": task.task_id, "stage": "fs_generated"})


def handle_consistency_check(args: argparse.Namespace) -> None:
    """Run consistency check on task at index."""
    state = _load_state(args.spec)
    index = args.index
    task_data = state["tasks"][index]

    task = _task_from_state(task_data)
    result = consistency_check(task)

    if result.state == "needs_llm_check":
        _respond_llm_needed(
            prompt=result.semantic_prompt,
            callback_mode="consistency_ingest",
            callback_args={"spec": args.spec, "index": index},
        )
    elif result.state == "passed":
        state["tasks"][index]["stage"] = "consistency_checked"
        state["tasks"][index]["consistency_check"] = result.result.model_dump() if result.result else None
        _save_state(state, args.spec)
        _respond_ok({"state": "passed", "issues": result.result.issues if result.result else []})
    else:
        state["tasks"][index]["consistency_check"] = result.result.model_dump() if result.result else None
        _save_state(state, args.spec)
        _respond_ok({
            "state": "failed",
            "regenerate": result.result.regenerate if result.result else False,
            "issues": result.result.issues if result.result else [],
        })


def handle_consistency_ingest(args: argparse.Namespace) -> None:
    """Ingest LLM semantic check response."""
    state = _load_state(args.spec)
    index = args.index
    task_data = state["tasks"][index]

    task = _task_from_state(task_data)
    result = consistency_check(task, llm_response=args.llm_response)

    state["tasks"][index]["stage"] = "consistency_checked"
    state["tasks"][index]["consistency_check"] = result.result.model_dump() if result.result else None
    _save_state(state, args.spec)
    _respond_ok({
        "state": result.state,
        "issues": result.result.issues if result.result else [],
    })


def handle_build(args: argparse.Namespace) -> None:
    """Build Docker images for all tasks."""
    state = _load_state(args.spec)
    spec = GenerationSpec(**state["spec"])

    tasks = []
    for task_data in state["tasks"]:
        task = _task_from_state(task_data)
        tasks.append(task)

    _log(f"Building {len(tasks)} Docker images...")
    results = build_batch(tasks)

    for i, result in enumerate(results):
        state["tasks"][i]["docker_image"] = result.image_name
        state["tasks"][i]["build_result"] = result.model_dump()
        if result.success:
            state["tasks"][i]["stage"] = "built"

    state["pipeline_stage"] = "built"
    _save_state(state, args.spec)

    built = sum(1 for r in results if r.success)
    failed = sum(1 for r in results if not r.success)
    _respond_ok({"built": built, "failed": failed})


def handle_validate_prompt(args: argparse.Namespace) -> None:
    """Generate solver prompt for task at index."""
    state = _load_state(args.spec)
    index = args.index
    task_data = state["tasks"][index]

    task = _task_from_state(task_data)
    prompt = make_validate_prompt(task)

    _respond_llm_needed(
        prompt=prompt,
        callback_mode="validate_ingest",
        callback_args={"spec": args.spec, "index": index},
    )


def handle_validate_ingest(args: argparse.Namespace) -> None:
    """Ingest LLM solver response → run validation in Docker."""
    state = _load_state(args.spec)
    index = args.index
    task_data = state["tasks"][index]

    task = _task_from_state(task_data)

    # Parse solver response
    actions = parse_solver_response(args.llm_response)

    # Run validation
    result = validate_with_solution(task, actions)

    state["tasks"][index]["validation_result"] = result.model_dump()
    state["tasks"][index]["stage"] = "validated"
    state["pipeline_stage"] = "validating"
    _save_state(state, args.spec)

    _respond_ok({
        "passed": result.passed,
        "criteria_results": result.criteria_results,
        "failure_reason": result.failure_reason,
    })


def handle_export(args: argparse.Namespace) -> None:
    """Export validated tasks to train.jsonl."""
    state = _load_state(args.spec)
    output_dir = args.output or state.get("_output_dir", "~/clawharness-tasks")

    tasks = []
    for task_data in state["tasks"]:
        task = _task_from_state(task_data)
        if task_data.get("validation_result"):
            task = task.model_copy(update={
                "validation_result": ValidationResult(**task_data["validation_result"]),
            })
        tasks.append(task)

    result = export(tasks, output_dir)

    state["pipeline_stage"] = "exported"
    _save_state(state, args.spec)

    _respond_ok(result.model_dump())


def handle_status(args: argparse.Namespace) -> None:
    """Report pipeline status."""
    state = _load_state(args.spec)

    task_stages = {}
    for t in state.get("tasks", []):
        stage = t.get("stage", "unknown")
        task_stages[stage] = task_stages.get(stage, 0) + 1

    _respond_ok({
        "version": state.get("version", VERSION),
        "pipeline_stage": state.get("pipeline_stage", "unknown"),
        "task_count": len(state.get("tasks", [])),
        "task_stages": task_stages,
    })


# --- Helpers ---


def _task_from_state(task_data: dict) -> TaskSpec:
    """Reconstruct TaskSpec from state dict."""
    from scripts.core.schema import SuccessCriterion

    criteria = []
    for c in task_data.get("success_criteria", []):
        criteria.append(SuccessCriterion(**c))

    return TaskSpec(
        task_id=task_data.get("task_id", "unknown"),
        domain=task_data.get("domain", "unknown"),
        difficulty=task_data.get("difficulty", "easy"),
        skill_target=task_data.get("skill_target", "unknown"),
        task_type=task_data.get("task_type", "code"),
        instruction=task_data.get("instruction", ""),
        initial_fs=task_data.get("initial_fs", {}),
        base_tools=task_data.get("base_tools", ["bash", "python3"]),
        success_criteria=criteria,
        docker_image=task_data.get("docker_image", ""),
    )


# --- Main ---


def main():
    parser = argparse.ArgumentParser(description="Claw Harnessing pipeline orchestrator")
    parser.add_argument("--mode", required=True, help="Pipeline mode to execute")
    parser.add_argument("--spec", help="Path to state file (.clawharness_state.json)")
    parser.add_argument("--index", type=int, help="Task index (0-based)")
    parser.add_argument("--llm-response", dest="llm_response", help="LLM response text")
    parser.add_argument("--input", help="Natural language description (for parse mode)")
    parser.add_argument("--output", help="Output directory")

    args = parser.parse_args()

    handlers = {
        "parse": handle_parse,
        "parse_ingest": handle_parse_ingest,
        "task_prompt": handle_task_prompt,
        "task_ingest": handle_task_ingest,
        "fs_prompt": handle_fs_prompt,
        "fs_ingest": handle_fs_ingest,
        "consistency_check": handle_consistency_check,
        "consistency_ingest": handle_consistency_ingest,
        "build": handle_build,
        "validate_prompt": handle_validate_prompt,
        "validate_ingest": handle_validate_ingest,
        "export": handle_export,
        "status": handle_status,
    }

    handler = handlers.get(args.mode)
    if not handler:
        _respond_error(f"Unknown mode: {args.mode}")
        sys.exit(1)

    try:
        handler(args)
    except Exception as e:
        _respond_error(f"Internal error in mode '{args.mode}': {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
