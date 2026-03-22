"""Tests for scripts/core/schema.py"""

import json

import pytest
from pydantic import ValidationError

from scripts.core.schema import (
    DEFAULTS,
    ConsistencyCheckResult,
    ConsistencyResult,
    ExportResult,
    GenerationSpec,
    IntentParserResult,
    SuccessCriterion,
    TaskSpec,
    ValidationResult,
    BuildResult,
)


# --- GenerationSpec ---


class TestGenerationSpec:
    def test_defaults_applied(self):
        spec = GenerationSpec(domain="cli-file-ops")
        assert spec.task_count == 20
        assert spec.difficulty_distribution == {"easy": 0.3, "medium": 0.5, "hard": 0.2}
        assert spec.base_tools == ["bash", "python3"]
        assert spec.target_agent == "metaclaw"
        assert spec.task_types == ["code"]

    def test_task_types_forced_to_code(self):
        spec = GenerationSpec(domain="git-workflow", task_types=["design", "review"])
        assert spec.task_types == ["code"]

    def test_custom_values(self):
        spec = GenerationSpec(
            domain="git-workflow",
            task_count=10,
            difficulty_distribution={"easy": 1.0},
            skill_targets=["git merge", "git rebase"],
            base_tools=["git", "bash"],
            output_dir="~/my-tasks",
        )
        assert spec.domain == "git-workflow"
        assert spec.task_count == 10
        assert spec.skill_targets == ["git merge", "git rebase"]

    def test_invalid_difficulty_key(self):
        with pytest.raises(ValidationError, match="invalid difficulty"):
            GenerationSpec(domain="cli-file-ops", difficulty_distribution={"super_hard": 1.0})

    def test_serialization_roundtrip(self):
        spec = GenerationSpec(domain="cli-file-ops", task_count=5)
        data = json.loads(spec.model_dump_json())
        spec2 = GenerationSpec(**data)
        assert spec == spec2


# --- SuccessCriterion ---


class TestSuccessCriterion:
    def test_exit_code_valid(self):
        c = SuccessCriterion(type="exit_code", cmd="python3 main.py")
        assert c.type == "exit_code"
        assert c.expected_exit == 0

    def test_file_exists_valid(self):
        c = SuccessCriterion(type="file_exists", path="/workspace/out.txt")
        assert c.path == "/workspace/out.txt"

    def test_file_contains_valid(self):
        c = SuccessCriterion(type="file_contains", path="/workspace/out.txt", pattern="hello")
        assert c.pattern == "hello"

    def test_file_not_contains_valid(self):
        c = SuccessCriterion(type="file_not_contains", path="/workspace/out.txt", pattern="error")
        assert c.type == "file_not_contains"

    def test_invalid_type_rejected(self):
        with pytest.raises(ValidationError, match="invalid criterion type"):
            SuccessCriterion(type="llm_judge")

    def test_invalid_type_unknown(self):
        with pytest.raises(ValidationError, match="invalid criterion type"):
            SuccessCriterion(type="banana")

    def test_exit_code_missing_cmd(self):
        with pytest.raises(ValidationError, match="requires 'cmd'"):
            SuccessCriterion(type="exit_code")

    def test_file_exists_missing_path(self):
        with pytest.raises(ValidationError, match="requires 'path'"):
            SuccessCriterion(type="file_exists")

    def test_file_contains_missing_pattern(self):
        with pytest.raises(ValidationError, match="requires 'pattern'"):
            SuccessCriterion(type="file_contains", path="/workspace/out.txt")

    def test_file_not_contains_missing_pattern(self):
        with pytest.raises(ValidationError, match="requires 'pattern'"):
            SuccessCriterion(type="file_not_contains", path="/workspace/out.txt")


# --- TaskSpec ---


class TestTaskSpec:
    def _make_task(self, **overrides):
        defaults = dict(
            task_id="test-001",
            domain="cli-file-ops",
            difficulty="easy",
            skill_target="file create",
            task_type="code",
            instruction="Create hello.txt",
            initial_fs={"/workspace/README.md": "instructions"},
            base_tools=["bash", "python3"],
            success_criteria=[
                SuccessCriterion(type="file_exists", path="/workspace/hello.txt"),
            ],
            docker_image="clawharness/cli-file-ops/test-001:v1",
        )
        defaults.update(overrides)
        return TaskSpec(**defaults)

    def test_valid_task(self):
        task = self._make_task()
        assert task.task_id == "test-001"
        assert task.base_tools == ["bash", "python3"]

    def test_serialization_roundtrip(self):
        task = self._make_task()
        data = json.loads(task.model_dump_json())
        task2 = TaskSpec(**data)
        assert task == task2

    def test_invalid_difficulty(self):
        with pytest.raises(ValidationError, match="invalid difficulty"):
            self._make_task(difficulty="extreme")

    def test_invalid_task_type(self):
        with pytest.raises(ValidationError, match="v0.1 only supports"):
            self._make_task(task_type="review")

    def test_optional_fields_default_none(self):
        task = self._make_task()
        assert task.consistency_check is None
        assert task.validation_result is None

    def test_with_consistency_and_validation(self):
        task = self._make_task(
            consistency_check=ConsistencyResult(passed=True),
            validation_result=ValidationResult(
                passed=True,
                solver_actions=["echo hello > /workspace/hello.txt"],
                criteria_results=[True],
            ),
        )
        assert task.consistency_check.passed is True
        assert task.validation_result.passed is True


# --- Other models ---


class TestBuildResult:
    def test_success(self):
        r = BuildResult(image_name="clawharness/test/t1:v1", success=True)
        assert r.error is None

    def test_failure(self):
        r = BuildResult(image_name="clawharness/test/t1:v1", success=False, error="build failed")
        assert r.error == "build failed"


class TestExportResult:
    def test_basic(self):
        r = ExportResult(jsonl_path="~/tasks/train.jsonl", task_count=5, image_names=["a", "b"])
        assert r.task_count == 5


class TestIntentParserResult:
    def test_needs_clarification(self):
        r = IntentParserResult(state="needs_clarification", clarification_prompt="what domain?")
        assert r.spec is None

    def test_ready(self):
        spec = GenerationSpec(domain="cli-file-ops")
        r = IntentParserResult(state="ready", spec=spec)
        assert r.spec.domain == "cli-file-ops"

    def test_invalid_state(self):
        with pytest.raises(ValidationError, match="state must be"):
            IntentParserResult(state="broken")


class TestConsistencyCheckResult:
    def test_passed(self):
        r = ConsistencyCheckResult(
            state="passed",
            result=ConsistencyResult(passed=True),
        )
        assert r.result.passed is True

    def test_needs_llm(self):
        r = ConsistencyCheckResult(state="needs_llm_check", semantic_prompt="check this")
        assert r.semantic_prompt == "check this"

    def test_invalid_state(self):
        with pytest.raises(ValidationError, match="state must be"):
            ConsistencyCheckResult(state="unknown")
