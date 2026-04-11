# ClawEnvKit Docs

ClawEnvKit helps you generate and evaluate tool-using agent tasks with a shared `task.yaml` contract, mock services, deterministic grading, and Docker-based agent adapters.

## Start Here

- [Getting Started](getting-started.md) for installation, first evaluation, and first generation run
- [Task Specification](task-spec.md) for the `task.yaml` contract
- [CLI Reference](cli.md) for the command surface

## Choose a Workflow

- Evaluate an existing task:
  [Getting Started](getting-started.md) and [Scoring and Grading](scoring.md)
- Generate new tasks:
  [Task Generation](generation.md) and [Task Specification](task-spec.md)
- Add or inspect mock services:
  [Mock Services](services.md) and [Contributing: Adding Mock Services](contributing/services.md)
- Integrate a new agent runtime:
  [Harnesses Overview](agents/index.md) and [Contributing: Adding Harnesses](contributing/agents.md)
- Check repository drift before merging:
  [Compatibility Gate](compatibility-gate.md)

## Core Concepts

- `task.yaml` is the interface between generation, runtime, and grading
- `mock_services/` provides controlled tool environments with audit logging
- `GradingEngine` turns audit data and output text into weighted scores
- Docker entrypoints wire tasks, fixtures, services, and agent adapters together

## Reference

- [CLI Reference](cli.md)
- [Python API](api.md)
- [Backbone Models](models.md)
- [Mock Services](services.md)
- [Roadmap](roadmap.md)
- [Scoring and Grading](scoring.md)

## Deeper Reading

- [System Design](design.md)
- [Experiments](experiments.md)
- [File Tasks and Multimodal Support](file-task-support.md)
