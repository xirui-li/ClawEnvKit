# API Reference

## GradingEngine

The core evaluation engine. Deterministic scoring with 14 check types.

```python
from clawharness.evaluate.engine import GradingEngine

engine = GradingEngine()
```

### `engine.grade(config, audit_data, agent_output)`

Grade a single agent run.

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `config` | `dict` | Task config (parsed from task.yaml) |
| `audit_data` | `dict[str, list[dict]]` | Audit log keyed by service name |
| `agent_output` | `str` | Agent's text output |

**Returns:** `GradingResult` with fields:

| Field | Type | Description |
|-------|------|-------------|
| `final_score` | `float` | 0.0 - 1.0 |
| `completion` | `float` | Weighted sum of scoring components |
| `robustness` | `float` | Error recovery rate |
| `safety` | `int` | 0 or 1 (gate) |
| `safety_violations` | `list[str]` | Violated safety checks |
| `component_results` | `list[ComponentResult]` | Per-check breakdown |

**Example:**

```python
import yaml

config = yaml.safe_load(open("dataset/todo/todo-001.yaml"))
audit_data = {"todo": [
    {"action": "create_task", "params": {"title": "Fix bug", "priority": "high"}, "status": 200},
    {"action": "list_tasks", "params": {}, "status": 200},
]}
agent_output = "Created task 'Fix bug' with high priority. Here are all tasks..."

result = engine.grade(config, audit_data, agent_output)
print(result.final_score)  # 0.92
```

### `engine.grade_pass3(config, audit_list, output_list)`

Grade with Pass^3: all 3 trials must pass the threshold.

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `config` | `dict` | Task config |
| `audit_list` | `list[dict]` | 3 audit logs |
| `output_list` | `list[str]` | 3 agent outputs |

---

## Task Generator

```python
from clawharness.generate.task_generator import generate_task_config, validate_task_config
```

### `generate_task_config(service, difficulty, api_key)`

Generate a task.yaml config via LLM.

### `validate_task_config(config)`

Validate a generated config:

- Check types are valid (from 14 types)
- Weights sum to 1.0
- Actions exist in service
- LLM judge weight <= 15%

---

## Agent Registry

```python
from clawharness.agents import list_agents, get_agent
```

### `list_agents()`

Returns list of registered agent names.

### `get_agent(name)`

Returns an `AgentAdapter` instance.

### `AgentAdapter` interface

```python
class AgentAdapter(ABC):
    def name(self) -> str: ...
    def capabilities(self) -> AgentCapabilities: ...
    def setup(self, workspace: str, model: str, api_key: str) -> None: ...
    def run(self, prompt: str, tools: list[dict], timeout: int = 120) -> AgentResult: ...
    def cleanup(self) -> None: ...
```

---

## CLI

```bash
clawharness eval <task-id>              # Run single evaluation
clawharness eval-all [--service X]      # Run all tasks
clawharness generate --service X --count N  # Generate tasks
clawharness services                    # List services
```
