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

## Agent Integration: Two Approaches

| Agent | Approach | Mechanism |
|-------|----------|-----------|
| **OpenClaw** | Native Plugin | TypeScript `registerTool()` — agent sees tools like `create_task` natively |
| **NanoClaw, IronClaw, CoPaw, PicoClaw, ZeroClaw, NemoClaw, Hermes** | Skill + curl | Markdown API docs → agent uses bash/curl |

### Native Plugin (OpenClaw)

```
entrypoint → OpenAPI spec → eval-tools.json → plugin registerTool()
Agent sees create_task() → tool internally calls localhost:9100 → bypasses SSRF
```

This is identical to how real MCP servers (Todoist, Gmail API) register tools — the agent experience is the same as production.

### Skill + curl (Other 7 agents)

```
entrypoint → OpenAPI spec → SKILL.md (with params + curl examples)
Agent reads SKILL.md → understands API → uses bash exec curl
```

All 7 agents share one `entrypoint_claw.sh`, differentiated by env vars (`AGENT_NAME`, `AGENT_CMD`, `SKILL_DIR`).

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
│   ├── agents/                    8 agent adapters
│   └── cli.py                     Unified CLI
├── extensions/                 ← OpenClaw plugin
│   └── clawharness-eval/          Registers mock endpoints as native tools
├── mock_services/              ← 19 FastAPI services (from Claw-Eval)
├── docker/                     ← Docker sandbox (8 agents)
│   ├── Dockerfile.openclaw        OpenClaw (native plugin)
│   ├── Dockerfile.nanoclaw        NanoClaw  ┐
│   ├── Dockerfile.ironclaw        IronClaw  │ Shared entrypoint_claw.sh
│   ├── Dockerfile.copaw           CoPaw     │ (Skill + curl)
│   ├── ...                        ...       ┘
│   ├── entrypoint_openclaw.sh     OpenClaw: gen tools → plugin → gateway
│   └── entrypoint_claw.sh         Others: gen SKILL.md → curl
├── dataset/                    ← 129 pre-generated tasks (13 services)
└── docs/                       ← This documentation
```
