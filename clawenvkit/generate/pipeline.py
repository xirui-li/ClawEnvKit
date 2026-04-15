"""Modular pipeline API: Parser, Generator, Validator.

Thin wrapper classes that delegate to existing module-level functions.
This provides a clean, composable interface without moving or rewriting
any logic.

Usage:
    from clawenvkit.generate import Parser, Generator, Validator

    parser = Parser()
    gen = Generator()
    val = Validator()

    # NL → structured spec
    intent = parser.parse_intent("Test if agent can schedule a meeting")

    # Structured spec → task config
    services = gen.resolve_services(intent["services"])
    prompt = gen.generate_task_prompt(services=services, difficulty=intent["difficulty"])
    config = gen.ingest_task_config(llm_response, services=services, atoms=intent["atoms"])

    # Validate
    issues = val.validate_task_config(config, services=services)
    gaps = val.verify_coverage(config, intent["atoms"])
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from clawenvkit.generate.service_generator import ServiceSpec
    from clawenvkit.compatibility.models import CompatibilityReport


class Parser:
    """NL request → structured spec.

    Wraps intent_parser.parse_intent: extracts services, difficulty,
    intent atoms, and missing services from a natural language request.
    """

    def parse_intent(
        self,
        request: str,
        api_key: str = "",
        model: str = "claude-haiku-4-5",
    ) -> dict:
        """Parse NL request into {services, missing_services, difficulty, atoms, reasoning}."""
        from clawenvkit.generate.intent_parser import parse_intent
        return parse_intent(request, api_key=api_key, model=model)


class Generator:
    """Structured spec → artifacts (task YAML, mock service code, fixture files).

    Wraps task_generator, service_generator, and fixture_generators.
    """

    # ── Task generation ──

    def resolve_services(
        self,
        services: list[str] | None = None,
        service: str = "",
        category: str = "",
    ) -> list[str]:
        """Resolve a unified service list from any input combination."""
        from clawenvkit.generate.task_generator import resolve_services
        return resolve_services(services, service, category)

    def generate_task_prompt(
        self,
        services: list[str] | None = None,
        service: str = "",
        category: str = "",
        difficulty: str = "medium",
        skill_target: str = "",
        domain: str = "",
        task_number: int = 1,
        existing_tasks: list[str] | None = None,
        focus_action: str = "",
    ) -> str:
        """Generate an LLM prompt to create a task.yaml config."""
        from clawenvkit.generate.task_generator import generate_task_config_prompt
        return generate_task_config_prompt(
            services=services, service=service, category=category,
            difficulty=difficulty, skill_target=skill_target, domain=domain,
            task_number=task_number, existing_tasks=existing_tasks,
            focus_action=focus_action,
        )

    def ingest_task_config(
        self,
        llm_response: str,
        services: list[str] | None = None,
        service: str = "",
        task_number: int = 1,
        atoms: list[dict] | None = None,
        check_feasibility: bool = False,
    ) -> dict:
        """Parse, validate, and optionally verify coverage + feasibility of LLM-generated task config."""
        from clawenvkit.generate.task_generator import ingest_task_config
        return ingest_task_config(
            llm_response, services=services, service=service,
            task_number=task_number, atoms=atoms,
            check_feasibility=check_feasibility,
        )

    # ── Service generation ──

    def plan_service(self, request: str, max_retries: int = 3) -> ServiceSpec:
        """Ask LLM to design a mock service structure. Returns ServiceSpec for review."""
        from clawenvkit.generate.service_generator import plan_service
        return plan_service(request, max_retries=max_retries)

    def generate_service(self, spec: ServiceSpec, verify: bool = True) -> Path:
        """Generate mock service files (server.py, __init__.py) from a ServiceSpec."""
        from clawenvkit.generate.service_generator import generate_service
        return generate_service(spec, verify=verify)

    def register_service(self, spec: ServiceSpec) -> None:
        """Register a new service in SERVICE_DEFINITIONS + sidecar JSON."""
        from clawenvkit.generate.service_generator import register_service
        return register_service(spec)

    # ── Fixture generation ──

    def generate_fixtures(
        self,
        category: str,
        topic: str,
        output_dir: Path,
        **kwargs,
    ) -> list[dict]:
        """Generate fixture files for file-dependent tasks."""
        from clawenvkit.generate.fixture_generators import generate_fixtures
        return generate_fixtures(category, topic, output_dir, **kwargs)

    # ── Read-only properties ──

    @property
    def service_definitions(self) -> dict:
        """Current SERVICE_DEFINITIONS dict (read-only view)."""
        from clawenvkit.generate.task_generator import SERVICE_DEFINITIONS
        return SERVICE_DEFINITIONS

    @property
    def cross_service_categories(self) -> dict:
        """Current CROSS_SERVICE_CATEGORIES dict (read-only view)."""
        from clawenvkit.generate.task_generator import CROSS_SERVICE_CATEGORIES
        return CROSS_SERVICE_CATEGORIES


class Validator:
    """All validation: task config, coverage, service spec, server, compatibility.

    Wraps validate_task_config, verify_coverage, validate_spec,
    validate_server, and the compatibility gate checker.
    """

    # ── Task config validation ──

    def validate_task_config(
        self,
        config: dict,
        services: list[str] | None = None,
        service: str = "",
    ) -> list[str]:
        """Validate a generated task config. Returns list of issues (empty = valid)."""
        from clawenvkit.generate.task_generator import validate_task_config
        return validate_task_config(config, services=services, service=service)

    def verify_coverage(
        self,
        config: dict,
        atoms: list[dict],
    ) -> list[str]:
        """Verify each intent atom is covered by the task config. Returns list of gaps."""
        from clawenvkit.generate.task_generator import verify_coverage
        return verify_coverage(config, atoms)

    def verify_feasibility(self, config: dict) -> list[str]:
        """Check if task is achievable given its fixtures and tools (LLM-based)."""
        from clawenvkit.generate.task_generator import verify_feasibility
        return verify_feasibility(config)

    # ── Service validation ──

    def validate_spec(self, spec: ServiceSpec) -> list[str]:
        """Validate a ServiceSpec against mock service standards."""
        from clawenvkit.generate.service_generator import validate_spec
        return validate_spec(spec)

    def validate_server(
        self,
        service_dir: Path,
        spec: ServiceSpec,
        timeout: int = 5,
    ) -> list[str]:
        """Start generated server and verify it works (integration test)."""
        from clawenvkit.generate.service_generator import validate_server
        return validate_server(service_dir, spec, timeout=timeout)

    # ── Compatibility gate ──

    def run_compatibility_checks(
        self,
        project_root: Path,
        check_names: list[str] | None = None,
    ) -> CompatibilityReport:
        """Run compatibility gate checks. Returns CompatibilityReport."""
        from clawenvkit.compatibility.checker import run_checks
        return run_checks(project_root, check_names=check_names)
