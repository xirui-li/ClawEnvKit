"""Auto-generate mock services from natural language descriptions.

Given a service name and description, generates:
1. A complete FastAPI mock service (server.py)
2. SERVICE_DEFINITIONS entry
3. Example fixture data

Usage:
    generator = ServiceGenerator()
    result = generator.generate("spotify", "Music streaming service — play, pause, search, playlists")
    # result.server_code, result.service_definition, result.example_fixtures
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
PROMPTS_DIR = PROJECT_ROOT / "prompts"


@dataclass
class GeneratedService:
    """Result of auto-generating a mock service."""
    service_name: str
    server_code: str
    service_definition: dict
    example_fixtures: list
    source: str = "llm-generated"


class ServiceGenerationError(Exception):
    pass


def _load_api_key() -> str:
    config_path = PROJECT_ROOT / "config.json"
    if config_path.exists():
        config = json.load(open(config_path))
        return config.get("ANTHROPIC_API_KEY") or config.get("claude") or ""
    return os.environ.get("ANTHROPIC_API_KEY", "")


def _call_llm(prompt: str, api_key: str) -> str:
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    model = os.environ.get("CLAWHARNESS_MODEL", "claude-sonnet-4-6")
    response = client.messages.create(
        model=model,
        max_tokens=8192,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```json"):
        text = text[len("```json"):]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


def generate_service(
    service_name: str,
    description: str,
    default_port: int = 9120,
    api_key: Optional[str] = None,
) -> GeneratedService:
    """Generate a complete mock service from a description.

    Args:
        service_name: short name (e.g., "spotify", "stripe", "twilio")
        description: what the service does (e.g., "Music streaming — play, pause, search")
        default_port: default port number
        api_key: Anthropic API key (reads from config.json if not provided)
    """
    if not api_key:
        api_key = _load_api_key()
    if not api_key:
        raise ServiceGenerationError("No API key found")

    template = (PROMPTS_DIR / "service_generation.md").read_text()
    prompt = template.replace("{service_name}", service_name)
    prompt = prompt.replace("{service_description}", description)
    prompt = prompt.replace("{SERVICE_NAME_UPPER}", service_name.upper())
    prompt = prompt.replace("{default_port}", str(default_port))

    response = _call_llm(prompt, api_key)
    cleaned = _strip_fences(response)

    # Parse JSON — might need to find it in response
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r'\{.*\}', cleaned, re.DOTALL)
        if match:
            data = json.loads(match.group())
        else:
            raise ServiceGenerationError(f"Failed to parse LLM response as JSON")

    server_code = data.get("server_code", "")
    service_def = data.get("service_definition", {})
    fixtures = data.get("example_fixtures", [])

    if not server_code or len(server_code) < 100:
        raise ServiceGenerationError("Generated server code is too short")

    if not service_def.get("endpoints"):
        raise ServiceGenerationError("Missing endpoints in service_definition")

    if not service_def.get("actions"):
        raise ServiceGenerationError("Missing actions in service_definition")

    return GeneratedService(
        service_name=service_name,
        server_code=server_code,
        service_definition=service_def,
        example_fixtures=fixtures,
        source="llm-generated",
    )


def install_service(result: GeneratedService) -> Path:
    """Install a generated service into mock_services/ directory.

    Returns path to the created server.py.
    """
    service_dir = PROJECT_ROOT / "mock_services" / result.service_name
    service_dir.mkdir(parents=True, exist_ok=True)

    # Write server.py
    server_path = service_dir / "server.py"
    server_path.write_text(result.server_code)

    # Write default fixtures
    fixtures_path = service_dir / "default_fixtures.json"
    with open(fixtures_path, "w") as f:
        json.dump(result.example_fixtures, f, indent=2)

    # Write metadata
    meta = {
        "service_name": result.service_name,
        "source": result.source,
        "service_definition": result.service_definition,
    }
    meta_path = service_dir / "metadata.json"
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)

    return server_path


def register_service(result: GeneratedService) -> None:
    """Add service to SERVICE_DEFINITIONS at runtime (not persisted to file)."""
    from scripts.grading.task_config_generator import SERVICE_DEFINITIONS
    SERVICE_DEFINITIONS[result.service_name] = result.service_definition


def generate_and_install(
    service_name: str,
    description: str,
    default_port: int = 9120,
) -> GeneratedService:
    """Generate, install, and register a new mock service.

    Full pipeline:
    1. LLM generates server code + definition + fixtures
    2. Writes files to mock_services/{service_name}/
    3. Registers in SERVICE_DEFINITIONS for task generation

    Returns the GeneratedService result.
    """
    print(f"[service-gen] Generating {service_name}...", file=sys.stderr)
    result = generate_service(service_name, description, default_port)

    print(f"[service-gen] Installing to mock_services/{service_name}/...", file=sys.stderr)
    path = install_service(result)

    print(f"[service-gen] Registering in SERVICE_DEFINITIONS...", file=sys.stderr)
    register_service(result)

    n_endpoints = len(result.service_definition.get("endpoints", []))
    n_actions = len(result.service_definition.get("actions", []))
    n_fixtures = len(result.example_fixtures)

    print(f"[service-gen] Done: {n_endpoints} endpoints, {n_actions} actions, {n_fixtures} fixtures", file=sys.stderr)
    print(f"[service-gen] Source: {result.source}", file=sys.stderr)
    print(f"[service-gen] Server: {path}", file=sys.stderr)

    return result
