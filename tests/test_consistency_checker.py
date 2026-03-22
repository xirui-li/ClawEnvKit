"""Tests for scripts/core/consistency_checker.py"""

import json

import pytest

from scripts.core.schema import SuccessCriterion, TaskSpec
from scripts.core.consistency_checker import (
    check,
    check_deterministic,
    check_semantic_ingest,
    check_semantic_prompt,
    extract_filenames_from_instruction,
)


def _make_task(**overrides):
    defaults = dict(
        task_id="test-001",
        domain="cli-file-ops",
        difficulty="easy",
        skill_target="file create",
        task_type="code",
        instruction="Create a new file in the workspace directory",
        initial_fs={"/workspace/README.md": "instructions"},
        base_tools=["bash", "python3"],
        success_criteria=[
            SuccessCriterion(type="file_exists", path="/workspace/hello.txt"),
        ],
        docker_image="",
    )
    defaults.update(overrides)
    return TaskSpec(**defaults)


# --- extract_filenames_from_instruction ---


class TestExtractFilenames:
    def test_quoted_filename(self):
        result = extract_filenames_from_instruction("Create a file called 'hello.txt'")
        assert "hello.txt" in result

    def test_double_quoted(self):
        result = extract_filenames_from_instruction('Edit "main.py" to fix the bug')
        assert "main.py" in result

    def test_workspace_path(self):
        result = extract_filenames_from_instruction("Fix /workspace/src/app.py")
        assert "/workspace/src/app.py" in result

    def test_no_filenames(self):
        result = extract_filenames_from_instruction("Create a directory and list files")
        assert result == []

    def test_multiple_filenames(self):
        result = extract_filenames_from_instruction("Copy 'a.txt' to 'b.txt'")
        assert "a.txt" in result
        assert "b.txt" in result


# --- check_deterministic ---


class TestCheckDeterministic:
    def test_clean_task_passes(self):
        task = _make_task()
        issues = check_deterministic(task)
        assert issues == []

    def test_missing_file_in_instruction(self):
        task = _make_task(
            instruction="Fix the bug in 'main.py'",
            initial_fs={"/workspace/README.md": "readme"},
        )
        issues = check_deterministic(task)
        assert any("main.py" in i and "not in initial_fs" in i for i in issues)

    def test_criterion_path_not_in_initial_fs(self):
        task = _make_task(
            success_criteria=[
                SuccessCriterion(
                    type="file_contains",
                    path="/workspace/output.csv",
                    pattern="result",
                ),
            ],
        )
        issues = check_deterministic(task)
        assert any("output.csv" in i for i in issues)

    def test_file_exists_criterion_not_flagged(self):
        """file_exists checks files the agent CREATES, so shouldn't be flagged."""
        task = _make_task(
            success_criteria=[
                SuccessCriterion(type="file_exists", path="/workspace/new_file.txt"),
            ],
        )
        issues = check_deterministic(task)
        assert not any("new_file.txt" in i for i in issues)

    def test_easy_task_too_many_files(self):
        task = _make_task(
            difficulty="easy",
            initial_fs={
                "/workspace/a.txt": "a",
                "/workspace/b.txt": "b",
                "/workspace/c.txt": "c",
            },
        )
        issues = check_deterministic(task)
        assert any("easy task has 3 files" in i for i in issues)

    def test_hard_task_too_few_criteria(self):
        task = _make_task(
            difficulty="hard",
            success_criteria=[
                SuccessCriterion(type="file_exists", path="/workspace/out.txt"),
            ],
        )
        issues = check_deterministic(task)
        assert any("hard task has only 1" in i for i in issues)

    def test_medium_task_no_heuristic_warnings(self):
        task = _make_task(
            difficulty="medium",
            instruction="Process the input files and produce output",
            initial_fs={"/workspace/a.txt": "a", "/workspace/b.txt": "b"},
            success_criteria=[
                SuccessCriterion(type="file_exists", path="/workspace/out.txt"),
                SuccessCriterion(type="exit_code", cmd="echo ok"),
            ],
        )
        issues = check_deterministic(task)
        assert issues == []


