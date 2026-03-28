# Mac Mini 测试指南

在装有 OpenClaw + Docker/Colima 的 Mac Mini 上跑完整 E2E 测试。

---

## 前置条件

- [x] Mac Mini 有 Docker/Colima
- [x] Mac Mini 有 OpenClaw（`~/.openclaw/workspace/`）
- [x] Mac Mini 有 Python 3.11+

---

## Step 1: Clone 项目

```bash
cd ~/Codebase
git clone https://github.com/xirui-li/claw-harnessing.git
cd claw-harnessing
```

## Step 2: 安装依赖

```bash
pip install -r requirements.txt
pip install fastapi uvicorn pyyaml
```

## Step 3: 确认 Docker 可用

```bash
colima start        # 如果用 Colima
docker ps            # 应该能跑
```

## Step 4: 设置 API Key

```bash
# 方法 A: 用 config.json
cp config.json.example config.json
# 编辑 config.json，填入 claude API key:
# {"claude": "sk-ant-..."}

# 方法 B: 环境变量
export ANTHROPIC_API_KEY=sk-ant-...
```

---

## 测试 1: 生成任务（不需要 Docker）

```bash
# 列出可用服务
python -m scripts.grading.cli services

# 生成 3 个 todo 任务
python -m scripts.grading.cli generate --service todo --count 3 --difficulty easy --output /tmp/test-tasks

# 检查输出
ls /tmp/test-tasks/todo/
cat /tmp/test-tasks/todo/todo-001.yaml
```

**预期结果：** 3 个 `.yaml` 文件，每个有 prompt + scoring_components + safety_checks

---

## 测试 2: Docker Sandbox（核心测试）

### 2a: 构建 Docker Image

```bash
# 用 dataset 里已有的任务
docker build -f docker/Dockerfile \
  --build-arg TASK_YAML=dataset/todo/todo-001.yaml \
  --build-arg SERVICE_NAME=todo \
  -t claw-harness:todo-001 .

# 应该看到 "Successfully tagged claw-harness:todo-001"
```

### 2b: 运行容器

```bash
docker run -d --network none --name todo-test claw-harness:todo-001
sleep 3

# 查看任务描述
docker logs todo-test 2>&1 | head -20
```

### 2c: 模拟 Agent 操作

```bash
# 列出任务
docker exec todo-test curl -s -X POST http://localhost:9100/todo/tasks \
  -H 'Content-Type: application/json' -d '{}'

# 创建新任务
docker exec todo-test curl -s -X POST http://localhost:9100/todo/tasks/create \
  -H 'Content-Type: application/json' \
  -d '{"title":"Fix login page crash on mobile","description":"iOS crash","priority":"high","due_date":"2024-12-15"}'

# 再次列出
docker exec todo-test curl -s -X POST http://localhost:9100/todo/tasks \
  -H 'Content-Type: application/json' -d '{}'

# 写 agent 输出
docker exec todo-test sh -c \
  "echo 'Created high-priority bug fix task. Listed all tasks to confirm.' > /workspace/agent_output.txt"
```

### 2d: 停止 + 自动打分

```bash
# 停止容器触发 grading
docker stop -t 10 todo-test

# 拷出结果
docker cp todo-test:/logs/ /tmp/todo-results/

# 查看分数
cat /tmp/todo-results/reward.txt
# 预期: 0.70 ~ 0.90

# 查看详细评分
python3 -m json.tool /tmp/todo-results/grading.json

# 清理
docker rm todo-test
```

**预期结果：**
```
reward.txt: 0.90 左右
grading.json: 5-7 个 components，大部分 passed=true，safety=1.0
```

---

## 测试 3: OpenClaw Agent 测试

### 3a: 安装 Skill

```bash
ln -sf ~/Codebase/claw-harnessing ~/.openclaw/workspace/skills/clawharness
```

### 3b: 构建 + 运行容器

```bash
# 构建 gmail 任务
docker build -f docker/Dockerfile \
  --build-arg TASK_YAML=dataset/gmail/gmail-001.yaml \
  --build-arg SERVICE_NAME=gmail \
  -t claw-harness:gmail-001 .

# 运行（不隔离网络，让 OpenClaw 能 docker exec）
docker run -d --name gmail-test claw-harness:gmail-001

# 查看任务
docker exec gmail-test cat /workspace/task_prompt.txt
docker exec gmail-test cat /workspace/task_tools.json
```

### 3c: 让 OpenClaw 执行

在 OpenClaw session 中：

```
帮我完成这个任务。环境在 Docker 容器 gmail-test 里。

任务描述在: docker exec gmail-test cat /workspace/task_prompt.txt
API 文档在: docker exec gmail-test cat /workspace/task_tools.json
API 地址: http://localhost:9100

用 docker exec gmail-test curl ... 来调 API。
完成后把总结写到: docker exec gmail-test sh -c "echo '...' > /workspace/agent_output.txt"
```

### 3d: 打分

```bash
docker stop -t 10 gmail-test
docker cp gmail-test:/logs/ /tmp/gmail-results/
cat /tmp/gmail-results/reward.txt
python3 -m json.tool /tmp/gmail-results/grading.json
docker rm gmail-test
```

---

## 测试 4: 批量评估（可选）

```bash
# 对所有 todo 任务跑评估
for task in dataset/todo/todo-*.yaml; do
    TASK_ID=$(python3 -c "import yaml; print(yaml.safe_load(open('$task')).get('task_id',''))")
    echo "=== $TASK_ID ==="

    docker build -f docker/Dockerfile \
      --build-arg TASK_YAML=$task \
      --build-arg SERVICE_NAME=todo \
      -t claw-harness:$TASK_ID . 2>/dev/null

    docker run -d --network none --name $TASK_ID claw-harness:$TASK_ID
    sleep 3

    # Simple agent: just list tasks
    docker exec $TASK_ID curl -s -X POST http://localhost:9100/todo/tasks \
      -H 'Content-Type: application/json' -d '{}' > /dev/null

    docker stop -t 5 $TASK_ID 2>/dev/null

    REWARD=$(docker cp $TASK_ID:/logs/reward.txt /dev/stdout 2>/dev/null)
    echo "  Score: $REWARD"

    docker rm $TASK_ID > /dev/null 2>&1
done
```

---

## 常见问题

### Docker build 失败
```
ERROR: "mock_services/todo/server.py" not found
```
确保从项目根目录运行 `docker build`，不是从 `docker/` 子目录。

### Mock service 没启动
```
curl: (7) Failed to connect to localhost port 9100
```
等几秒再试，或者检查 `docker logs <container>` 看错误信息。

### 分数为 0
检查 `grading.json` 里的 `safety_violations`——可能 agent 调了不该调的 API（如 delete_task）。

### Colima 不能挂载
确保 Dockerfile 里的 path 都在 `$HOME` 下，Colima 默认只挂载 home 目录。
