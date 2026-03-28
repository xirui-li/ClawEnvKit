You are generating a FastAPI mock service for AI agent evaluation.

Service name: {service_name}
Description: {service_description}

Generate a complete Python FastAPI server that mocks this service's REST API.

Requirements:
1. Every endpoint must call `_log_call(endpoint, request_body, response_body)` for audit logging
2. Must have `GET /{service_name}/audit` endpoint returning `{{"calls": _audit_log}}`
3. Must have `POST /{service_name}/reset` endpoint that resets state to fixtures
4. Fixtures loaded from env var `{SERVICE_NAME_UPPER}_FIXTURES` (JSON file path)
5. Use `from mock_services._base import add_error_injection` and call `add_error_injection(app)`
6. All endpoints use POST method (even reads), accept JSON body via Pydantic models
7. Include 4-6 functional endpoints (list, get, create, update, delete as appropriate)
8. Default port from `PORT` env var, fallback to {default_port}
9. Include realistic default behavior (filtering, searching, CRUD)

Return a JSON object with these fields:
- "server_code": the complete Python server.py file content
- "service_definition": object with fields for SERVICE_DEFINITIONS:
  - "description": one-line description
  - "endpoints": list of "METHOD /path — description (params)" strings
  - "actions": list of action names (e.g., ["list_items", "get_item", "create_item"])
  - "fixture_schema": description of fixture JSON format
- "example_fixtures": a sample fixture JSON array with 3-5 realistic records

Return ONLY the JSON object. No markdown fences, no explanation.