# --- check (full flow) ---


class TestCheck:
    def test_clean_easy_task_passes(self):
        task = _make_task()
        result = check(task)
        assert result.state == "passed"
        assert result.result.passed is True

    def test_blocking_issue_fails(self):
        task = _make_task(
            instruction="Fix the bug in 'main.py'",
            initial_fs={"/workspace/README.md": "readme"},
        )
        result = check(task)
        assert result.state == "failed"
        assert result.result.regenerate is True

    def test_soft_warning_passes(self):
        """Easy task with 3 files is a soft warning, not blocking."""
        task = _make_task(
            instruction="Create a new output file",
            initial_fs={
                "/workspace/a.txt": "a",
                "/workspace/b.txt": "b",
                "/workspace/c.txt": "c",
            },
        )
        result = check(task)
        assert result.state == "passed"
        assert result.result.regenerate is False
        assert len(result.result.issues) > 0  # soft warning present

    def test_hard_task_triggers_semantic(self):
        task = _make_task(
            difficulty="hard",
            initial_fs={
                "/workspace/a.py": "code",
                "/workspace/b.py": "code",
                "/workspace/c.py": "code",
            },
            success_criteria=[
                SuccessCriterion(type="exit_code", cmd="python3 /workspace/a.py"),
                SuccessCriterion(type="file_exists", path="/workspace/out.txt"),
            ],
        )
        result = check(task)
        assert result.state == "needs_llm_check"
        assert result.semantic_prompt is not None

    def test_hard_task_skip_semantic(self):
        task = _make_task(
            difficulty="hard",
            initial_fs={
                "/workspace/a.py": "code",
                "/workspace/b.py": "code",
                "/workspace/c.py": "code",
            },
            success_criteria=[
                SuccessCriterion(type="exit_code", cmd="python3 /workspace/a.py"),
                SuccessCriterion(type="file_exists", path="/workspace/out.txt"),
            ],
        )
        result = check(task, skip_semantic=True)
        assert result.state == "passed"

    def test_easy_task_no_semantic(self):
        task = _make_task(difficulty="easy")
        result = check(task)
        assert result.state == "passed"
        assert result.semantic_prompt is None


# --- check_semantic_prompt ---


class TestCheckSemanticPrompt:
    def test_contains_task_fields(self):
        task = _make_task(
            difficulty="hard",
            instruction="Fix the broken import",
        )
        prompt = check_semantic_prompt(task)
        assert "hard" in prompt
        assert "Fix the broken import" in prompt
        assert "code" in prompt


# --- check_semantic_ingest ---


class TestCheckSemanticIngest:
    def test_passed(self):
        task = _make_task()
        response = json.dumps({"passed": True, "issues": []})
        result = check_semantic_ingest(task, response)
        assert result.passed is True
        assert result.regenerate is False

    def test_failed_blocking(self):
        task = _make_task()
        response = json.dumps({
            "passed": False,
            "issues": ["instruction references 'config.py' which is not in initial_fs"],
        })
        result = check_semantic_ingest(task, response)
        assert result.passed is False
        assert result.regenerate is True

    def test_failed_soft(self):
        task = _make_task()
        response = json.dumps({
            "passed": False,
            "issues": ["difficulty seems too easy for this task"],
        })
        result = check_semantic_ingest(task, response)
        assert result.passed is False
        assert result.regenerate is False  # soft issue, no regeneration

    def test_invalid_json_fails_open(self):
        task = _make_task()
        result = check_semantic_ingest(task, "not json at all")
        assert result.passed is True  # fail-open

    def test_with_llm_response(self):
        """Full flow: check() with llm_response ingests semantic result."""
        task = _make_task(difficulty="hard")
        response = json.dumps({"passed": True, "issues": []})
        result = check(task, llm_response=response)
        assert result.state == "passed"
        assert result.result.passed is True
