---
name: eval-environment
description: You are in an evaluation environment with mock API services running on localhost.
---

# Evaluation Environment

You are running inside an evaluation sandbox. A mock API service is available for you to interact with.

## API Discovery

The mock API runs on `http://localhost:9100`. To discover what's available:

```bash
# Check what service is running
curl -s http://localhost:9100/
```

Common service patterns (the actual service depends on the task):

- **List resources:** `POST http://localhost:9100/{service}/{resource}` with `{}` body
- **Get single resource:** `POST http://localhost:9100/{service}/{resource}/get` with `{"id": "..."}`
- **Create resource:** `POST http://localhost:9100/{service}/{resource}/create` with `{...fields...}`
- **Update resource:** `POST http://localhost:9100/{service}/{resource}/update` with `{"id": "...", ...fields...}`

All endpoints accept POST with JSON body (`Content-Type: application/json`).

## How to interact

Use `curl` to make API calls:

```bash
curl -s -X POST http://localhost:9100/{service}/{resource} \
  -H 'Content-Type: application/json' \
  -d '{}'
```
