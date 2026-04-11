"""Pass F: Packaging integrity checks."""

from __future__ import annotations

from pathlib import Path

from .models import Finding


def check_packaging(project_root: Path) -> list[Finding]:
    findings = []

    pyproject = project_root / "pyproject.toml"
    if not pyproject.exists():
        findings.append(Finding("PKG_MISSING_PYPROJECT", "error", "pyproject.toml not found"))
        return findings

    content = pyproject.read_text()

    # Check package-data doesn't reference nonexistent package-relative paths
    if "package-data" in content.lower():
        # If package-data is declared, check that referenced patterns exist
        import re
        for match in re.finditer(r'"([^"]+\*[^"]*)"', content):
            pattern = match.group(1)
            # These should be under clawenvkit/ to work in wheel mode
            if not pattern.startswith("clawenvkit") and "/" in pattern:
                findings.append(Finding(
                    "PKG_BAD_PACKAGE_DATA", "warning",
                    f"package-data pattern '{pattern}' is not under clawenvkit/ — won't be in wheel",
                    file=str(pyproject),
                ))

    # Check that paths.py assumptions are valid for editable install
    paths_py = project_root / "clawenvkit" / "paths.py"
    if paths_py.exists():
        paths_code = paths_py.read_text()
        # Check referenced directories exist
        for dirname in ("prompts", "mock_services", "Auto-ClawEval-mini"):
            if dirname in paths_code:
                if not (project_root / dirname).exists():
                    findings.append(Finding(
                        "PKG_MISSING_ROOT_DIR", "warning",
                        f"paths.py references '{dirname}/' but it doesn't exist at repo root",
                        file=str(paths_py),
                    ))

    return findings
