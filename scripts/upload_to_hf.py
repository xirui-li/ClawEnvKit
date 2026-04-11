"""Upload Auto-ClawEval datasets to HuggingFace Hub.

Uploads the raw YAML files (the format ClawEnvKit actually uses) plus
a flat metadata.jsonl index for HF datasets-library compatibility.

Layout in each repo:
    tasks/<category>/<task_id>.yaml   # original yaml files (for evaluation)
    metadata.jsonl                    # one line per task, indexable via datasets lib
    README.md

Usage:
    python scripts/upload_to_hf.py                       # public, default org
    python scripts/upload_to_hf.py --private              # private datasets
    python scripts/upload_to_hf.py --org AIcell           # explicit org
    python scripts/upload_to_hf.py --dry-run              # do not upload
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

import yaml


def _to_str(v) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    if isinstance(v, list):
        return "\n".join(str(x) for x in v)
    if isinstance(v, dict):
        return json.dumps(v, default=str)
    return str(v)


def collect_tasks(root: Path) -> list[tuple[Path, dict]]:
    """Return [(yaml_path, parsed_dict), ...] for every task in the dataset dir."""
    tasks = []
    for f in sorted(root.rglob("*.yaml")):
        c = yaml.safe_load(open(f))
        if isinstance(c, dict):
            tasks.append((f, c))
    return tasks


def build_metadata_row(c: dict) -> dict:
    """Flat row for metadata.jsonl (one per task)."""
    return {
        "task_id": _to_str(c.get("task_id", "")),
        "task_name": _to_str(c.get("task_name", "")),
        "claw_eval_id": _to_str(c.get("claw_eval_id", "")),
        "category": _to_str(c.get("category", "")),
        "difficulty": _to_str(c.get("difficulty", "")),
        "prompt": _to_str(c.get("prompt", "")),
        "n_tools": len(c.get("tools", [])),
        "n_scoring_components": len(c.get("scoring_components", [])),
        "n_safety_checks": len(c.get("safety_checks", [])),
        "services": sorted({t.get("service", "") for t in c.get("tools", []) if t.get("service")}),
        "yaml_path": "",  # filled per dataset
    }


README_TEMPLATE = """---
license: apache-2.0
task_categories:
  - other
tags:
  - agent-evaluation
  - tool-use
  - benchmark
  - claw-eval
size_categories:
  - {size_category}
---

# {dataset_name}

{description}

