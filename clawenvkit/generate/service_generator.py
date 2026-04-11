"""Service Generator: create mock services for real SaaS APIs.

Given a natural language description (e.g., "GitHub issue tracker" or "Stripe payments"),
generates a complete mock service that matches the existing pattern:
  1. Plan the service structure (endpoints, data model) -> show to user for confirmation
  2. Generate mock_services/<name>/server.py (FastAPI)
  3. Register in SERVICE_DEFINITIONS

Usage:
    from clawenvkit.generate.service_generator import plan_service, generate_service

    # Step 1: Plan (interactive -- user reviews and confirms)
    spec = plan_service("GitHub issue tracker and PR management")

    # Step 2: Generate (writes files + registers)
    generate_service(spec)

CLI:
    clawenvkit service create --request "Slack messaging API"
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from clawenvkit.paths import PROJECT_ROOT


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class EndpointSpec:
    """Specification for a single API endpoint."""
    method: str          # POST (always POST for mock services)
    path: str            # e.g., /github/issues
    name: str            # action name: list_issues
    description: str     # human-readable description
    params: list[dict] = field(default_factory=list)
    returns: str = ""    # brief description of response


@dataclass
class ServiceSpec:
    """Full specification for a mock service."""
    name: str                         # e.g., "github"
    real_service: str                 # e.g., "GitHub"
    description: str                  # one-line description
    endpoints: list[EndpointSpec] = field(default_factory=list)
    data_model: dict = field(default_factory=dict)  # {"issues": ["id", "title", ...]}
    fixture_schema: str = ""          # for SERVICE_DEFINITIONS


# ---------------------------------------------------------------------------
# Step 1: Plan -- LLM designs the service structure
# ---------------------------------------------------------------------------

PLAN_PROMPT = """You are designing a mock API service for AI agent evaluation.

The user wants to simulate: {request}

You must design a simplified mock version of this real SaaS API. The mock will:
- Run as a FastAPI server on localhost
- Store data in-memory (loaded from JSON fixtures)
- Support CRUD-like operations relevant to agent tasks
- Log all calls for audit/grading

## Constraints
- All endpoints use POST method (convention for this evaluation framework)
- URL pattern: /{{service_name}}/{{resource}} or /{{service_name}}/{{resource}}/{{action}}
- Keep it focused: 4-7 endpoints covering the core operations an AI agent would need
- Use realistic field names matching the real API where possible
- Service name should be lowercase, no spaces (e.g., "github", "stripe", "slack")

## Existing services (don't duplicate these):
{existing_services}

## Output JSON:
{{
  "name": "github",
  "real_service": "GitHub",
  "description": "Issue tracking, pull requests, and repository management",
  "endpoints": [
    {{
      "path": "/github/issues",
      "name": "list_issues",
      "description": "List issues in a repository",
      "params": [
        {{"name": "repo", "type": "string", "required": false}},
        {{"name": "state", "type": "string", "required": false, "default": "open"}}
      ],
      "returns": "List of issues with id, title, state, assignee, labels, created_at"
    }}
  ],
  "data_model": {{
    "issues": ["id", "title", "body", "state", "assignee", "labels", "created_at", "repo"]
  }},
  "fixture_schema": "issues: [{{id, title, body, state, assignee, labels, created_at, repo}}]"
}}

