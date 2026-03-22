"""Step 2 (CODE, cont.): Build Docker images from TaskSpec."""

from __future__ import annotations

import json
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

# Tool name → apk package mapping (only tools that need explicit install)
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

# Tools built into Alpine/busybox — skip these in apk add
_BUILTIN_TOOLS = {
    "cat", "chmod", "chown", "cp", "date", "echo", "env", "head",
    "ls", "mkdir", "mv", "pwd", "rm", "rmdir", "sh", "sleep", "sort",
    "tail", "tar", "test", "touch", "tr", "uniq", "wc", "which", "xargs",
}

MAX_INITIAL_FS_BYTES = 10 * 1024 * 1024  # 10MB


class ImageBuildError(Exception):
    """Raised when Docker image build fails."""
    pass


def generate_dockerfile(task: TaskSpec, base_image: str = "alpine:3.19") -> str:
    """Generate Dockerfile content. Tools layer first (cached), COPY second."""
    # Map base_tools to apk packages, skipping builtins
    packages = set()
    for tool in task.base_tools:
        if tool in _BUILTIN_TOOLS:
            continue  # already in Alpine/busybox
        pkg = _APK_PACKAGES.get(tool, tool)
        packages.add(pkg)
    # Always include bash
    packages.add("bash")

    packages_str = " ".join(sorted(packages))

    # Check if pytest is needed (task has test_files or pytest_pass criteria)
    needs_pytest = (
        bool(task.test_files)
        or any(c.type == "pytest_pass" for c in task.success_criteria)
    )

    # Check if mock server is needed
    needs_mock = task.mock_server_config is not None

    # pip packages needed
    pip_packages = []
    if needs_pytest:
        pip_packages.append("pytest")
    if needs_mock:
        pip_packages.append("flask")

    pip_line = ""
    if pip_packages:
        packages.add("py3-pip")
        packages_str = " ".join(sorted(packages))
        pkgs = " ".join(pip_packages)
        pip_line = f"\n# Layer 1b: pip packages\nRUN pip3 install {pkgs} --break-system-packages --quiet\n"

    # Mock server setup: copy mock_server.py into container
    mock_copy_line = ""
    if needs_mock:
        mock_copy_line = "\n# Layer 2b: mock server\nCOPY mock_server.py /workspace/mock_server/server.py\n"

    return f"""FROM {base_image}

# Layer 1: tools (cached across tasks in same domain)
RUN apk add --no-cache {packages_str}
{pip_line}
# Layer 2: task-specific initial filesystem
COPY initial_fs/ /workspace/
RUN chmod -R 755 /workspace/
{mock_copy_line}
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
    # Write initial_fs + test_files (both go into /workspace/)
    all_files = {**task.initial_fs, **task.test_files}
    for path, content in all_files.items():
        # Strip leading /workspace/ to get relative path inside initial_fs/
        rel_path = path.removeprefix("/workspace/").lstrip("/")
        file_path = fs_dir / rel_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content)

    # Write mock server files if needed
    if task.mock_server_config is not None:
        # Copy mock_server.py module into build context
        mock_server_src = Path(__file__).resolve().parent / "mock_server.py"
        if mock_server_src.exists():
            import shutil
            shutil.copy2(mock_server_src, build_dir / "mock_server.py")

        # Write responses.json into initial_fs/mock_server/
        mock_dir = fs_dir / "mock_server"
        mock_dir.mkdir(parents=True, exist_ok=True)

        responses = task.mock_server_config.responses
        (mock_dir / "responses.json").write_text(json.dumps(responses, indent=2))

        # Write expected_calls.json
        expected = {
            "calls": task.mock_server_config.expected_calls,
            "min_calls": task.mock_server_config.min_calls,
            "strict": task.mock_server_config.strict,
        }
        (mock_dir / "expected_calls.json").write_text(json.dumps(expected, indent=2))


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
