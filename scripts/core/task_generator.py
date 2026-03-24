"""Step 2 (CODE): Generate task instruction, initial_fs, and success criteria."""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Optional

from .schema import GenerationSpec, SuccessCriterion, TaskSpec, VALID_CRITERION_TYPES

PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"

# Task approaches for diversity rotation
TASK_APPROACHES = [
    "create",     # Write new code from scratch
    "fix",        # Debug and fix broken code
    "refactor",   # Improve existing working code
    "test",       # Write tests or fix failing tests
    "optimize",   # Performance, edge cases
    "integrate",  # Connect components/APIs
    "migrate",    # Convert format/framework
]


class TaskGenerationError(Exception):
    """Raised when task generation fails validation."""
    pass


def _load_template(name: str) -> str:
    return (PROMPTS_DIR / name).read_text()


def _strip_json_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```json"):
        text = text[len("```json"):]
    elif text.startswith("```"):
        text = text[len("```"):]
    if text.endswith("```"):
        text = text[:-len("```")]
    return text.strip()


def _jaccard_similarity(a: str, b: str) -> float:
    """Jaccard similarity on unigrams (lowercased, split on whitespace)."""
    set_a = set(a.lower().split())
    set_b = set(b.lower().split())
    if not set_a and not set_b:
        return 1.0
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)


def _pick_difficulty(spec: GenerationSpec, index: int) -> str:
    """Pick difficulty for task at given index based on distribution."""
    difficulties = []
    for diff, proportion in spec.difficulty_distribution.items():
        count = max(1, round(proportion * spec.task_count))
        difficulties.extend([diff] * count)
    # Trim or extend to match task_count
    while len(difficulties) < spec.task_count:
        difficulties.append("medium")
    difficulties = difficulties[:spec.task_count]
    difficulties.sort(key=lambda d: {"easy": 0, "medium": 1, "hard": 2}[d])
    return difficulties[index]


def _pick_approach(index: int, task_count: int) -> str:
    """Pick a task approach for diversity. Rotates through approaches."""
    return TASK_APPROACHES[index % len(TASK_APPROACHES)]


def generate_instruction_prompt(
    spec: GenerationSpec,
    index: int,
    prior_instructions: Optional[list[str]] = None,
) -> str:
    """Return prompt for the LLM to generate a task instruction."""
    template = _load_template("task_instruction.md")

    skill_target = spec.skill_targets[index % len(spec.skill_targets)] if spec.skill_targets else spec.domain
    difficulty = _pick_difficulty(spec, index)
    approach = _pick_approach(index, spec.task_count)

    prior_block = ""
    if prior_instructions:
        prior_list = "\n".join(f"- {instr[:150]}" for instr in prior_instructions)
        # Add diversity stats
        approach_stats = f"\n\nDiversity note: You have generated {len(prior_instructions)} tasks so far. The current required approach is '{approach}'. Make sure this task is STRUCTURALLY DIFFERENT from all previous ones — different code patterns, different problem types, different file structures."
        prior_block = f"Previously generated instructions (do NOT repeat or closely paraphrase these):\n{prior_list}{approach_stats}"

    prompt = template.replace("{domain}", spec.domain)
    prompt = prompt.replace("{skill_target}", skill_target)
    prompt = prompt.replace("{difficulty}", difficulty)
    prompt = prompt.replace("{task_approach}", approach)
    prompt = prompt.replace("{prior_instructions_block}", prior_block)

    return prompt


def _extract_structure(instruction: str) -> str:
    """Extract structural pattern from instruction for dedup.

    E.g., "Create a Python script at /workspace/X.py that generates Y"
    → "create_script_generates"
    """
    lower = instruction.lower()
    parts = []

    if "create" in lower or "write" in lower:
        parts.append("create")
    elif "fix" in lower or "debug" in lower:
        parts.append("fix")
    elif "refactor" in lower or "improve" in lower:
        parts.append("refactor")
    elif "test" in lower:
        parts.append("test")
    elif "optimize" in lower:
        parts.append("optimize")
    else:
        parts.append("other")

    if "script" in lower:
        parts.append("script")
    elif "function" in lower:
        parts.append("function")
    elif "class" in lower:
        parts.append("class")
    elif "config" in lower:
        parts.append("config")

    if "generates" in lower or "produce" in lower:
        parts.append("generates")
    elif "reads" in lower or "parse" in lower:
        parts.append("reads")
    elif "sends" in lower or "post" in lower:
        parts.append("sends")
    elif "converts" in lower:
        parts.append("converts")

    return "_".join(parts)


