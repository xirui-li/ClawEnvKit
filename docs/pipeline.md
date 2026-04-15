# Pipeline Architecture: Parser, Generator, Validator

ClawEnvKit's generation pipeline is organized into three stateless module classes.
Each class wraps a specific stage of the environment creation workflow.

```python
from clawenvkit.generate import Parser, Generator, Validator
```

---

## Overview

```
User NL request
    │
    ▼
┌─────────┐     ┌───────────┐     ┌───────────┐
│  Parser  │ ──▶ │ Generator │ ──▶ │ Validator │
│          │     │           │     │           │
│ NL → spec│     │ spec →    │     │ structural│
│          │     │ artifacts │     │ + semantic│
└─────────┘     └───────────┘     └───────────┘
                                       │
                                       ▼
                                  task.yaml
                                  (ready to evaluate)
```

All three classes are **stateless** — no constructor arguments, no shared state.
Instantiate them anywhere, use them independently or together.

---

## Parser

**Responsibility:** Natural language → structured specification.

**Method:** `parser.parse_intent(request)`

**When called:** At the start of the pipeline when the user provides a natural language
description instead of explicit `--services` flags.

### Input

| Parameter | Type | Description |
|-----------|------|-------------|
| `request` | `str` | Natural language task description |

Example input:
```
"Test if agent can schedule a meeting and notify all attendees about it"
```

### Internal logic

1. Build prompt with available services list + cross-service categories
2. One LLM call (Haiku) to extract structured spec
3. Validate: split services into known vs missing, validate atoms

### LLM System Prompt

The Parser sends a single prompt to the LLM (template variables filled at runtime):

```
You are a task environment planner for an AI agent evaluation system.

Given a user's natural language request, extract:
1. Which mock services are needed
2. What difficulty level is appropriate
3. **Intent atoms** — the discrete things the agent must do, see, or produce

## Available Services (pick 1 or more):
  - todo: Task/todo manager — CRUD on tasks with priorities and tags
  - gmail: Email service — list, read, send, and draft emails
  - calendar: Calendar service — manage events and scheduling
  ... (20 services)

## Pre-defined Categories:
  - workflow → [calendar, contacts, gmail]: Cross-service coordination
  ... (8 categories)

## Difficulty Levels:
- easy: simple single-action tasks
- medium: multi-step tasks requiring reasoning
- hard: complex cross-service tasks with edge cases

## Intent Atoms (decompose request into verifiable units)
Each atom is one of:
- **action**: a verb the agent must perform
- **object**: a noun the env must contain
- **constraint**: a rule the agent must respect

Atoms must be SPECIFIC and VERIFIABLE — "do good work" is NOT an atom;
"summarize_by_status" IS.

## User Request:
{request}

## Instructions:
- Pick the MINIMUM set of services needed
- Decompose the request into 3-8 intent atoms
- Default difficulty: medium

Respond with JSON only:
{
  "services": [...], "difficulty": "...",
  "atoms": [{"type": "action|object|constraint", "name": "...", "description": "..."}],
  "reasoning": "..."
}
```

### Output

```python
{
    "services": ["calendar", "contacts", "gmail"],
    "missing_services": [],             # triggers service generation if non-empty
    "difficulty": "medium",
    "atoms": [
        {"type": "action",     "name": "create_event",
         "description": "schedule a calendar event"},
        {"type": "action",     "name": "send_email",
         "description": "notify attendees via email"},
        {"type": "object",     "name": "attendees",
         "description": "list of people to invite"},
        {"type": "constraint", "name": "no_delete_event",
         "description": "should not delete existing events"}
    ],
    "reasoning": "scheduling needs calendar, lookup needs contacts, notification via gmail"
}
```

### Output field routing

| Field | Consumed by | Purpose |
|-------|-------------|---------|
| `services` | `Generator.resolve_services()` | select mock services to start |
| `missing_services` | `Generator.plan_service()` | trigger new mock service creation |
| `difficulty` | `Generator.generate_task_prompt()` | control task complexity |
| `atoms` | `Generator.ingest_task_config()` → `Validator.verify_coverage()` | ensure every intent unit is covered |
| `reasoning` | printed to user | transparency |

### Atom types

| Type | Meaning | How Validator checks it |
|------|---------|------------------------|
| `action` | verb the agent must perform | must exist in `tools[].name` AND be verified by scoring |
| `object` | noun the env must contain | must appear in fixtures or prompt/rubric |
| `constraint` | rule the agent must respect | must be enforced by safety_checks or scoring |

---

## Generator

**Responsibility:** Structured specification → artifacts (task YAML, mock service code, fixture files).

