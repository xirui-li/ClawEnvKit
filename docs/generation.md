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
  - LLM judge weight <= 0.15?
        ↓
Valid task.yaml ready for evaluation
```

## Generate Tasks

```bash
# Generate 10 gmail tasks
clawharness generate --service gmail --count 10

# Generate with specific difficulty
clawharness generate --service todo --count 5 --difficulty hard

# Generate to specific directory
clawharness generate --service calendar --count 3 --output /tmp/new-tasks
```

## Pre-generated Dataset

129 tasks across 13 services (3 easy + 4 medium + 3 hard each):

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
- `llm_judge` weight capped at 15% (prevent over-reliance on subjective scoring)
- Safety checks reference valid tool names
