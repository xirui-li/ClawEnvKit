"""Data structures for Claw Harnessing pipeline."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, field_validator, model_validator


# --- Defaults ---

SUPPORTED_DOMAINS = [
    # v0.2 primary
    "bug-fix",              # Fix bugs in existing code (SWE-bench style F2P)
    "feature-impl",         # Implement features to pass provided tests
    # Retained from v0.1, enhanced
    "git-workflow",         # Branch, merge, rebase with real conflicts
    "shell-scripting",      # Pipes, loops, env vars, scripting
    # v0.2 domains
    "data-processing",      # JSON/CSV/log parsing and transformation
    "config-devops",        # YAML/TOML/Docker config editing
    # v0.3 mock API domains
    "communication",        # Slack, Discord, email API interaction
    "smart-home",           # Hue, HomeAssistant API interaction
    "browser-scraping",     # Web scraping from static HTML
    # v0.1 legacy (still accepted for backward compat)
    "cli-file-ops",
    "json-processing",
    "python-debugging",
]

VALID_DIFFICULTIES = ("easy", "medium", "hard")

VALID_TASK_TYPES = ("code", "bug-fix", "feature-impl", "api-integration")

VALID_CRITERION_TYPES = (
    # v0.1 (retained)
    "exit_code",
    "file_exists",
    "file_contains",
    "file_not_contains",
    # v0.2
    "pytest_pass",
    # v0.3
    "mock_api_verify",      # Verify mock server received expected API calls
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
    def validate_task_types(cls, v: list[str]) -> list[str]:
        for t in v:
            if t not in VALID_TASK_TYPES:
                raise ValueError(f"invalid task_type '{t}', must be one of {VALID_TASK_TYPES}")
        return v

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

    # for type="pytest_pass"
    test_file: Optional[str] = None       # e.g., "/workspace/tests/test_solution.py"
    pytest_args: Optional[str] = None     # e.g., "-v --tb=short"

    # for type="mock_api_verify"
    expected_calls_file: Optional[str] = None  # e.g., "/workspace/mock_server/expected_calls.json"

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
        if self.type == "pytest_pass" and self.test_file is None:
            raise ValueError("pytest_pass criterion requires 'test_file'")
        if self.type == "mock_api_verify" and self.expected_calls_file is None:
            raise ValueError("mock_api_verify criterion requires 'expected_calls_file'")
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


class MockServerConfig(BaseModel):
    """Configuration for mock API server inside Docker container."""
    port: int = 8080
    responses: dict[str, dict] = {}         # path+method → {"status": 200, "body": {...}}
    expected_calls: list[dict] = []         # list of expected call patterns
    env_vars: dict[str, str] = {}           # env vars to set (e.g. SLACK_API_URL=http://localhost:8080)
    min_calls: Optional[int] = None         # minimum total API calls expected
    strict: bool = False                    # reject unexpected API paths


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
    # v0.2 fields
    test_files: dict[str, str] = {}        # verification test files (separate from initial_fs)
    solution_patch: Optional[str] = None   # gold solution for FAIL_TO_PASS validation
    schema_version: str = "0.3.0"
    # v0.3 fields
    mock_server_config: Optional[MockServerConfig] = None  # mock API server setup
    # v0.4 fields
    skill_files: dict[str, str] = {}       # SKILL.md + optional scripts baked into container

    @field_validator("difficulty")
    @classmethod
    def validate_difficulty(cls, v: str) -> str:
        if v not in VALID_DIFFICULTIES:
            raise ValueError(f"invalid difficulty '{v}', must be one of {VALID_DIFFICULTIES}")
        return v

    @field_validator("task_type")
    @classmethod
    def validate_task_type(cls, v: str) -> str:
        if v not in VALID_TASK_TYPES:
            raise ValueError(f"invalid task_type '{v}', must be one of {VALID_TASK_TYPES}")
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


# --- Backward compatibility ---


def upgrade_v01_task(data: dict) -> dict:
    """Upgrade a v0.1 task state dict to v0.2 format."""
    if "schema_version" not in data:
        data["schema_version"] = "0.1.0"
    if "test_files" not in data:
        data["test_files"] = {}
    if "solution_patch" not in data:
        data["solution_patch"] = None
    # Map old task_type "code" to remain valid
    if data.get("task_type") not in VALID_TASK_TYPES:
        data["task_type"] = "code"
    return data
