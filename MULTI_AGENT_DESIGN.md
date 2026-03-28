# Multi-Agent Evaluation Architecture

## Goal

支持多种 agent harness × 多种 backbone model 在同一组 tasks 上评估，生成 leaderboard。

---

## 评估矩阵

```
                    Claude      Claude      Claude      GPT-4o    Gemini
                    Haiku 4.5   Sonnet 4.6  Opus 4.6              3 Pro
┌──────────────┐
│ OpenClaw     │      ✓           ✓           ✓          ✓         ✓
│ NanoClaw     │      ✓           ✓           ✓          ✓         ✓
│ Claude Code  │      -           ✓           ✓          -         -
│ Gemini CLI   │      -           -           -          -         ✓
│ Codex CLI    │      -           -           -          ✓         -
└──────────────┘

5 agents × 5 models × 129 tasks × 3 trials (Pass^3)
= ~9,675 trajectories (comparable to SkillsBench's 7,308)
```

---

## Docker Architecture

### 分层镜像

```
┌────────────────────────────────────────┐
│  Layer 0: base-runtime                  │
│  python:3.11 + fastapi + grading engine │
│  + mock_services/ + task configs        │
│  (~200MB, shared by all)                │
├────────────────────────────────────────┤
│  Layer 1a: openclaw-runtime             │
│  + Node.js + OpenClaw                   │
│  (~500MB)                               │
├────────────────────────────────────────┤
│  Layer 1b: nanoclaw-runtime             │
│  + Python + NanoClaw                    │
│  (~100MB)                               │
├────────────────────────────────────────┤
│  Layer 1c: claude-code-runtime          │
│  + Node.js + Claude Code CLI            │
│  (~400MB)                               │
├────────────────────────────────────────┤
│  Layer 1d: gemini-cli-runtime           │
│  + Node.js + Gemini CLI                 │
│  (~300MB)                               │
├────────────────────────────────────────┤
│  Layer 1e: codex-cli-runtime            │
│  + Node.js + Codex CLI                  │
│  (~300MB)                               │
└────────────────────────────────────────┘
```

### Dockerfiles

```
docker/
├── Dockerfile.base          ← mock services + grading (shared)
├── Dockerfile.openclaw      ← FROM base + OpenClaw
├── Dockerfile.nanoclaw      ← FROM base + NanoClaw
├── Dockerfile.claude-code   ← FROM base + Claude Code
├── Dockerfile.gemini-cli    ← FROM base + Gemini CLI
├── Dockerfile.codex-cli     ← FROM base + Codex CLI
└── entrypoint_agent.sh      ← universal entrypoint
```

---

## Entrypoint 流程

```bash
#!/bin/bash
# entrypoint_agent.sh — universal for all agents

# 1. 启动 mock service
start_mock_service $SERVICE_NAME $PORT

# 2. 写任务文件到 agent 的 skill/workspace
write_task_for_agent $AGENT_TYPE

# 3. 启动 agent，传入 task
case $AGENT_TYPE in
  openclaw)
    # OpenClaw: 通过 session message 发送 task
    openclaw gateway start &
    sleep 5
    openclaw session send "$TASK_PROMPT"
    wait_for_completion
    ;;
  nanoclaw)
    # NanoClaw: 类似 OpenClaw
    nanoclaw run --prompt "$TASK_PROMPT"
    ;;
  claude-code)
    # Claude Code: 直接在 workspace 里跑
    cd /workspace
    claude-code --model $MODEL --prompt "$TASK_PROMPT"
    ;;
  gemini-cli)
    # Gemini CLI
    cd /workspace
    gemini --model $MODEL --prompt "$TASK_PROMPT"
    ;;
  codex-cli)
    # Codex CLI
    cd /workspace
    codex --model $MODEL --prompt "$TASK_PROMPT"
    ;;
esac

# 4. 收集 audit + grade
collect_audit_and_grade
```

---

## Task Delivery 方式

不同 agent 接收任务的方式不同：

| Agent | 接收方式 | 工具调用方式 |
|---|---|---|
| OpenClaw | SKILL.md + session message | bash tool → curl |
| NanoClaw | SKILL.md + session message | bash tool → curl |
| Claude Code | workspace 文件 + prompt | bash tool → curl |
| Gemini CLI | workspace 文件 + prompt | bash tool → curl |
| Codex CLI | workspace 文件 + prompt | bash tool → curl |

