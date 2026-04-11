"""Pass A (partial) + C: Generator vs runtime compatibility checks."""

from __future__ import annotations

from pathlib import Path

from .models import Finding


def check_generator(project_root: Path) -> list[Finding]:
    """Check SERVICE_DEFINITIONS vs actual mock services."""
    import sys
    sys.path.insert(0, str(project_root))

    findings = []

    try:
        from clawenvkit.generate.task_generator import SERVICE_DEFINITIONS, CROSS_SERVICE_CATEGORIES
    except ImportError as e:
        findings.append(Finding("GENERATOR_IMPORT_FAIL", "error", f"Cannot import task_generator: {e}"))
        return findings

    # --- Every service in DEFINITIONS has a mock service ---
    for svc, defn in SERVICE_DEFINITIONS.items():
        svc_dir = project_root / "mock_services" / svc
        svc_server = svc_dir / "server.py"

        if not svc_dir.exists():
            findings.append(Finding(
                "GEN_MISSING_SERVICE_DIR", "error",
                f"SERVICE_DEFINITIONS['{svc}'] but mock_services/{svc}/ not found",
                context={"service": svc},
            ))
            continue

        if not svc_server.exists():
            findings.append(Finding(
                "GEN_MISSING_SERVER", "error",
                f"mock_services/{svc}/ exists but server.py missing",
                context={"service": svc},
            ))
            continue

        # --- Check endpoints exist in server code ---
        server_code = svc_server.read_text()
        for ep_desc in defn.get("endpoints", []):
            # Parse "POST /todo/tasks — List tasks (status)" → "/todo/tasks"
            parts = ep_desc.split(" — ")[0].split()
            if len(parts) >= 2:
                endpoint = parts[1]
                # web_real uses /web/ prefix
                check_ep = endpoint
                if svc in ("web_real", "web_real_injection"):
                    check_ep = endpoint.replace(f"/{svc}/", "/web/")
                if check_ep not in server_code and f'"{check_ep}"' not in server_code:
                    findings.append(Finding(
                        "GEN_ENDPOINT_MISSING", "warning",
                        f"Endpoint '{endpoint}' in SERVICE_DEFINITIONS['{svc}'] not found in server.py",
                        file=str(svc_server), context={"service": svc, "endpoint": endpoint},
                    ))

    # --- Cross-service categories reference known services ---
    for cat, cat_def in CROSS_SERVICE_CATEGORIES.items():
        for svc in cat_def.get("services", []):
            if svc not in SERVICE_DEFINITIONS:
                findings.append(Finding(
                    "GEN_CATEGORY_UNKNOWN_SERVICE", "error",
                    f"Category '{cat}' references service '{svc}' not in SERVICE_DEFINITIONS",
                    context={"category": cat, "service": svc},
                ))

    return findings
