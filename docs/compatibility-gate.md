# Merge Compatibility Gate Design

## Goal

Add an automatic pre-merge compatibility gate that catches the kinds of breakages this repo is currently vulnerable to:

- task YAMLs that no longer match runtime behavior
- mock services whose API surface drifts from generator definitions
- Docker entrypoints that reference missing files or incompatible paths
- tasks that reference missing fixture assets
- packaging / install paths that work in editable mode but break in wheel or container mode

The gate should fail fast in CI and give a contributor a short, actionable report.

## Why This Exists

This codebase has several layers that can drift independently:

- `dataset/*.yaml`
- `clawharness/generate/task_generator.py`
- `mock_services/*/server.py`
- `docker/entrypoint*.sh`
- Dockerfiles
- packaging metadata in `pyproject.toml`

A PR can easily update one layer and silently break another. Today many of those failures are only discovered manually, or only after trying to run a task end-to-end. The compatibility gate is meant to catch those issues before merge.

## Design Principles

1. Prefer static checks before expensive runtime checks.
2. Fail on deterministic incompatibilities, warn on heuristics.
3. Report by invariant, not by implementation detail.
4. Keep the first version local-only and dependency-light.
5. Make the output usable both by humans and CI bots.

## Non-Goals

- Full benchmark execution across all agents on every PR
- Replacing unit tests or end-to-end smoke tests
- Judging task quality or experiment validity
- Verifying third-party API credentials

## What The Gate Should Enforce

### 1. Dataset Surface Compatibility

For every task YAML:

- every `tools[].service` maps to an existing mock service
- every `tools[].endpoint` exists in that service's FastAPI route surface
- every `scoring_components[].check.service` references a service actually present in the task
- every `safety_checks[].tool_name` references a declared tool name
- every `files[].source` exists
- every fixture path that points into `/workspace/...` is backed by a declared `files[].target`

This catches broken tasks before runtime.

### 2. Generator vs Runtime Compatibility

For every service in `SERVICE_DEFINITIONS`:

- a matching `mock_services/<service>/server.py` exists
- every generator endpoint exists in the real service
- every declared action has a valid runtime mapping strategy
- every cross-service category only references known services

This prevents `clawharness generate` from creating tasks that cannot run.

### 3. Scoring vs Audit Compatibility

For every task:

- `scoring_components.check.action` must be compatible with current audit normalization
- if action names differ from tool names, the checker must explicitly verify that the entrypoint normalization logic can still produce the expected action
- tasks using `audit_field_*` checks must target fields present in the corresponding request body shape or task tool schema

This is one of the highest-value checks because many tasks can look valid while being unscoreable.

### 4. Fixture Extraction Compatibility

For each entrypoint that supports multi-service tasks:

- fixture resource keys used in dataset tasks must be mapped to the correct service
- ambiguous keys such as `articles` must be handled consistently
- service-specific fixture env vars must resolve to real files

This prevents backend-specific breakage where a task works under one agent image and fails under another.

### 5. Docker / Entrypoint Integrity

For each Dockerfile and referenced entrypoint:

- the entrypoint file exists
- every referenced Python module or script exists
- every expected copied directory actually exists in the image build context
- required Python dependencies for referenced services are installed in the image
- documented mount paths match runtime paths

This catches issues like entrypoints calling deleted files, or images missing `httpx` while shipping `web_real`.

### 6. Packaging Integrity

For package builds:

- files referenced by `clawharness.paths` are actually included in the package/wheel
- `package-data` rules point to real package-relative files
- installed-mode path assumptions are consistent with editable-mode and Docker-mode assumptions

This is especially important because the repo currently mixes repo-root assets with Python package code.

## Proposed Architecture

Create a new package:

```text
clawharness/compatibility/
├── __init__.py
├── checker.py              # main orchestration
├── models.py               # dataclasses for findings/results
├── dataset_checks.py       # task YAML / file / tool checks
├── generator_checks.py     # SERVICE_DEFINITIONS / category checks
├── runtime_checks.py       # entrypoint / Dockerfile / dependency checks
├── packaging_checks.py     # pyproject / wheel-mode assumptions
└── report.py               # text + JSON output
```

### Core Types

```python
Finding(
    code: str,              # e.g. TASK_MISSING_FILE
    severity: str,          # error | warning
    message: str,
    file: str | None,
    context: dict,
)

CheckResult(
    name: str,
    findings: list[Finding],
)

CompatibilityReport(
    passed: bool,
    findings: list[Finding],
    summary: dict,
)
```

## Checker Passes

### Pass A: Repository Inventory

Build an in-memory index of:

- dataset tasks
- mock service route tables
- generator service definitions
- Dockerfiles
- entrypoints
- docs-referenced runtime paths

This pass should be pure filesystem inspection and should run first.

### Pass B: Task Checks

