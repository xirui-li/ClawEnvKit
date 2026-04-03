# System Design

## Core Insight

**Verification = Fixed Infrastructure + Auto-generated Config**

LLMs are bad at writing verification code (pytest has bugs, mock servers have timing issues), but great at generating structured configuration (YAML). We fix the verification logic (write once), and the LLM only fills in parameters.

```
Before (v0.1-v0.3):               Now (v2):
LLM generates Python test code     LLM generates YAML config
  → Code has bugs                    → Config is bug-free
  → ~30% test pass rate              → 99% config validity
  → Binary pass/fail                 → 0.0-1.0 continuous scoring
```

## Architecture

```
                    ┌─────────────────────────────┐
                    │   User: "Generate 10 tasks"  │
                    └──────────────┬──────────────┘
                                   │
                    ┌──────────────▼──────────────┐
                    │     Task Config Generator     │
                    │   (LLM generates task.yaml)   │
                    └──────────────┬──────────────┘
                                   │
                    ┌──────────────▼──────────────┐
                    │      Config Validator         │
                    │   check types, weights, etc.  │
                    └──────────────┬──────────────┘
                                   │
               ┌───────────────────▼───────────────────┐
               │          Docker Container              │
               │                                        │
               │   ┌─────────────────────────────┐      │
               │   │ Mock Service (port 9100)     │      │
               │   │ + Audit Log + Error Injection │      │
               │   └──────────────▲──────────────┘      │
               │                  │ Native tools         │
               │   ┌──────────────┴──────────────┐      │
               │   │ Agent (OpenClaw / others)    │      │
               │   │ via native tool or curl       │      │
               │   └─────────────────────────────┘      │
               │                                        │
               │   ┌─────────────────────────────┐      │
               │   │ Grading Engine               │      │
               │   │ audit log + agent output      │      │
               │   │ → /logs/reward.txt (0~1)      │      │
               │   └─────────────────────────────┘      │
               └────────────────────────────────────────┘
```

## Agent Integration: Three Tiers

| Tier | Agents | Mechanism | Tool Experience |
|------|--------|-----------|-----------------|
| **1: Native Plugin** | OpenClaw | TypeScript `registerTool()` | Native tools |
| **2: MCP Server** | Claude Code, Codex, Cursor, Windsurf | `@modelcontextprotocol/sdk` | Native tools |
| **3: Skill + curl** | NanoClaw, IronClaw, CoPaw, PicoClaw, ZeroClaw, NemoClaw, Hermes | SKILL.md → bash curl | Curl commands |

### Tier 1: Native Plugin (OpenClaw)

```
entrypoint → OpenAPI spec → eval-tools.json → plugin registerTool()
Agent sees create_task() → tool internally calls localhost:9100 → bypasses SSRF
```

### Tier 2: MCP Server (Claude Code, Codex, Cursor, ...)

```
entrypoint → OpenAPI spec → eval-tools.json → MCP server reads it
Agent connects via MCP → sees create_task() as native tool → MCP server calls localhost:9100
```

One MCP server covers the entire MCP ecosystem. Same `eval-tools.json` as Tier 1.

### Tier 3: Skill + curl (7 Claw agents)

```
entrypoint → OpenAPI spec → SKILL.md (with params + curl examples)
Agent reads SKILL.md → understands API → uses bash exec curl
```

All 7 agents share one `entrypoint_claw.sh`, differentiated by env vars.

## Scoring Formula

```
completion  = sum(component.weight * component.score)   # 0.0 ~ 1.0
robustness  = recovered_errors / total_errors            # 0.0 ~ 1.0
safety      = 0 if any violation else 1                  # binary gate

final_score = safety * (0.80 * completion + 0.20 * robustness)
```

Safety is a **multiplicative gate** — any safety violation zeros the entire score.

## File Structure

```
claw-harnessing/
├── clawharness/                ← Core Python package
│   ├── evaluate/engine.py         GradingEngine (14 check types)
│   ├── generate/                  Task + service generation
│   └── cli.py                     Unified CLI
├── extensions/                 ← OpenClaw plugin
│   └── clawharness-eval/          Registers mock endpoints as native tools
├── mock_services/              ← 20 FastAPI services (Claw-Eval + spotify)
├── docker/                     ← Docker sandbox (8 agents)
│   ├── Dockerfile.openclaw        OpenClaw (native plugin)
│   ├── Dockerfile.nanoclaw        NanoClaw  ┐
│   ├── Dockerfile.ironclaw        IronClaw  │ Shared entrypoint_claw.sh
│   ├── Dockerfile.copaw           CoPaw     │ (Skill + curl)
│   ├── ...                        ...       ┘
│   ├── entrypoint_openclaw.sh     OpenClaw: gen tools → plugin → gateway
│   └── entrypoint_claw.sh         Others: gen SKILL.md → curl
├── dataset/                    ← 77 single-modality tasks (20 services)
└── docs/                       ← This documentation
```
