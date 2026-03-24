"""Tests for scripts/core/task_generator.py"""

import json

import pytest

from scripts.core.schema import GenerationSpec, SuccessCriterion, TaskSpec
from scripts.core.task_generator import (
    TaskGenerationError,
    generate_fs_prompt,
    generate_instruction_prompt,
    generate_test_prompt,
    ingest_fs_and_criteria,
    ingest_instruction,
    _extract_structure,
    ingest_test_file,
    _jaccard_similarity,
)


def _make_spec(**overrides):
    defaults = dict(
        domain="cli-file-ops",
        task_count=5,
        difficulty_distribution={"easy": 1.0},
        skill_targets=["file create", "file edit"],
        base_tools=["bash", "python3"],
        output_dir="~/test-tasks",
    )
    defaults.update(overrides)
    return GenerationSpec(**defaults)


# --- generate_instruction_prompt ---


class TestGenerateInstructionPrompt:
    def test_contains_domain(self):
        spec = _make_spec()
        prompt = generate_instruction_prompt(spec, 0)
        assert "cli-file-ops" in prompt

    def test_contains_difficulty(self):
        spec = _make_spec()
        prompt = generate_instruction_prompt(spec, 0)
        assert "easy" in prompt

    def test_contains_skill_target(self):
        spec = _make_spec()
        prompt = generate_instruction_prompt(spec, 0)
        assert "file create" in prompt

    def test_skill_target_wraps_around(self):
        spec = _make_spec(skill_targets=["file create", "file edit"])
        prompt = generate_instruction_prompt(spec, 2)
        assert "file create" in prompt  # index 2 % 2 == 0

    def test_prior_instructions_included(self):
        spec = _make_spec()
        prompt = generate_instruction_prompt(spec, 1, prior_instructions=["Create a file named foo.txt"])
        assert "Create a file named foo.txt" in prompt
        assert "do NOT repeat" in prompt

    def test_no_prior_instructions(self):
        spec = _make_spec()
        prompt = generate_instruction_prompt(spec, 0, prior_instructions=None)
        assert "do NOT repeat" not in prompt

    def test_empty_skill_targets_uses_domain(self):
        spec = _make_spec(skill_targets=[])
        prompt = generate_instruction_prompt(spec, 0)
        assert "cli-file-ops" in prompt


# --- ingest_instruction ---


class TestIngestInstruction:
    def test_valid_instruction(self):
        spec = _make_spec()
        result = ingest_instruction(spec, 0, "Create a file called hello.txt")
        assert result == "Create a file called hello.txt"

    def test_strips_whitespace(self):
        spec = _make_spec()
        result = ingest_instruction(spec, 0, "  Create hello.txt  \n")
        assert result == "Create hello.txt"

    def test_empty_raises(self):
        spec = _make_spec()
        with pytest.raises(TaskGenerationError, match="empty instruction"):
            ingest_instruction(spec, 0, "   ")

    def test_duplicate_rejected(self):
        spec = _make_spec()
        prior = ["Create a file called hello.txt with some content"]
        with pytest.raises(TaskGenerationError, match="too similar"):
            ingest_instruction(
                spec, 1,
                "Create a file called hello.txt with some content inside",
                prior_instructions=prior,
            )

    def test_unique_accepted(self):
        spec = _make_spec()
        prior = ["Create a file called hello.txt"]
        result = ingest_instruction(
            spec, 1,
            "Delete all .log files from the /workspace/logs directory",
            prior_instructions=prior,
        )
        assert "Delete" in result


# --- Jaccard similarity ---


class TestJaccardSimilarity:
    def test_identical(self):
        assert _jaccard_similarity("hello world", "hello world") == 1.0

    def test_disjoint(self):
        assert _jaccard_similarity("hello world", "foo bar") == 0.0

    def test_partial(self):
        sim = _jaccard_similarity("create a file", "create a directory")
        assert 0.0 < sim < 1.0

    def test_empty(self):
        assert _jaccard_similarity("", "") == 1.0


# --- structural dedup ---


class TestExtractStructure:
    def test_create_script_generates(self):
        s = _extract_structure("Create a Python script at /workspace/gen.py that generates an HTML report")
        assert "create" in s
        assert "script" in s
        assert "generates" in s

    def test_fix_function(self):
        s = _extract_structure("Fix the broken calculate function in math_utils.py")
        assert "fix" in s
        assert "function" in s

    def test_refactor_class(self):
        s = _extract_structure("Refactor the UserManager class to use dependency injection")
        assert "refactor" in s
        assert "class" in s

    def test_optimize(self):
        s = _extract_structure("Optimize the database query in reports.py")
        assert "optimize" in s


