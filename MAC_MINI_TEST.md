# Mac Mini 测试指南

## 前置条件

- Docker / Colima 已安装并运行
- Anthropic API key

## Setup

```bash
cd ~/Codebase/claw-harnessing
git pull
pip install -r requirements.txt
pip install fastapi uvicorn pyyaml anthropic

# Colima 需要 8GB 内存（OpenClaw build 需要）
colima start --cpu 4 --memory 8
docker ps       # 确认 Docker 可用

# 安装 buildx（OpenClaw Dockerfile 需要）
brew install docker-buildx
mkdir -p ~/.docker/cli-plugins
ln -sf $(brew --prefix)/bin/docker-buildx ~/.docker/cli-plugins/docker-buildx
```

---

## 测试 1: 一条命令全自动评估（核心）

```bash
# Build
docker build -f docker/Dockerfile \
  --build-arg TASK_YAML=dataset/todo/todo-001.yaml \
  --build-arg SERVICE_NAME=todo \
  -t claw-harness:todo-001 .

# Run — agent 自动执行，自动打分
ANTHROPIC_API_KEY=你的key docker run --rm \
  -e ANTHROPIC_API_KEY \
  -e MODEL=claude-sonnet-4-6 \
  -v /tmp/results:/logs \
  claw-harness:todo-001
```

**预期输出：**
```
[harness] Task: create_high_priority_bug_task
[harness] Starting todo...
[agent] Turn 1/15 — create_task
[agent] Turn 2/15 — list_tasks
[agent] Completed in 3 turns, 12.8s
Score: 0.90
  ✅ [30%] task_created: 1.00
  ✅ [20%] task_title_correct: 1.00
  ...
0.9000
```

**查看详细结果：**
```bash
cat /tmp/results/reward.txt          # 0.9000
cat /tmp/results/grading.json | python3 -m json.tool
cat /tmp/results/efficiency.json     # turns, tokens, wall_time
```

---

## 测试 2: 切换不同 model

```bash
# Claude Haiku (弱模型)
ANTHROPIC_API_KEY=你的key docker run --rm \
  -e ANTHROPIC_API_KEY \
  -e MODEL=claude-3-haiku-20240307 \
  -v /tmp/results-haiku:/logs \
  claw-harness:todo-001

# Claude Sonnet (中等)
ANTHROPIC_API_KEY=你的key docker run --rm \
  -e ANTHROPIC_API_KEY \
  -e MODEL=claude-sonnet-4-6 \
  -v /tmp/results-sonnet:/logs \
  claw-harness:todo-001

# 比较分数
echo "Haiku: $(cat /tmp/results-haiku/reward.txt)"
echo "Sonnet: $(cat /tmp/results-sonnet/reward.txt)"
```

---

## 测试 3: 不同 service 的 task

```bash
# Gmail task
docker build -f docker/Dockerfile \
  --build-arg TASK_YAML=dataset/gmail/gmail-001.yaml \
  --build-arg SERVICE_NAME=gmail \
  -t claw-harness:gmail-001 .

ANTHROPIC_API_KEY=你的key docker run --rm \
  -e ANTHROPIC_API_KEY \
  -v /tmp/results-gmail:/logs \
  claw-harness:gmail-001

# Helpdesk task
docker build -f docker/Dockerfile \
  --build-arg TASK_YAML=dataset/helpdesk/helpdesk-001.yaml \
  --build-arg SERVICE_NAME=helpdesk \
  -t claw-harness:helpdesk-001 .

ANTHROPIC_API_KEY=你的key docker run --rm \
  -e ANTHROPIC_API_KEY \
  -v /tmp/results-helpdesk:/logs \
  claw-harness:helpdesk-001
```

---

## 测试 4: OpenClaw Agent 在容器内跑（完整 agent 评估 + 原生 Tool）

