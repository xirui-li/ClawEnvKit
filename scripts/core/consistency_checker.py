"""Step 3 (REVIEW): Check generated tasks for internal consistency."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

from .schema import ConsistencyCheckResult, ConsistencyResult, TaskSpec

PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"

# File extensions to look for in instruction text
_FILE_EXTENSIONS = r"\.(?:py|md|json|txt|sh|yaml|yml|csv|xml|html|js|ts|cfg|ini|toml|log)"
_FILENAME_PATTERN = re.compile(
    r"""(?:['"`])([^'"`]*?""" + _FILE_EXTENSIONS + r""")(?:['"`])"""
    r"""|"""
    r"""(/workspace/\S*?""" + _FILE_EXTENSIONS + r""")""",
    re.IGNORECASE,
)


def _strip_json_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```json"):
        text = text[len("```json"):]
    elif text.startswith("```"):
        text = text[len("```"):]
    if text.endswith("```"):
        text = text[:-len("```")]
    return text.strip()


def extract_filenames_from_instruction(instruction: str) -> list[str]:
    """Extract filenames from instruction text (heuristic, not exhaustive)."""
    matches = _FILENAME_PATTERN.findall(instruction)
    filenames = []
    for groups in matches:
        for g in groups:
            if g:
                filenames.append(g)
    return filenames


def check_deterministic(task: TaskSpec) -> list[str]:
    """Fast deterministic checks. Returns list of issue strings (empty = pass)."""
    issues = []

    # 1. Check files referenced in instruction exist in initial_fs
    referenced = extract_filenames_from_instruction(task.instruction)
    for f in referenced:
        # Normalize: if filename doesn't start with /workspace/, prepend it
        check_path = f if f.startswith("/workspace/") else f"/workspace/{f}"
        if check_path not in task.initial_fs:
            issues.append(f"instruction references '{f}' but it is not in initial_fs")

    # 2. Check criterion paths exist in initial_fs (for file_exists, we allow
    #    paths that the agent is expected to CREATE, so only check file_contains
    #    and file_not_contains which need pre-existing files)
    for criterion in task.success_criteria:
        if criterion.type in ("file_contains", "file_not_contains"):
            if criterion.path and criterion.path not in task.initial_fs:
                issues.append(
                    f"criterion checks '{criterion.path}' which is not in initial_fs"
                )

    # 3. Difficulty heuristics (soft warnings)
    file_count = len(task.initial_fs)
    criteria_count = len(task.success_criteria)

    if task.difficulty == "easy" and file_count > 2:
        issues.append(f"easy task has {file_count} files in initial_fs (expected ≤ 2)")
    if task.difficulty == "hard" and criteria_count < 2:
        issues.append(f"hard task has only {criteria_count} success criterion (expected ≥ 2)")

    return issues


def _is_blocking_issue(issue: str) -> bool:
    """Determine if an issue is blocking (should trigger regeneration)."""
    blocking_keywords = ["not in initial_fs", "which is not in"]
    return any(kw in issue for kw in blocking_keywords)


def check_semantic_prompt(task: TaskSpec) -> str:
    """Return prompt for LLM semantic consistency check."""
    template = (PROMPTS_DIR / "consistency_check.md").read_text()

    # Format initial_fs for display
    fs_lines = []
    for path, content in task.initial_fs.items():
        preview = content[:200] + "..." if len(content) > 200 else content
        fs_lines.append(f"  {path}:\n    {preview}")
    initial_fs_str = "\n".join(fs_lines) if fs_lines else "  (empty)"

    # Format criteria for display
    criteria_lines = []
    for c in task.success_criteria:
        criteria_lines.append(f"  - type: {c.type}" +
                              (f", cmd: {c.cmd}" if c.cmd else "") +
                              (f", path: {c.path}" if c.path else "") +
                              (f", pattern: {c.pattern}" if c.pattern else "") +
                              (f", expected_exit: {c.expected_exit}" if c.type == "exit_code" else ""))
    criteria_str = "\n".join(criteria_lines) if criteria_lines else "  (none)"

    prompt = template.replace("{task_type}", task.task_type)
    prompt = prompt.replace("{difficulty}", task.difficulty)
    prompt = prompt.replace("{instruction}", task.instruction)
    prompt = prompt.replace("{initial_fs}", initial_fs_str)
    prompt = prompt.replace("{success_criteria}", criteria_str)

    return prompt


def check_semantic_ingest(task: TaskSpec, llm_response: str) -> ConsistencyResult:
    """Parse LLM semantic check response into ConsistencyResult."""
    cleaned = _strip_json_fences(llm_response)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        # If LLM returns garbage, treat as passed (fail-open for semantic check)
        return ConsistencyResult(passed=True, issues=["semantic check returned invalid JSON"])

    passed = data.get("passed", True)
    issues = data.get("issues", [])

    # Determine if regeneration is needed
    regenerate = not passed and any(_is_blocking_issue(i) for i in issues)

    return ConsistencyResult(
        passed=passed,
        issues=issues,
        regenerate=regenerate,
    )


def check(
    task: TaskSpec,
    llm_response: Optional[str] = None,
    skip_semantic: bool = False,
) -> ConsistencyCheckResult:
    """Run consistency checks on a task.

    First call (no llm_response): runs deterministic checks, may request semantic.
    Second call (with llm_response): ingests semantic check result.
    """
    # If we have an LLM response, we're ingesting semantic check results
    if llm_response is not None:
        result = check_semantic_ingest(task, llm_response)
        state = "passed" if result.passed else "failed"
        return ConsistencyCheckResult(state=state, result=result)

    # Run deterministic checks first
    det_issues = check_deterministic(task)

    # Separate blocking vs soft issues
    blocking = [i for i in det_issues if _is_blocking_issue(i)]
    soft = [i for i in det_issues if not _is_blocking_issue(i)]

    # If blocking issues found, fail immediately
    if blocking:
        result = ConsistencyResult(
            passed=False,
            issues=det_issues,
            regenerate=True,
        )
        return ConsistencyCheckResult(state="failed", result=result)

    # Determine if semantic check is needed
    # v0.1: only for hard difficulty (no review type yet)
    needs_semantic = (
        not skip_semantic
        and task.difficulty == "hard"
        and not blocking
    )

    if needs_semantic:
        prompt = check_semantic_prompt(task)
        return ConsistencyCheckResult(
            state="needs_llm_check",
            semantic_prompt=prompt,
        )

    # All checks passed (deterministic only)
    result = ConsistencyResult(
        passed=True,
        issues=soft,  # include soft warnings but still pass
        regenerate=False,
    )
    return ConsistencyCheckResult(state="passed", result=result)