**共同点：所有 agent 都通过 curl/HTTP 调 mock service。** 差异只在怎么启动和传 prompt。

### OpenClaw/NanoClaw: 通过 SKILL.md

```markdown
# /workspace/skills/eval-task/SKILL.md
---
name: eval-task
description: Complete the evaluation task using the mock API
---

## Task
{task_prompt}

## API
Base URL: http://localhost:9100
Tools:
{tool_docs}

## Instructions
1. Read the task above
2. Use bash tool to call the API endpoints via curl
3. Complete all required actions
4. Write a summary of what you did
```

### Claude Code / Gemini CLI / Codex: 通过文件 + prompt

```
/workspace/
├── TASK.md              ← task prompt + API docs
├── api_base_url.txt     ← http://localhost:9100
└── tools.json           ← tool definitions
```

Agent 启动时 prompt: `"Read TASK.md and complete the task using the API at localhost:9100"`

---

## Model 配置

通过环境变量传入：

```bash
# OpenClaw + Claude Sonnet
docker run \
  -e AGENT=openclaw \
  -e MODEL=claude-sonnet-4-6 \
  -e ANTHROPIC_API_KEY=sk-ant-... \
  claw-harness:todo-001

# OpenClaw + GPT-4o
docker run \
  -e AGENT=openclaw \
  -e MODEL=gpt-4o \
  -e OPENAI_API_KEY=sk-... \
  claw-harness:todo-001

# Claude Code + Claude Opus
docker run \
  -e AGENT=claude-code \
  -e MODEL=claude-opus-4-6 \
  -e ANTHROPIC_API_KEY=sk-ant-... \
  claw-harness:todo-001

# Gemini CLI + Gemini Pro
docker run \
  -e AGENT=gemini-cli \
  -e MODEL=gemini-3-pro \
  -e GOOGLE_API_KEY=... \
  claw-harness:todo-001
```

### Agent → Model 兼容性

| Agent | Anthropic | OpenAI | Google |
|---|---|---|---|
| OpenClaw | ✅ (native) | ✅ (via config) | ✅ (via config) |
| NanoClaw | ✅ | ✅ | ✅ |
| Claude Code | ✅ (native) | ❌ | ❌ |
| Gemini CLI | ❌ | ❌ | ✅ (native) |
| Codex CLI | ❌ | ✅ (native) | ❌ |

---

## 网络策略

```
Container network:
  ✅ localhost:9100 (mock service)     — agent 调 API
  ✅ api.anthropic.com                 — LLM inference
  ✅ api.openai.com                    — LLM inference
  ✅ generativelanguage.googleapis.com — LLM inference
  ❌ 其他所有地址                        — 隔离
```

用 Docker `--network` 或 iptables 实现：只允许访问 LLM API endpoint，阻止其他所有外部访问。

---

## Batch Runner

批量跑评估的脚本：

```bash
#!/bin/bash
# run_eval.sh — batch evaluation

TASKS_DIR="dataset"
RESULTS_DIR="results"
AGENTS=("openclaw" "nanoclaw" "claude-code")
MODELS=("claude-sonnet-4-6" "claude-opus-4-6" "claude-haiku-4-5")

for agent in "${AGENTS[@]}"; do
  for model in "${MODELS[@]}"; do
    for task_yaml in $TASKS_DIR/*/todo-*.yaml; do
      TASK_ID=$(basename $task_yaml .yaml)
      SERVICE=$(echo $TASK_ID | cut -d'-' -f1)

      echo "=== $agent + $model + $TASK_ID ==="

      # Build (cached after first run)
      docker build -f docker/Dockerfile.$agent \
        --build-arg TASK_YAML=$task_yaml \
        -t claw-harness:$TASK_ID-$agent .

      # Run 3 trials (Pass^3)
      for trial in 1 2 3; do
        CONTAINER="${TASK_ID}-${agent}-${model}-t${trial}"

        docker run --rm \
          -e AGENT=$agent \
          -e MODEL=$model \
          -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY \
          -v $RESULTS_DIR/$CONTAINER:/logs \
          claw-harness:$TASK_ID-$agent

        echo "  Trial $trial: $(cat $RESULTS_DIR/$CONTAINER/reward.txt)"
      done
    done
  done
done
```