```bash
# Step 1: Build OpenClaw base image（首次需要，之后缓存）
cd ~/Codebase/openclaw
DOCKER_BUILDKIT=1 docker build -t openclaw:latest .
# ⚠️ 需要 8GB 内存 + buildx

# Step 2: Build evaluation image（含 clawharness-eval plugin）
cd ~/Codebase/claw-harnessing
docker build -f docker/Dockerfile.openclaw -t claw-harness-openclaw .

# Step 3: Run — volume-mount task.yaml
ANTHROPIC_API_KEY=你的key docker run --rm \
  -e ANTHROPIC_API_KEY \
  -v $(pwd)/dataset/todo/todo-001.yaml:/opt/clawharness/task.yaml:ro \
  -v /tmp/openclaw-results:/logs \
  claw-harness-openclaw
```

**容器内部流程：**
```
1. 启动 todo mock service (port 9100)
2. 从 OpenAPI spec + task.yaml 生成 tool 定义 → /tmp/eval-tools.json
3. 启动 OpenClaw gateway → 加载 clawharness-eval plugin
   → 注册原生 tool: create_task, list_tasks, update_task, delete_task
4. 运行 OpenClaw agent → 看到原生 tool，自然调用（跟 sendSlackMessage 一样）
5. 收集 audit log → GradingEngine 打分
```

**预期输出：**
```
[harness] Task: create_high_priority_bug_task
[harness] Starting todo...
[harness] todo ready
[harness] Generated 4 tool definitions
[harness] Configuring OpenClaw...
[harness] Starting OpenClaw gateway...
[harness] Gateway ready
[harness] Running OpenClaw agent...
(OpenClaw agent 通过原生 tool 调 mock API)
Score: 0.90
  ✅ task_created: 1.00
  ✅ task_title_correct: 1.00
  ...
0.9000
```

**对比两种 agent 在同一 task 上的分数：**
```bash
echo "ReAct loop: $(cat /tmp/results/reward.txt)"
echo "OpenClaw:   $(cat /tmp/openclaw-results/reward.txt)"
```

**注意：** OpenClaw 镜像只需 build 一次，所有 task 通过 volume-mount 切换。不需要 per-task rebuild。

---

## 测试 4b: 其他 Agent 框架（NanoClaw, IronClaw, ...）

所有非 OpenClaw 框架共享同一套 Skill+curl 机制。以 NanoClaw 为例：

```bash
# Step 1: Build NanoClaw base image
cd ~/Codebase/nanoclaw
docker build -t nanoclaw:latest .

# Step 2: Build evaluation image
cd ~/Codebase/claw-harnessing
docker build -f docker/Dockerfile.nanoclaw -t claw-harness-nanoclaw .

# Step 3: Run
ANTHROPIC_API_KEY=你的key docker run --rm \
  -e ANTHROPIC_API_KEY \
  -v $(pwd)/dataset/todo/todo-001.yaml:/opt/clawharness/task.yaml:ro \
  -v /tmp/nanoclaw-results:/logs \
  claw-harness-nanoclaw
```

**其他框架同理，替换对应的 Dockerfile：**

| Framework | Build Command |
|-----------|---------------|
| NanoClaw | `docker build -f docker/Dockerfile.nanoclaw -t claw-harness-nanoclaw .` |
| IronClaw | `docker build -f docker/Dockerfile.ironclaw -t claw-harness-ironclaw .` |
| CoPaw | `docker build -f docker/Dockerfile.copaw -t claw-harness-copaw .` |
| PicoClaw | `docker build -f docker/Dockerfile.picoclaw -t claw-harness-picoclaw .` |
| ZeroClaw | `docker build -f docker/Dockerfile.zeroclaw -t claw-harness-zeroclaw .` |
| NemoClaw | `docker build -f docker/Dockerfile.nemoclaw -t claw-harness-nemoclaw .` |
| Hermes | `docker build -f docker/Dockerfile.hermes -t claw-harness-hermes .` |

**多 Agent 对比同一 task：**
```bash
TASK=dataset/todo/todo-001.yaml
for agent in openclaw nanoclaw ironclaw copaw; do
    echo -n "$agent: "
    docker run --rm \
      -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY \
      -v $(pwd)/$TASK:/opt/clawharness/task.yaml:ro \
      -v /tmp/results-$agent:/logs \
      claw-harness-$agent 2>/dev/null | tail -1
done
```

---

## 测试 4c: Cross-Service Tasks

