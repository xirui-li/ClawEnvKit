# Mock Services

19 mock API services with audit logging and error injection, originally from [Claw-Eval](https://github.com/claw-eval/Claw-Eval).

## Available Services

| Service | Domain | Typical Tasks |
|---------|--------|---------------|
| `gmail` | Email | Triage inbox, draft replies, mark read |
| `calendar` | Scheduling | Create events, resolve conflicts, find free slots |
| `todo` | Task management | Create/prioritize tasks, bulk updates |
| `contacts` | Directory | Search people, send messages |
| `helpdesk` | IT support | Triage tickets, escalate, close with resolution |
| `notes` | Meeting notes | Find and share relevant notes |
| `crm` | CRM | Customer analysis, export reports |
| `finance` | Accounting | Expense reports, transaction analysis |
| `inventory` | Supply chain | Restock low-stock items, create orders |
| `scheduler` | Cron jobs | Create/update/disable scheduled jobs |
| `rss` | News feeds | Curate articles, publish newsletters |
| `kb` | Knowledge base | Search and update documentation |
| `config` | Secrets management | Rotate API keys (safety test: don't leak secrets) |
| `web` | Search (mock) | Search queries, fetch pages |
| `web_real` | Search (real) | Real SERP API calls |
| `web_real_injection` | Search + injection | Real search with prompt injection |
| `ocr` | OCR | Extract text from images |
| `caption` | Image description | Describe images |
| `documents` | PDF | Extract text from PDF |

## Shared Features

Every mock service includes:

- **Audit Log** — records every API call with action, params, timestamp
- **Error Injection** — randomly returns 429/500 errors to test agent robustness
- **`/audit` endpoint** — GradingEngine pulls data from here
- **`/reset` endpoint** — resets state to fixtures
- **POST-only endpoints** — Claw-Eval convention, even for reads

## API Pattern

All services follow the same REST-like pattern:

```bash
# List resources
curl -s -X POST http://localhost:9100/{service}/{resource} \
  -H 'Content-Type: application/json' -d '{}'

# Get single resource
curl -s -X POST http://localhost:9100/{service}/{resource}/get \
  -H 'Content-Type: application/json' -d '{"id": "..."}'

# Create resource
curl -s -X POST http://localhost:9100/{service}/{resource}/create \
  -H 'Content-Type: application/json' -d '{"title": "...", ...}'

# Update resource
curl -s -X POST http://localhost:9100/{service}/{resource}/update \
  -H 'Content-Type: application/json' -d '{"id": "...", "field": "new_value"}'
```

## Error Injection

Controlled via `ERROR_RATE` environment variable (default: 0):

```bash
# 25% error rate
docker run -e ERROR_RATE=0.25 ...
```

When triggered, errors are randomly distributed:

- **35%** → HTTP 429 (rate limit) with `Retry-After: 2` header
- **35%** → HTTP 500 (server error)
- **30%** → Slow response (2-4 second delay, still returns real data)

Exempt endpoints: `/audit`, `/reset`, `/health`, `/docs`, `/openapi.json`

## Auto-Generate New Services

Don't see your domain? Generate a mock service from a description:

```python
from clawharness.generate.service_generator import generate_and_install

generate_and_install("spotify", "Music streaming — search, play, pause, playlists")
# → mock_services/spotify/server.py auto-generated
# → Review once, then generate unlimited tasks
```

See [Contributing: Adding Mock Services](contributing/services.md) for the full guide.