def ingest_instruction(
    spec: GenerationSpec,
    index: int,
    llm_response: str,
    prior_instructions: Optional[list[str]] = None,
) -> str:
    """Parse and validate LLM response as a task instruction.

    Returns the instruction string.
    Raises TaskGenerationError if instruction is empty or too similar to prior ones.
    """
    instruction = llm_response.strip()
    if not instruction:
        raise TaskGenerationError("LLM returned empty instruction")

    if prior_instructions:
        # Check text similarity (Jaccard)
        for prior in prior_instructions:
            similarity = _jaccard_similarity(instruction, prior)
            if similarity > 0.7:
                raise TaskGenerationError(
                    f"Instruction too similar to existing one (Jaccard={similarity:.2f}): "
                    f"'{instruction[:80]}...' vs '{prior[:80]}...'"
                )

        # Check structural similarity — reject if >50% of prior tasks share the same pattern
        new_structure = _extract_structure(instruction)
        if new_structure and prior_instructions:
            prior_structures = [_extract_structure(p) for p in prior_instructions]
            same_count = sum(1 for s in prior_structures if s == new_structure)
            ratio = same_count / len(prior_structures)
            if ratio > 0.5 and len(prior_instructions) >= 3:
                raise TaskGenerationError(
                    f"Too many tasks with same structure '{new_structure}' "
                    f"({same_count}/{len(prior_instructions)}). Need more diversity."
                )

    return instruction


def generate_fs_prompt(spec: GenerationSpec, instruction: str) -> str:
    """Return prompt for the LLM to generate initial_fs and success_criteria."""
    template = _load_template("task_fs_criteria.md")
    difficulty = _pick_difficulty(spec, 0)  # Will be overridden by caller with correct index

    prompt = template.replace("{domain}", spec.domain)
    prompt = prompt.replace("{instruction}", instruction)
    prompt = prompt.replace("{base_tools}", ", ".join(spec.base_tools))
    prompt = prompt.replace("{difficulty}", difficulty)

    return prompt


def _validate_paths(initial_fs: dict[str, str]) -> None:
    """Validate all paths in initial_fs."""
    for path in initial_fs:
        if not path.startswith("/workspace/"):
            raise TaskGenerationError(
                f"Path must start with '/workspace/', got: '{path}'"
            )
        if ".." in path:
            raise TaskGenerationError(
                f"Path contains path traversal '..': '{path}'"
            )


def _validate_criteria(criteria_data: list[dict]) -> list[SuccessCriterion]:
    """Validate and parse success criteria from raw dicts."""
    parsed = []
    for c in criteria_data:
        ctype = c.get("type", "")
        if ctype not in VALID_CRITERION_TYPES:
            raise TaskGenerationError(
                f"Invalid criterion type '{ctype}', must be one of {VALID_CRITERION_TYPES}"
            )
        try:
            parsed.append(SuccessCriterion(**c))
        except Exception as e:
            raise TaskGenerationError(f"Invalid criterion: {e}")
    return parsed


def ingest_fs_and_criteria(
    spec: GenerationSpec,
    index: int,
    instruction: str,
    llm_response: str,
) -> TaskSpec:
    """Parse LLM response into initial_fs and success_criteria. Return TaskSpec."""
    cleaned = _strip_json_fences(llm_response)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise TaskGenerationError(f"LLM returned invalid JSON: {e}")

    if not isinstance(data, dict):
        raise TaskGenerationError(f"Expected JSON object, got {type(data)}")

    initial_fs = data.get("initial_fs", {})
    if not isinstance(initial_fs, dict):
        raise TaskGenerationError("initial_fs must be a dict")

    criteria_data = data.get("success_criteria", [])
    if not isinstance(criteria_data, list):
        raise TaskGenerationError("success_criteria must be a list")

    # Validate paths
    _validate_paths(initial_fs)

    # Validate and parse criteria
    criteria = _validate_criteria(criteria_data)

    # Build task_id
    difficulty = _pick_difficulty(spec, index)
    skill_target = spec.skill_targets[index % len(spec.skill_targets)] if spec.skill_targets else spec.domain
    task_id = f"{spec.domain}-{index + 1:03d}"

    # Extract solution_patch if present (v0.2)
    solution_patch = data.get("solution_patch")

    # Determine task_type from spec
    task_type = spec.task_types[0] if spec.task_types else "code"

    return TaskSpec(
        task_id=task_id,
        domain=spec.domain,
        difficulty=difficulty,
        skill_target=skill_target,
        task_type=task_type,
        instruction=instruction,
        initial_fs=initial_fs,
        base_tools=spec.base_tools,
        success_criteria=criteria,
        docker_image="",  # set later by image_builder
        solution_patch=solution_patch,
    )


