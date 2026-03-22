"""Tests for scripts/core/image_builder.py"""

import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from scripts.core.schema import BuildResult, SuccessCriterion, TaskSpec
from scripts.core.image_builder import (
    BUILD_ROOT,
    ImageBuildError,
    MAX_INITIAL_FS_BYTES,
    build,
    build_batch,
    generate_dockerfile,
    _check_size,
    _image_name,
    _write_build_context,
)


def _make_task(task_id="test-001", **overrides):
    defaults = dict(
        task_id=task_id,
        domain="cli-file-ops",
        difficulty="easy",
        skill_target="file create",
        task_type="code",
        instruction="Create hello.txt",
        initial_fs={"/workspace/README.md": "create hello.txt"},
        base_tools=["bash", "python3"],
        success_criteria=[
            SuccessCriterion(type="file_exists", path="/workspace/hello.txt"),
        ],
        docker_image="",
    )
    defaults.update(overrides)
    return TaskSpec(**defaults)


# --- generate_dockerfile ---


class TestGenerateDockerfile:
    def test_tools_layer_before_copy(self):
        task = _make_task()
        df = generate_dockerfile(task)
        apk_pos = df.index("apk add")
        copy_pos = df.index("COPY initial_fs/")
        assert apk_pos < copy_pos

    def test_includes_base_tools(self):
        task = _make_task(base_tools=["git", "bash", "python3"])
        df = generate_dockerfile(task)
        assert "git" in df
        assert "bash" in df
        assert "python3" in df

    def test_custom_base_image(self):
        task = _make_task()
        df = generate_dockerfile(task, base_image="ubuntu:22.04")
        assert "FROM ubuntu:22.04" in df

    def test_workdir_set(self):
        task = _make_task()
        df = generate_dockerfile(task)
        assert "WORKDIR /workspace" in df

    def test_bash_always_included(self):
        task = _make_task(base_tools=["python3"])
        df = generate_dockerfile(task)
        assert "bash" in df


# --- _image_name ---


class TestImageName:
    def test_format(self):
        task = _make_task(task_id="cli-file-ops-042")
        assert _image_name(task) == "clawharness/cli-file-ops/cli-file-ops-042:v1"


# --- _check_size ---


class TestCheckSize:
    def test_under_limit(self):
        task = _make_task()
        size = _check_size(task)
        assert size < MAX_INITIAL_FS_BYTES

    def test_over_limit(self):
        big_content = "x" * (MAX_INITIAL_FS_BYTES + 1)
        task = _make_task(initial_fs={"/workspace/big.txt": big_content})
        with pytest.raises(ImageBuildError, match="exceeds limit"):
            _check_size(task)


# --- _write_build_context ---


class TestWriteBuildContext:
    def test_writes_files(self, tmp_path):
        task = _make_task(
            initial_fs={
                "/workspace/main.py": "print('hello')",
                "/workspace/sub/config.json": '{"key": "val"}',
            }
        )
        _write_build_context(task, tmp_path, "alpine:3.19")

        assert (tmp_path / "Dockerfile").exists()
        assert (tmp_path / "initial_fs" / "main.py").read_text() == "print('hello')"
        assert (tmp_path / "initial_fs" / "sub" / "config.json").read_text() == '{"key": "val"}'


# --- build (mocked subprocess) ---


class TestBuild:
    @patch("scripts.core.image_builder.subprocess.run")
    @patch("scripts.core.image_builder.shutil.rmtree")
    def test_successful_build(self, mock_rmtree, mock_run):
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="", stderr=""),  # docker build
            MagicMock(returncode=0, stdout="12345678\n", stderr=""),  # docker inspect
        ]
        task = _make_task()
        result = build(task)

        assert result.success is True
        assert result.image_name == "clawharness/cli-file-ops/test-001:v1"
        assert result.image_size_bytes == 12345678
        # Build context cleaned up
        mock_rmtree.assert_called()

    @patch("scripts.core.image_builder.subprocess.run")
    @patch("scripts.core.image_builder.shutil.rmtree")
    def test_failed_build(self, mock_rmtree, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="build error msg")
        task = _make_task()
        result = build(task)

        assert result.success is False
        assert "build error msg" in result.error
        # Build context still cleaned up
        mock_rmtree.assert_called()

    @patch("scripts.core.image_builder.subprocess.run")
    @patch("scripts.core.image_builder.shutil.rmtree")
    def test_build_context_under_home(self, mock_rmtree, mock_run):
        mock_run.side_effect = [
            MagicMock(returncode=0),
            MagicMock(returncode=0, stdout="0\n"),
        ]
        task = _make_task()
        build(task)

        # Check the docker build command uses path under ~/.clawharness/
        build_call = mock_run.call_args_list[0]
        build_path = build_call[0][0][-1]  # last arg is the build dir
        assert str(Path.home()) in build_path
        assert ".clawharness" in build_path

    def test_oversized_initial_fs_rejected(self):
        big_content = "x" * (MAX_INITIAL_FS_BYTES + 1)
        task = _make_task(initial_fs={"/workspace/big.txt": big_content})
        result = build(task)
        assert result.success is False
        assert "exceeds limit" in result.error

    @patch("scripts.core.image_builder.subprocess.run")
    @patch("scripts.core.image_builder.shutil.rmtree")
    def test_cleanup_on_exception(self, mock_rmtree, mock_run):
        mock_run.side_effect = RuntimeError("unexpected crash")
        task = _make_task()
        result = build(task)
        assert result.success is False
        mock_rmtree.assert_called()


# --- build_batch ---


class TestBuildBatch:
    @patch("scripts.core.image_builder.build")
    def test_all_succeed(self, mock_build):
        mock_build.side_effect = [
            BuildResult(image_name="img1", success=True),
            BuildResult(image_name="img2", success=True),
            BuildResult(image_name="img3", success=True),
        ]
        tasks = [_make_task(f"t{i}") for i in range(3)]
        results = build_batch(tasks, max_workers=2)
        assert len(results) == 3
        assert all(r.success for r in results)

    @patch("scripts.core.image_builder.build")
    def test_failure_isolated(self, mock_build):
        mock_build.side_effect = [
            BuildResult(image_name="img1", success=True),
            BuildResult(image_name="img2", success=False, error="failed"),
            BuildResult(image_name="img3", success=True),
        ]
        tasks = [_make_task(f"t{i}") for i in range(3)]
        results = build_batch(tasks, max_workers=2)
        assert results[0].success is True
        assert results[1].success is False
        assert results[2].success is True

    @patch("scripts.core.image_builder.build")
    def test_preserves_order(self, mock_build):
        mock_build.side_effect = [
            BuildResult(image_name="clawharness/d/t0:v1", success=True),
            BuildResult(image_name="clawharness/d/t1:v1", success=True),
        ]
        tasks = [_make_task("t0"), _make_task("t1")]
        results = build_batch(tasks)
        assert results[0].image_name == "clawharness/d/t0:v1"
        assert results[1].image_name == "clawharness/d/t1:v1"
