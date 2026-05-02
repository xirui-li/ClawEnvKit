# Supported Harnesses

ClawEnvKit supports 10 evaluation harnesses across three integration tiers.
All harnesses use their **native agent loop** — no fallback agents.

## Harness Comparison

| Harness | Tier | Tool Mechanism | Native Agent | Language | Verified |
|---------|------|---------------|-------------|----------|----------|
| **OpenClaw** | 1 - Native Plugin | TypeScript `registerTool()` | OpenClaw gateway | TypeScript | 0.82 |
| **Claude Code** | 2 - MCP | Node.js MCP server (stdio) | `claude` CLI | Node.js | 0.86 |
| **NanoClaw** | 2 - MCP | Python MCP server (stdio) | `claude` CLI (bundled) | Node.js | 0.88 |
| **IronClaw** | 2 - MCP | Python MCP server (via `ironclaw mcp add`) | `ironclaw` CLI | Rust | MCP verified |
| **PicoClaw** | 2 - MCP | Python MCP server (stdio) | `picoclaw agent` | Go | 0.52 |
| **ZeroClaw** | 2 - MCP | Python MCP server (stdio) | `zeroclaw agent` | Rust | 0.78 |
| **CoPaw** | 3 - SKILL.md + shell | curl via `execute_shell_command` | `copaw app` + REST API | Python | 0.76 |
| **NemoClaw** | 3 - SKILL.md + shell | curl via OpenClaw shell | `openclaw agent --local` | TypeScript | 0.80 |
| **Hermes** | 3 - SKILL.md + shell | curl via `terminal` toolset | `python cli.py -q` | Python | 0.68 |
| **Agent Loop** | 3 - Direct function calling | OpenAI-format tool calls (no Docker) | Python agent loop | Python | ~0.55 |

## Integration Tiers

### Tier 1 - Native Plugin
The harness provides a plugin/extension API to register custom tools.
Mock service endpoints are registered as native tools via `registerTool()`.
The agent calls `create_task(title, priority)` exactly like `sendSlackMessage`.

**Harnesses:** OpenClaw

### Tier 2 - MCP (Model Context Protocol)
A lightweight MCP server exposes mock service endpoints as tools over stdio.
The agent's MCP client connects at startup, discovers tools via `tools/list`,
and calls them via `tools/call`. Two MCP server implementations:

- **Node.js** (`mcp_server/index.js`): Full `@modelcontextprotocol/sdk` with Zod schemas.
  Used by Claude Code (requires Content-Length framing).
- **Python** (`mcp_server/mcp_server.py`): Zero-dependency JSON-RPC 2.0, NDJSON framing
  (auto-detects Content-Length). Used by NanoClaw, IronClaw, PicoClaw, ZeroClaw.

**Harnesses:** Claude Code, NanoClaw, IronClaw, PicoClaw, ZeroClaw

### Tier 3 - SKILL.md + Shell / Direct Function Calling
The entrypoint generates a `SKILL.md` file documenting all mock API endpoints
with curl examples. This is appended to the task prompt. The agent uses its
built-in shell/terminal tool to execute curl commands against localhost:9100.

Agent Loop is a variant that uses direct OpenAI-format function calling
(no Docker, no shell) as a baseline.

**Harnesses:** CoPaw, NemoClaw, Hermes, Agent Loop

## Docker Images

Each harness ships its own `Dockerfile.<agent>` in [`docker/`](https://github.com/xirui-li/ClawEnvKit/tree/main/docker).
Most of them layer ClawEnvKit's eval infrastructure (mock services, MCP server,
entrypoint) on top of an upstream **base image** that ships the agent runtime
itself.

### Pulling Published Images (default path)

Both layers — the base images and the harness images — are published on GHCR
under the `ghcr.io/xirui-li/` namespace. From a fresh checkout you don't need
to build anything: just pull and run.

```bash
docker pull ghcr.io/xirui-li/clawenvkit-claudecode:latest
docker run --rm -e ANTHROPIC_API_KEY=$KEY \
  -v ./Auto-ClawEval-mini/todo/todo-001.yaml:/opt/clawenvkit/task.yaml:ro \
  ghcr.io/xirui-li/clawenvkit-claudecode:latest
```

Published images (all `linux/amd64`):