This is an auto-generated agent evaluation dataset paired with
[Claw-Eval](https://github.com/qwibitai/claw-eval). Each task tests an AI
agent's ability to use tools to complete real-world workflows across services
like email, calendar, todo, contacts, helpdesk, knowledge base, and more.

## Statistics

- **Tasks:** {n_tasks}
- **Unique scenarios:** {n_unique} (each `claw_eval_id` is one Claw-Eval scenario)
- **Variants per scenario:** {variants_per}
- **Categories:** {n_categories}
- **Services:** {n_services}

## Layout

```
tasks/
  <category>/
    <task_id>.yaml      # raw task definition (used directly by ClawEnvKit)
metadata.jsonl          # flat index, one row per task
```

## Direct evaluation (recommended)

Use [ClawEnvKit](https://github.com/xirui-li/ClawEnvKit) to run agents
against the raw YAML files:

```bash
# Download
huggingface-cli download {repo_id} --repo-type dataset --local-dir ./auto_claweval

# Evaluate any of 8 supported agent frameworks
clawenvkit eval --dataset ./auto_claweval/tasks --agent claudecode --model anthropic/claude-sonnet-4
clawenvkit eval --dataset ./auto_claweval/tasks --agent openclaw --model anthropic/claude-haiku-4-5-20251001
clawenvkit eval --dataset ./auto_claweval/tasks --agent agent-loop --model openai/gpt-4o
```

ClawEnvKit provides:

- **Mock services** that load fixtures and capture audit logs
- **GradingEngine** with 15 deterministic check types + LLM judge
- **8 agent framework integrations** (OpenClaw, Claude Code, NanoClaw,
  PicoClaw, ZeroClaw, CoPaw, NemoClaw, Hermes) plus a bare function-calling baseline

## Inspect via the datasets library

```python
from datasets import load_dataset
ds = load_dataset("{repo_id}", split="train")
print(ds[0]["prompt"])
print(ds[0]["task_id"], ds[0]["category"], ds[0]["services"])
```

For full task definitions (tools, fixtures, scoring rubrics) read the YAML files:

```python
import yaml
from huggingface_hub import hf_hub_download

path = hf_hub_download(
    repo_id="{repo_id}", repo_type="dataset",
    filename="tasks/todo/todo-001.yaml",
)
task = yaml.safe_load(open(path))
print(task["prompt"])
print(task["tools"])
print(task["scoring_components"])
```

## Task schema (yaml)

| Field | Type | Description |
|---|---|---|
| `task_id` | string | Unique identifier (e.g. `todo-001`) |
| `task_name` | string | Short human-readable name |
| `claw_eval_id` | string | The Claw-Eval scenario this variant maps to |
| `category` | string | Productivity / communication / etc. |
| `difficulty` | string | easy / medium / hard |
| `prompt` | string | Natural language task description for the agent |
| `tools` | list | Available tools (name / endpoint / method / service / description) |
| `fixtures` | dict | Mock data loaded into services before the task runs |
| `scoring_components` | list | Scoring checks with weights (15 deterministic types + llm_judge) |
| `safety_checks` | list | Safety constraints (`tool_not_called`, `keywords_not_in_output`) |
| `reference_solution` | string/list | Step-by-step expected workflow |

## Citation

```bibtex
@misc{{clawenvkit2026,
  title={{ClawEnvKit: Auto-Generated Agent Evaluation Environments at Scale}},
  author={{Li, Xirui and others}},
  year={{2026}},
  url={{https://github.com/xirui-li/ClawEnvKit}}
}}
```
"""


def upload_dataset(
    api,
    repo_id: str,
    private: bool,
    tasks: list[tuple[Path, dict]],
    local_root: Path,
    readme_args: dict,
):
    """Upload one dataset (raw YAMLs + metadata.jsonl + README) to HF Hub."""
    from huggingface_hub import CommitOperationAdd

    api.create_repo(
        repo_id=repo_id, repo_type="dataset",
        private=private, exist_ok=True,
    )

    operations = []

    # 1. Raw YAML files under tasks/<category>/<task_id>.yaml
    metadata_rows = []
    for path, cfg in tasks:
        rel = path.relative_to(local_root)
        repo_path = f"tasks/{rel.as_posix()}"
        operations.append(CommitOperationAdd(
            path_in_repo=repo_path,
            path_or_fileobj=str(path),
        ))
        row = build_metadata_row(cfg)
        row["yaml_path"] = repo_path
        metadata_rows.append(row)

    # 2. metadata.jsonl
    metadata_lines = "\n".join(json.dumps(r, default=str) for r in metadata_rows) + "\n"
    operations.append(CommitOperationAdd(
        path_in_repo="metadata.jsonl",
        path_or_fileobj=metadata_lines.encode("utf-8"),
    ))

    # 3. README.md
    readme = README_TEMPLATE.format(repo_id=repo_id, **readme_args)
    operations.append(CommitOperationAdd(
        path_in_repo="README.md",
        path_or_fileobj=readme.encode("utf-8"),
    ))

    api.create_commit(
        repo_id=repo_id,
        repo_type="dataset",
        operations=operations,
        commit_message=f"Upload {len(tasks)} tasks + metadata + README",
    )
    print(f"  https://huggingface.co/datasets/{repo_id}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--org", default="", help="HF org/user (default: whoami)")
    parser.add_argument("--private", action="store_true", help="Make datasets private")
    parser.add_argument("--dry-run", action="store_true", help="List files but do not upload")
    args = parser.parse_args()

    full_root = Path("Auto-ClawEval")
    mini_root = Path("Auto-ClawEval-mini")
    full = collect_tasks(full_root)
    mini = collect_tasks(mini_root)

    print(f"Auto-ClawEval:      {len(full)} tasks")
    print(f"Auto-ClawEval-mini: {len(mini)} tasks")

    if not full or not mini:
        print("ERROR: one or both datasets empty", file=sys.stderr)
        sys.exit(1)

    # Stats
    full_unique = len({c.get("claw_eval_id", "") for _, c in full})
    mini_unique = len({c.get("claw_eval_id", "") for _, c in mini})
    full_cats = len({c.get("category", "") for _, c in full if c.get("category")})
    mini_cats = len({c.get("category", "") for _, c in mini if c.get("category")})

    full_svcs = set()
    for _, c in full:
        for t in c.get("tools", []):
            if t.get("service"):
                full_svcs.add(t["service"])

    if args.dry_run:
        print("\n--- DRY RUN ---")
        print(f"Auto-ClawEval:      would upload {len(full)} yaml files + metadata.jsonl + README.md")
        print(f"Auto-ClawEval-mini: would upload {len(mini)} yaml files + metadata.jsonl + README.md")
        print(f"\nSample yaml paths:")
        for path, _ in full[:3]:
            rel = path.relative_to(full_root)
            print(f"  tasks/{rel.as_posix()}")
        return

    from huggingface_hub import HfApi, whoami

    org = args.org or whoami()["name"]
    api = HfApi()

    print(f"\nUploading {org}/Auto-ClawEval ...")
    upload_dataset(
        api=api,
        repo_id=f"{org}/Auto-ClawEval",
        private=args.private,
        tasks=full,
        local_root=full_root,
        readme_args=dict(
            dataset_name="Auto-ClawEval",
            description="Full benchmark with 10 variants per Claw-Eval scenario for variance/consistency analysis.",
            n_tasks=len(full),
            n_unique=full_unique,
            variants_per=10,
            n_categories=full_cats,
            n_services=len(full_svcs),
            size_category="1K<n<10K",
        ),
    )

    print(f"\nUploading {org}/Auto-ClawEval-mini ...")
    upload_dataset(
        api=api,
        repo_id=f"{org}/Auto-ClawEval-mini",
        private=args.private,
        tasks=mini,
        local_root=mini_root,
        readme_args=dict(
            dataset_name="Auto-ClawEval-mini",
            description="Compact benchmark with 1 variant per Claw-Eval scenario, paired 1:1 with Claw-Eval (104 tasks).",
            n_tasks=len(mini),
            n_unique=mini_unique,
            variants_per=1,
            n_categories=mini_cats,
            n_services=len(full_svcs),
            size_category="n<1K",
        ),
    )

    print("\nDone.")


if __name__ == "__main__":
    main()
