"""Step 2 (CODE): Generate task instruction, initial_fs, and success criteria."""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Optional

from .schema import GenerationSpec, SuccessCriterion, TaskSpec, VALID_CRITERION_TYPES

PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"


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


def generate_instruction_prompt(
    spec: GenerationSpec,
    index: int,
    prior_instructions: Optional[list[str]] = None,
) -> str:
    """Return prompt for the LLM to generate a task instruction."""
    template = _load_template("task_instruction.md")

    skill_target = spec.skill_targets[index % len(spec.skill_targets)] if spec.skill_targets else spec.domain
    difficulty = _pick_difficulty(spec, index)

    prior_block = ""
    if prior_instructions:
        prior_list = "\n".join(f"- {instr}" for instr in prior_instructions)
        prior_block = f"Previously generated instructions (do NOT repeat or closely paraphrase these):\n{prior_list}"

    prompt = template.replace("{domain}", spec.domain)
    prompt = prompt.replace("{skill_target}", skill_target)
    prompt = prompt.replace("{difficulty}", difficulty)
    prompt = prompt.replace("{prior_instructions_block}", prior_block)

    return prompt


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

    # Check uniqueness against prior instructions
    if prior_instructions:
        for prior in prior_instructions:
            similarity = _jaccard_similarity(instruction, prior)
            if similarity > 0.7:
                raise TaskGenerationError(
                    f"Instruction too similar to existing one (Jaccard={similarity:.2f}): "
                    f"'{instruction[:80]}...' vs '{prior[:80]}...'"
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

    return TaskSpec(
        task_id=task_id,
        domain=spec.domain,
        difficulty=difficulty,
        skill_target=skill_target,
        task_type="code",
        instruction=instruction,
        initial_fs=initial_fs,
        base_tools=spec.base_tools,
        success_criteria=criteria,
        docker_image="",  # set later by image_builder
    )
