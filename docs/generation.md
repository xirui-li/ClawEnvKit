# Task Generation

ClawHarnessing auto-generates evaluation tasks via LLM. The LLM produces YAML config (not test code), achieving 99% validity.

## How It Works

```
"Generate 10 email tasks"
        ↓
LLM receives:
  - Service definition (endpoints, actions, fixture schema)
  - Difficulty level (easy/medium/hard)
  - Generation prompt (14 check types, scoring rules)
        ↓
LLM generates task.yaml:
  - prompt (natural language task)
  - fixtures (mock data)
  - scoring_components (what to check)
  - safety_checks (forbidden actions)
  - tools (available API endpoints)
        ↓
Config Validator:
  - Check types valid?
  - Weights sum to 1.0?
  - Actions exist in service?
  - LLM judge weight <= 55%?
        ↓
Valid task.yaml ready for evaluation
```

## Generate Tasks

Unified interface — everything goes through a service list:

```bash
# Single-service tasks
clawharness generate --services gmail --count 10
clawharness generate --services todo --count 5 --difficulty hard

# Cross-service tasks (agent must use multiple APIs)
clawharness generate --services calendar,contacts,gmail --count 5
clawharness generate --services helpdesk,crm,inventory --count 3 --difficulty hard

# Category shortcut (auto-resolves to service list)
clawharness generate --category workflow --count 5       # → calendar,contacts,gmail
clawharness generate --category ops_dashboard --count 3  # → 6 services

# List available categories
clawharness categories

# Custom output directory
clawharness generate --services todo --count 3 --output /tmp/new-tasks
```

### Cross-Service Categories

| Category | Services | Example Task |
|----------|----------|-------------|
| communication | gmail, contacts | Find colleague's email, send follow-up |
| productivity | calendar, todo, notes | Review notes, create action items, schedule follow-up |
| operations | helpdesk, inventory, crm | Customer reports defect → ticket + inventory + CRM |
| workflow | calendar, contacts, gmail | Schedule meeting: check availability, find attendees, send invites |
| ops_dashboard | 6 services | Weekly ops review across all systems |
| procurement | 5 services | Evaluate vendors: inventory needs, pricing, reviews |
| safety | config, gmail | Audit API keys, notify without leaking secrets |
| knowledge | kb, rss | Research topic across KB and news feeds |

## Pre-generated Dataset

Tasks across 20 services (100% Claw-Eval coverage) (3 easy + 4 medium + 3 hard each):

```bash
ls dataset/
# calendar/  contacts/  crm/  finance/  gmail/  helpdesk/
# inventory/  kb/  notes/  rss/  scheduler/  todo/  config/
```

## Config vs Code Generation

This is the core design decision:

| Approach | What LLM generates | Validity | Scoring |
|----------|-------------------|----------|---------|
| **Code generation** (v0.1-v0.3) | Python pytest | ~30% | Binary pass/fail |
| **Config generation** (v2, current) | YAML scoring rules | **99%** | 0.0-1.0 continuous |

The GradingEngine is fixed, deterministic code (written once). The LLM only generates structured parameters — which check type to use, what field to match, what weight to assign. This is fundamentally more reliable than generating executable test code.

## Generate New Services

For domains not covered by the 19 existing services:

```python
from clawharness.generate.service_generator import generate_and_install

# LLM generates FastAPI server + fixtures + service definition
generate_and_install("spotify", "Music streaming — search, play, pause, playlists")
# NOTE: registers in current process only. To use with CLI, manually add
# the service definition to clawharness/generate/task_generator.py SERVICE_DEFINITIONS

# Review the generated server.py (ensure audit logging works)
# Then generate tasks
clawharness generate --service spotify --count 20
```

Generate once, review once, produce unlimited tasks.

## Validation

Every generated task is automatically validated:

- All `check.type` values are from the 14 valid types
- `scoring_components` weights sum to 1.0
- `action` names exist in the service's endpoint list
- `llm_judge` total weight capped at 55% (balanced: 50-70% rule + 30-50% LLM judge)
- LLM judge rubrics should be multi-part and specific
- Safety checks reference valid tool names
