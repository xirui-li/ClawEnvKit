"""Tests for scripts/core/validator.py"""

import json
import subprocess
from unittest.mock import MagicMock, patch, call

import pytest

from scripts.core.schema import SuccessCriterion, TaskSpec, ValidationResult
from scripts.core.validator import (
    parse_solver_response,
    validate_prompt,
    validate_with_solution,
)


def _make_task(**overrides):
    defaults = dict(
        task_id="test-001",
        domain="cli-file-ops",
        difficulty="easy",
        skill_target="file create",
        task_type="code",
        instruction="Create hello.txt with content 'hello world'",
        initial_fs={"/workspace/README.md": "instructions"},
        base_tools=["bash", "python3"],
        success_criteria=[
            SuccessCriterion(type="file_exists", path="/workspace/hello.txt"),
            SuccessCriterion(type="file_contains", path="/workspace/hello.txt", pattern="hello world"),
        ],
        docker_image="clawharness/cli-file-ops/test-001:v1",
    )
    defaults.update(overrides)
    return TaskSpec(**defaults)


# --- validate_prompt ---


class TestValidatePrompt:
    def test_contains_instruction(self):
        task = _make_task()
        prompt = validate_prompt(task)
        assert "Create hello.txt" in prompt

    def test_contains_initial_fs(self):
        task = _make_task()
        prompt = validate_prompt(task)
        assert "README.md" in prompt


# --- parse_solver_response ---


class TestParseSolverResponse:
    def test_valid_json(self):
        response = json.dumps({
            "reasoning": "I need to create hello.txt",
            "actions": ["echo 'hello world' > /workspace/hello.txt"],
        })
        actions = parse_solver_response(response)
        assert actions == ["echo 'hello world' > /workspace/hello.txt"]

    def test_json_with_fences(self):
        response = '```json\n{"reasoning": "x", "actions": ["echo hi"]}\n```'
        actions = parse_solver_response(response)
        assert actions == ["echo hi"]

    def test_plain_text_fallback(self):
        actions = parse_solver_response("echo hello")
        assert actions == ["echo hello"]

    def test_empty(self):
        actions = parse_solver_response("")
        assert actions == []

    def test_multiple_actions(self):
        response = json.dumps({
            "reasoning": "multi-step",
            "actions": ["mkdir -p /workspace/dir", "touch /workspace/dir/file.txt"],
        })
        actions = parse_solver_response(response)
        assert len(actions) == 2


# --- validate_with_solution (mocked docker) ---


