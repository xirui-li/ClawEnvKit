# Contributing: Adding a New Mock Service

Adding a new mock service unlocks an entire category of auto-generated tasks. Each service takes ~4 hours to build and enables unlimited task generation.

---

## Architecture

```
mock_services/
  ├── _base.py              ← shared audit log + error injection (don't modify)
  ├── your_service/
  │   └── server.py         ← your new FastAPI service
  └── ...

scripts/grading/
  └── task_config_generator.py  ← add SERVICE_DEFINITIONS entry
```

---

## Step 1: Write the Mock Service

Create `mock_services/your_service/server.py`:

```python
"""Mock YourService API for agent evaluation."""

from __future__ import annotations

import json
import copy
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Mock YourService API")

# Add error injection (random 429/500 responses)
from mock_services._base import add_error_injection
add_error_injection(app)

# --- Fixtures ---

FIXTURES_PATH = Path(os.environ.get(
    "YOURSERVICE_FIXTURES",
    str(Path(__file__).parent / "default_fixtures.json"),
))

_items: list[dict[str, Any]] = []
_audit_log: list[dict[str, Any]] = []


def _load_fixtures() -> None:
    global _items
    if FIXTURES_PATH.exists():
        with open(FIXTURES_PATH) as f:
            _items = json.load(f)

_load_fixtures()


# --- Audit logging ---

def _log_call(endpoint: str, request_body: dict, response_body: Any) -> None:
    _audit_log.append({
        "endpoint": endpoint,
        "request_body": request_body,
        "response_body": response_body,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


# --- API Endpoints ---

class ListRequest(BaseModel):
    status: str = "all"
    max_results: int = 50

@app.post("/yourservice/items")
def list_items(req: ListRequest):
    """List all items, optionally filtered."""
    items = _items
    if req.status != "all":
        items = [i for i in items if i.get("status") == req.status]
    items = items[:req.max_results]
    body = {"items": items, "total": len(items)}
    _log_call("/yourservice/items", req.dict(), body)
    return body


class GetRequest(BaseModel):
    item_id: str

@app.post("/yourservice/items/get")
def get_item(req: GetRequest):
    """Get a single item by ID."""
    item = next((i for i in _items if i["id"] == req.item_id), None)
    body = item or {"error": "not found"}
    _log_call("/yourservice/items/get", req.dict(), body)
    return body


class CreateRequest(BaseModel):
    title: str
    description: str = ""
    # add more fields as needed

@app.post("/yourservice/items/create")
def create_item(req: CreateRequest):
    """Create a new item."""
    new_item = {
        "id": f"item-{len(_items)+1:03d}",
        "title": req.title,
        "description": req.description,
        "status": "active",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _items.append(new_item)
    _log_call("/yourservice/items/create", req.dict(), new_item)
    return new_item


# --- Audit + Reset (required for every service) ---

@app.get("/yourservice/audit")
def get_audit():
    """Return full audit log for grading."""
    return {"calls": _audit_log}

@app.post("/yourservice/reset")
def reset():
    """Reset state to fixtures."""
    global _audit_log
    _audit_log = []
    _load_fixtures()
    return {"status": "reset"}


# --- Run ---

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "9120")))
```

### Key requirements:

- **Every endpoint must call `_log_call()`** — this is how the GradingEngine knows what happened
- **Must have `/yourservice/audit`** — returns `{"calls": [...]}`
- **Must have `/yourservice/reset`** — resets state to fixtures
- **Fixtures loaded from env var** — `YOURSERVICE_FIXTURES` points to JSON file
- **Must use `add_error_injection(app)`** — enables robustness testing
- **POST for everything** — Claw-Eval convention, even for reads

---

## Step 2: Add SERVICE_DEFINITIONS Entry

Edit `scripts/grading/task_config_generator.py`, add to `SERVICE_DEFINITIONS`:

```python
"yourservice": {
    "description": "One-line description of what the service does",
    "endpoints": [
        "POST /yourservice/items — List items (status, max_results)",
        "POST /yourservice/items/get — Get item (item_id)",
        "POST /yourservice/items/create — Create item (title, description)",
    ],
    "actions": ["list_items", "get_item", "create_item"],
    "fixture_schema": "items: [{id, title, description, status, created_at}]",
},
```

### Fields explained:

