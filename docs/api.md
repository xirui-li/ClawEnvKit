# API Reference

## GradingEngine

The core evaluation engine. Deterministic scoring with 15 check types + 2 safety check types.

```python
from clawenvkit.evaluate.engine import GradingEngine

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
| `component_results` | `list[CheckResult]` | Per-check breakdown |

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

### `engine.grade_pass3(trial_results, pass_threshold=0.5)`

Grade with Pass^3: all 3 trials must pass the threshold.

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `trial_results` | `list[GradingResult]` | 3 GradingResult from independent `grade()` calls |
| `pass_threshold` | `float` | Minimum final_score to count as "pass" (default 0.5) |

**Returns:** `Pass3Result` with fields:

| Field | Type | Description |
|-------|------|-------------|
| `passed` | `bool` | True if ALL 3 trials passed |
| `trial_scores` | `list[float]` | Individual trial scores |
| `mean_score` | `float` | Average final_score across trials |
| `min_score` | `float` | Worst trial score |
| `completion_mean` | `float` | Average completion across trials |
| `robustness_mean` | `float` | Average robustness across trials |
| `safety_all_passed` | `bool` | True if all trials passed safety |
| `efficiency_mean` | `EfficiencyMetrics` | Average efficiency (turns, tokens, time) |

**Example:**

```python
results = [engine.grade(config, audit, output) for audit, output in zip(audits, outputs)]
pass3 = engine.grade_pass3(results, pass_threshold=0.5)
print(pass3.passed, pass3.mean_score)
```

---

## Check Types

### Scoring (15 types)

| Type | What it checks | Key fields |
|------|---------------|------------|
| `audit_action_exists` | Agent called a specific API | service, action |
| `audit_field_equals` | API param has exact value | service, action, field, value |
| `audit_field_contains` | API param contains substring | service, action, field, contains |
| `audit_count_gte` | API called at least N times | service, action, count |
| `audit_count_equals` | API called exactly N times | service, action, count |
| `audit_sequence` | APIs called in correct order | service, actions |
| `keywords_present` | Output mentions key facts | keywords |
| `keywords_absent` | Output avoids forbidden terms | keywords |
| `pattern_match` | Output matches regex | pattern |
| `min_length` | Output has minimum length | min_length |
| `file_exists` | File was created | path |
| `file_hash_equals` | File has expected hash | path, hash |
| `exit_code` | Command returns expected code | cmd, expected_exit |
| `pytest_pass` | Pytest tests pass | test_file |
| `llm_judge` | LLM evaluates quality | rubric |

### Safety (2 types)

| Type | What it checks | Key fields |
|------|---------------|------------|
| `tool_not_called` | Agent did NOT call a tool | tool_name |
| `keywords_not_in_output` | Output does NOT contain keywords | keywords |

---

## Generation Pipeline

Three classes wrap the generation and validation pipeline:

```python
from clawenvkit.generate import Parser, Generator, Validator
```

### Parser

```python
parser = Parser()
intent = parser.parse_intent("Test if agent can schedule a meeting")
# → {"services": ["calendar", "contacts", "gmail"],
#    "missing_services": [],
#    "difficulty": "medium",
#    "atoms": [{"type": "action", "name": "schedule_meeting", ...}],
#    "reasoning": "..."}
```

### Generator

```python
gen = Generator()

# Resolve services from any input form
gen.resolve_services(services=["todo"])               # → ["todo"]
gen.resolve_services(category="workflow")              # → ["calendar", "contacts", "gmail"]

# Generate LLM prompt for task creation
prompt = gen.generate_task_prompt(services=["todo"], difficulty="medium")

# Parse + validate + verify coverage in one call
config = gen.ingest_task_config(llm_response, services=["todo"], atoms=intent["atoms"])

# Create new mock services
spec = gen.plan_service("Stripe payments API")
gen.generate_service(spec, verify=True)
gen.register_service(spec)

# Generate fixture files for file-dependent tasks
files = gen.generate_fixtures(category="terminal", topic="SQLite recovery", output_dir=path)

# Read-only access to service registry
gen.service_definitions["todo"]         # → {"description": ..., "endpoints": ..., "actions": ...}
gen.cross_service_categories["workflow"] # → {"services": ["calendar","contacts","gmail"], ...}
```

### Validator

```python
val = Validator()

# Structural validation (15 check types, weights, service/endpoint references, safety)
issues = val.validate_task_config(config, services=["todo"])

# Semantic coverage (every intent atom has a tool + scoring check)
gaps = val.verify_coverage(config, intent["atoms"])

# Service spec validation (before code generation)
issues = val.validate_spec(spec)

# Integration test (start server, hit endpoints)
issues = val.validate_server(service_dir, spec)

# CI compatibility gate
report = val.run_compatibility_checks(project_root)
```

**Structural checks** performed by `validate_task_config`:
- Check types valid (15 scoring + 2 safety types)
- Required fields per check type
- Weights sum to 1.0
- Services/actions/endpoints exist in SERVICE_DEFINITIONS
- No safety vs scoring contradictions
- /workspace references require files[] field
- Cross-service: tools reference 2+ services
- LLM judge total weight capped at 55%

> **Backward compatible:** All underlying functions remain importable from their original modules:
> ```python
> from clawenvkit.generate.task_generator import validate_task_config, SERVICE_DEFINITIONS
> ```

---

## LLM Client

```python
from clawenvkit.llm_client import detect_provider, call_llm

provider, api_key, base_url, model = detect_provider()
response_text = call_llm("Generate a task config...")
```

Auto-detects provider: `OPENROUTER_API_KEY` > `ANTHROPIC_API_KEY` > `OPENAI_API_KEY` > `config.json`.

---

## Agent Execution (Docker)

All agents run via Docker. Set `CLAWENVKIT_IMAGE` to choose agent:

```bash
export CLAWENVKIT_IMAGE=clawenvkit:openclaw  # or :nanoclaw, :claudecode

# Via CLI
clawenvkit eval todo-001

# Via Docker directly
docker run --rm -e ANTHROPIC_API_KEY=$KEY \
  -v ./task.yaml:/opt/clawenvkit/task.yaml:ro \
  clawenvkit:openclaw
```

> **Note:** `clawenvkit:base` has no built-in agent — it starts mock services and waits for an external agent.

---

## CLI

```bash
clawenvkit eval <task-id>                                  # Run single evaluation
clawenvkit eval-all [--service X]                          # Run all tasks
clawenvkit generate --services todo --count 5              # Generate tasks
clawenvkit generate --request "Test meeting scheduling"    # From natural language
clawenvkit services                                        # List available services
clawenvkit categories                                      # List cross-service categories
clawenvkit service create --request "Stripe payments"      # Create new mock service
clawenvkit compat                                          # Run compatibility checks
```
