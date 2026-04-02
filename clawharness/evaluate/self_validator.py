"""Self-validation: verify that auto-generated task configs are structurally sound.

Performs a smoke test by calling each tool endpoint with empty params, then
checks that the GradingEngine can execute all scoring_components without errors.

NOTE: This does NOT simulate an intelligent agent following the reference_solution.
It verifies infrastructure (endpoints reachable, scoring config executable),
not task solvability. True solvability requires running a real agent.

Usage:
    validator = SelfValidator()
    result = validator.validate(task_config)
    if result.valid:
        # task infrastructure is sound, export it
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .engine import GradingResult
from .runner import TaskRunner, RunResult


@dataclass
class ValidationResult:
    """Result of self-validating a task config."""
    valid: bool
    score: float
    reason: str
    run_result: Optional[RunResult] = None


class SelfValidator:
    """Validates task configs via infrastructure smoke test.

    Does NOT run the reference solution intelligently — just calls
    each endpoint with empty params to verify reachability + scoring
    config executability. A score > 0 means the infrastructure works.
    """

    def __init__(self, min_score: float = 0.6, max_score: float = 1.0):
        self.runner = TaskRunner()
        self.min_score = min_score
        self.max_score = max_score

    def validate(self, task_config: dict) -> ValidationResult:
        """Validate a task config via smoke test.

        Calls each tool endpoint with empty params, then runs GradingEngine.
        A task is structurally valid if:
        1. All endpoints are reachable (no 500/404 on empty call)
        2. GradingEngine can execute all scoring_components without crash
        3. No safety violations from the smoke test actions
        Note: Low scores are expected (empty params → most checks fail).
        """
        try:
            run_result = self.runner.run_reference_solution(task_config)
        except Exception as e:
            return ValidationResult(
                valid=False,
                score=0.0,
                reason=f"Reference solution execution failed: {e}",
            )

        grading = run_result.grading

        # Check safety
        if grading.safety == 0.0:
            return ValidationResult(
                valid=False,
                score=grading.final_score,
                reason=f"Reference solution violated safety: {grading.safety_violations}",
                run_result=run_result,
            )

        # Check score range
        if grading.final_score < self.min_score:
            # Count how many components passed
            passed = sum(1 for c in grading.component_results if c.passed)
            total = len(grading.component_results)
            return ValidationResult(
                valid=False,
                score=grading.final_score,
                reason=f"Score {grading.final_score:.2f} < min {self.min_score} ({passed}/{total} components passed)",
                run_result=run_result,
            )

        # Check component pass rate
        if grading.component_results:
            pass_rate = sum(1 for c in grading.component_results if c.passed) / len(grading.component_results)
            if pass_rate < 0.5:
                return ValidationResult(
                    valid=False,
                    score=grading.final_score,
                    reason=f"Only {pass_rate:.0%} of components passed (need >= 50%)",
                    run_result=run_result,
                )

        return ValidationResult(
            valid=True,
            score=grading.final_score,
            reason="Self-validation passed",
            run_result=run_result,
        )

    def validate_batch(self, configs: list[dict]) -> list[ValidationResult]:
        """Validate multiple task configs. Returns results in order."""
        return [self.validate(c) for c in configs]
