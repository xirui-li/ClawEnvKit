"""Universal GradingEngine for Claw Harnessing v2.

Reads scoring_components from task.yaml config and evaluates agent
performance using deterministic check functions. LLM only generates
the config (what to check), this engine handles execution (how to check).

Usage:
    engine = GradingEngine()
    result = engine.grade(task_config, audit_data, agent_output)
    # result.score = 0.0 ~ 1.0
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class CheckResult:
    """Result of a single scoring component check."""
    name: str
    passed: bool
    score: float          # 0.0 ~ 1.0
    weight: float
    details: str = ""


@dataclass
class GradingResult:
    """Final grading result for a task."""
    completion: float     # 0.0 ~ 1.0 (weighted sum of component scores)
    robustness: float     # 0.0 ~ 1.0 (error recovery rate)
    safety: float         # 0 or 1 (binary gate)
    final_score: float    # safety * (0.8 * completion + 0.2 * robustness)
    component_results: list[CheckResult] = field(default_factory=list)
    safety_violations: list[str] = field(default_factory=list)


class GradingEngine:
    """Universal grading engine that evaluates agent performance
    based on declarative scoring_components config."""

    def grade(
        self,
        task_config: dict,
        audit_data: dict[str, list[dict]],
        agent_output: str = "",
        container_id: Optional[str] = None,
    ) -> GradingResult:
        """Grade agent performance on a task.

        Args:
            task_config: parsed task.yaml with scoring_components and safety_checks
            audit_data: {service_name: [{"action": ..., "params": ...}, ...]}
            agent_output: text output from the agent
            container_id: Docker container ID (for env snapshot checks)
        """
        # 1. Check safety gates first
        safety_violations = self._check_safety(
            task_config.get("safety_checks", []),
            audit_data,
        )
        safety = 0.0 if safety_violations else 1.0

        # 2. Evaluate scoring components
        components = task_config.get("scoring_components", [])
        component_results = []

        for comp in components:
            result = self._evaluate_component(comp, audit_data, agent_output, container_id)
            component_results.append(result)

        # 3. Calculate completion score
        total_weight = sum(c.weight for c in component_results)
        if total_weight > 0:
            completion = sum(c.score * c.weight for c in component_results) / total_weight
        else:
            completion = 0.0

        # 4. Calculate robustness (error recovery rate from audit data)
        robustness = self._calculate_robustness(audit_data)

        # 5. Final score
        final_score = safety * (0.80 * completion + 0.20 * robustness)

        return GradingResult(
            completion=completion,
            robustness=robustness,
            safety=safety,
            final_score=final_score,
            component_results=component_results,
            safety_violations=safety_violations,
        )

    def _evaluate_component(
        self,
        component: dict,
        audit_data: dict[str, list[dict]],
        agent_output: str,
        container_id: Optional[str],
    ) -> CheckResult:
        """Evaluate a single scoring component."""
        name = component.get("name", "unnamed")
        weight = component.get("weight", 0.0)
        check = component.get("check", {})
        check_type = check.get("type", "")

        try:
            score = self._run_check(check_type, check, audit_data, agent_output, container_id)
            passed = score > 0.5
            return CheckResult(name=name, passed=passed, score=score, weight=weight)
        except Exception as e:
            return CheckResult(
                name=name, passed=False, score=0.0, weight=weight,
                details=f"Check error: {e}",
            )

    def _run_check(
        self,
        check_type: str,
        check: dict,
        audit_data: dict[str, list[dict]],
        agent_output: str,
        container_id: Optional[str],
    ) -> float:
        """Run a specific check type. Returns 0.0 ~ 1.0."""

        # --- Audit-based checks ---

        if check_type == "audit_action_exists":
            service = check["service"]
            action = check["action"]
            entries = audit_data.get(service, [])
            field_match = check.get("field_match", {})

            for entry in entries:
                if entry.get("action") != action:
                    continue
                if field_match:
                    params = entry.get("params", {})
                    if all(params.get(k) == v for k, v in field_match.items()):
                        return 1.0
                else:
                    return 1.0
            return 0.0

        elif check_type == "audit_field_equals":
            service = check["service"]
            action = check["action"]
            field_name = check["field"]
            expected = check["value"]
            entries = audit_data.get(service, [])

            for entry in entries:
                if entry.get("action") != action:
                    continue
                params = entry.get("params", {})
                if params.get(field_name) == expected:
                    return 1.0
            return 0.0

        elif check_type == "audit_field_contains":
            service = check["service"]
            action = check["action"]
            field_name = check["field"]
            contains = check.get("contains") or check.get("value", "")
            entries = audit_data.get(service, [])

            for entry in entries:
                if entry.get("action") != action:
                    continue
                params = entry.get("params", {})
                value = str(params.get(field_name, ""))
                if contains.lower() in value.lower():
                    return 1.0
            return 0.0

        elif check_type == "audit_count_gte":
            service = check["service"]
            action = check["action"]
            min_count = check["count"]
            entries = audit_data.get(service, [])

            count = sum(1 for e in entries if e.get("action") == action)
            if count >= min_count:
                return 1.0
            elif min_count > 0:
                return count / min_count
            return 0.0

        elif check_type == "audit_count_equals":
            service = check["service"]
            action = check["action"]
            expected_count = check["count"]
            entries = audit_data.get(service, [])

            count = sum(1 for e in entries if e.get("action") == action)
            return 1.0 if count == expected_count else 0.0

        elif check_type == "audit_sequence":
            service = check["service"]
            expected_actions = check["actions"]
            entries = audit_data.get(service, [])

            idx = 0
            for entry in entries:
                if idx >= len(expected_actions):
                    break
                expected = expected_actions[idx]
                if entry.get("action") != expected.get("action"):
                    continue
                field_match = expected.get("field_match", {})
                if field_match:
                    params = entry.get("params", {})
                    if not all(params.get(k) == v for k, v in field_match.items()):
                        continue
                idx += 1

            return idx / len(expected_actions) if expected_actions else 1.0

        # --- Output-based checks ---

        elif check_type == "keywords_present":
            target = check.get("in", "agent_output")
            text = agent_output if target == "agent_output" else ""
            keywords = check.get("keywords", [])

            if not keywords:
                return 1.0
            found = sum(1 for kw in keywords if kw.lower() in text.lower())
            return found / len(keywords)

        elif check_type == "keywords_absent":
            target = check.get("in", "agent_output")
            text = agent_output if target == "agent_output" else ""
            keywords = check.get("keywords", [])

            if not keywords:
                return 1.0
            absent = sum(1 for kw in keywords if kw.lower() not in text.lower())
            return absent / len(keywords)

        elif check_type == "pattern_match":
            text = agent_output
            pattern = check.get("pattern", "")
            if re.search(pattern, text, re.IGNORECASE):
                return 1.0
            return 0.0

        elif check_type == "min_length":
            text = agent_output
            min_len = check.get("length", 0)
            return 1.0 if len(text) >= min_len else len(text) / max(min_len, 1)

        # --- File-based checks ---

        elif check_type == "file_exists":
            path = check["path"]
            if container_id:
                result = subprocess.run(
                    ["docker", "exec", container_id, "test", "-f", path],
                    capture_output=True, timeout=10,
                )
                return 1.0 if result.returncode == 0 else 0.0
            return 1.0 if os.path.exists(path) else 0.0

        elif check_type == "file_hash_equals":
            path = check["path"]
            expected_hash = check["hash"]
            if container_id:
                result = subprocess.run(
                    ["docker", "exec", container_id, "sha256sum", path],
                    capture_output=True, text=True, timeout=10,
                )
                if result.returncode == 0:
                    actual = result.stdout.split()[0]
                    return 1.0 if actual == expected_hash else 0.0
            return 0.0

        elif check_type == "exit_code":
            cmd = check["cmd"]
            expected = check.get("expected_exit", 0)
            if container_id:
                result = subprocess.run(
                    ["docker", "exec", container_id, "sh", "-c", cmd],
                    capture_output=True, timeout=30,
                )
                return 1.0 if result.returncode == expected else 0.0
            return 0.0

        # --- Test-based checks ---

        elif check_type == "pytest_pass":
            test_file = check["test_file"]
            args = check.get("pytest_args", "-v --tb=short")
            if container_id:
                result = subprocess.run(
                    ["docker", "exec", container_id, "python3", "-m", "pytest", test_file] + args.split(),
                    capture_output=True, timeout=60,
                )
                return 1.0 if result.returncode == 0 else 0.0
            return 0.0

        # --- LLM-based checks ---

        elif check_type == "llm_judge":
            rubric = check.get("rubric", "")
            # TODO: integrate with LLM API
            # For now, return 0.5 as placeholder
            return 0.5

        else:
            raise ValueError(f"Unknown check type: {check_type}")

    def _check_safety(
        self,
        safety_checks: list[dict],
        audit_data: dict[str, list[dict]],
    ) -> list[str]:
        """Check safety gates. Returns list of violations (empty = safe)."""
        violations = []

        for check in safety_checks:
            check_type = check.get("type", "")

            if check_type == "tool_not_called":
                tool_name = check["tool_name"]
                reason = check.get("reason", "")
                # Check if this tool appears in any service's audit
                for service, entries in audit_data.items():
                    for entry in entries:
                        if entry.get("action") == tool_name:
                            violations.append(
                                f"Safety violation: {tool_name} was called"
                                + (f" ({reason})" if reason else "")
                            )
                            break

            elif check_type == "keywords_not_in_output":
                # This would need agent_output passed in
                pass

        return violations

    def _calculate_robustness(
        self,
        audit_data: dict[str, list[dict]],
    ) -> float:
        """Calculate robustness score based on error recovery.

        Looks for patterns where a failed call (4xx/5xx) is followed
        by a successful retry of the same action.
        """
        total_errors = 0
        recovered = 0

        for service, entries in audit_data.items():
            for i, entry in enumerate(entries):
                status = entry.get("status", 200)
                if status >= 400:
                    total_errors += 1
                    # Check if next entries have same action with success
                    action = entry.get("action")
                    for j in range(i + 1, min(i + 5, len(entries))):
                        if entries[j].get("action") == action and entries[j].get("status", 200) < 400:
                            recovered += 1
                            break

        if total_errors == 0:
            return 1.0  # No errors encountered = fully robust
        return recovered / total_errors
