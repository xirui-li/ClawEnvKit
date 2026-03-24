"""Step 4 (TEST): Round-trip validation in Docker container."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Optional

from .schema import SuccessCriterion, TaskSpec, ValidationResult

PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"

ACTION_TIMEOUT = 30   # seconds per docker exec
PYTEST_TIMEOUT = 60   # seconds for pytest runs


def _strip_json_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```json"):
        text = text[len("```json"):]
    elif text.startswith("```"):
        text = text[len("```"):]
    if text.endswith("```"):
        text = text[:-len("```")]
    return text.strip()


def validate_prompt(task: TaskSpec) -> str:
    """Return prompt for LLM to solve the task."""
    template = (PROMPTS_DIR / "task_solver.md").read_text()

    # Format initial_fs summary
    fs_lines = []
    for path, content in task.initial_fs.items():
        preview = content[:200] + "..." if len(content) > 200 else content
        fs_lines.append(f"  {path}:\n    {preview}")
    fs_summary = "\n".join(fs_lines) if fs_lines else "  (empty)"

    prompt = template.replace("{instruction}", task.instruction)
    prompt = prompt.replace("{initial_fs_summary}", fs_summary)

    return prompt


def parse_solver_response(llm_response: str) -> list[str]:
    """Parse LLM solver response into list of bash actions."""
    cleaned = _strip_json_fences(llm_response)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        # If not JSON, treat entire response as a single bash command
        return [llm_response.strip()] if llm_response.strip() else []

    if isinstance(data, dict):
        actions = data.get("actions", [])
        if isinstance(actions, list):
            return [str(a) for a in actions]
    return []


def _docker_run(image: str) -> str:
    """Start container, return container ID."""
    result = subprocess.run(
        ["docker", "run", "-d", "--network", "none", image, "sleep", "300"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"docker run failed: {result.stderr}")
    return result.stdout.strip()


def _docker_exec(container_id: str, command: str, timeout: int = ACTION_TIMEOUT) -> subprocess.CompletedProcess:
    """Execute command in container."""
    return subprocess.run(
        ["docker", "exec", container_id, "sh", "-c", command],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _docker_stop(container_id: str) -> None:
    """Stop container."""
    subprocess.run(
        ["docker", "stop", "-t", "2", container_id],
        capture_output=True,
        timeout=15,
    )


def _docker_rm(container_id: str) -> None:
    """Remove container."""
    subprocess.run(
        ["docker", "rm", "-f", container_id],
        capture_output=True,
        timeout=15,
    )


def _check_criterion(container_id: str, criterion: SuccessCriterion) -> bool:
    """Check a single success criterion. Returns True if passed."""
    if criterion.type == "exit_code":
        result = _docker_exec(container_id, criterion.cmd)
        return result.returncode == criterion.expected_exit

    elif criterion.type == "file_exists":
        result = _docker_exec(container_id, f"test -f {criterion.path}")
        return result.returncode == 0

    elif criterion.type == "file_contains":
        result = _docker_exec(
            container_id,
            f"grep -qF '{criterion.pattern}' {criterion.path}",
        )
        return result.returncode == 0

    elif criterion.type == "file_not_contains":
        result = _docker_exec(
            container_id,
            f"grep -qF '{criterion.pattern}' {criterion.path}",
        )
        return result.returncode != 0

    elif criterion.type == "pytest_pass":
        pytest_args = criterion.pytest_args or "-v --tb=short"
        result = _docker_exec(
            container_id,
            f"python3 -m pytest {criterion.test_file} {pytest_args}",
            timeout=PYTEST_TIMEOUT,
        )
        return result.returncode == 0

    elif criterion.type == "mock_api_verify":
        result = _docker_exec(
            container_id,
            f"python3 /workspace/mock_server/server.py verify --expected {criterion.expected_calls_file}",
            timeout=ACTION_TIMEOUT,
        )
        return result.returncode == 0

    return False


def validate_with_solution(
    task: TaskSpec,
    solver_actions: list[str],
) -> ValidationResult:
    """Run solver actions in Docker container and check criteria."""
    container_id = _docker_run(task.docker_image)

    try:
        # Start mock server if configured
        if task.mock_server_config is not None:
            port = task.mock_server_config.port
            _docker_exec(
                container_id,
                f"python3 /workspace/mock_server/server.py serve "
                f"--port {port} "
                f"--responses /workspace/mock_server/responses.json "
                f"--log /tmp/mock_requests.jsonl &",
                timeout=5,
            )
            # Set environment variables for the agent's code
            for key, val in task.mock_server_config.env_vars.items():
                _docker_exec(container_id, f"export {key}={val}")

        # Execute solver actions
        for action in solver_actions:
            try:
                _docker_exec(container_id, action)
            except subprocess.TimeoutExpired:
                return ValidationResult(
                    passed=False,
                    solver_actions=solver_actions,
                    criteria_results=[],
                    failure_reason=f"Action timed out ({ACTION_TIMEOUT}s): {action[:100]}",
                )

        # Check all criteria
        criteria_results = []
        for criterion in task.success_criteria:
            try:
                passed = _check_criterion(container_id, criterion)
            except subprocess.TimeoutExpired:
                passed = False
            criteria_results.append(passed)

        all_passed = all(criteria_results)

        failure_reason = None
        if not all_passed:
            failed_indices = [i for i, p in enumerate(criteria_results) if not p]
            failure_reason = f"Criteria failed at indices: {failed_indices}"

        return ValidationResult(
            passed=all_passed,
            solver_actions=solver_actions,
            criteria_results=criteria_results,
            failure_reason=failure_reason,
        )

    except Exception as e:
        return ValidationResult(
            passed=False,
            solver_actions=solver_actions,
            criteria_results=[],
            failure_reason=str(e),
        )

    finally:
        _docker_stop(container_id)
        _docker_rm(container_id)


def validate_fail_to_pass(
    task: TaskSpec,
    solver_actions: list[str],
) -> ValidationResult:
    """Two-phase FAIL_TO_PASS validation for tasks with test_files.

    Phase 1: Run pytest tests on initial state → must FAIL (proves tests are meaningful)
    Phase 2: Apply solver actions, then run tests → must PASS (proves task is solvable)

    Falls back to validate_with_solution() if task has no pytest_pass criteria.
    """
    pytest_criteria = [c for c in task.success_criteria if c.type == "pytest_pass"]
    if not pytest_criteria:
        return validate_with_solution(task, solver_actions)

    container_id = _docker_run(task.docker_image)

    try:
        # Phase 1: tests should FAIL on initial state
        for criterion in pytest_criteria:
            try:
                passed = _check_criterion(container_id, criterion)
            except subprocess.TimeoutExpired:
                passed = False
            if passed:
                return ValidationResult(
                    passed=False,
                    solver_actions=solver_actions,
                    criteria_results=[],
                    failure_reason=f"FAIL_TO_PASS Phase 1: test {criterion.test_file} already passes on initial state (tests are trivial or wrong)",
                )

        # Phase 2: apply solver actions
        for action in solver_actions:
            try:
                _docker_exec(container_id, action)
            except subprocess.TimeoutExpired:
                return ValidationResult(
                    passed=False,
                    solver_actions=solver_actions,
                    criteria_results=[],
                    failure_reason=f"Action timed out ({ACTION_TIMEOUT}s): {action[:100]}",
                )

        # Phase 2: check ALL criteria (pytest + v0.1 style)
        criteria_results = []
        for criterion in task.success_criteria:
            try:
                passed = _check_criterion(container_id, criterion)
            except subprocess.TimeoutExpired:
                passed = False
            criteria_results.append(passed)

        all_passed = all(criteria_results)
        failure_reason = None
        if not all_passed:
            failed_indices = [i for i, p in enumerate(criteria_results) if not p]
            failure_reason = f"FAIL_TO_PASS Phase 2: criteria failed at indices: {failed_indices}"

        return ValidationResult(
            passed=all_passed,
            solver_actions=solver_actions,
            criteria_results=criteria_results,
            failure_reason=failure_reason,
        )

    except Exception as e:
        return ValidationResult(
            passed=False,
            solver_actions=solver_actions,
            criteria_results=[],
            failure_reason=str(e),
        )

    finally:
        _docker_stop(container_id)
        _docker_rm(container_id)


def validate_multistep(
    task: TaskSpec,
    step_actions: dict[int, list[str]],
) -> ValidationResult:
    """Validate a multi-step task by executing steps sequentially.

    Args:
        task: TaskSpec with non-empty steps field
        step_actions: {step_id: [bash commands]} — solver's actions per step

    Each step's check_criteria are verified after running that step's actions.
    All steps must pass for the task to pass. Final success_criteria are also checked.
    """
    if not task.steps:
        all_actions = []
        for actions in step_actions.values():
            all_actions.extend(actions)
        return validate_with_solution(task, all_actions)

    container_id = _docker_run(task.docker_image)
    all_actions = []
    all_criteria_results = []

    try:
        # Start mock server if needed
        if task.mock_server_config is not None:
            port = task.mock_server_config.port
            _docker_exec(
                container_id,
                f"python3 /workspace/mock_server/server.py serve "
                f"--port {port} "
                f"--responses /workspace/mock_server/responses.json "
                f"--log /tmp/mock_requests.jsonl &",
                timeout=5,
            )

        for step in task.steps:
            actions = step_actions.get(step.step_id, [])
            all_actions.extend(actions)

            # Execute this step's actions
            for action in actions:
                try:
                    _docker_exec(container_id, action)
                except subprocess.TimeoutExpired:
                    return ValidationResult(
                        passed=False,
                        solver_actions=all_actions,
                        criteria_results=all_criteria_results,
                        failure_reason=f"Step {step.step_id} action timed out: {action[:100]}",
                    )

            # Check intermediate criteria
            for criterion in step.check_criteria:
                try:
                    passed = _check_criterion(container_id, criterion)
                except subprocess.TimeoutExpired:
                    passed = False
                all_criteria_results.append(passed)

                if not passed:
                    return ValidationResult(
                        passed=False,
                        solver_actions=all_actions,
                        criteria_results=all_criteria_results,
                        failure_reason=f"Step {step.step_id} check failed: {criterion.type}",
                    )

        # Check final success_criteria
        for criterion in task.success_criteria:
            try:
                passed = _check_criterion(container_id, criterion)
            except subprocess.TimeoutExpired:
                passed = False
            all_criteria_results.append(passed)

        all_passed = all(all_criteria_results)
        failure_reason = None
        if not all_passed:
            failed = [i for i, p in enumerate(all_criteria_results) if not p]
            failure_reason = f"Final criteria failed at indices: {failed}"

        return ValidationResult(
            passed=all_passed,
            solver_actions=all_actions,
            criteria_results=all_criteria_results,
            failure_reason=failure_reason,
        )

    except Exception as e:
        return ValidationResult(
            passed=False,
            solver_actions=all_actions,
            criteria_results=all_criteria_results,
            failure_reason=str(e),
        )

    finally:
        _docker_stop(container_id)
        _docker_rm(container_id)