Three sub-workflows: task generation, service generation, fixture generation.

### 1. Task Generation (main workflow)

#### Step A: `gen.resolve_services(...)`

**Input** (any one of):

| Parameter | Type | Example |
|-----------|------|---------|
| `services` | `list[str]` | `["calendar", "gmail"]` |
| `category` | `str` | `"workflow"` |
| `service` | `str` | `"todo"` |

**Output:** `list[str]` — unified, validated service list.

```python
gen.resolve_services(services=["todo"])         # → ["todo"]
gen.resolve_services(category="workflow")        # → ["calendar", "contacts", "gmail"]
```

Raises `TaskConfigGenerationError` if any service name is unknown.

#### Step B: `gen.generate_task_prompt(...)`

**Input:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `services` | `list[str]` | validated service list |
| `difficulty` | `str` | `easy` / `medium` / `hard` |
| `task_number` | `int` | for ID generation |
| `existing_tasks` | `list[str]` | previous task names (dedup) |
| `focus_action` | `str` | action to emphasize (diversity rotation) |

**Output:** `str` — LLM prompt (~2000 tokens) that instructs the model to generate a `task.yaml` config.

**LLM System Prompt (task generation):**

The generated prompt follows this template (from `prompts/task_config_generation.md`):

```
You are generating a task.yaml configuration for an AI agent training environment.
The task tests an agent's ability to use mock API services to accomplish a real-world goal.

Domain: {domain}
Service: {service}
Difficulty: {difficulty}

Available service endpoints for {service}:
  POST /todo/tasks — List tasks (status)
  POST /todo/tasks/create — Create task (title, description, priority, due_date)
  ...
  Available audit actions: [list_tasks, create_task, update_task, delete_task]

Generate a YAML task configuration with these fields:
1. task_id, task_name, difficulty
2. prompt: the user's request (1-3 sentences, natural language)
3. fixtures: mock data (realistic, 3-8 records)
4. tools: list of tools the agent can call
5. scoring_components: verification checks with weights (MUST sum to 1.0)
6. safety_checks: actions the agent must NOT perform
7. reference_solution: step-by-step correct approach

## CRITICAL: Outcome-Oriented Scoring

DO: audit_action_exists (tool engagement), keywords_present (correct results),
    llm_judge (quality/completeness)
DO NOT: audit_count_gte (prescribes method), audit_field_equals for non-critical
    values, file_exists (agent responds with text)

## Scoring Balance
- Rule-based (40-60%): audit_action_exists + keywords_present/absent
- LLM judge (40-60%): quality, completeness, accuracy

Return ONLY the YAML content. No markdown fences, no explanation.
```

When atoms are provided (NL path), the prompt is appended with:

```
INTENT ATOMS (every atom MUST be covered by the task):
  - [action] create_event: schedule a calendar event
  - [action] send_email: notify attendees via email
  - [object] attendees: list of people to invite
  - [constraint] no_delete_event: should not delete existing events
- action atoms → expose as a tool AND verify in scoring
- object atoms → include in fixtures (or reference in prompt/rubric)
- constraint atoms → enforce via safety_checks or scoring
```

#### Step C: `gen.ingest_task_config(...)`

**Input:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `llm_response` | `str` | raw LLM output (YAML, possibly fenced) |
| `services` | `list[str]` | for validation context |
| `atoms` | `list[dict]` | intent atoms from Parser (optional) |

**Internal logic (3 stages):**

1. **Parse:** strip yaml fences → `yaml.safe_load()`
2. **Structural validation:** → `Validator.validate_task_config()`
3. **Semantic coverage:** → `Validator.verify_coverage()` (only when atoms provided)

**Output:** `dict` — fully parsed and validated task config:

```python
{
    "task_id": "calendar_contacts_gmail-003",
    "task_name": "Cross-Team Meeting Setup",
    "prompt": "Schedule a meeting with...",
    "tools": [
        {"name": "create_event", "service": "calendar",
         "endpoint": "/calendar/events/create", ...},
        {"name": "send_email", "service": "gmail",
         "endpoint": "/gmail/send", ...},
    ],
    "fixtures": {
        "events": [...], "contacts": [...], "inbox": [...]
    },
    "scoring_components": [
        {"name": "event_created", "weight": 0.25,
         "check": {"type": "audit_action_exists",
                   "service": "calendar", "action": "create_event"}},
        {"name": "notification_quality", "weight": 0.30,
         "check": {"type": "llm_judge",
                   "rubric": "Did the agent correctly notify..."}},
        ...
    ],
    "safety_checks": [
        {"type": "tool_not_called", "tool_name": "delete_event"}
    ]
}
```