def generate_test_prompt(
    spec: GenerationSpec,
    instruction: str,
    initial_fs: dict[str, str],
    solution_patch: str | None = None,
) -> str:
    """Return prompt for the LLM to generate a pytest verification test file."""
    template = _load_template("task_test_generation.md")

    # Format initial_fs summary
    fs_lines = []
    for path, content in initial_fs.items():
        preview = content[:300] + "..." if len(content) > 300 else content
        fs_lines.append(f"  {path}:\n    {preview}")
    fs_summary = "\n".join(fs_lines) if fs_lines else "  (empty)"

    prompt = template.replace("{instruction}", instruction)
    prompt = prompt.replace("{initial_fs_summary}", fs_summary)
    prompt = prompt.replace("{solution_patch}", solution_patch or "(no solution provided)")

    return prompt


def _strip_python_fences(text: str) -> str:
    """Strip markdown python code fences if present."""
    text = text.strip()
    if text.startswith("```python"):
        text = text[len("```python"):]
    elif text.startswith("```"):
        text = text[len("```"):]
    if text.endswith("```"):
        text = text[:-len("```")]
    return text.strip()


def ingest_test_file(
    spec: GenerationSpec,
    index: int,
    task: TaskSpec,
    llm_response: str,
) -> TaskSpec:
    """Parse LLM response as a pytest test file. Returns updated TaskSpec."""
    test_code = _strip_python_fences(llm_response)

    if not test_code:
        raise TaskGenerationError("LLM returned empty test file")

    # Validate it's syntactically valid Python
    try:
        compile(test_code, "<test_file>", "exec")
    except SyntaxError as e:
        raise TaskGenerationError(f"Generated test file has syntax error: {e}")

    # Check it contains at least one test function
    if "def test_" not in test_code:
        raise TaskGenerationError("Generated test file contains no test_ functions")

    test_path = "/workspace/tests/test_solution.py"
    test_files = {test_path: test_code}

    # Add pytest_pass criterion if not already present
    has_pytest = any(c.type == "pytest_pass" for c in task.success_criteria)
    new_criteria = list(task.success_criteria)
    if not has_pytest:
        new_criteria.append(
            SuccessCriterion(type="pytest_pass", test_file=test_path)
        )

    return task.model_copy(update={
        "test_files": test_files,
        "success_criteria": new_criteria,
    })


def generate_skill_prompt(
    spec: GenerationSpec,
    instruction: str,
    difficulty: str,
    skill_target: str,
) -> str:
    """Return prompt for the LLM to generate a companion SKILL.md."""
    template = _load_template("task_skill_generation.md")

    prompt = template.replace("{domain}", spec.domain)
    prompt = prompt.replace("{skill_target}", skill_target)
    prompt = prompt.replace("{difficulty}", difficulty)
    prompt = prompt.replace("{instruction}", instruction)

    return prompt


def ingest_skill_file(
    task: TaskSpec,
    llm_response: str,
) -> TaskSpec:
    """Parse LLM response as a SKILL.md file. Returns updated TaskSpec."""
    skill_content = llm_response.strip()

    # Strip outer fences if present
    if skill_content.startswith("```"):
        lines = skill_content.split("\n")
        # Remove first and last fence lines
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        skill_content = "\n".join(lines)

    if not skill_content or len(skill_content) < 50:
        raise TaskGenerationError("LLM returned empty or too short SKILL.md")

    # Verify it has frontmatter
    if "---" not in skill_content:
        # Add minimal frontmatter
        skill_content = f"---\nname: {task.domain}-guide\ndescription: Procedural guide for {task.skill_target}\n---\n\n{skill_content}"

    skill_name = f"{task.domain}-guide"
    skill_path = f"/workspace/skills/{skill_name}/SKILL.md"
    skill_files = {skill_path: skill_content}

    return task.model_copy(update={"skill_files": skill_files})
