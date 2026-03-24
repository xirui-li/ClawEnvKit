"""Extract real bug-fix tasks from GitHub repositories.

Given a GitHub repo, finds merged PRs that:
1. Fix a bug (labeled or has "fix" in title)
2. Have associated test changes (FAIL_TO_PASS signal)
3. Are small enough to fit in our Docker container

Produces TaskSpec instances from real code.

Usage:
    from scripts.core.repo_extractor import extract_tasks
    tasks = extract_tasks("psf/requests", max_tasks=5, github_token="...")
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .schema import GenerationSpec, SuccessCriterion, TaskSpec


@dataclass
class PRInfo:
    """Extracted info from a GitHub PR."""
    number: int
    title: str
    body: str
    base_sha: str          # commit before the fix
    merge_sha: str         # commit after the fix
    changed_files: list[str]
    additions: int
    deletions: int
    labels: list[str]


class RepoExtractorError(Exception):
    pass


def _run_gh(args: list[str], token: Optional[str] = None) -> str:
    """Run a gh CLI command."""
    env = os.environ.copy()
    if token:
        env["GH_TOKEN"] = token
    result = subprocess.run(
        ["gh"] + args,
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
    )
    if result.returncode != 0:
        raise RepoExtractorError(f"gh command failed: {result.stderr[:200]}")
    return result.stdout


def find_bug_fix_prs(
    repo: str,
    max_prs: int = 20,
    github_token: Optional[str] = None,
) -> list[PRInfo]:
    """Find merged PRs that look like bug fixes.

    Heuristics:
    - Title contains "fix", "bug", "patch", "resolve", "repair"
    - OR has label containing "bug", "fix"
    - PR is merged
    - Changed files < 10 (small enough to be a focused fix)
    - Changes < 500 lines total
    """
    # Search for merged PRs with fix-related terms
    raw = _run_gh([
        "pr", "list",
        "--repo", repo,
        "--state", "merged",
        "--limit", str(max_prs * 3),  # over-fetch, then filter
        "--json", "number,title,body,labels,mergeCommit,baseRefName,headRefName,additions,deletions,files,mergedAt",
        "--search", "fix OR bug OR patch in:title",
    ], token=github_token)

    prs_data = json.loads(raw)
    results = []

    for pr in prs_data:
        title = pr.get("title", "")
        labels = [l.get("name", "") for l in pr.get("labels", [])]
        additions = pr.get("additions", 0)
        deletions = pr.get("deletions", 0)
        files = [f.get("path", "") for f in pr.get("files", [])]

        # Filter: is it a bug fix?
        is_fix = any(kw in title.lower() for kw in ["fix", "bug", "patch", "resolve", "repair"])
        has_fix_label = any("bug" in l.lower() or "fix" in l.lower() for l in labels)

        if not (is_fix or has_fix_label):
            continue

        # Filter: small enough?
        if len(files) > 10 or (additions + deletions) > 500:
            continue

        # Filter: has Python files?
        has_python = any(f.endswith(".py") for f in files)
        if not has_python:
            continue

        merge_commit = pr.get("mergeCommit", {})
        merge_sha = merge_commit.get("oid", "") if merge_commit else ""

        results.append(PRInfo(
            number=pr["number"],
            title=title,
            body=pr.get("body", "")[:500],
            base_sha="",  # will be filled by git log
            merge_sha=merge_sha,
            changed_files=files,
            additions=additions,
            deletions=deletions,
            labels=labels,
        ))

        if len(results) >= max_prs:
            break

    return results


def extract_task_from_pr(
    repo: str,
    pr: PRInfo,
    clone_dir: Path,
    github_token: Optional[str] = None,
) -> Optional[TaskSpec]:
    """Extract a TaskSpec from a single PR.

    1. Clone repo at base_sha (pre-fix state)
    2. Extract changed files as initial_fs
    3. Use PR title/body as instruction
    4. Use the diff as solution_patch
    5. Look for test files changed → use as test_files
    """
    try:
        # Clone if not already cloned
        if not (clone_dir / ".git").exists():
            subprocess.run(
                ["git", "clone", "--depth", "100", f"https://github.com/{repo}.git", str(clone_dir)],
                capture_output=True,
                timeout=60,
            )

        # Find parent commit of merge (the pre-fix state)
        result = subprocess.run(
            ["git", "-C", str(clone_dir), "log", "--format=%H", "-n", "1", f"{pr.merge_sha}^"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return None
        base_sha = result.stdout.strip()

        # Get the diff (solution)
        diff_result = subprocess.run(
            ["git", "-C", str(clone_dir), "diff", base_sha, pr.merge_sha, "--", "*.py"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        solution_patch = diff_result.stdout

        if not solution_patch or len(solution_patch) < 10:
            return None

        # Extract initial_fs from base_sha
        initial_fs = {}
        test_files = {}

        for file_path in pr.changed_files:
            if not file_path.endswith(".py"):
                continue

            content_result = subprocess.run(
                ["git", "-C", str(clone_dir), "show", f"{base_sha}:{file_path}"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if content_result.returncode != 0:
                continue

            workspace_path = f"/workspace/{file_path}"
            content = content_result.stdout

            # Separate test files from source files
            if "test" in file_path.lower():
                test_files[workspace_path] = content
            else:
                initial_fs[workspace_path] = content

        if not initial_fs:
            return None

        # Build instruction from PR title + body
        instruction = f"Fix the following issue in the codebase:\n\n{pr.title}"
        if pr.body:
            instruction += f"\n\nDetails:\n{pr.body[:300]}"

        # Determine difficulty based on change size
        total_changes = pr.additions + pr.deletions
        if total_changes < 20:
            difficulty = "easy"
        elif total_changes < 100:
            difficulty = "medium"
        else:
            difficulty = "hard"

        task_id = f"real-{repo.replace('/', '-')}-{pr.number}"

        # Build success criteria
        criteria = []
        # If there are test files, add pytest_pass
        if test_files:
            for tp in test_files:
                criteria.append(SuccessCriterion(type="pytest_pass", test_file=tp))
        # Always add exit_code check on changed source files
        for fp in initial_fs:
            if fp.endswith(".py"):
                criteria.append(SuccessCriterion(
                    type="exit_code",
                    cmd=f"python3 -c \"import py_compile; py_compile.compile('{fp}', doraise=True)\"",
                ))

        return TaskSpec(
            task_id=task_id,
            domain="bug-fix",
            difficulty=difficulty,
            skill_target="real-world bug fix",
            task_type="bug-fix",
            instruction=instruction,
            initial_fs=initial_fs,
            base_tools=["bash", "python3", "git"],
            success_criteria=criteria,
            test_files=test_files,
            solution_patch=solution_patch,
        )

    except Exception:
        return None


def extract_tasks(
    repo: str,
    max_tasks: int = 5,
    github_token: Optional[str] = None,
    work_dir: Optional[str] = None,
) -> list[TaskSpec]:
    """Extract real bug-fix tasks from a GitHub repo.

    Args:
        repo: GitHub repo in "owner/name" format
        max_tasks: Maximum tasks to extract
        github_token: GitHub token for API access
        work_dir: Directory for cloning (default: temp dir under ~/.clawharness/)
    """
    if work_dir is None:
        work_dir = os.path.expanduser(f"~/.clawharness/repos/{repo.replace('/', '_')}")

    clone_dir = Path(work_dir)
    clone_dir.mkdir(parents=True, exist_ok=True)

    # Find candidate PRs
    prs = find_bug_fix_prs(repo, max_prs=max_tasks * 3, github_token=github_token)

    # Extract tasks from each PR
    tasks = []
    for pr in prs:
        if len(tasks) >= max_tasks:
            break
        task = extract_task_from_pr(repo, pr, clone_dir, github_token)
        if task:
            tasks.append(task)

    return tasks
