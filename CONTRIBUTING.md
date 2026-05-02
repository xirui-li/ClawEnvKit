# Contributing: Adding a New Mock Service

Adding a new mock service unlocks an entire category of auto-generated tasks. Each service takes ~4 hours to build and enables unlimited task generation.

---

## Architecture

```
mock_services/
  ├── _base.py              ← shared audit log + error injection + load_fixtures()
  ├── your_service/
  │   └── server.py         ← your new FastAPI service
  └── ...

clawenvkit/generate/
  └── task_generator.py     ← add SERVICE_DEFINITIONS entry
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
from mock_services._base import add_error_injection, load_fixtures
add_error_injection(app)

# --- Fixtures ---

FIXTURES_PATH = os.environ.get("YOURSERVICE_FIXTURES", "")

_items: list[dict[str, Any]] = []
_audit_log: list[dict[str, Any]] = []


def _load_fixtures() -> None:
    global _items
    _items = load_fixtures(FIXTURES_PATH, id_field="item_id") if FIXTURES_PATH else []

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

## Step 2: Register the Service

**Option A: Manual** — Edit `clawenvkit/generate/task_generator.py`, add to `SERVICE_DEFINITIONS`:

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

**Option B: Automatic** — Use the Generator to design, generate, and register in one step:

```python
from clawenvkit.generate import Generator
gen = Generator()
spec = gen.plan_service("Your Service — one-line description")
gen.generate_service(spec, verify=True)
gen.register_service(spec)
```

Or via CLI: `clawenvkit service create --request "Your Service description"`

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
clawenvkit generate --services yourservice --count 1 --difficulty easy
```

Should produce a valid task.yaml with scoring_components referencing your service's actions.

### 3c: Run in Docker

```bash
# Pull a published harness image (or use any from docs/agents/index.md)
docker pull ghcr.io/xirui-li/clawenvkit-claudecode:latest
export CLAWENVKIT_IMAGE=ghcr.io/xirui-li/clawenvkit-claudecode:latest

clawenvkit eval yourservice-001
```

If you've modified `mock_services/`, `clawenvkit/`, or the entrypoint, rebuild
the harness image locally — the published base will still be pulled from GHCR
underneath:

```bash
docker build -f docker/Dockerfile.openclaw -t clawenvkit:openclaw .
export CLAWENVKIT_IMAGE=clawenvkit:openclaw
```

If you're testing a fork of an upstream agent, build the upstream base
locally and pass it via `--build-arg`:

```bash
git clone https://github.com/your-fork/openclaw.git
docker build -f openclaw/Dockerfile -t openclaw:my-fork openclaw
docker build -f docker/Dockerfile.openclaw \
  --build-arg BASE_IMAGE=openclaw:my-fork \
  -t clawenvkit:openclaw .
```

See [`docs/agents/index.md`](docs/agents/index.md) for the per-harness build
matrix.

---

## Step 4: Submit PR

Your PR should include:
- [ ] `mock_services/yourservice/server.py`
- [ ] Entry in `SERVICE_DEFINITIONS` in `clawenvkit/generate/task_generator.py`
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

---
---

# Contributing: Adding a New Evaluation Harness

Each harness has a different way to discover and use tools. We support **three integration approaches** — pick the one that matches the harness.

---

## Integration Approaches

```
                        ┌──────────────────────────┐
                        │   Mock Service (FastAPI)   │
                        │   localhost:9100            │
                        └──────────┬───────────────┘
                                   │
               ┌───────────────────┼───────────────────┐
               │                   │                   │
    ┌──────────▼──────┐ ┌─────────▼────────┐ ┌───────▼────────┐
    │  A: Native Plugin│ │ B: Skill + curl  │ │  C: MCP Server │
    │  (OpenClaw)      │ │ (大多数 agent)    │ │  (通用，未来)   │
    │                  │ │                  │ │                │
    │  registerTool()  │ │  Markdown 描述   │ │  MCP 协议      │
    │  → agent 原生调用 │ │  → agent 用 curl │ │  → 原生 tool   │
    └──────────────────┘ └──────────────────┘ └────────────────┘
```

### A: Native Plugin — agent 看到原生 tool（最佳体验）

Agent 看到 `create_task(title, priority)` 就像看到 `sendSlackMessage`。

**适用于：** 有 plugin/extension 系统的框架（OpenClaw）

**优点：** 最自然，无 SSRF 问题，agent 不需要懂 curl
**缺点：** 每个框架要写框架特定的 plugin 代码

**已实现：** OpenClaw → `extensions/clawenvkit-eval/`

### B: Skill Markdown + curl — agent 读描述后自己调 API

Agent 读一个 Markdown 文件，了解有哪些 API，然后通过 bash/exec 执行 curl。

**适用于：** 有 bash/exec 能力的框架（NanoClaw, IronClaw, CoPaw, PicoClaw, ZeroClaw, NemoClaw, Hermes）

