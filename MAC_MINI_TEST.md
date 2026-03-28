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

colima start    # 如果用 Colima
docker ps       # 确认 Docker 可用
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

## 测试 4: 批量评估

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

## 测试 5: 生成新 task 并评估

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

## 测试 6: 自动生成新 service + task

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
