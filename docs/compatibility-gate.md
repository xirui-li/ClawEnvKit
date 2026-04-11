# Compatibility Gate

Static checks that catch cross-layer breakages before they reach runtime.

## Quick Start

```bash
# Run all checks
clawenvkit compat

# JSON output (for CI)
clawenvkit compat --format json

# Run specific check category
clawenvkit compat --check dataset
clawenvkit compat --check runtime

# Direct module invocation
python -m clawenvkit.compatibility.checker
python -m clawenvkit.compatibility.checker --format json
python -m clawenvkit.compatibility.checker --check dataset
```

### Exit Codes

- `0`: no errors
- `1`: compatibility errors found

## What It Checks

This codebase has several layers that can drift independently:

- `dataset/*.yaml` — task definitions
- `clawenvkit/generate/task_generator.py` — generator service definitions
- `mock_services/*/server.py` — runtime API surfaces
- `docker/entrypoint*.sh` — entrypoints
- `pyproject.toml` — packaging metadata

A PR can update one layer and silently break another. The compatibility gate
catches those issues statically.

### Check Categories

| Category | What it validates |
|----------|-------------------|
| `dataset` | Task YAML integrity: tool services exist, endpoints exist, scoring actions match, fixture files present |
| `generator` | SERVICE_DEFINITIONS match actual mock services, endpoints, action names |
| `runtime` | Entrypoints reference existing files, Dockerfiles copy existing dirs |
| `packaging` | pyproject.toml package-data points to real files |

### Dataset Checks

For every task YAML:

- every `tools[].service` maps to an existing mock service
- every `tools[].endpoint` exists in that service's FastAPI route surface
- every `scoring_components[].check.service` references a service present in the task
- every `safety_checks[].tool_name` references a declared tool name
- every `files[].source` exists
- every fixture path that points into `/workspace/...` is backed by a declared `files[].target`

### Generator Checks

For every service in `SERVICE_DEFINITIONS`:

- a matching `mock_services/<service>/server.py` exists
- every generator endpoint exists in the real service
- every declared action has a valid runtime mapping strategy

### Runtime Checks

For each Dockerfile and entrypoint:

- the entrypoint file exists
- every referenced Python module or script exists
- every expected copied directory exists in the build context

### Packaging Checks

- `pyproject.toml` package-data matches real package-relative files
- files referenced by `clawenvkit.paths` are included in the package

## CLI Flags

```
clawenvkit compat [--format {human,json}] [--check CHECK ...]
```

| Flag | Description |
|------|-------------|
| `--format human` | Human-readable grouped output (default) |
| `--format json` | Machine-readable JSON report |
| `--check NAME` | Run only specific check(s). Repeatable. Options: `dataset`, `generator`, `runtime`, `packaging` |

## Output Format

### Human Output

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

### Error (blocks CI)

- missing task file assets
- missing endpoints or services
- task actions unscoreable under supported backends
- entrypoint references missing files

### Warning (informational)

- backend-specific behavior differences
- undocumented but functioning fallback behavior

## Architecture

```text
clawenvkit/compatibility/
├── __init__.py
├── checker.py              # main orchestration + CLI entrypoint
├── models.py               # Finding, CheckResult, CompatibilityReport
├── dataset_checks.py       # task YAML / file / tool checks
├── generator_checks.py     # SERVICE_DEFINITIONS / category checks
├── runtime_checks.py       # entrypoint / Dockerfile / dependency checks
├── packaging_checks.py     # pyproject / wheel-mode assumptions
└── report.py               # text + JSON output
```

## CI Integration

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
      - run: clawenvkit compat --format json
```