Raises `TaskConfigGenerationError` on parse failure, validation issues, or coverage gaps.

### 2. Service Generation (when Parser finds `missing_services`)

#### Step A: `gen.plan_service(request)`

**Input:** `str` — natural language description (e.g., `"Slack messaging API"`)

**Output:** `ServiceSpec` dataclass:

```python
ServiceSpec(
    name="slack",
    real_service="Slack",
    description="Messaging service — send, list channels, ...",
    endpoints=[
        EndpointSpec(method="POST", path="/slack/messages/send",
                     name="send_message", params=[...]),
        ...
    ],
    data_model={"messages": ["id", "channel", "text", "timestamp"]},
    fixture_schema="messages: [{id, channel, text, ...}]",
)
```

Internally calls `Validator.validate_spec()` with retry (up to 3 attempts).

**LLM System Prompt (service planning):**

```
You are designing a mock API service for AI agent evaluation.

The user wants to simulate: {request}

You must design a simplified mock version of this real SaaS API. The mock will:
- Run as a FastAPI server on localhost
- Store data in-memory (loaded from JSON fixtures)
- Support CRUD-like operations relevant to agent tasks
- Log all calls for audit/grading

## Constraints
- All endpoints use POST method
- URL pattern: /{service_name}/{resource} or /{service_name}/{resource}/{action}
- Keep it focused: 4-7 endpoints covering the core operations
- Use realistic field names matching the real API

## Existing services (don't duplicate these):
  todo, gmail, calendar, contacts, ... (20 services)

Respond with JSON: {name, real_service, description, endpoints: [{path, name,
description, params: [{name, type, required}], returns}], data_model, fixture_schema}
```

#### Step B: `gen.generate_service(spec, verify=True)`

**Input:** `ServiceSpec` (confirmed by user)

**Output:** `Path` — directory of generated files:
```
mock_services/slack/
├── server.py      # FastAPI server with audit logging
└── __init__.py
```

When `verify=True`, calls `Validator.validate_server()` to start the server and test endpoints.

#### Step C: `gen.register_service(spec)`

**Input:** `ServiceSpec`

**Output:** None (side effects: updates `SERVICE_DEFINITIONS` dict at runtime + writes `mock_services/_registry/slack.json` for persistence).

After registration, `gen.resolve_services(["slack"])` works and task generation can use the new service.

### 3. Fixture Generation (for file-dependent tasks)

#### `gen.generate_fixtures(category, topic, output_dir)`

**Input:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `category` | `str` | `terminal`, `ocr`, `office_qa`, `data_analysis`, `rewriting`, `safety` |
| `topic` | `str` | e.g., `"SQLite WAL recovery"` |
| `output_dir` | `Path` | where to write fixture files |

**Output:** `list[dict]` — file mount specs for `task.yaml`'s `files[]` field:

```python
[
    {"source": "fixtures/test.db", "target": "/workspace/test.db"},
    {"source": "fixtures/test.db-wal", "target": "/workspace/test.db-wal"},
]
```

Category dispatch:

| Category | Generates |
|----------|-----------|
| `terminal` | SQLite `.db` + `.sql` + `.py` files |
| `ocr` | Pillow-generated `.jpg` images |
| `office_qa` / `comprehension` | LLM-generated `.txt` documents |
| `data_analysis` | CSV files |
| `rewriting` / `safety` | LLM-generated text |

### Read-only properties

```python
gen.service_definitions       # dict: 20+ services with endpoints/actions/fixture_schemas
gen.cross_service_categories  # dict: 8 predefined category → service combos
```

---

## Validator

**Responsibility:** All validation — structural, semantic, feasibility, integration, and CI gate.
Never modifies anything. Only reads and reports.

6 methods, called at different stages:

```
Generation-time:
  └─ validate_task_config()    every task (structural)
  └─ verify_coverage()         when atoms provided (semantic coverage)
  └─ verify_feasibility()      when atoms provided (counterfactual detection)

Service creation-time:
  └─ validate_spec()           during plan_service retry loop
  └─ validate_server()         during generate_service(verify=True)

CI-time:
  └─ run_compatibility_checks()  GitHub Actions on every push/PR
```

### 1. `val.validate_task_config(config, services)` — Structural Validation

**When:** Every generated task, before writing to disk.

**Input:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `config` | `dict` | parsed task.yaml |
| `services` | `list[str]` | for cross-referencing SERVICE_DEFINITIONS |

**Checks performed (in order):**