Respond with JSON only."""


def _parse_spec_from_llm(content: str) -> ServiceSpec:
    """Parse LLM response into a ServiceSpec."""
    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r'^```\w*\n?', '', cleaned)
        cleaned = re.sub(r'\n?```$', '', cleaned)

    data = json.loads(cleaned.strip())

    endpoints = []
    for ep in data.get("endpoints", []):
        endpoints.append(EndpointSpec(
            method="POST",
            path=ep["path"],
            name=ep["name"],
            description=ep.get("description", ""),
            params=ep.get("params", []),
            returns=ep.get("returns", ""),
        ))

    return ServiceSpec(
        name=data["name"],
        real_service=data.get("real_service", data["name"]),
        description=data.get("description", ""),
        endpoints=endpoints,
        data_model=data.get("data_model", {}),
        fixture_schema=data.get("fixture_schema", ""),
    )


def plan_service(request: str, max_retries: int = 3) -> ServiceSpec:
    """Ask LLM to design a mock service structure, with validation and retry.

    Returns a ServiceSpec for user review before generation.
    Retries up to max_retries times if spec validation fails.
    """
    from clawenvkit.llm_client import call_llm
    from clawenvkit.generate.task_generator import SERVICE_DEFINITIONS

    existing = ", ".join(sorted(SERVICE_DEFINITIONS.keys()))

    prompt = PLAN_PROMPT.format(
        request=request,
        existing_services=existing,
    )

    last_error = ""
    for attempt in range(max_retries):
        retry_prompt = prompt
        if last_error:
            retry_prompt += f"\n\nPrevious attempt failed validation:\n{last_error}\nFix these issues."

        content = call_llm(retry_prompt, max_tokens=2000, temperature=0)

        try:
            spec = _parse_spec_from_llm(content)
        except (json.JSONDecodeError, KeyError) as e:
            last_error = f"JSON parse error: {e}"
            continue

        # Validate spec
        issues = validate_spec(spec)
        if not issues:
            return spec

        last_error = "\n".join(f"- {issue}" for issue in issues)
        # Auto-fix common issues
        if spec.name != spec.name.lower():
            spec.name = spec.name.lower()
        # Check again after auto-fix
        issues = validate_spec(spec)
        if not issues:
            return spec

    raise ValueError(f"Failed to generate valid service spec after {max_retries} attempts.\nLast issues:\n{last_error}")


def validate_spec(spec: ServiceSpec) -> list[str]:
    """Validate a ServiceSpec against our mock service standards.

    Returns list of issues (empty = valid).
    """
    issues = []

    # Name
    if not spec.name or not spec.name.replace("_", "").isalnum():
        issues.append(f"Invalid service name: '{spec.name}' (must be lowercase alphanumeric + underscores)")
    if spec.name != spec.name.lower():
        issues.append(f"Service name must be lowercase: '{spec.name}'")

    # Must have endpoints
    if not spec.endpoints:
        issues.append("No endpoints defined")
    elif len(spec.endpoints) < 2:
        issues.append(f"Too few endpoints ({len(spec.endpoints)}), need at least 2")
    elif len(spec.endpoints) > 10:
        issues.append(f"Too many endpoints ({len(spec.endpoints)}), keep it under 10")

    # Must have data model
    if not spec.data_model:
        issues.append("No data_model defined")

    # Endpoint checks
    seen_names = set()
    seen_paths = set()
    for ep in spec.endpoints:
        # Path must start with /{service_name}/
        if not ep.path.startswith(f"/{spec.name}/"):
            issues.append(f"Endpoint path '{ep.path}' must start with '/{spec.name}/'")

        # Action name must be valid Python identifier
        if not ep.name.isidentifier():
            issues.append(f"Action name '{ep.name}' is not a valid Python identifier")

        # No duplicates
        if ep.name in seen_names:
            issues.append(f"Duplicate action name: '{ep.name}'")
        seen_names.add(ep.name)
        if ep.path in seen_paths:
            issues.append(f"Duplicate endpoint path: '{ep.path}'")
        seen_paths.add(ep.path)

        # Param names must be valid Python identifiers
        for p in ep.params:
            if not p.get("name", "").isidentifier():
                issues.append(f"Param name '{p.get('name')}' in {ep.name} is not valid")
            if p.get("type") not in (None, "string", "integer", "number", "boolean", "array"):
                issues.append(f"Unknown param type '{p.get('type')}' in {ep.name}")

    # Should have at least one list/read action
    has_read = any(
        any(k in ep.name for k in ("list", "get", "search", "fetch"))
        for ep in spec.endpoints
    )
    if not has_read:
        issues.append("No list/get/search endpoint (agents need to read data)")

    return issues


def validate_server(service_dir: Path, spec: ServiceSpec, timeout: int = 5) -> list[str]:
    """Start the generated server and verify it works.

    Checks:
    1. Server starts without import/syntax errors
    2. OpenAPI spec is served (all paths present)
    3. Audit endpoint works
    4. At least one endpoint returns 200

    Returns list of issues (empty = valid).
    """
    import subprocess
    import time
    import urllib.request

    import random
    issues = []
    port = random.randint(19000, 19999)
    server_py = service_dir / "server.py"

    proc = subprocess.Popen(
        ["python3", str(server_py)],
        env={**os.environ, "PORT": str(port), "ERROR_RATE": "0"},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    try:
        # Wait for server to start (try up to 5 seconds)
        for _ in range(10):
            time.sleep(0.5)
            if proc.poll() is not None:
                break
            try:
                urllib.request.urlopen(f"http://localhost:{port}/openapi.json", timeout=1)
                break  # server is ready
            except Exception:
                continue

        if proc.poll() is not None:
            stderr = proc.stderr.read().decode()
            issues.append(f"Server failed to start: {stderr[:300]}")
            return issues

        # Check OpenAPI
        try:
            resp = urllib.request.urlopen(f"http://localhost:{port}/openapi.json", timeout=timeout)
            openapi = json.loads(resp.read())
            paths = set(openapi.get("paths", {}).keys())
            for ep in spec.endpoints:
                if ep.path not in paths:
                    issues.append(f"Missing endpoint in OpenAPI: {ep.path}")
        except Exception as e:
            issues.append(f"OpenAPI fetch failed: {e}")
            return issues

        # Check audit endpoint
        try:
            resp = urllib.request.urlopen(f"http://localhost:{port}/{spec.name}/audit", timeout=timeout)
            audit = json.loads(resp.read())
            if "calls" not in audit:
                issues.append("Audit endpoint missing 'calls' field")
        except Exception as e:
            issues.append(f"Audit endpoint failed: {e}")

        # Call the first list/get endpoint to verify it returns 200
        for ep in spec.endpoints:
            try:
                req = urllib.request.Request(
                    f"http://localhost:{port}{ep.path}",
                    data=json.dumps({}).encode(),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                resp = urllib.request.urlopen(req, timeout=timeout)
                if resp.status == 200:
                    break  # at least one works
            except Exception:
                continue
        else:
            issues.append("No endpoint returned 200 with empty body")

    finally:
        proc.kill()
        proc.wait()

    return issues


def format_spec_for_review(spec: ServiceSpec) -> str:
    """Format a ServiceSpec as human-readable text for user confirmation."""
    lines = []
    lines.append(f"  Service:     {spec.name}")
    lines.append(f"  Real API:    {spec.real_service}")
    lines.append(f"  Description: {spec.description}")
    lines.append("")
    lines.append("  Endpoints:")
    for ep in spec.endpoints:
        params = []
        for p in ep.params:
            s = f"{p['name']}: {p.get('type', 'string')}"
            if p.get("required"):
                s += " (required)"
            elif "default" in p:
                s += f" = {p['default']}"
            params.append(s)
        lines.append(f"    POST {ep.path}")
        lines.append(f"      -> {ep.name}({', '.join(params)})")
        lines.append(f"         {ep.description}")
        lines.append("")

    lines.append("  Data Model:")
    for resource, fields in spec.data_model.items():
        lines.append(f"    {resource}: [{', '.join(fields)}]")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Step 2: Generate -- write server.py
# ---------------------------------------------------------------------------

SERVER_TEMPLATE = '''\
"""Mock {real_service} API service for agent evaluation."""

from __future__ import annotations

import copy
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Mock {real_service} API")

from mock_services._base import add_error_injection, load_fixtures
add_error_injection(app)

FIXTURES_PATH = Path(os.environ.get("{env_var}_FIXTURES", "/dev/null"))

{state_vars}


def _load_fixtures() -> None:
{load_fixtures_body}


_load_fixtures()


def _log_call(endpoint: str, request_body: dict[str, Any], response_body: Any) -> None:
    _audit_log.append({{
        "endpoint": endpoint,
        "request_body": request_body,
        "response_body": response_body,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }})


{request_models}

{endpoint_handlers}

@app.get("/{name}/audit")
def get_audit() -> dict[str, Any]:
    return {{"calls": _audit_log}}


@app.post("/{name}/reset")
def reset_state() -> dict[str, str]:
    global _audit_log
    _audit_log = []
    _load_fixtures()
    return {{"status": "reset"}}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "9100")))
'''


def _generate_request_model(ep: EndpointSpec) -> str:
    class_name = "".join(w.capitalize() for w in ep.name.split("_")) + "Request"
    type_map = {"string": "str", "integer": "int", "boolean": "bool",
                "number": "float", "array": "list"}
    fields = []
    for p in ep.params:
        ptype = type_map.get(p.get("type", "string"), "str")
        if p.get("required"):
            fields.append(f"    {p['name']}: {ptype}")
        elif "default" in p and p["default"] is not None:
            fields.append(f"    {p['name']}: {ptype} = {repr(p['default'])}")
        else:
            fields.append(f"    {p['name']}: {ptype} | None = None")
    if not fields:
        fields.append("    pass")
    return f"class {class_name}(BaseModel):\n" + "\n".join(fields)


def _generate_endpoint_handler(ep: EndpointSpec, service_name: str, primary_resource: str) -> str:
    class_name = "".join(w.capitalize() for w in ep.name.split("_")) + "Request"
    is_list = any(k in ep.name for k in ("list", "search", "get_all"))
    is_get = ep.name.startswith("get_") and not is_list
    is_create = any(k in ep.name for k in ("create", "add", "new", "send", "post"))
    is_update = any(k in ep.name for k in ("update", "edit", "modify", "assign"))
    is_delete = any(k in ep.name for k in ("delete", "remove", "close", "archive"))

    lines = [f'@app.post("{ep.path}")']

    if is_list:
        lines.append(f'def {ep.name}(req: {class_name} | None = None) -> dict[str, Any]:')
        lines.append(f'    if req is None:')
        lines.append(f'        req = {class_name}()')
        lines.append(f'    results = [copy.deepcopy(item) for item in _{primary_resource}]')
        lines.append(f'    resp = {{"{primary_resource}": results, "total": len(results)}}')
        lines.append(f'    _log_call("{ep.path}", req.model_dump(), resp)')
        lines.append(f'    return resp')
    elif is_get:
        id_param = next((p["name"] for p in ep.params if "id" in p["name"]), "id")
        lines.append(f'def {ep.name}(req: {class_name}) -> dict[str, Any]:')
        lines.append(f'    for item in _{primary_resource}:')
        lines.append(f'        if item.get("id", "") == req.{id_param} or item.get("{id_param}", "") == req.{id_param}:')
        lines.append(f'            resp = copy.deepcopy(item)')
        lines.append(f'            _log_call("{ep.path}", req.model_dump(), resp)')
        lines.append(f'            return resp')
        lines.append(f'    resp = {{"error": "Not found"}}')
        lines.append(f'    _log_call("{ep.path}", req.model_dump(), resp)')
        lines.append(f'    return resp')
    elif is_create:
        lines.append(f'def {ep.name}(req: {class_name}) -> dict[str, Any]:')
        lines.append(f'    new_id = f"{service_name}_{{len(_{primary_resource}) + 1:03d}}"')
        lines.append(f'    item = {{"id": new_id, **req.model_dump(), "created_at": datetime.now(timezone.utc).isoformat()}}')
        lines.append(f'    _{primary_resource}.append(item)')
        lines.append(f'    resp = {{"status": "created", "item": item}}')
        lines.append(f'    _log_call("{ep.path}", req.model_dump(), resp)')
        lines.append(f'    return resp')
    elif is_update:
        id_param = next((p["name"] for p in ep.params if "id" in p["name"]), "id")
        lines.append(f'def {ep.name}(req: {class_name}) -> dict[str, Any]:')
        lines.append(f'    for item in _{primary_resource}:')
        lines.append(f'        if item.get("id", "") == req.{id_param} or item.get("{id_param}", "") == req.{id_param}:')
        lines.append(f'            updates = {{k: v for k, v in req.model_dump().items() if v is not None and k != "{id_param}"}}')
        lines.append(f'            item.update(updates)')
        lines.append(f'            resp = {{"status": "updated", "item": copy.deepcopy(item)}}')
        lines.append(f'            _log_call("{ep.path}", req.model_dump(), resp)')
        lines.append(f'            return resp')
        lines.append(f'    resp = {{"error": "Not found"}}')
        lines.append(f'    _log_call("{ep.path}", req.model_dump(), resp)')
        lines.append(f'    return resp')
    elif is_delete:
        id_param = next((p["name"] for p in ep.params if "id" in p["name"]), "id")
        lines.append(f'def {ep.name}(req: {class_name}) -> dict[str, Any]:')
        lines.append(f'    for i, item in enumerate(_{primary_resource}):')
        lines.append(f'        if item.get("id", "") == req.{id_param} or item.get("{id_param}", "") == req.{id_param}:')
        lines.append(f'            removed = _{primary_resource}.pop(i)')
        lines.append(f'            resp = {{"status": "deleted", "item": removed}}')
        lines.append(f'            _log_call("{ep.path}", req.model_dump(), resp)')
        lines.append(f'            return resp')
        lines.append(f'    resp = {{"error": "Not found"}}')
        lines.append(f'    _log_call("{ep.path}", req.model_dump(), resp)')
        lines.append(f'    return resp')
    else:
        lines.append(f'def {ep.name}(req: {class_name}) -> dict[str, Any]:')
        lines.append(f'    resp = {{"status": "ok", "action": "{ep.name}", "params": req.model_dump()}}')
        lines.append(f'    _log_call("{ep.path}", req.model_dump(), resp)')
        lines.append(f'    return resp')

    return "\n".join(lines)


def generate_service(spec: ServiceSpec, verify: bool = True) -> Path:
    """Generate mock service files from a confirmed ServiceSpec.

    Creates:
      - mock_services/<name>/__init__.py
      - mock_services/<name>/server.py

    If verify=True, starts the server and validates it against our standards.
    Raises ValueError if server validation fails.

    Returns path to the service directory.
    """
    service_dir = PROJECT_ROOT / "mock_services" / spec.name
    service_dir.mkdir(parents=True, exist_ok=True)
    (service_dir / "__init__.py").write_text("")

    primary_resource = list(spec.data_model.keys())[0] if spec.data_model else "items"
    state_vars = f"_{primary_resource}: list[dict[str, Any]] = []\n_audit_log: list[dict[str, Any]] = []"
    load_body = f"    global _{primary_resource}\n"
    load_body += f'    _{primary_resource} = load_fixtures(FIXTURES_PATH, id_field="id")'
    models = "\n\n\n".join(_generate_request_model(ep) for ep in spec.endpoints)
    handlers = "\n\n\n".join(
        _generate_endpoint_handler(ep, spec.name, primary_resource)
        for ep in spec.endpoints
    )

    server_code = SERVER_TEMPLATE.format(
        real_service=spec.real_service,
        name=spec.name,
        env_var=spec.name.upper(),
        state_vars=state_vars,
        load_fixtures_body=load_body,
        request_models=models,
        endpoint_handlers=handlers,
    )

    (service_dir / "server.py").write_text(server_code)

    # Verify: start server and check it matches our standards
    if verify:
        issues = validate_server(service_dir, spec)
        if issues:
            detail = "\n".join(f"  - {i}" for i in issues)
            raise ValueError(
                f"Generated server failed validation:\n{detail}\n"
                f"Server code at: {service_dir / 'server.py'}"
            )

    return service_dir


# ---------------------------------------------------------------------------
# Step 3: Register in SERVICE_DEFINITIONS
# ---------------------------------------------------------------------------

def build_service_definition(spec: ServiceSpec) -> dict:
    """Build a SERVICE_DEFINITIONS entry from a ServiceSpec."""
    endpoints = []
    actions = []
    for ep in spec.endpoints:
        params_str = ", ".join(p["name"] for p in ep.params)
        endpoints.append(f"POST {ep.path} -- {ep.description} ({params_str})")
        actions.append(ep.name)
    return {
        "description": spec.description,
        "endpoints": endpoints,
        "actions": actions,
        "fixture_schema": spec.fixture_schema,
    }


def register_service(spec: ServiceSpec) -> None:
    """Register a new service in SERVICE_DEFINITIONS.

    - Updates runtime dict
    - Writes sidecar JSON for persistence across sessions
    """
    from clawenvkit.generate.task_generator import SERVICE_DEFINITIONS

    definition = build_service_definition(spec)
    SERVICE_DEFINITIONS[spec.name] = definition

    registry_dir = PROJECT_ROOT / "mock_services" / "_registry"
    registry_dir.mkdir(exist_ok=True)
    sidecar = registry_dir / f"{spec.name}.json"
    sidecar.write_text(json.dumps({
        "name": spec.name,
        "real_service": spec.real_service,
        "definition": definition,
        "spec": {
            "endpoints": [
                {"path": ep.path, "name": ep.name, "description": ep.description,
                 "params": ep.params, "returns": ep.returns}
                for ep in spec.endpoints
            ],
            "data_model": spec.data_model,
        },
    }, indent=2))


def load_custom_services() -> None:
    """Load custom service registrations from sidecar files.

    Called at import time to pick up previously generated services.
    """
    from clawenvkit.generate.task_generator import SERVICE_DEFINITIONS

    registry_dir = PROJECT_ROOT / "mock_services" / "_registry"
    if not registry_dir.exists():
        return
    for sidecar in registry_dir.glob("*.json"):
        try:
            data = json.loads(sidecar.read_text())
            name = data["name"]
            if name not in SERVICE_DEFINITIONS:
                SERVICE_DEFINITIONS[name] = data["definition"]
        except Exception:
            pass