class TestStructuralDedup:
    def test_too_many_same_structure_rejected(self):
        spec = _make_spec(task_count=10)
        priors = [
            "Create a Python script at /workspace/gen1.py that generates an HTML page",
            "Create a Python script at /workspace/gen2.py that generates a CSV report",
            "Create a Python script at /workspace/gen3.py that generates a JSON file",
            "Create a Python script at /workspace/gen4.py that generates an XML doc",
        ]
        with pytest.raises(TaskGenerationError, match="same structure"):
            ingest_instruction(
                spec, 4,
                "Create a Python script at /workspace/gen5.py that generates a PDF",
                prior_instructions=priors,
            )

    def test_diverse_structures_accepted(self):
        spec = _make_spec(task_count=10)
        priors = [
            "Create a Python script that generates an HTML page",
            "Fix the broken import in the calculator module",
            "Refactor the UserManager class to use async",
        ]
        result = ingest_instruction(
            spec, 3,
            "Optimize the search function to handle edge cases",
            prior_instructions=priors,
        )
        assert "Optimize" in result

    def test_approach_in_prompt(self):
        spec = _make_spec()
        prompt = generate_instruction_prompt(spec, 0)
        assert "create" in prompt  # index 0 → "create" approach

    def test_approach_rotates(self):
        spec = _make_spec()
        p0 = generate_instruction_prompt(spec, 0)
        p1 = generate_instruction_prompt(spec, 1)
        p2 = generate_instruction_prompt(spec, 2)
        assert "create" in p0
        assert "fix" in p1
        assert "refactor" in p2


# --- generate_fs_prompt ---


class TestGenerateFsPrompt:
    def test_contains_instruction(self):
        spec = _make_spec()
        prompt = generate_fs_prompt(spec, "Create hello.txt")
        assert "Create hello.txt" in prompt

    def test_contains_domain(self):
        spec = _make_spec()
        prompt = generate_fs_prompt(spec, "Create hello.txt")
        assert "cli-file-ops" in prompt

    def test_contains_base_tools(self):
        spec = _make_spec(base_tools=["git", "bash"])
        prompt = generate_fs_prompt(spec, "Create hello.txt")
        assert "git" in prompt
        assert "bash" in prompt


# --- ingest_fs_and_criteria ---


class TestIngestFsAndCriteria:
    def _valid_response(self, **overrides):
        data = {
            "initial_fs": {"/workspace/README.md": "instructions here"},
            "success_criteria": [
                {"type": "file_exists", "path": "/workspace/hello.txt"},
            ],
        }
        data.update(overrides)
        return json.dumps(data)

    def test_valid_response(self):
        spec = _make_spec()
        task = ingest_fs_and_criteria(spec, 0, "Create hello.txt", self._valid_response())
        assert task.task_id == "cli-file-ops-001"
        assert task.domain == "cli-file-ops"
        assert task.instruction == "Create hello.txt"
        assert task.base_tools == ["bash", "python3"]
        assert task.docker_image == ""
        assert len(task.success_criteria) == 1

    def test_path_traversal_rejected(self):
        response = json.dumps({
            "initial_fs": {"/workspace/../etc/passwd": "root:x:0:0"},
            "success_criteria": [],
        })
        spec = _make_spec()
        with pytest.raises(TaskGenerationError, match="path traversal"):
            ingest_fs_and_criteria(spec, 0, "hack", response)

    def test_path_outside_workspace_rejected(self):
        response = json.dumps({
            "initial_fs": {"/tmp/evil.txt": "bad"},
            "success_criteria": [],
        })
        spec = _make_spec()
        with pytest.raises(TaskGenerationError, match="must start with '/workspace/'"):
            ingest_fs_and_criteria(spec, 0, "hack", response)

    def test_invalid_criterion_type(self):
        response = json.dumps({
            "initial_fs": {"/workspace/a.txt": "content"},
            "success_criteria": [{"type": "llm_judge"}],
        })
        spec = _make_spec()
        with pytest.raises(TaskGenerationError, match="Invalid criterion type"):
            ingest_fs_and_criteria(spec, 0, "task", response)

    def test_malformed_json(self):
        spec = _make_spec()
        with pytest.raises(TaskGenerationError, match="invalid JSON"):
            ingest_fs_and_criteria(spec, 0, "task", "not json")

    def test_json_with_markdown_fences(self):
        raw = self._valid_response()
        fenced = f"```json\n{raw}\n```"
        spec = _make_spec()
        task = ingest_fs_and_criteria(spec, 0, "Create hello.txt", fenced)
        assert task.task_id == "cli-file-ops-001"

    def test_base_tools_copied_from_spec(self):
        spec = _make_spec(base_tools=["git", "bash", "python3"])
        task = ingest_fs_and_criteria(spec, 0, "Create hello.txt", self._valid_response())
        assert task.base_tools == ["git", "bash", "python3"]

    def test_task_id_increments(self):
        spec = _make_spec()
        task0 = ingest_fs_and_criteria(spec, 0, "task 0", self._valid_response())
        task1 = ingest_fs_and_criteria(spec, 1, "task 1", self._valid_response())
        assert task0.task_id == "cli-file-ops-001"
        assert task1.task_id == "cli-file-ops-002"

    def test_exit_code_criterion_missing_cmd(self):
        response = json.dumps({
            "initial_fs": {"/workspace/a.txt": "x"},
            "success_criteria": [{"type": "exit_code"}],
        })
        spec = _make_spec()
        with pytest.raises(TaskGenerationError, match="Invalid criterion"):
            ingest_fs_and_criteria(spec, 0, "task", response)

    def test_multiple_criteria(self):
        response = json.dumps({
            "initial_fs": {"/workspace/main.py": "print('hi')"},
            "success_criteria": [
                {"type": "exit_code", "cmd": "python3 /workspace/main.py", "expected_exit": 0},
                {"type": "file_contains", "path": "/workspace/main.py", "pattern": "print"},
            ],
        })
        spec = _make_spec()
        task = ingest_fs_and_criteria(spec, 0, "fix main.py", response)
        assert len(task.success_criteria) == 2

    def test_solution_patch_extracted(self):
        response = json.dumps({
            "initial_fs": {"/workspace/main.py": "import broken"},
            "success_criteria": [
                {"type": "exit_code", "cmd": "python3 /workspace/main.py", "expected_exit": 0},
            ],
            "solution_patch": "sed -i 's/broken/os/' /workspace/main.py",
        })
        spec = _make_spec()
        task = ingest_fs_and_criteria(spec, 0, "fix import", response)
        assert task.solution_patch == "sed -i 's/broken/os/' /workspace/main.py"

    def test_solution_patch_optional(self):
        response = json.dumps({
            "initial_fs": {"/workspace/a.txt": "x"},
            "success_criteria": [],
        })
        spec = _make_spec()
        task = ingest_fs_and_criteria(spec, 0, "task", response)
        assert task.solution_patch is None