Run per-task checks:

- task schema sanity
- tool service existence
- tool endpoint existence
- scoring service existence
- safety tool existence
- missing file sources
- broken workspace asset references

Output should be grouped by task path.

### Pass C: Runtime Mapping Checks

Interpret the action normalization logic from:

- `docker/entrypoint_auto.sh`
- `docker/entrypoint_claw.sh`
- `docker/entrypoint_openclaw.sh`
- `docker/entrypoint_claudecode.sh`

For each task action expectation:

- compute whether at least one backend can emit it
- optionally require that all supported backends emit it

Version 1 should at least enforce one invariant:

- default supported backends must not disagree on action naming for the current dataset

### Pass D: Asset Closure Checks

Validate:

- `files[].source` exists
- `files[].target` and fixture `file_path` / `image_path` references are coherent
- OCR/document tasks are not referencing invisible workspace files

This pass should fail hard because these are deterministic breakages.

### Pass E: Image / Entrypoint Checks

Statically parse each Dockerfile and entrypoint to verify:

- copied files exist
- executed scripts exist
- referenced Python modules exist
- service dependencies implied by services are installed

Examples:

- `web_real` requires `httpx` and `trafilatura`
- entrypoints referencing `agent_loop.py` should fail if the file is gone

### Pass F: Packaging Checks

Validate:

- `pyproject.toml` package-data matches real package-relative files
- any path returned by `clawharness.paths` exists under at least one supported install mode

Optional later extension:

- actually build a wheel in CI and inspect included files

## Command Interface

Add a CLI entrypoint:

```bash
clawharness compat
clawharness compat --format json
clawharness compat --check dataset
clawharness compat --check runtime
clawharness compat --changed-only
```

### Exit Codes

- `0`: no errors
- `1`: compatibility errors found
- `2`: checker internal failure

## Output Format

### Human Output

Default output should be compact and grouped:

```text
Compatibility: FAILED

[ERROR] TASK_MISSING_FILE
  dataset/ocr/ocr-004.yaml
  Missing file source: fixtures/images/bizcard_001.png

[ERROR] ACTION_RUNTIME_MISMATCH
  dataset/comprehension/comprehension-002.yaml
  scoring action=search_articles cannot be produced by entrypoint_claw.sh
```

### JSON Output

Machine-readable report for CI annotations:

```json
{
  "passed": false,
  "summary": {
    "errors": 12,
    "warnings": 3,
    "tasks_checked": 104
  },
  "findings": [...]
}
```

## Severity Policy

### Error

Must block merge:

- missing task file assets
- missing endpoints
- missing services
- task actions unscoreable under supported backends
- entrypoint references missing files
- packaging metadata points to nonexistent resources

### Warning

Does not block initial rollout:

- backend-specific behavior differences that do not affect the default path
- undocumented but still functioning fallback behavior
- dead docs references

## CI Integration

Add a lightweight workflow:

```yaml
name: compatibility
on:
  pull_request:
  push:
    branches: [main]
jobs:
  compat:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
      - run: pip install -e .
      - run: python -m clawharness.compatibility.checker
```

### Rollout Strategy

Phase 1:

- run on every PR
- warnings only in CI comment
- manual review of false positives

Phase 2:

- block on deterministic `error` findings
- keep heuristic findings as warnings

Phase 3:

- add optional changed-files mode for faster PR feedback
- add wheel-build validation

## Initial Rule Set For V1

The first merge-gate version should implement only the highest-signal checks:

1. Missing `files[].source`
2. Broken `/workspace/...` asset references
3. Missing service or endpoint for every task tool
4. `scoring action` not producible by runtime normalization
5. Entrypoint references missing script/module
6. Docker image missing required dependency for referenced service
7. Package-data points to nonexistent files

This covers the majority of the concrete bugs already observed in this repo.

## Open Questions

1. Should compatibility be defined against only the default backend, or against all supported backends?
2. Should generated-but-uncommitted services be supported as a first-class workflow, or should persisted registration be mandatory?
3. Do we want the checker to parse shell scripts semantically, or is targeted regex extraction sufficient for v1?

## Recommended Decision

For v1:

- gate on the default backend plus all backends documented as supported in `docs/`
- require persisted service registration for mergeable new services
- use targeted static parsing first, then add runtime smoke checks only where static analysis is too weak

## Deliverables

Implementation should be considered complete when the repo has:

- a `clawharness compat` command
- CI wiring for PRs
- JSON and human-readable reports
- blocking checks for deterministic breakages
- regression tests for at least the rule parsers and report generation

## Success Criteria

This design is successful if a future PR cannot merge when it:

- adds a task with missing assets
- changes a route without updating task definitions
- breaks action normalization for existing scoring rules
- ships an entrypoint that references deleted code
- relies on package resources that are not actually shipped
