# Getting Started

This guide gets you from a fresh clone to three useful outcomes:

1. run an existing evaluation
2. generate a new task
3. verify the repository with the compatibility gate

## Prerequisites

- Python 3.10+
- Docker or Colima
- A source checkout of this repository
- At least one provider key for generation or LLM-backed grading:
  `OPENROUTER_API_KEY`, `ANTHROPIC_API_KEY`, or `OPENAI_API_KEY`
- An agent image if you want to run `clawenvkit eval`

## Clone and Install

```bash
git clone https://github.com/xirui-li/ClawEnvKit.git
cd ClawEnvKit
```

Choose an install profile:

| Profile | Command | Use when |
|---|---|---|
| Core runtime | `pip install -e .` | You only need the package and CLI |
| Generation | `pip install -e ".[generate]"` | You want to generate tasks or fixtures |
| Optional service deps | `pip install -e ".[services]"` | You need live web or document-parsing services |
| Full local setup | `pip install -e ".[all]"` | You want docs, tests, generation, and optional services |

For most contributors and first-time users, `pip install -e ".[all]"` is the simplest choice.

## Set Provider Credentials

At least one provider key is needed for generation and `llm_judge` scoring:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

The shared LLM client can also use `OPENROUTER_API_KEY` or `OPENAI_API_KEY`. Some agent images may still require provider-specific credentials of their own.

## Get an Agent Image

`clawenvkit eval` runs an agent inside Docker, so you must set `CLAWENVKIT_IMAGE`.

The simplest path is to pull a published image from GHCR — no Docker build,
no base image setup:

```bash
docker pull ghcr.io/xirui-li/clawenvkit-claudecode:latest
export CLAWENVKIT_IMAGE=ghcr.io/xirui-li/clawenvkit-claudecode:latest
```

Eight harness images are published — see [`docs/agents/index.md`](agents/index.md)
for the full list. The only exception is IronClaw: its upstream has no LICENSE
file so we don't redistribute it; build it locally if you need it (and consult
the agents docs for the build steps).

To build images locally — e.g. you modified `mock_services/` or want to point
at a fork of an upstream agent — every Dockerfile accepts a `BASE_IMAGE`
build-arg you can override:

```bash
docker build -f docker/Dockerfile.claudecode -t clawenvkit:claudecode .
# or, with a custom base
docker build -f docker/Dockerfile.openclaw \
  --build-arg BASE_IMAGE=openclaw:my-fork \
  -t clawenvkit:openclaw .
```

## Run Your First Evaluation

```bash
clawenvkit eval todo-001
```

By default, results are written to `~/claw-results/<task-id>/`. The most important outputs are:

- `reward.txt` for the final score
- `grading.json` for component-by-component grading details
- agent and service logs collected by the entrypoint

To run all tasks for one service:

```bash
clawenvkit eval-all --service todo
```

## Generate Your First Task

Generate a single-service task:

```bash
clawenvkit generate --services todo --count 1 --output tasks
```

Generate from a natural-language request:

```bash
clawenvkit generate --request "Test meeting scheduling" --count 1 --output tasks
```

Useful discovery commands:

```bash
clawenvkit services
clawenvkit categories
```

## Run the Compatibility Gate

The compatibility gate checks for drift between datasets, services, generators, and Docker runtime assumptions:

```bash
clawenvkit compat
```

For machine-readable output:

```bash
clawenvkit compat --format json
```

## What to Read Next

- [Task Specification](task-spec.md) to understand the `task.yaml` contract
- [Scoring and Grading](scoring.md) to understand how runs are scored
- [Mock Services](services.md) to understand the available tool environments
- [Task Generation](generation.md) to understand the generation pipeline
- [CLI Reference](cli.md) for the full command surface