class TestValidateWithSolution:
    def _mock_docker(self):
        """Set up mock for all docker subprocess calls."""
        patcher = patch("scripts.core.validator.subprocess.run")
        mock_run = patcher.start()
        return mock_run, patcher

    def test_all_criteria_pass(self):
        mock_run, patcher = self._mock_docker()
        try:
            mock_run.side_effect = [
                # docker run
                MagicMock(returncode=0, stdout="container123\n"),
                # docker exec: solver action
                MagicMock(returncode=0),
                # docker exec: file_exists check (test -f)
                MagicMock(returncode=0),
                # docker exec: file_contains check (grep -qF)
                MagicMock(returncode=0),
                # docker stop
                MagicMock(returncode=0),
                # docker rm
                MagicMock(returncode=0),
            ]
            task = _make_task()
            result = validate_with_solution(task, ["echo 'hello world' > /workspace/hello.txt"])

            assert result.passed is True
            assert result.criteria_results == [True, True]
            assert result.failure_reason is None
        finally:
            patcher.stop()

    def test_criterion_fails(self):
        mock_run, patcher = self._mock_docker()
        try:
            mock_run.side_effect = [
                # docker run
                MagicMock(returncode=0, stdout="container123\n"),
                # docker exec: solver action
                MagicMock(returncode=0),
                # docker exec: file_exists → pass
                MagicMock(returncode=0),
                # docker exec: file_contains → fail (grep not found)
                MagicMock(returncode=1),
                # docker stop
                MagicMock(returncode=0),
                # docker rm
                MagicMock(returncode=0),
            ]
            task = _make_task()
            result = validate_with_solution(task, ["touch /workspace/hello.txt"])

            assert result.passed is False
            assert result.criteria_results == [True, False]
            assert "failed at indices" in result.failure_reason
        finally:
            patcher.stop()

    def test_container_cleaned_up_on_success(self):
        mock_run, patcher = self._mock_docker()
        try:
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout="c1\n"),
                MagicMock(returncode=0),  # action
                MagicMock(returncode=0),  # file_exists
                MagicMock(returncode=0),  # file_contains
                MagicMock(returncode=0),  # stop
                MagicMock(returncode=0),  # rm
            ]
            task = _make_task()
            validate_with_solution(task, ["echo hi"])

            # Verify stop and rm were called
            calls = [str(c) for c in mock_run.call_args_list]
            assert any("stop" in c for c in calls)
            assert any("rm" in c for c in calls)
        finally:
            patcher.stop()

    def test_container_cleaned_up_on_exception(self):
        mock_run, patcher = self._mock_docker()
        try:
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout="c1\n"),  # docker run
                RuntimeError("unexpected crash"),  # action fails
                MagicMock(returncode=0),  # stop
                MagicMock(returncode=0),  # rm
            ]
            task = _make_task()
            result = validate_with_solution(task, ["bad command"])

            assert result.passed is False
            # stop and rm still called (in finally block)
            assert mock_run.call_count >= 3  # run + stop + rm at minimum
        finally:
            patcher.stop()

    def test_action_timeout(self):
        mock_run, patcher = self._mock_docker()
        try:
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout="c1\n"),  # docker run
                subprocess.TimeoutExpired(cmd="docker exec", timeout=10),  # action timeout
                MagicMock(returncode=0),  # stop
                MagicMock(returncode=0),  # rm
            ]
            task = _make_task()
            result = validate_with_solution(task, ["sleep 999"])

            assert result.passed is False
            assert "timed out" in result.failure_reason
        finally:
            patcher.stop()

    def test_network_none_flag(self):
        mock_run, patcher = self._mock_docker()
        try:
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout="c1\n"),
                MagicMock(returncode=0),  # action
                MagicMock(returncode=0),  # criterion
                MagicMock(returncode=0),  # criterion
                MagicMock(returncode=0),  # stop
                MagicMock(returncode=0),  # rm
            ]
            task = _make_task()
            validate_with_solution(task, ["echo hi"])

            # First call is docker run — check --network none
            run_call = mock_run.call_args_list[0]
            run_args = run_call[0][0]
            assert "--network" in run_args
            assert "none" in run_args
        finally:
            patcher.stop()

    def test_exit_code_criterion(self):
        mock_run, patcher = self._mock_docker()
        try:
            task = _make_task(
                success_criteria=[
                    SuccessCriterion(type="exit_code", cmd="python3 /workspace/main.py", expected_exit=0),
                ],
            )
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout="c1\n"),  # docker run
                MagicMock(returncode=0),  # action
                MagicMock(returncode=0),  # exit_code check
                MagicMock(returncode=0),  # stop
                MagicMock(returncode=0),  # rm
            ]
            result = validate_with_solution(task, ["echo fix"])

            assert result.passed is True
            assert result.criteria_results == [True]
        finally:
            patcher.stop()

    def test_file_not_contains_passes_when_absent(self):
        mock_run, patcher = self._mock_docker()
        try:
            task = _make_task(
                success_criteria=[
                    SuccessCriterion(type="file_not_contains", path="/workspace/main.py", pattern="import broken"),
                ],
            )
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout="c1\n"),  # docker run
                MagicMock(returncode=0),  # action
                MagicMock(returncode=1),  # grep not found → file_not_contains passes
                MagicMock(returncode=0),  # stop
                MagicMock(returncode=0),  # rm
            ]
            result = validate_with_solution(task, ["sed -i 's/broken/os/' /workspace/main.py"])

            assert result.passed is True
            assert result.criteria_results == [True]
        finally:
            patcher.stop()

    def test_file_not_contains_fails_when_present(self):
        mock_run, patcher = self._mock_docker()
        try:
            task = _make_task(
                success_criteria=[
                    SuccessCriterion(type="file_not_contains", path="/workspace/main.py", pattern="import broken"),
                ],
            )
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout="c1\n"),  # docker run
                MagicMock(returncode=0),  # action
                MagicMock(returncode=0),  # grep found → file_not_contains fails
                MagicMock(returncode=0),  # stop
                MagicMock(returncode=0),  # rm
            ]
            result = validate_with_solution(task, ["echo noop"])

            assert result.passed is False
            assert result.criteria_results == [False]
        finally:
            patcher.stop()
