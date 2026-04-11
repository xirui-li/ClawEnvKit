# CLI Reference

`clawenvkit` exposes one CLI for evaluation, generation, discovery, and compatibility checks.

## Overview

| Command | Purpose |
|---|---|
| `clawenvkit eval` | Run a single task through Docker |
| `clawenvkit eval-all` | Run all tasks, or all tasks for one service |
| `clawenvkit generate` | Generate task YAMLs from structured or natural-language input |
| `clawenvkit services` | List available services |
| `clawenvkit categories` | List cross-service categories |
| `clawenvkit service create` | Create a new mock service from a real SaaS API |
| `clawenvkit compat` | Run the compatibility gate |

## `clawenvkit eval`

Run one task by task ID or path:

```bash
clawenvkit eval todo-001
clawenvkit eval dataset/todo/todo-001.yaml
```

Options:

| Option | Description |
|---|---|
| `task` | Task ID such as `todo-001` or a direct YAML path |
| `--model` | Override the model name passed into the container |
| `--results` | Output directory for logs and grading artifacts |

Notes:

- Requires `CLAWENVKIT_IMAGE`
- Default results path is `~/claw-results`
- Passes provider keys such as `OPENROUTER_API_KEY`, `ANTHROPIC_API_KEY`, and `OPENAI_API_KEY` into Docker

## `clawenvkit eval-all`

Run many tasks in one pass:

```bash
clawenvkit eval-all
clawenvkit eval-all --service todo
```

Options:

| Option | Description |
|---|---|
| `--service` | Limit the run to one dataset subdirectory |
| `--model` | Override the model name |
| `--results` | Output directory for logs and grading artifacts |
| `--force` | Re-run tasks even if `reward.txt` already exists |

## `clawenvkit generate`

Generate task configs from either structured inputs or a natural-language request.

Structured examples:

```bash
clawenvkit generate --services todo --count 5
clawenvkit generate --services calendar,contacts,gmail --count 3
clawenvkit generate --category workflow --count 3
```

Natural-language example:

```bash
clawenvkit generate --request "Test meeting scheduling" --count 1
```

Options:

| Option | Description |
|---|---|
| `--request` | Natural-language request. The intent parser infers services and difficulty |
| `--services` | Comma-separated service list |
| `--service` | Legacy single-service alias |
| `--category` | Cross-service category shortcut |
| `--count` | Number of tasks to generate |
| `--difficulty` | Difficulty label, default `medium` |
| `--output` | Output directory for generated tasks |

Notes:

- Uses the shared LLM client, which detects `OPENROUTER_API_KEY`, `ANTHROPIC_API_KEY`, or `OPENAI_API_KEY`
- Generated tasks are validated before being written out

## `clawenvkit services`

List known services and endpoint counts:

```bash
clawenvkit services
```

## `clawenvkit categories`

List cross-service category shortcuts:

```bash
clawenvkit categories
```

## `clawenvkit service create`

Create a new mock service from a natural language description of a real SaaS API:

```bash
clawenvkit service create --request "Slack messaging and channels"
clawenvkit service create --request "Stripe payment processing" --yes  # skip confirmation
```

Options:

| Option | Description |
|---|---|
| `--request` | Natural language description of the SaaS API to mock |
| `--yes`, `-y` | Skip interactive confirmation prompt |

Flow:

1. LLM plans API structure (endpoints, data model, params)
2. Validates spec against standards (name format, endpoint count, path prefix, etc.)
3. Shows proposed structure for user review
4. Generates `mock_services/<name>/server.py`
5. Starts server and validates (OpenAPI, audit endpoint, endpoint responses)
6. Registers in `SERVICE_DEFINITIONS` (persisted via `mock_services/_registry/`)

The new service is immediately available for task generation:

```bash
clawenvkit generate --services slack --count 5
```

Also triggered automatically when `generate --request` detects unknown services:

```bash
clawenvkit generate --request "File GitHub issues from Jira tickets"
# → Detects github + jira missing → offers to create them
```

## `clawenvkit compat`

Run the compatibility gate:

```bash
clawenvkit compat
clawenvkit compat --format json
clawenvkit compat --check dataset --check runtime
```

Options:

| Option | Description |
|---|---|
| `--format human` | Human-readable report |
| `--format json` | JSON report for CI or tooling |
| `--check` | Limit the run to specific checks |

Exit behavior:

- exit code `0` when the report passes
- exit code `1` when it fails

## Common Environment Variables

| Variable | Purpose |
|---|---|
| `CLAWENVKIT_IMAGE` | Docker image used by `eval` and `eval-all` |
| `MODEL` | Model name passed into generation and evaluation |
| `OPENROUTER_API_KEY` | LLM provider key for generation and grading |
| `ANTHROPIC_API_KEY` | LLM provider key and sometimes agent runtime credential |
| `OPENAI_API_KEY` | LLM provider key |