**优点：** 通用，一套 Markdown 生成逻辑适配所有 agent
**缺点：** 依赖 agent 的 curl 能力，可能被 SSRF 阻挡

**已实现：** SKILL.md generation logic in `entrypoint_claw.sh`

### C: MCP Server — 标准协议，通用性最强

写一个 MCP (Model Context Protocol) server 包装 mock service，任何支持 MCP 的 agent 都能用。

**适用于：** 支持 MCP 的框架（NanoClaw, OpenClaw, 未来更多）

**优点：** 一次实现，所有 MCP agent 通用
**缺点：** 需要框架支持 MCP 协议

**已实现：** `mcp_server/index.js` — 支持 Claude Code, Codex, Cursor, Windsurf, Continue 等

---

## 每个框架的适配状态

| Agent | 集成方式 | 状态 | 配置方法 | Docker 文件 |
|-------|---------|------|---------|-------------|
| **OpenClaw** | A: Native Plugin | ✅ 已完成 | TypeScript plugin → `registerTool()` | `Dockerfile.openclaw` |
| **NanoClaw** | B: Skill + curl | 🔧 需要 Dockerfile | `.env` patch (`ANTHROPIC_BASE_URL`) | 需创建 |
| **IronClaw** | B: Skill + curl | 🔧 需要 Dockerfile | `.ironclaw/.env` patch (`LLM_BASE_URL`) | 需创建 |
| **CoPaw** | B: Skill + curl | 🔧 需要 Dockerfile | `.copaw/config.json` patch | 需创建 |
| **PicoClaw** | B: Skill + curl | 🔧 需要 Dockerfile | `.picoclaw/config.json` patch | 需创建 |
| **ZeroClaw** | B: Skill + curl | 🔧 需要 Dockerfile | `.zeroclaw/config.toml` patch | 需创建 |
| **NemoClaw** | B: Skill + curl | 🔧 需要 Dockerfile | `.nemoclaw/config.json` patch | 需创建 |
| **Hermes** | B: Skill + curl | 🔧 需要 Dockerfile | `.hermes/config.yaml` patch | 需创建 |

---

## 方式 A: 添加 Native Plugin（参考 OpenClaw）

如果目标框架有 plugin/extension 系统，这是最佳方案。

### 需要的文件

```
extensions/clawenvkit-{agent}/
├── manifest 文件 (框架要求的格式)
├── 入口文件 (TS/JS/Python，取决于框架)
└── package/config 文件
```

### 核心逻辑（通用）

不管什么框架，plugin 核心逻辑都是一样的：

```
1. 读 /tmp/eval-tools.json（entrypoint 生成的 tool 定义）
2. 对每个 tool:
   a. 构建参数 schema（从 OpenAPI 属性）
   b. 注册为原生 tool
   c. tool.execute() 内部 HTTP 调 localhost:9100
```

### OpenClaw 参考实现

```
extensions/clawenvkit-eval/
├── openclaw.plugin.json       manifest（id, name, configSchema）
├── package.json               依赖（@sinclair/typebox）+ 入口声明
└── index.ts                   读 JSON → TypeBox schema → api.registerTool()
```

entrypoint 生成的 `/tmp/eval-tools.json` 格式：
```json
[
  {
    "name": "create_task",
    "description": "Create a new task with title, description, priority, due date",
    "endpoint": "/todo/tasks/create",
    "method": "post",
    "port": 9100,
    "parameters": {
      "title": {"type": "string", "title": "Title"},
      "priority": {"type": "string", "default": "medium", "title": "Priority"}
    },
    "required": ["title"]
  }
]
```

### 添加新框架的 Plugin 步骤

1. 研究目标框架的 plugin API（怎么注册 tool、tool schema 格式、execute 返回值格式）
2. 创建 `extensions/clawenvkit-{agent}/` 目录
3. 写 manifest + 入口文件（参考 OpenClaw 的 `index.ts`）
4. 更新 `docker/Dockerfile.{agent}` — COPY plugin 到框架的 extensions 目录
5. 更新 `docker/entrypoint_{agent}.sh` — 确保有 tool JSON 生成步骤
6. 测试：agent 能看到并使用注册的 tool

---

## 方式 B: 添加 Skill + curl 适配（大多数框架）

对于没有 plugin 系统、但有 bash/exec 能力的框架，用 Markdown skill 描述 API。

### 核心机制

SKILL.md generation is handled by `entrypoint_claw.sh` (shared entrypoint).
No Python agent adapter needed — all agent integration is via Docker entrypoints.

### 添加新框架的步骤

#### 1. 创建 Dockerfile

