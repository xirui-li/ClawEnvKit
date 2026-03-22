"""Data structures for Claw Harnessing pipeline."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, field_validator, model_validator


# --- Defaults ---

SUPPORTED_DOMAINS = [
    "cli-file-ops",
    "git-workflow",
    "json-processing",
    "shell-scripting",
    "python-debugging",
]

VALID_DIFFICULTIES = ("easy", "medium", "hard")

VALID_CRITERION_TYPES = (
    "exit_code",
    "file_exists",
    "file_contains",
    "file_not_contains",
)

DEFAULTS = {
    "task_count": 20,
    "difficulty_distribution": {"easy": 0.3, "medium": 0.5, "hard": 0.2},
    "base_tools": ["bash", "python3"],
    "target_agent": "metaclaw",
    "task_types": ["code"],
}


# --- Core data structures ---


class GenerationSpec(BaseModel):
    domain: str
    task_count: int = DEFAULTS["task_count"]
    difficulty_distribution: dict[str, float] = DEFAULTS["difficulty_distribution"]
    skill_targets: list[str] = []
    base_tools: list[str] = DEFAULTS["base_tools"]
    output_dir: str = "~/clawharness-tasks"
    target_agent: str = DEFAULTS["target_agent"]
    task_types: list[str] = DEFAULTS["task_types"]

    @field_validator("task_types")
    @classmethod
    def force_code_only(cls, v: list[str]) -> list[str]:
        """v0.1: only 'code' task type is supported."""
        return ["code"]

    @field_validator("difficulty_distribution")
    @classmethod
    def validate_difficulty_keys(cls, v: dict[str, float]) -> dict[str, float]:
        for key in v:
            if key not in VALID_DIFFICULTIES:
                raise ValueError(f"invalid difficulty '{key}', must be one of {VALID_DIFFICULTIES}")
        return v


class SuccessCriterion(BaseModel):
    type: str

    # for type="exit_code"
    cmd: Optional[str] = None
    expected_exit: int = 0

    # for type="file_exists" | "file_contains" | "file_not_contains"
    path: Optional[str] = None
    pattern: Optional[str] = None  # file_contains / file_not_contains only

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        if v not in VALID_CRITERION_TYPES:
            raise ValueError(
                f"invalid criterion type '{v}', must be one of {VALID_CRITERION_TYPES}"
            )
        return v

    @model_validator(mode="after")
    def validate_fields_for_type(self) -> SuccessCriterion:
        if self.type == "exit_code" and self.cmd is None:
            raise ValueError("exit_code criterion requires 'cmd'")
        if self.type in ("file_exists", "file_contains", "file_not_contains") and self.path is None:
            raise ValueError(f"{self.type} criterion requires 'path'")
        if self.type == "file_contains" and self.pattern is None:
            raise ValueError("file_contains criterion requires 'pattern'")
        if self.type == "file_not_contains" and self.pattern is None:
            raise ValueError("file_not_contains criterion requires 'pattern'")
        return self


class ConsistencyResult(BaseModel):
    passed: bool
    issues: list[str] = []
    regenerate: bool = False
    llm_check_prompt: Optional[str] = None


class ValidationResult(BaseModel):
    passed: bool
    solver_actions: list[str] = []
    criteria_results: list[bool] = []
    failure_reason: Optional[str] = None
    retry_count: int = 0


class TaskSpec(BaseModel):
    task_id: str
    domain: str
    difficulty: str
    skill_target: str
    task_type: str = "code"
    instruction: str = ""
    initial_fs: dict[str, str] = {}
    base_tools: list[str] = []
    success_criteria: list[SuccessCriterion] = []
    docker_image: str = ""
    consistency_check: Optional[ConsistencyResult] = None
    validation_result: Optional[ValidationResult] = None

    @field_validator("difficulty")
    @classmethod
    def validate_difficulty(cls, v: str) -> str:
        if v not in VALID_DIFFICULTIES:
            raise ValueError(f"invalid difficulty '{v}', must be one of {VALID_DIFFICULTIES}")
        return v

    @field_validator("task_type")
    @classmethod
    def validate_task_type(cls, v: str) -> str:
        if v != "code":
            raise ValueError("v0.1 only supports task_type='code'")
        return v


class BuildResult(BaseModel):
    image_name: str
    build_time_seconds: float = 0.0
    image_size_bytes: int = 0
    success: bool = True
    error: Optional[str] = None


class ExportResult(BaseModel):
    jsonl_path: str
    task_count: int = 0
    failed_validation_count: int = 0
    image_names: list[str] = []


class IntentParserResult(BaseModel):
    state: str  # "needs_clarification" | "ready"
    spec: Optional[GenerationSpec] = None
    clarification_prompt: Optional[str] = None

    @field_validator("state")
    @classmethod
    def validate_state(cls, v: str) -> str:
        if v not in ("needs_clarification", "ready"):
            raise ValueError(f"state must be 'needs_clarification' or 'ready', got '{v}'")
        return v


class ConsistencyCheckResult(BaseModel):
    state: str  # "passed" | "failed" | "needs_llm_check"
    result: Optional[ConsistencyResult] = None
    semantic_prompt: Optional[str] = None

    @field_validator("state")
    @classmethod
    def validate_state(cls, v: str) -> str:
        if v not in ("passed", "failed", "needs_llm_check"):
            raise ValueError(f"state must be 'passed', 'failed', or 'needs_llm_check', got '{v}'")
        return v