# --- generate_test_prompt ---


class TestGenerateTestPrompt:
    def test_contains_instruction(self):
        spec = _make_spec()
        prompt = generate_test_prompt(
            spec, "Fix the broken import",
            {"/workspace/main.py": "import broken"},
            "sed -i 's/broken/os/' main.py",
        )
        assert "Fix the broken import" in prompt

    def test_contains_initial_fs(self):
        spec = _make_spec()
        prompt = generate_test_prompt(
            spec, "Fix it",
            {"/workspace/main.py": "import broken"},
        )
        assert "main.py" in prompt

    def test_contains_solution(self):
        spec = _make_spec()
        prompt = generate_test_prompt(
            spec, "Fix it",
            {"/workspace/main.py": "code"},
            "the fix command",
        )
        assert "the fix command" in prompt

    def test_no_solution_handled(self):
        spec = _make_spec()
        prompt = generate_test_prompt(spec, "Fix it", {})
        assert "no solution provided" in prompt


# --- ingest_test_file ---


class TestIngestTestFile:
    def _make_task_for_test(self):
        return TaskSpec(
            task_id="test-001",
            domain="bug-fix",
            difficulty="easy",
            skill_target="fix import",
            task_type="bug-fix",
            instruction="Fix the import",
            initial_fs={"/workspace/main.py": "import broken"},
            base_tools=["bash", "python3"],
            success_criteria=[
                SuccessCriterion(type="exit_code", cmd="python3 /workspace/main.py"),
            ],
        )

    def test_valid_test_file(self):
        spec = _make_spec()
        task = self._make_task_for_test()
        test_code = 'import subprocess\n\ndef test_main_runs():\n    r = subprocess.run(["python3", "/workspace/main.py"], capture_output=True)\n    assert r.returncode == 0\n'
        updated = ingest_test_file(spec, 0, task, test_code)
        assert "/workspace/tests/test_solution.py" in updated.test_files
        assert any(c.type == "pytest_pass" for c in updated.success_criteria)

    def test_strips_python_fences(self):
        spec = _make_spec()
        task = self._make_task_for_test()
        fenced = '```python\ndef test_x():\n    assert True\n```'
        updated = ingest_test_file(spec, 0, task, fenced)
        assert "```" not in updated.test_files["/workspace/tests/test_solution.py"]

    def test_empty_raises(self):
        spec = _make_spec()
        task = self._make_task_for_test()
        with pytest.raises(TaskGenerationError, match="empty test file"):
            ingest_test_file(spec, 0, task, "   ")

    def test_syntax_error_raises(self):
        spec = _make_spec()
        task = self._make_task_for_test()
        with pytest.raises(TaskGenerationError, match="syntax error"):
            ingest_test_file(spec, 0, task, "def test_x(\n    broken syntax")

    def test_no_test_function_raises(self):
        spec = _make_spec()
        task = self._make_task_for_test()
        with pytest.raises(TaskGenerationError, match="no test_ functions"):
            ingest_test_file(spec, 0, task, "def helper(): pass")

    def test_preserves_existing_criteria(self):
        spec = _make_spec()
        task = self._make_task_for_test()
        test_code = "def test_ok():\n    assert True\n"
        updated = ingest_test_file(spec, 0, task, test_code)
        # Original exit_code criterion still there + new pytest_pass
        assert len(updated.success_criteria) == 2
        types = [c.type for c in updated.success_criteria]
        assert "exit_code" in types
        assert "pytest_pass" in types