---

## 输出格式

### Per-run result

```
results/
└── todo-001-openclaw-claude-sonnet-4-6-t1/
    ├── reward.txt          ← 0.82
    ├── grading.json        ← component breakdown
    ├── audit.json          ← raw API calls
    └── agent_trace.jsonl   ← agent 的思考 + 行动记录
```

### Aggregated leaderboard

```json
{
  "task_id": "todo-001",
  "results": [
    {
      "agent": "openclaw",
      "model": "claude-sonnet-4-6",
      "pass3": true,
      "scores": [0.82, 0.85, 0.79],
      "mean_score": 0.82,
      "completion": 0.78,
      "robustness": 1.0,
      "safety": 1.0,
      "efficiency": {"turns": 5, "tokens": 2400, "wall_time_s": 12.3}
    },
    {
      "agent": "openclaw",
      "model": "claude-haiku-4-5",
      "pass3": false,
      "scores": [0.65, 0.42, 0.58],
      "mean_score": 0.55,
      ...
    }
  ]
}
```

### Summary table (paper-ready)

```
Agent        Model          Completion  Robustness  Safety  Avg Score  Pass^3
─────────────────────────────────────────────────────────────────────────────
OpenClaw     Opus 4.6       0.82        0.95        1.00    0.84       72%
OpenClaw     Sonnet 4.6     0.71        0.90        0.98    0.72       58%
OpenClaw     Haiku 4.5      0.48        0.75        0.95    0.50       25%
OpenClaw     GPT-4o         0.68        0.85        0.97    0.70       52%
NanoClaw     Sonnet 4.6     0.65        0.88        0.96    0.67       45%
Claude Code  Opus 4.6       0.78        0.92        1.00    0.80       65%
Gemini CLI   Gemini Pro     0.60        0.80        0.94    0.62       38%
```

---

## 实现计划

### Phase 1: Base Image + Lightweight Agent (1 week)

- [ ] `Dockerfile.base` — mock services + grading + task config
- [ ] 内置轻量 Python agent loop（ReAct，调 Anthropic API）
- [ ] `entrypoint_agent.sh` — start service → run agent → grade
- [ ] 验证：`docker run -e ANTHROPIC_API_KEY=... claw-harness:todo-001` 全自动输出分数
- [ ] 支持 `MODEL` 环境变量切换 backbone

### Phase 2: OpenClaw Agent Image (1 week)

- [ ] `Dockerfile.openclaw` — FROM base + Node.js + OpenClaw
- [ ] SKILL.md 自动生成（per-task）
- [ ] 验证：OpenClaw 在容器内自动完成 task
- [ ] 支持 OpenClaw 配置不同 backbone

### Phase 3: Additional Agents (1 week)

- [ ] `Dockerfile.nanoclaw`
- [ ] `Dockerfile.claude-code`
- [ ] `Dockerfile.gemini-cli`
- [ ] `Dockerfile.codex-cli`
- [ ] 每个 agent 至少通过 3 个 tasks

### Phase 4: Batch Runner + Leaderboard (1 week)

- [ ] `run_eval.sh` — batch evaluation script
- [ ] Pass^3 aggregation
- [ ] Leaderboard JSON + CSV 输出
- [ ] Paper-ready tables

### Phase 5: Full Evaluation (2 weeks)

- [ ] 5 agents × 3-5 models × 129 tasks × 3 trials
- [ ] 收集 ~5,000+ trajectories
- [ ] 生成 leaderboard
- [ ] 写 paper

---

## 与 SkillsBench 的对比

| | SkillsBench | Claw Harnessing |
|---|---|---|
| Tasks | 84 (human) | 129 (auto-generated) |
| Agents | 3 (Claude Code, Gemini CLI, Codex) | 5 (+ OpenClaw, NanoClaw) |
| Models | 7 | 5+ |
| Trajectories | 7,308 | ~9,675 (projected) |
| Skills condition | with/without/self-gen | N/A (tasks ARE the eval) |
| Verification | pytest | multi-strategy GradingEngine |
| Tasks source | human-written | auto-generated |
| Scoring | pass rate | 0-1 continuous (3 dimensions) |
| Safety | no | yes (multiplicative gate) |
| Robustness | no | yes (error injection) |
| Reproducibility | Pass^3 | Pass^3 |
