"""Step 2 (CODE, cont.): Build Docker images from TaskSpec."""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

from .schema import BuildResult, TaskSpec

# All build contexts under ~/  (not /tmp/) due to Colima mount limitation
BUILD_ROOT = Path.home() / ".clawharness" / "build"

# Tool name → apk package mapping
_APK_PACKAGES = {
    "bash": "bash",
    "git": "git",
    "python3": "python3",
    "pip": "py3-pip",
    "py3-pip": "py3-pip",
    "jq": "jq",
    "curl": "curl",
    "sed": "sed",
    "awk": "gawk",
    "grep": "grep",
}

MAX_INITIAL_FS_BYTES = 10 * 1024 * 1024  # 10MB


class ImageBuildError(Exception):
    """Raised when Docker image build fails."""
    pass


def generate_dockerfile(task: TaskSpec, base_image: str = "alpine:3.19") -> str:
    """Generate Dockerfile content. Tools layer first (cached), COPY second."""
    # Map base_tools to apk packages
    packages = set()
    for tool in task.base_tools:
        pkg = _APK_PACKAGES.get(tool, tool)
        packages.add(pkg)
    # Always include bash
    packages.add("bash")

    packages_str = " ".join(sorted(packages))

    return f"""FROM {base_image}

# Layer 1: tools (cached across tasks in same domain)
RUN apk add --no-cache {packages_str}

# Layer 2: task-specific initial filesystem
COPY initial_fs/ /workspace/
RUN chmod -R 755 /workspace/

WORKDIR /workspace
"""


def _image_name(task: TaskSpec) -> str:
    return f"clawharness/{task.domain}/{task.task_id}:v1"


def _check_size(task: TaskSpec) -> int:
    """Check total initial_fs size. Raises ImageBuildError if > 10MB. Returns size."""
    total = sum(len(content.encode("utf-8")) for content in task.initial_fs.values())
    if total > MAX_INITIAL_FS_BYTES:
        raise ImageBuildError(
            f"initial_fs total size {total} bytes exceeds limit of {MAX_INITIAL_FS_BYTES} bytes"
        )
    return total


def _write_build_context(task: TaskSpec, build_dir: Path, base_image: str) -> None:
    """Write Dockerfile and initial_fs into build_dir."""
    build_dir.mkdir(parents=True, exist_ok=True)

    # Write Dockerfile
    dockerfile = generate_dockerfile(task, base_image)
    (build_dir / "Dockerfile").write_text(dockerfile)

    # Write initial_fs files
    fs_dir = build_dir / "initial_fs"
    fs_dir.mkdir(exist_ok=True)
    for path, content in task.initial_fs.items():
        # Strip leading /workspace/ to get relative path inside initial_fs/
        rel_path = path.removeprefix("/workspace/").lstrip("/")
        file_path = fs_dir / rel_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content)


def build(task: TaskSpec, base_image: str = "alpine:3.19") -> BuildResult:
    """Build Docker image from TaskSpec. Returns BuildResult."""
    image = _image_name(task)
    build_dir = BUILD_ROOT / task.task_id

    try:
        # Check size before building
        _check_size(task)

        # Write build context
        _write_build_context(task, build_dir, base_image)

        # Run docker build
        start = time.monotonic()
        result = subprocess.run(
            ["docker", "build", "-t", image, str(build_dir)],
            capture_output=True,
            text=True,
            timeout=300,
        )
        elapsed = time.monotonic() - start

        if result.returncode != 0:
            return BuildResult(
                image_name=image,
                build_time_seconds=elapsed,
                success=False,
                error=result.stderr[:500],
            )

        # Get image size
        inspect = subprocess.run(
            ["docker", "image", "inspect", image, "--format", "{{.Size}}"],
            capture_output=True,
            text=True,
        )
        size_bytes = int(inspect.stdout.strip()) if inspect.returncode == 0 else 0

        return BuildResult(
            image_name=image,
            build_time_seconds=elapsed,
            image_size_bytes=size_bytes,
            success=True,
        )
    except ImageBuildError as e:
        return BuildResult(image_name=image, success=False, error=str(e))
    except subprocess.TimeoutExpired:
        return BuildResult(image_name=image, success=False, error="docker build timed out (300s)")
    except Exception as e:
        return BuildResult(image_name=image, success=False, error=str(e))
    finally:
        # Always clean up build context
        if build_dir.exists():
            shutil.rmtree(build_dir, ignore_errors=True)


def build_batch(
    tasks: list[TaskSpec],
    max_workers: int = 4,
    base_image: str = "alpine:3.19",
) -> list[BuildResult]:
    """Build multiple images in parallel. Failure-isolated."""
    results: dict[str, BuildResult] = {}

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(build, task, base_image): task.task_id
            for task in tasks
        }
        for future in as_completed(futures):
            task_id = futures[future]
            try:
                results[task_id] = future.result()
            except Exception as e:
                results[task_id] = BuildResult(
                    image_name=f"clawharness/unknown/{task_id}:v1",
                    success=False,
                    error=str(e),
                )

    # Return in original order
    return [results[task.task_id] for task in tasks]
