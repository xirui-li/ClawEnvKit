"""Self-validation: verify that auto-generated task configs are well-formed.

Runs reference_solution against mock services and checks that GradingEngine
produces a score within expected range. Tasks that fail self-validation
are discarded.

Usage:
    validator = SelfValidator()
    result = validator.validate(task_config)
    if result.valid:
        # task is good, export it
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
    """Validates task configs by running reference solutions."""

    def __init__(self, min_score: float = 0.6, max_score: float = 1.0):
        self.runner = TaskRunner()
        self.min_score = min_score
        self.max_score = max_score

    def validate(self, task_config: dict) -> ValidationResult:
        """Validate a task config by running its reference solution.

        A task is valid if:
        1. Reference solution can execute without errors
        2. GradingEngine score is within [min_score, max_score]
        3. At least 50% of scoring components pass
        4. No safety violations from reference solution
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
