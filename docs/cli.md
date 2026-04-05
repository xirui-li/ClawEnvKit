# CLI Reference

`clawharness` exposes one CLI for evaluation, generation, discovery, and compatibility checks.

## Overview

| Command | Purpose |
|---|---|
| `clawharness eval` | Run a single task through Docker |
| `clawharness eval-all` | Run all tasks, or all tasks for one service |
| `clawharness generate` | Generate task YAMLs from structured or natural-language input |
| `clawharness services` | List available services |
| `clawharness categories` | List cross-service categories |
| `clawharness compat` | Run the compatibility gate |

## `clawharness eval`

Run one task by task ID or path:

```bash
clawharness eval todo-001
clawharness eval dataset/todo/todo-001.yaml
```

Options:

| Option | Description |
|---|---|
| `task` | Task ID such as `todo-001` or a direct YAML path |
| `--model` | Override the model name passed into the container |
| `--results` | Output directory for logs and grading artifacts |

Notes:

- Requires `CLAW_HARNESS_IMAGE`
- Default results path is `~/claw-results`
- Passes provider keys such as `OPENROUTER_API_KEY`, `ANTHROPIC_API_KEY`, and `OPENAI_API_KEY` into Docker

## `clawharness eval-all`

Run many tasks in one pass:

```bash
clawharness eval-all
clawharness eval-all --service todo
```

Options:

| Option | Description |
|---|---|
| `--service` | Limit the run to one dataset subdirectory |
| `--model` | Override the model name |
| `--results` | Output directory for logs and grading artifacts |
| `--force` | Re-run tasks even if `reward.txt` already exists |

## `clawharness generate`

Generate task configs from either structured inputs or a natural-language request.

Structured examples:

```bash
clawharness generate --services todo --count 5
clawharness generate --services calendar,contacts,gmail --count 3
clawharness generate --category workflow --count 3
```

Natural-language example:

```bash
clawharness generate --request "Test meeting scheduling" --count 1
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

## `clawharness services`

List known services and endpoint counts:

```bash
clawharness services
```

## `clawharness categories`

List cross-service category shortcuts:

```bash
clawharness categories
```

## `clawharness compat`

Run the compatibility gate:

```bash
clawharness compat
clawharness compat --format json
clawharness compat --check dataset --check runtime
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
| `CLAW_HARNESS_IMAGE` | Docker image used by `eval` and `eval-all` |
| `MODEL` | Model name passed into generation and evaluation |
| `OPENROUTER_API_KEY` | LLM provider key for generation and grading |
| `ANTHROPIC_API_KEY` | LLM provider key and sometimes agent runtime credential |
| `OPENAI_API_KEY` | LLM provider key |
