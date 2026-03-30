# Contributing: Adding Mock Services

Adding a new mock service unlocks an entire category of auto-generated tasks. Each service takes ~4 hours to build and enables unlimited task generation.

## Step 1: Write the Mock Service

Create `mock_services/your_service/server.py`:

```python
"""Mock YourService API for agent evaluation."""
from __future__ import annotations
import json, copy, os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Mock YourService API")

from mock_services._base import add_error_injection
add_error_injection(app)

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

def _log_call(endpoint: str, request_body: dict, response_body: Any) -> None:
    _audit_log.append({
        "endpoint": endpoint,
        "request_body": request_body,
        "response_body": response_body,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

# --- Your endpoints here ---

class CreateRequest(BaseModel):
    title: str
    description: str = ""

@app.post("/yourservice/items/create")
def create_item(req: CreateRequest):
    new_item = {"id": f"item-{len(_items)+1:03d}", "title": req.title, ...}
    _items.append(new_item)
    _log_call("/yourservice/items/create", req.dict(), new_item)
    return new_item

# --- Required: audit + reset ---

@app.get("/yourservice/audit")
def get_audit():
    return {"calls": _audit_log}

@app.post("/yourservice/reset")
def reset():
    global _audit_log
    _audit_log = []
    _load_fixtures()
    return {"status": "reset"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "9120")))
```

### Key Requirements

- **Every endpoint must call `_log_call()`** — this is how GradingEngine verifies behavior
- **Must have `/yourservice/audit`** — returns `{"calls": [...]}`
- **Must have `/yourservice/reset`** — resets state to fixtures
- **Must use `add_error_injection(app)`** — enables robustness testing
- **POST for everything** — Claw-Eval convention, even for reads

## Step 2: Add SERVICE_DEFINITIONS Entry

Edit `clawharness/generate/task_generator.py`, add to `SERVICE_DEFINITIONS`:

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

## Step 3: Test

```bash
# Start service
PORT=9120 python mock_services/yourservice/server.py &

# Test endpoints
curl -s -X POST http://localhost:9120/yourservice/items/create \
  -H 'Content-Type: application/json' \
  -d '{"title":"Test item"}'

# Check audit log
curl -s http://localhost:9120/yourservice/audit | python3 -m json.tool

# Generate a task
clawharness generate --service yourservice --count 1
```

## Step 4: PR Checklist

- [ ] `mock_services/yourservice/server.py`
- [ ] Entry in `SERVICE_DEFINITIONS`
- [ ] At least 1 generated task.yaml that passes validation
- [ ] Manual test showing audit log records all calls

## Tips

- **Keep services simple** — 3-6 endpoints is enough
- **Make fixtures realistic** — real names, dates, amounts
- **Include at least one "dangerous" action** — something the agent should NOT do (e.g., `delete_all`)
- **Test with error injection** — set `ERROR_RATE=0.1` to verify middleware works
