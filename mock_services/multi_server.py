"""Multi-service mock server for cross-service tasks.

Imports and mounts multiple mock service FastAPI apps into a single server.
Each service keeps its own URL prefix (/gmail/*, /calendar/*, /todo/*, etc.)
so they don't conflict.

Usage:
    # Start specific services
    python multi_server.py --services todo,gmail,calendar

    # Start all 13 core services
    python multi_server.py --all

    # Custom port
    PORT=9100 python multi_server.py --services todo,gmail
"""

from __future__ import annotations

import argparse
import importlib
import os
import sys
from pathlib import Path

# Ensure mock_services package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI
from fastapi.routing import APIRoute
from mock_services._base import add_error_injection

# Service name → route prefix mapping (for services where name ≠ prefix)
SERVICE_PREFIX = {
    "web_real": "/web",
    "web_real_injection": "/web",
}

CORE_SERVICES = [
    "calendar", "config", "contacts", "crm", "finance",
    "gmail", "helpdesk", "inventory", "kb", "notes",
    "rss", "scheduler", "todo",
]

# Services that need special handling or external deps — skip by default
EXTRA_SERVICES = ["caption", "documents", "ocr", "spotify", "web", "web_real", "web_real_injection"]


def create_multi_app(services: list[str]) -> FastAPI:
    """Create a FastAPI app that combines multiple mock services."""
    multi_app = FastAPI(title="ClawHarness Multi-Service Mock API")
    add_error_injection(multi_app)

    loaded = []
    for svc in services:
        server_path = Path(__file__).parent / svc / "server.py"
        if not server_path.exists():
            print(f"[multi] WARNING: {svc}/server.py not found, skipping", flush=True)
            continue

        try:
            # Ensure fixture env var exists (empty JSON array as fallback)
            fixture_env = f"{svc.upper()}_FIXTURES"
            if fixture_env not in os.environ:
                fallback = f"/tmp/{svc}_fixtures.json"
                if not Path(fallback).exists():
                    Path(fallback).write_text("[]")
                os.environ[fixture_env] = fallback

            # Import the service module dynamically
            module = importlib.import_module(f"mock_services.{svc}.server")
            svc_app = getattr(module, "app", None)
            if svc_app is None:
                print(f"[multi] WARNING: {svc}/server.py has no 'app', skipping", flush=True)
                continue

            # Copy only business APIRoutes with service-specific prefixes.
            # This skips framework routes (/docs, /openapi.json, /redoc)
            # and per-service /injected_errors (multi_app has its own).
            svc_prefix = SERVICE_PREFIX.get(svc, f"/{svc}")
            registered = {r.path for r in multi_app.routes if hasattr(r, "path")}
            for route in svc_app.routes:
                if not isinstance(route, APIRoute):
                    continue
                if not route.path.startswith(svc_prefix):
                    continue
                if route.path in registered:
                    print(f"[multi] WARNING: duplicate route {route.path}, skipping", flush=True)
                    continue
                multi_app.routes.append(route)
                registered.add(route.path)

            loaded.append(svc)
        except Exception as e:
            print(f"[multi] ERROR loading {svc}: {e}", flush=True)

    print(f"[multi] Loaded {len(loaded)} services: {', '.join(loaded)}", flush=True)
    return multi_app


def main():
    parser = argparse.ArgumentParser(description="Multi-service mock server")
    parser.add_argument("--services", type=str, help="Comma-separated service names")
    parser.add_argument("--all", action="store_true", help="Load all 13 core services")
    args = parser.parse_args()

    if args.all:
        services = CORE_SERVICES
    elif args.services:
        services = [s.strip() for s in args.services.split(",")]
    else:
        # Default: load from SERVICES env var, or all core
        env_services = os.environ.get("SERVICES", "")
        if env_services:
            services = [s.strip() for s in env_services.split(",")]
        else:
            services = CORE_SERVICES

    app = create_multi_app(services)

    import uvicorn
    port = int(os.environ.get("PORT", "9100"))
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
