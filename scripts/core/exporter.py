"""Export validated tasks to train.jsonl."""

from __future__ import annotations

import json
import os
from pathlib import Path

from .schema import ExportResult, TaskSpec


def export(
    tasks: list[TaskSpec],
    output_dir: str,
    split: str = "train",
) -> ExportResult:
    """Write validated tasks to {output_dir}/{split}.jsonl.

    Filters out tasks where validation_result.passed is False.
    Returns ExportResult with paths and counts.
    """
    out_path = Path(os.path.expanduser(output_dir))
    out_path.mkdir(parents=True, exist_ok=True)

    jsonl_path = out_path / f"{split}.jsonl"

    passed_tasks = []
    failed_count = 0

    for task in tasks:
        if task.validation_result is not None and not task.validation_result.passed:
            failed_count += 1
            continue
        passed_tasks.append(task)

    with open(jsonl_path, "w") as f:
        for task in passed_tasks:
            line = {
                "task_id": task.task_id,
                "task_type": task.task_type,
                "instruction": task.instruction,
                "docker_image": task.docker_image,
                "success_criteria": [c.model_dump() for c in task.success_criteria],
                "schema_version": task.schema_version,
            }
            if task.test_files:
                line["test_files"] = task.test_files
            if task.mock_server_config:
                line["mock_server_config"] = task.mock_server_config.model_dump()
            f.write(json.dumps(line, ensure_ascii=False) + "\n")

    return ExportResult(
        jsonl_path=str(jsonl_path),
        task_count=len(passed_tasks),
        failed_validation_count=failed_count,
        image_names=[t.docker_image for t in passed_tasks],
    )