| Harness | Harness image | Base image |
|---------|---------------|------------|
| OpenClaw | `ghcr.io/xirui-li/clawenvkit-openclaw` | `ghcr.io/xirui-li/clawenvkit-base-openclaw` |
| Claude Code | `ghcr.io/xirui-li/clawenvkit-claudecode` | (no separate base — `node:22-slim` + `npm install`) |
| NanoClaw | `ghcr.io/xirui-li/clawenvkit-nanoclaw` | `ghcr.io/xirui-li/clawenvkit-base-nanoclaw` |
| PicoClaw | `ghcr.io/xirui-li/clawenvkit-picoclaw` | `ghcr.io/xirui-li/clawenvkit-base-picoclaw` |
| ZeroClaw² | `ghcr.io/xirui-li/clawenvkit-zeroclaw` | `ghcr.io/xirui-li/clawenvkit-base-zeroclaw` |
| CoPaw | `ghcr.io/xirui-li/clawenvkit-copaw` | `ghcr.io/xirui-li/clawenvkit-base-copaw` |
| NemoClaw | `ghcr.io/xirui-li/clawenvkit-nemoclaw` | `ghcr.io/xirui-li/clawenvkit-base-nemoclaw` |
| Hermes | `ghcr.io/xirui-li/clawenvkit-hermes` | `ghcr.io/xirui-li/clawenvkit-base-hermes` |
| IronClaw¹ | (not published) | (not published — must build locally) |

Each image exists as `:latest` and as a pinned semver (`:v0.3.0` for the
current release). For paper-stable reproducibility, pin to the semver tag.

¹ IronClaw is excluded by default in `run_harnesses.sh` — its native agent
loop runs 50 iterations per task and tends to time out. Its upstream repo
also ships without a LICENSE file, so we don't redistribute it. If you need
to evaluate IronClaw, see *Building from source* below.

² The published `clawenvkit-base-zeroclaw` image is **not** built using
upstream's official Dockerfile — that Dockerfile has incomplete workspace
COPY directives and won't build cleanly in CI. Instead it's built from
upstream zeroclaw-labs/zeroclaw at `v0.7.4` using a minimal Dockerfile we
maintain (`COPY . . && cargo build --release --bin zeroclaw
--no-default-features`), a build path the upstream maintainer explicitly
supports. The resulting binary is functionally identical for ClawEnvKit
eval. For strict paper-grade reproducibility, treat this as a known asterisk.

### Building from Source (advanced)

Build harness images locally when you need to:

- modify `mock_services/`, `clawenvkit/`, or the entrypoint
- evaluate a fork of an upstream agent
- evaluate IronClaw (the only harness without a published image)

Every `Dockerfile.<agent>` declares `ARG BASE_IMAGE=ghcr.io/xirui-li/clawenvkit-base-<agent>:latest`,
so you can either rebuild on the published base or override the base via
`--build-arg`:

```bash
# Rebuild harness on the published base (e.g. after editing mock_services/)
docker build -f docker/Dockerfile.openclaw -t clawenvkit:openclaw .

# Build a base image yourself from a fork, then layer the harness on it
git clone https://github.com/your-fork/openclaw.git
docker build -f openclaw/Dockerfile -t openclaw:my-fork openclaw
docker build -f docker/Dockerfile.openclaw \
  --build-arg BASE_IMAGE=openclaw:my-fork \
  -t clawenvkit:openclaw .
```

Per-agent base build commands (use these to reproduce the published images,
or to build IronClaw):

| Harness | Upstream repo | Build the base image |
|---------|---------------|----------------------|
| OpenClaw | [openclaw/openclaw](https://github.com/openclaw/openclaw) | `docker build -f openclaw/Dockerfile -t openclaw:latest openclaw` |
| NanoClaw | [qwibitai/nanoclaw](https://github.com/qwibitai/nanoclaw) | `docker build -f nanoclaw/container/Dockerfile -t nanoclaw:latest nanoclaw/container` |
| IronClaw | [nearai/ironclaw](https://github.com/nearai/ironclaw) | `docker build -f ironclaw/Dockerfile -t ironclaw:latest ironclaw` |
| CoPaw | [agentscope-ai/CoPaw](https://github.com/agentscope-ai/CoPaw) | `docker build -f copaw/deploy/Dockerfile -t copaw:latest copaw` |
| Hermes | [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent) | `docker build -f hermes/Dockerfile -t hermes:latest hermes` |
| NemoClaw | [nvidia/nemoclaw](https://github.com/nvidia/nemoclaw) | `docker build -f nemoclaw/Dockerfile -t nemoclaw:latest nemoclaw` |
| PicoClaw | [sipeed/picoclaw](https://github.com/sipeed/picoclaw) | `docker build -f picoclaw/docker/Dockerfile -t picoclaw:latest picoclaw` |
| ZeroClaw | [zeroclaw-labs/zeroclaw](https://github.com/zeroclaw-labs/zeroclaw) | upstream Dockerfile is broken; see footnote ² above for the working build |

If you're rebuilding to match a *published* base, also pass
`--build-arg BASE_IMAGE=<agent>:latest` to the harness build so it consumes
your local image rather than re-pulling from GHCR.

## Batch Evaluation

```bash
# All 10 harnesses with one model
bash run_harnesses.sh --model anthropic/claude-haiku-4-5-20251001 --dataset Auto-ClawEval-mini --resume

# Single harness
bash run_harnesses.sh --harness picoclaw --model anthropic/claude-sonnet-4.6 --resume

# All harnesses via Python
python3 scripts/evaluate.py --all-harnesses --model anthropic/claude-sonnet-4.6
```