| Field | What it's for |
|---|---|
| `description` | LLM sees this to understand the service |
| `endpoints` | LLM uses these to generate tool definitions in task.yaml |
| `actions` | Valid audit action names (used in config validation) |
| `fixture_schema` | LLM uses this to generate realistic fixture data |

### Action naming convention:

Endpoint path → action name:
```
/yourservice/items         → list_items
/yourservice/items/get     → get_item
/yourservice/items/create  → create_item
/yourservice/items/update  → update_item
/yourservice/items/delete  → delete_item
```

---

## Step 3: Test

### 3a: Test the service manually

```bash
# Start service
PORT=9120 python mock_services/yourservice/server.py &

# Test endpoints
curl -s -X POST http://localhost:9120/yourservice/items \
  -H 'Content-Type: application/json' -d '{}'

curl -s -X POST http://localhost:9120/yourservice/items/create \
  -H 'Content-Type: application/json' \
  -d '{"title":"Test item","description":"Testing"}'

# Check audit log
curl -s http://localhost:9120/yourservice/audit | python3 -m json.tool

# Kill service
kill %1
```

### 3b: Generate a task config

```bash
python -m scripts.grading.cli generate --service yourservice --count 1 --difficulty easy
```

Should produce a valid task.yaml with scoring_components referencing your service's actions.

### 3c: Run in Docker

```bash
docker build -f docker/Dockerfile \
  --build-arg TASK_YAML=tasks/yourservice/yourservice-001.yaml \
  --build-arg SERVICE_NAME=yourservice \
  -t claw-harness:yourservice-001 .

docker run -d --name test claw-harness:yourservice-001
sleep 3
docker exec test curl -s -X POST http://localhost:9100/yourservice/items -d '{}'
docker stop test
docker cp test:/logs/ ./results/
cat results/reward.txt
```

---

## Step 4: Submit PR

Your PR should include:
- [ ] `mock_services/yourservice/server.py`
- [ ] Entry in `SERVICE_DEFINITIONS` in `task_config_generator.py`
- [ ] At least 1 generated task.yaml that passes validation
- [ ] Manual test showing audit log records all calls

---

## Existing Services (for reference)

| Service | Port | Endpoints | Fixture format |
|---|---|---|---|
| gmail | 9100 | messages, messages/get, send, drafts/save | `[{id, from, to, subject, body, date, read, priority}]` |
| calendar | 9101 | events, events/get, events/create, events/delete, user_events | `[{id, title, start_time, end_time, attendees, location}]` |
| todo | 9102 | tasks, tasks/create, tasks/update, tasks/delete | `[{id, title, description, priority, status, due_date, tags}]` |
| contacts | 9103 | search, get, send_message | `[{id, name, email, phone, department, title}]` |
| finance | 9104 | transactions, transactions/get, report/submit | `[{id, date, description, amount, category, vendor}]` |
| notes | 9105 | list, get, share | `[{id, title, content, date, attendees, tags}]` |
| kb | 9106 | search, articles/get, articles/update | `[{id, title, content, category, last_updated}]` |
| helpdesk | 9107 | tickets, tickets/get, tickets/update, tickets/close | `[{id, title, description, status, priority, category}]` |
| inventory | 9108 | products, products/get, orders/create | `[{id, name, category, quantity, min_stock, price}]` |
| rss | 9109 | feeds, articles, articles/get, publish | `feeds: [...], articles: [...]` |
| crm | 9110 | customers, customers/get, export | `[{id, name, email, tier, industry, status, revenue}]` |
| config | 9111 | integrations, integrations/get, integrations/update, notify | `[{id, name, status, api_key, secret}]` |
| scheduler | 9112 | jobs, jobs/get, jobs/create, jobs/update, jobs/delete, jobs/history | `[{id, name, cron_expression, action, enabled, tags}]` |

---

## Tips

- **Keep services simple** — 3-6 endpoints is enough. The GradingEngine's power comes from combining multiple checks, not from complex APIs.
- **Make fixtures realistic** — real names, dates, amounts. LLM generates better tasks when it sees realistic fixture schemas.
- **Include at least one "dangerous" action** — something the agent should NOT do (e.g., `delete_all`, `send_to_external`). This enables safety testing.
- **Test with error injection** — set `ERROR_RATE=0.1` env var to verify your service handles the middleware correctly.
