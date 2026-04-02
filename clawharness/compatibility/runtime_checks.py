"""Pass E: Docker / entrypoint integrity checks."""

from __future__ import annotations

import re
from pathlib import Path

from .models import Finding

# Known service → Python dependency mapping
SERVICE_DEPENDENCIES = {
    "web_real": ["httpx", "trafilatura"],
    "web_real_injection": ["httpx", "trafilatura"],
}


def check_runtime(project_root: Path) -> list[Finding]:
    findings = []
    docker_dir = project_root / "docker"

    if not docker_dir.exists():
        findings.append(Finding("DOCKER_DIR_MISSING", "error", "docker/ directory not found"))
        return findings

    # --- Check each Dockerfile ---
    for df in sorted(docker_dir.glob("Dockerfile*")):
        content = df.read_text()

        # Find entrypoint reference
        entrypoint_match = re.search(r'ENTRYPOINT\s+\[?"([^"]+)"', content)
        if entrypoint_match:
            ep_path = entrypoint_match.group(1)
            # Check if source entrypoint exists in build context
            ep_filename = Path(ep_path).name
            candidates = [
                docker_dir / ep_filename,
                project_root / ep_path.lstrip("/"),
            ]
            if not any(c.exists() for c in candidates):
                findings.append(Finding(
                    "DOCKER_MISSING_ENTRYPOINT", "error",
                    f"Dockerfile references entrypoint '{ep_path}' but source not found",
                    file=str(df),
                ))

        # Find COPY'd files that don't exist
        for copy_match in re.finditer(r'COPY\s+(\S+)\s+', content):
            src = copy_match.group(1)
            if src.startswith("--") or src.startswith("$"):
                continue
            src_path = project_root / src
            if not src_path.exists() and not src.startswith("/"):
                findings.append(Finding(
                    "DOCKER_MISSING_COPY_SOURCE", "error",
                    f"COPY source '{src}' not found in build context",
                    file=str(df), context={"source": src},
                ))

        # Check pip install includes required service deps
        pip_match = re.search(r'pip3?\s+install.*?\n\s+(.+)', content)
        if pip_match:
            installed_packages = pip_match.group(1).lower()
            for svc, deps in SERVICE_DEPENDENCIES.items():
                # Check if this Dockerfile copies mock_services
                if "mock_services" in content:
                    for dep in deps:
                        if dep not in installed_packages:
                            findings.append(Finding(
                                "DOCKER_MISSING_DEPENDENCY", "warning",
                                f"Service '{svc}' needs '{dep}' but not in pip install",
                                file=str(df), context={"service": svc, "dependency": dep},
                            ))

    # --- Check entrypoints don't reference missing files ---
    for ep in sorted(docker_dir.glob("entrypoint*.sh")):
        content = ep.read_text()

        # Find python3 /path/to/script.py references
        for py_match in re.finditer(r'python3\s+(/\S+\.py)', content):
            # These are container paths — check if the source exists
            py_path = py_match.group(1)
            # Map container path to repo path
            repo_path = py_path.replace("/opt/clawharness/", "")
            if (project_root / repo_path).exists():
                continue
            # Also check if it's a relative reference
            if not any((project_root / p).exists() for p in [repo_path, repo_path.lstrip("/")]):
                findings.append(Finding(
                    "ENTRYPOINT_MISSING_SCRIPT", "error",
                    f"Entrypoint references '{py_path}' but '{repo_path}' not found",
                    file=str(ep),
                ))

    return findings