```bash
# 生成跨 service 任务
clawharness generate --category workflow --count 3 --difficulty medium --output /tmp/cross-tasks

# 或者直接指定 services
clawharness generate --services calendar,contacts,gmail --count 3 --output /tmp/cross-tasks

# 用 OpenClaw 跑（自动启动多个 mock service）
docker run --rm \
  -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY \
  -v /tmp/cross-tasks/workflow/workflow-001.yaml:/opt/clawharness/task.yaml:ro \
  -v /tmp/cross-results:/logs \
  claw-harness-openclaw
```

**预期：** Agent 会调用多个 service 的 API（如 calendar + contacts + gmail），audit 记录分 service 收集。

---

## 测试 5: 批量评估

```bash
#!/bin/bash
# 跑所有 todo tasks
for task in dataset/todo/todo-*.yaml; do
    TASK_ID=$(python3 -c "import yaml; print(yaml.safe_load(open('$task')).get('task_id',''))")

    docker build -f docker/Dockerfile \
      --build-arg TASK_YAML=$task \
      --build-arg SERVICE_NAME=todo \
      -t claw-harness:$TASK_ID . 2>/dev/null

    echo -n "$TASK_ID: "
    ANTHROPIC_API_KEY=你的key docker run --rm \
      -e ANTHROPIC_API_KEY \
      -e MODEL=claude-sonnet-4-6 \
      -v /tmp/batch-results/$TASK_ID:/logs \
      claw-harness:$TASK_ID 2>/dev/null | tail -1
done
```

---

## 测试 6: 生成新 task 并评估

```bash
# 生成 3 个 calendar tasks
python -m scripts.grading.cli generate \
  --service calendar --count 3 --difficulty medium \
  --output /tmp/new-tasks

# Build 并跑
for task in /tmp/new-tasks/calendar/*.yaml; do
    TASK_ID=$(python3 -c "import yaml; print(yaml.safe_load(open('$task')).get('task_id',''))")

    docker build -f docker/Dockerfile \
      --build-arg TASK_YAML=$task \
      --build-arg SERVICE_NAME=calendar \
      -t claw-harness:$TASK_ID . 2>/dev/null

    echo -n "$TASK_ID: "
    ANTHROPIC_API_KEY=你的key docker run --rm \
      -e ANTHROPIC_API_KEY \
      -v /tmp/new-results/$TASK_ID:/logs \
      claw-harness:$TASK_ID 2>/dev/null | tail -1
done
```

---

## 测试 7: 自动生成新 service + task

```bash
# 从描述自动生成 Spotify mock service
python3 -c "
from scripts.grading.service_generator import generate_and_install
generate_and_install('spotify', 'Music streaming — search, play, pause, playlists')
"

# 为新 service 生成 task
python -m scripts.grading.cli generate \
  --service spotify --count 1 --difficulty easy \
  --output /tmp/spotify-tasks

# Build 并跑
docker build -f docker/Dockerfile \
  --build-arg TASK_YAML=/tmp/spotify-tasks/spotify/spotify-001.yaml \
  --build-arg SERVICE_NAME=spotify \
  -t claw-harness:spotify-001 . 2>/dev/null

ANTHROPIC_API_KEY=你的key docker run --rm \
  -e ANTHROPIC_API_KEY \
  -v /tmp/spotify-results:/logs \
  claw-harness:spotify-001
```

---

## 环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `ANTHROPIC_API_KEY` | (必填) | API key |
| `MODEL` | `claude-sonnet-4-6` | LLM model |
| `MAX_TURNS` | `15` | agent 最大轮数 |
| `PORT` | `9100` | mock service 端口 |

---

## 常见问题

**Docker build 失败**
```
确保从项目根目录运行，不是 docker/ 子目录
```

**Score 为 0.00**
```bash
# 检查是否有 safety violation
cat /tmp/results/grading.json | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('safety_violations',[]))"
```

**Agent 一直 "Unknown tool"**
```
可能是 task.yaml 里的 tool name 跟 scoring_components 里的 action name 不匹配
```

**Colima mount 问题**
```
所有路径必须在 $HOME 下，Colima 默认只挂载 home 目录
```