```dockerfile
# docker/Dockerfile.youragent
FROM youragent:latest

USER root
RUN apt-get update && apt-get install -y python3 python3-pip curl jq \
    && rm -rf /var/lib/apt/lists/*
RUN pip3 install --no-cache-dir --break-system-packages fastapi uvicorn pyyaml

# ClawEnvKit infrastructure
COPY clawenvkit/ /opt/clawenvkit/clawenvkit/
COPY mock_services/ /opt/clawenvkit/mock_services/

COPY docker/entrypoint_youragent.sh /opt/clawenvkit/entrypoint.sh
RUN chmod +x /opt/clawenvkit/entrypoint.sh

ENV TASK_YAML=/opt/clawenvkit/task.yaml
ENV PYTHONPATH=/opt/clawenvkit
ENV PORT=9100

ENTRYPOINT ["/opt/clawenvkit/entrypoint.sh"]
```

#### 3. 创建 Entrypoint

```bash
#!/bin/bash
# docker/entrypoint_youragent.sh
set -e

TASK_YAML="${TASK_YAML:-/opt/clawenvkit/task.yaml}"
PORT="${PORT:-9100}"
# ... (解析 task.yaml, 启动 mock service — 跟 entrypoint_openclaw.sh 前半部分一样)

# --- Generate skill markdown ---
python3 << 'SKILL_EOF'
import yaml, os
task = yaml.safe_load(open(os.environ['TASK_YAML']))
tools = task.get('tools', [])
service = os.environ.get('SERVICE_NAME', '')
port = os.environ.get('PORT', '9100')

md = f"# Evaluation Environment\n\nAPI service running on localhost:{port}.\n\n"
for t in tools:
    md += f"## {t['name']}\n{t.get('description','')}\n"
    md += f"```bash\ncurl -s -X {t.get('method','POST')} http://localhost:{port}{t['endpoint']} \\\n"
    md += f"  -H 'Content-Type: application/json' -d '{{}}'\n```\n\n"

# Write to agent's skill directory (adjust path per harness)
skill_dir = os.path.expanduser("~/.youragent/skills/eval-task")
os.makedirs(skill_dir, exist_ok=True)
with open(f"{skill_dir}/SKILL.md", "w") as f:
    f.write(md)
SKILL_EOF

# --- Run agent ---
youragent agent --message "$TASK_PROMPT" --timeout 120 2>&1 | tee /workspace/agent_output.txt || true

# --- Grade --- (same as other entrypoints)
```

#### 4. 每个框架的配置细节

| Harness | Config File | Config Format | API URL Key |
|---------|-------------|---------------|-------------|
| NanoClaw | `~/.nanoclaw/.env` | `KEY=value` | `ANTHROPIC_BASE_URL` |
| IronClaw | `~/.ironclaw/.env` | `KEY=value` | `LLM_BASE_URL` |
| CoPaw | `~/.copaw/config.json` | JSON | `models.default.base_url` |
| PicoClaw | `~/.picoclaw/config.json` | JSON | `model_list[].base_url` |
| ZeroClaw | `~/.zeroclaw/config.toml` | TOML | `provider.base_url` |
| NemoClaw | `~/.nemoclaw/config.json` | JSON | `providers.metaclaw.base_url` |
| Hermes | `~/.hermes/config.yaml` | YAML | `custom_providers.metaclaw.base_url` |

---

## 方式 C: 添加 MCP Server（通用方案，未来）

MCP (Model Context Protocol) 是 Anthropic 推出的标准协议。一个 MCP server 可以被任何支持 MCP 的 agent 使用。

### 概念

```
Mock Service (FastAPI)  ←HTTP→  MCP Server  ←MCP→  Agent
  localhost:9100                  stdio/SSE         (任何 MCP agent)
```

### 已实现

```
mcp_servers/clawenvkit-eval/
├── package.json
└── index.ts    # 读 /tmp/eval-tools.json, 暴露为 MCP tools
```

MCP server 的核心逻辑跟 OpenClaw plugin 几乎一样（读 JSON → 注册 tool → execute 调 HTTP），区别只是用 MCP 协议而不是 harness-specific API。

### 步骤

1. 安装 `@modelcontextprotocol/sdk`
2. 对每个 tool: `server.tool(name, schema, handler)`
3. handler 内部 HTTP 调 mock service
4. Agent config 里加 MCP server 配置

这个方案的好处是**一次实现，所有 MCP agent 通用**。等 MCP 生态更成熟后优先考虑。

---

## 提交 PR 时的 Checklist

### 新 Agent 框架

- [ ] Config patching in `docker/entrypoint_claw.sh`
- [ ] `docker/Dockerfile.{agent}` — Docker image
- [ ] `docker/entrypoint_{agent}.sh` — 容器 entrypoint
- [ ] 如果是方式 A: `extensions/clawenvkit-{agent}/` — native plugin
- [ ] 在 README.md "Supported Agents" 表格里加一行
- [ ] 手动测试: `docker run` 能跑通一个 task 并输出 score

### 已有框架改为 Native Plugin

- [ ] `extensions/clawenvkit-{agent}/` — plugin 文件
- [ ] 更新 `docker/Dockerfile.{agent}` — COPY plugin
- [ ] 更新 `docker/entrypoint_{agent}.sh` — 加 tool JSON 生成
- [ ] 测试: agent 使用原生 tool 而不是 curl
