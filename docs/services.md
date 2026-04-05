# Mock Services

ClawHarnessing ships with 20 mock services. Together they cover the core Claw-Eval-style API tasks, multimodal/file-backed tasks, and live web variants used for research and safety testing.

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
| `spotify` | Music streaming | Search tracks, manage playlists, playback control |

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

## Cross-Service Categories

Services can be combined for multi-step, cross-service tasks:

| Category | Services | Example Task |
|----------|----------|-------------|
| **communication** | gmail, contacts | Find colleague email, send follow-up |
| **productivity** | calendar, todo, notes | Review notes → create tasks → schedule follow-up |
| **operations** | helpdesk, inventory, crm | Customer complaint → ticket + inventory + CRM |
| **workflow** | calendar, contacts, gmail | Schedule meeting: availability + attendees + invites |
| **ops_dashboard** | helpdesk, crm, inventory, kb, scheduler, config | Weekly ops review across all systems |
| **procurement** | crm, finance, inventory, kb, rss | Evaluate vendors across multiple data sources |
| **safety** | config, gmail | Audit API keys without leaking secrets |
| **knowledge** | kb, rss | Research across knowledge base and news |

```bash
# Generate cross-service tasks
clawharness generate --category workflow --count 5
clawharness generate --services helpdesk,crm,inventory --count 3

# List all categories
clawharness categories
```

Cross-service tasks use `multi_server.py` to run all needed services on one port (URL prefixes don't conflict: `/gmail/*`, `/calendar/*`, `/todo/*`).

## Multimodal and Live-Service Extensions

| Service | Domain | Typical Tasks |
|---------|--------|---------------|
| `ocr` | OCR | Extract text from images (menus, receipts, forms) |
| `caption` | Image description | Describe image contents |
| `documents` | Document processing | Extract text from PDFs |
| `web` | Web search (mock) | Search queries, fetch pages (controlled fixtures) |
| `web_real` | Web search (real) | Real SERP API search (requires network) |
| `web_real_injection` | Safety test | Real search + prompt injection payloads |
| `spotify` | Music streaming | Search tracks, playlists, playback control |

### File Fixtures

Tasks can include non-API files (images, PDFs, CSVs) that are copied to `/workspace/`:

```yaml
files:
  - source: fixtures/media/menu.jpeg
    target: /workspace/menu.jpeg
  - source: fixtures/pdf/report.pdf
    target: /workspace/report.pdf
```

The agent finds these files in its workspace and processes them using its built-in tools (image, pdf, read, bash).

## Generate New Services

Don't see your domain? Generate a mock service from a description:

```python
from clawharness.generate.service_generator import generate_and_install

generate_and_install("spotify", "Music streaming — search, play, pause, playlists")
# NOTE: registers in current process only. To use with CLI, manually add
# the service definition to clawharness/generate/task_generator.py SERVICE_DEFINITIONS
# → mock_services/spotify/server.py auto-generated
# → Review once, then generate unlimited tasks
```

See [Contributing: Adding Mock Services](contributing/services.md) for the full guide.
