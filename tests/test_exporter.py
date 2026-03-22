"""Tests for scripts/core/exporter.py"""

import json

import pytest

from scripts.core.schema import SuccessCriterion, TaskSpec, ValidationResult
from scripts.core.exporter import export


def _make_task(task_id="test-001", passed=True, **overrides):
    defaults = dict(
        task_id=task_id,
        domain="cli-file-ops",
        difficulty="easy",
        skill_target="file create",
        task_type="code",
        instruction="Create hello.txt",
        initial_fs={"/workspace/README.md": "instructions"},
        base_tools=["bash", "python3"],
        success_criteria=[
            SuccessCriterion(type="file_exists", path="/workspace/hello.txt"),
        ],
        docker_image=f"clawharness/cli-file-ops/{task_id}:v1",
        validation_result=ValidationResult(
            passed=passed,
            solver_actions=["echo hi"],
            criteria_results=[True],
        ),
    )
    defaults.update(overrides)
    return TaskSpec(**defaults)


class TestExport:
    def test_writes_jsonl(self, tmp_path):
        tasks = [_make_task("t-001"), _make_task("t-002")]
        result = export(tasks, str(tmp_path), split="train")

        assert result.task_count == 2
        assert result.failed_validation_count == 0

        lines = (tmp_path / "train.jsonl").read_text().strip().split("\n")
        assert len(lines) == 2

        data = json.loads(lines[0])
        assert data["task_id"] == "t-001"
        assert data["instruction"] == "Create hello.txt"
        assert data["docker_image"] == "clawharness/cli-file-ops/t-001:v1"
        assert len(data["success_criteria"]) == 1

    def test_filters_failed_tasks(self, tmp_path):
        tasks = [
            _make_task("t-001", passed=True),
            _make_task("t-002", passed=False),
            _make_task("t-003", passed=True),
        ]
        result = export(tasks, str(tmp_path))

        assert result.task_count == 2
        assert result.failed_validation_count == 1

        lines = (tmp_path / "train.jsonl").read_text().strip().split("\n")
        assert len(lines) == 2
        ids = [json.loads(l)["task_id"] for l in lines]
        assert "t-001" in ids
        assert "t-003" in ids
        assert "t-002" not in ids

    def test_custom_split(self, tmp_path):
        tasks = [_make_task()]
        result = export(tasks, str(tmp_path), split="val")
        assert "val.jsonl" in result.jsonl_path
        assert (tmp_path / "val.jsonl").exists()

    def test_creates_output_dir(self, tmp_path):
        out = tmp_path / "nested" / "dir"
        tasks = [_make_task()]
        result = export(tasks, str(out))
        assert out.exists()
        assert (out / "train.jsonl").exists()

    def test_image_names_in_result(self, tmp_path):
        tasks = [_make_task("t-001"), _make_task("t-002")]
        result = export(tasks, str(tmp_path))
        assert len(result.image_names) == 2
        assert "clawharness/cli-file-ops/t-001:v1" in result.image_names

    def test_no_validation_result_included(self, tmp_path):
        """Tasks without validation_result are included (not filtered)."""
        task = _make_task(validation_result=None)
        result = export([task], str(tmp_path))
        assert result.task_count == 1

    def test_empty_tasks(self, tmp_path):
        result = export([], str(tmp_path))
        assert result.task_count == 0
        assert (tmp_path / "train.jsonl").read_text() == ""
