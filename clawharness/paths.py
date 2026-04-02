"""Path resolution for ClawHarnessing.

Supports two installation modes:
  1. Source / editable install (pip install -e .):
     prompts/ and mock_services/ are at repo root
  2. Standalone install (future pip install clawharness):
     prompts/ bundled inside package via package_data

Usage:
    from clawharness.paths import PROJECT_ROOT, PROMPTS_DIR, MOCK_SERVICES_DIR
"""

from pathlib import Path
import os

# clawharness/ package directory
_PACKAGE_DIR = Path(__file__).resolve().parent

# Project root: two levels up from clawharness/paths.py
# Works for editable install where clawharness/ is inside the repo
_CANDIDATE_ROOT = _PACKAGE_DIR.parent


def _find_project_root() -> Path:
    """Find the project root directory.

    Checks multiple candidates in order:
    1. CLAWHARNESS_ROOT env var (explicit override)
    2. Parent of clawharness/ package (editable install)
    3. Current working directory (fallback)
    """
    # Explicit override
    env_root = os.environ.get("CLAWHARNESS_ROOT")
    if env_root and Path(env_root).is_dir():
        return Path(env_root)

    # Editable install: repo root has prompts/ and mock_services/
    if (_CANDIDATE_ROOT / "prompts").is_dir() and (_CANDIDATE_ROOT / "mock_services").is_dir():
        return _CANDIDATE_ROOT

    # Docker container: /opt/clawharness/ has everything
    docker_root = Path("/opt/clawharness")
    if docker_root.is_dir() and (docker_root / "mock_services").is_dir():
        return docker_root

    # Fallback: cwd
    cwd = Path.cwd()
    if (cwd / "prompts").is_dir():
        return cwd

    # Last resort: use candidate root anyway
    return _CANDIDATE_ROOT


PROJECT_ROOT = _find_project_root()
PROMPTS_DIR = PROJECT_ROOT / "prompts"
MOCK_SERVICES_DIR = PROJECT_ROOT / "mock_services"
DATASET_DIR = PROJECT_ROOT / "dataset"