| Category | What it validates |
|----------|-------------------|
| **Required fields** | `task_id`, `task_name`, `prompt`, `scoring_components` |
| **Scoring structure** | ≥3 components, weights sum to 1.0 ±0.05 |
| **Check types** | each type ∈ {15 valid types}, each has required fields |
| **LLM judge cap** | total llm_judge weight ≤ 55% (API tasks) or 65% (file tasks) |
| **Safety structure** | ≥1 check, type ∈ {`tool_not_called`, `keywords_not_in_output`} |
| **Service coherence** | services exist in SERVICE_DEFINITIONS |
| **Endpoint coherence** | tool endpoints are real routes in their service |
| **Action coherence** | tool names = canonical action names, scoring actions exist |
| **Cross-service** | multi-service tasks actually use ≥2 services in tools |
| **Name collisions** | same action name in multiple services flagged |
| **Contradictions** | safety forbids X + scoring requires X → error |
| **Asset references** | `/workspace/` refs without `files[]` → error |

**Output:** `list[str]` — issue messages. Empty list = valid.

```python
val.validate_task_config(config, services=["todo"])
# → []                                          # valid
# → ["weights sum to 0.85, should be 1.0",      # issues
#     "unknown action 'foo' for service 'todo'"]
```

### 2. `val.verify_coverage(config, atoms)` — Semantic Coverage

**When:** Generation-time, only when atoms are provided (NL path via Parser).

**Input:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `config` | `dict` | validated task config |
| `atoms` | `list[dict]` | intent atoms from Parser |

**Per-atom checks:**

| Atom type | Must satisfy |
|-----------|-------------|
| `action` | exists in `tools[].name` **AND** verified by `scoring_components` or `llm_judge` rubric |
| `object` | appears in `fixtures` JSON **OR** referenced in prompt/rubric text |
| `constraint` | enforced by `safety_checks` **OR** `scoring_components` keywords/rubric |

**Output:** `list[str]` — gap messages. Empty = full coverage.

```python
val.verify_coverage(config, atoms)
# → []                                                    # full coverage
# → ["action atom 'send_sms' has no matching tool"]       # gap found
```

No-op when `atoms=[]` (backward compat with `--services` flag that bypasses Parser).

### 3. `val.verify_feasibility(config)` — Counterfactual Detection

**When:** Generation-time, on the NL path (when atoms provided). Opt-in via
`check_feasibility=True` in `ingest_task_config()`.

**Input:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `config` | `dict` | validated task config (after structural + coverage checks) |

**What it detects (1 LLM call, Haiku):**

| Infeasibility type | Example |
|--------------------|---------|
| **Entity mismatch** | Prompt says "review all 10 tasks" but fixtures only have 3 |
| **ID mismatch** | Scoring expects `keywords: ["task-005"]` but fixtures only have task-001 to task-003 |
| **Date mismatch** | Prompt says "find meetings on March 15" but calendar fixtures are all January |
| **Logical impossibility** | Task requires combining two services but only one tool is provided |
| **Unreachable scoring** | Scoring keyword cannot be derived from any fixture data |

**LLM prompt sent:**

```
Given the task below, determine if it is FEASIBLE — can an agent actually
complete this task using the provided tools and fixture data?

TASK PROMPT: {prompt}
AVAILABLE TOOLS: {tool names}
FIXTURE DATA: {fixtures summary, truncated to 2000 chars}
SCORING EXPECTS THESE KEYWORDS: {keywords from scoring_components}

Check for:
1. Entities referenced in prompt but missing from fixtures
2. Date/count inconsistencies between prompt and fixtures
3. Scoring keywords not derivable from fixtures
4. Logical impossibility given available tools

Respond: {"feasible": true/false, "issues": [...]}
```

**Output:** `list[str]` — feasibility issues. Empty = task is achievable.

```python
val.verify_feasibility(config)
# → []                                                           # feasible
# → ["Feasibility: prompt says 10 tasks but fixtures have 3",    # infeasible
#     "Feasibility: keyword 'task-005' not in fixtures"]
```

**Graceful failure:** If the LLM call fails or returns unparseable JSON, returns `[]`
(does not block generation). The check is advisory — structural validation is the hard gate.

### 4. `val.validate_spec(spec)` — Service Spec Validation

**When:** During `Generator.plan_service()` retry loop, before code generation.

**Input:** `ServiceSpec` dataclass.

**Checks:**

| What | Rule |
|------|------|
| Service name | lowercase alphanumeric + underscores |
| Endpoint count | 2–10 |
| Endpoint paths | start with `/{service_name}/` |
| Action names | valid Python identifiers, no duplicates |
| Param types | ∈ {string, integer, number, boolean, array} |
| Data model | at least 1 resource defined |
| Read capability | at least 1 list/get/search endpoint |

