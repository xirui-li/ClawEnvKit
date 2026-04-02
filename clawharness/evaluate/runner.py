"""Task runner: starts mock services, executes actions, collects audit, grades.

This is the glue between mock_services, agent actions, and GradingEngine.

Usage:
    runner = TaskRunner()
    result = runner.run_and_grade(task_config, actions=["list inbox", "reply to msg001"])
    print(result.final_score)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .engine import GradingEngine, GradingResult

from clawharness.paths import PROJECT_ROOT, MOCK_SERVICES_DIR


@dataclass
class RunResult:
    """Result of running and grading a task."""
    grading: GradingResult
    audit_data: dict[str, list[dict]]
    agent_output: str
    actions_executed: list[str]
    service_errors: list[str]


class TaskRunner:
    """Runs a task config against mock services and grades the result."""

    def __init__(self):
        self.engine = GradingEngine()
        self._processes: list[subprocess.Popen] = []

    def run_and_grade(
        self,
        task_config: dict,
        actions: list[str],
        agent_output: str = "",
        timeout: int = 60,
    ) -> RunResult:
        """Run actions against mock services and grade.

        Args:
            task_config: parsed task.yaml config
            actions: list of tool calls (as shell commands calling mock service endpoints)
            agent_output: text output from agent
            timeout: max seconds for all actions
        """
        services = task_config.get("services", [])
        service_errors = []

        try:
            # 1. Start mock services
            ports = self._start_services(services)

            # 2. Wait for services to be healthy
            self._wait_healthy(services, ports)

            # 3. Execute actions
            actions_executed = []
            for action in actions:
                try:
                    result = subprocess.run(
                        ["sh", "-c", action],
                        capture_output=True,
                        text=True,
                        timeout=30,
                        env={**os.environ, **self._build_env(services, ports)},
                    )
                    actions_executed.append(action)
                    if result.stdout:
                        agent_output += result.stdout
                except subprocess.TimeoutExpired:
                    service_errors.append(f"Action timed out: {action[:80]}")
                except Exception as e:
                    service_errors.append(f"Action error: {e}")

            # 4. Collect audit data from all services
            audit_data = self._collect_audit(services, ports)

            # 5. Grade
            grading = self.engine.grade(task_config, audit_data, agent_output)

            return RunResult(
                grading=grading,
                audit_data=audit_data,
                agent_output=agent_output,
                actions_executed=actions_executed,
                service_errors=service_errors,
            )

        finally:
            self._stop_services()

    def run_reference_solution(
        self,
        task_config: dict,
    ) -> RunResult:
        """Smoke test: call each tool endpoint with empty params, then grade.

        NOT an intelligent execution of the reference_solution steps.
        Used for self-validation to verify infrastructure (endpoints reachable,
        scoring config executable). Low scores are expected.
        """
        ref = task_config.get("reference_solution", "")
        if not ref:
            # No reference solution — run with empty actions
            return self.run_and_grade(task_config, actions=[], agent_output="")

        # Parse reference_solution into actions
        # Each line that starts with a number or dash is a step description,
        # not an executable command. We need tool-call style commands.
        actions = self._parse_reference_actions(task_config)

        return self.run_and_grade(
            task_config,
            actions=actions,
            agent_output=f"Executed reference solution: {ref[:200]}",
        )

    def _start_services(self, services: list[dict]) -> dict[str, int]:
        """Start mock services as subprocesses. Returns {service_name: port}."""
        ports = {}

        for svc in services:
            name = svc.get("name") or svc.get("template", "unknown")
            port = svc.get("port", 9100 + len(ports))

            server_path = PROJECT_ROOT / "mock_services" / name / "server.py"
            if not server_path.exists():
                continue

            # Build env for this service
            env = {**os.environ}
            env["PORT"] = str(port)

            # Pass fixture data as env vars
            fixtures = svc.get("fixtures", {})
            if fixtures:
                fixture_path = f"/tmp/mock_{name}_fixtures.json"
                with open(fixture_path, "w") as f:
                    json.dump(fixtures, f)

                # Service-specific env var naming
                env_key = f"{name.upper()}_FIXTURES"
                env[env_key] = fixture_path

            proc = subprocess.Popen(
                [sys.executable, str(server_path)],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self._processes.append(proc)
            ports[name] = port

        return ports

    def _wait_healthy(self, services: list[dict], ports: dict[str, int], timeout: int = 10):
        """Wait for all services to respond to health checks."""
        import urllib.request
        import urllib.error

        deadline = time.time() + timeout
        for svc in services:
            name = svc.get("name") or svc.get("template", "unknown")
            port = ports.get(name)
            if not port:
                continue

            health_url = svc.get("health_check", f"http://localhost:{port}/{name}/audit")

            while time.time() < deadline:
                try:
                    urllib.request.urlopen(health_url, timeout=2)
                    break
                except (urllib.error.URLError, ConnectionError, OSError):
                    time.sleep(0.3)

    def _build_env(self, services: list[dict], ports: dict[str, int]) -> dict[str, str]:
        """Build environment variables mapping service names to URLs."""
        env = {}
        for svc in services:
            name = svc.get("name") or svc.get("template", "unknown")
            port = ports.get(name)
            if port:
                env[f"{name.upper()}_URL"] = f"http://localhost:{port}"
                env[f"{name.upper()}_API_URL"] = f"http://localhost:{port}"
        return env

    def _collect_audit(self, services: list[dict], ports: dict[str, int]) -> dict[str, list[dict]]:
        """Fetch audit logs from all running mock services."""
        import urllib.request
        audit_data = {}

        for svc in services:
            name = svc.get("name") or svc.get("template", "unknown")
            port = ports.get(name)
            if not port:
                continue

            audit_url = f"http://localhost:{port}/{name}/audit"
            try:
                resp = urllib.request.urlopen(audit_url, timeout=5)
                data = json.loads(resp.read())

                # Normalize: extract the calls/actions list
                if isinstance(data, dict):
                    # Most services return {"calls": [...], "sent_messages": [...], ...}
                    calls = data.get("calls", [])
                    # Convert API calls to action-level entries
                    entries = []
                    for call in calls:
                        entry = {
                            "action": call.get("endpoint", "").split("/")[-1],
                            "params": call.get("params", call.get("body", {})),
                            "status": call.get("status", 200),
                            "timestamp": call.get("timestamp", ""),
                        }
                        entries.append(entry)

                    # Also add semantic actions (sent_messages, drafts, etc.)
                    for key, items in data.items():
                        if key == "calls":
                            continue
                        if isinstance(items, list):
                            for item in items:
                                entries.append({
                                    "action": key.rstrip("s"),  # sent_messages → sent_message
                                    "params": item if isinstance(item, dict) else {"value": item},
                                    "status": 200,
                                })

                    audit_data[name] = entries
                elif isinstance(data, list):
                    audit_data[name] = data
                else:
                    audit_data[name] = []

            except Exception:
                audit_data[name] = []

        return audit_data

    def _parse_reference_actions(self, task_config: dict) -> list[str]:
        """Generate smoke-test curl commands (one per tool, empty params).

        Does NOT parse or execute the reference_solution steps.
        Just calls each endpoint with {} body to verify reachability.
        """
        actions = []
        services = task_config.get("services", [])

        # Build port map
        ports = {}
        for svc in services:
            name = svc.get("name") or svc.get("template", "unknown")
            port = svc.get("port", 9100 + len(ports))
            ports[name] = port

        # Generate curl commands from tools
        tools = task_config.get("tools", [])
        for tool in tools:
            service = tool.get("service", "")
            endpoint = tool.get("endpoint", "")
            method = tool.get("method", "POST")
            port = ports.get(service, 9100)

            if method == "GET":
                actions.append(f"curl -s http://localhost:{port}{endpoint}")
            else:
                actions.append(f"curl -s -X {method} http://localhost:{port}{endpoint} -H 'Content-Type: application/json' -d '{{}}'")

        return actions

    def _stop_services(self):
        """Stop all mock service processes."""
        for proc in self._processes:
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        self._processes.clear()