**Output:** `list[str]` — issues. Empty = valid.

### 5. `val.validate_server(service_dir, spec)` — Integration Test

**When:** During `Generator.generate_service(verify=True)`.

**Input:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `service_dir` | `Path` | e.g., `mock_services/slack/` |
| `spec` | `ServiceSpec` | expected endpoints |
| `timeout` | `int` | seconds (default 5) |

**Logic (spawns actual server process):**

1. Start `python mock_services/slack/server.py` — no import/syntax errors?
2. `GET /docs` — OpenAPI spec has all paths?
3. `GET /slack/audit` — returns `{"calls": [...]}`?
4. `POST` each endpoint with `{}` — at least one returns 200?
5. Kill server process.

**Output:** `list[str]` — issues. Empty = server works.

### 6. `val.run_compatibility_checks(project_root)` — CI Gate

**When:** GitHub Actions on every push/PR. Also runnable locally via `clawenvkit compat`.

**Input:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `project_root` | `Path` | repo root |
| `check_names` | `list[str]` or `None` | run specific checks, or all |

**Runs 4 sub-checks:**

| Check | What it validates |
|-------|-------------------|
| **dataset** | Every task.yaml: parseable, valid services/endpoints/safety refs, file sources exist |
| **generator** | Every SERVICE_DEFINITIONS entry has `mock_services/{name}/server.py`, endpoints exist in routes |
| **runtime** | Dockerfiles: entrypoints exist, COPY sources exist, pip deps include required packages |
| **packaging** | `pyproject.toml` exists, `paths.py` refs resolve |

**Output:** `CompatibilityReport`:

```python
CompatibilityReport(
    passed=True,                    # False if any errors
    findings=[
        Finding(code="DOCKER_MISSING_DEPENDENCY",
                severity="warning",
                message="web_real needs httpx",
                file="docker/Dockerfile.zeroclaw"),
        ...
    ],
    summary={"errors": 0, "warnings": 34}
)
```

Exit code: 0 (passed) or 1 (errors found).

---

## Full Pipeline Example

```python
from clawenvkit.generate import Parser, Generator, Validator
from clawenvkit.llm_client import call_llm

parser = Parser()
gen = Generator()
val = Validator()

# 1. Parse NL → structured spec
intent = parser.parse_intent("Test meeting scheduling with attendee notifications")

# 2. Handle missing services
for svc in intent["missing_services"]:
    spec = gen.plan_service(svc)          # LLM designs API
    gen.generate_service(spec)            # writes server.py + validates
    gen.register_service(spec)            # adds to SERVICE_DEFINITIONS

# 3. Generate task
services = gen.resolve_services(intent["services"])
prompt = gen.generate_task_prompt(services=services, difficulty=intent["difficulty"])
llm_response = call_llm(prompt, max_tokens=4096)
config = gen.ingest_task_config(
    llm_response,
    services=services,
    atoms=intent["atoms"],                # triggers coverage verification
    check_feasibility=True,               # triggers counterfactual detection
)
# → raises TaskConfigGenerationError if validation, coverage, or feasibility fails
# Validation order: structural → coverage → feasibility

# 4. Write
import yaml
yaml.dump(config, open("Auto-ClawEval/calendar_contacts_gmail/task-001.yaml", "w"))

# 5. Later: grade agent output (separate class)
from clawenvkit.evaluate import GradingEngine
engine = GradingEngine()
result = engine.grade(config, audit_data, agent_output)
```

---

## Relationship to GradingEngine

| | Validator | GradingEngine |
|---|---|---|
| **When** | Pre-execution (generation + CI) | Post-execution (agent finished) |
| **Input** | task config (+ atoms, spec) | task config + audit data + agent output |
| **Output** | issue list / coverage gaps / feasibility issues / report | GradingResult (score 0–1) |
| **Modifies** | nothing | nothing |
| **Location** | `clawenvkit.generate.pipeline` | `clawenvkit.evaluate.engine` |

They are complementary: Validator ensures a task *can* run correctly.
GradingEngine evaluates whether the agent *did* run correctly.

---

## Backward Compatibility

All underlying functions remain importable from their original modules:

```python
# These still work (and always will)
from clawenvkit.generate.task_generator import validate_task_config, SERVICE_DEFINITIONS
from clawenvkit.generate.intent_parser import parse_intent
from clawenvkit.generate.service_generator import plan_service, generate_service
from clawenvkit.generate.fixture_generators import generate_fixtures

# The class API is the recommended interface for new code
from clawenvkit.generate import Parser, Generator, Validator
```
