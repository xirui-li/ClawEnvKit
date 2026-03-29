# Volume-Based Task Execution Design

## 目标

Build 一次 base image，通过 volume mount 切换 task，零重建跑 129 个 task。

---

## 架构

```
Base Image（build 一次，~200MB 或 ~1.5GB with OpenClaw）
├── 19 mock services（gmail, todo, calendar...）
├── GradingEngine（14 check types）
├── Agent（ReAct loop 或 OpenClaw）
└── entrypoint.sh

Volume Mount（每次跑不同 task）
├── task.yaml → /opt/claw-harness/task.yaml:ro    （只读！）
└── results/  → /logs                              （写入）

Environment Variables
├── SERVICE_NAME=todo          （哪个 mock service）
├── ANTHROPIC_API_KEY=sk-...   （LLM API）
├── MODEL=claude-sonnet-4-6    （backbone）
└── MAX_TURNS=15               （agent 最大轮数）
```

---

## 使用方式

```bash
# Build 一次
docker build -f docker/Dockerfile -t claw-harness:base .

# 跑不同 task（零重建）
docker run --rm \
  -e ANTHROPIC_API_KEY=$KEY \
  -e SERVICE_NAME=todo \
  -v $(pwd)/dataset/todo/todo-001.yaml:/opt/claw-harness/task.yaml:ro \
  -v /tmp/results/todo-001:/logs \
  claw-harness:base

docker run --rm \
  -e ANTHROPIC_API_KEY=$KEY \
  -e SERVICE_NAME=gmail \
  -v $(pwd)/dataset/gmail/gmail-003.yaml:/opt/claw-harness/task.yaml:ro \
  -v /tmp/results/gmail-003:/logs \
  claw-harness:base
```

---

## Dockerfile 改动

### 之前（per-task build）
```dockerfile
ARG TASK_YAML=task.yaml           # ← 每个 task 不同
ARG SERVICE_NAME=todo             # ← 每个 task 不同
COPY ${TASK_YAML} /opt/claw-harness/task.yaml
ENV SERVICE_NAME=${SERVICE_NAME}
```

### 之后（volume mount）
```dockerfile
# 不再 COPY task.yaml，运行时 mount 进来
# SERVICE_NAME 通过 -e 传入
ENV TASK_YAML=/opt/claw-harness/task.yaml
ENV PYTHONPATH=/opt/claw-harness
ENV PORT=9100
ENV MAX_TURNS=15
ENV MODEL=claude-sonnet-4-6
```

---

## Entrypoint 改动

### 启动时检查 task.yaml 存在
```bash
if [ ! -f "$TASK_YAML" ]; then
    echo "[harness] ERROR: No task.yaml found at $TASK_YAML" >&2
    echo "[harness] Mount with: -v /path/to/task.yaml:$TASK_YAML:ro" >&2
    exit 1
fi
```

### SERVICE_NAME 自动推断
```bash
# 如果没通过 -e 传入，从 task.yaml 自动推断
if [ -z "$SERVICE_NAME" ]; then
    SERVICE_NAME=$(python3 -c "import yaml; print(yaml.safe_load(open('$TASK_YAML')).get('task_id','').split('-')[0])")
    export SERVICE_NAME
fi
```

---

## 风险与对策

### 1. task.yaml 被意外修改
**风险：** entrypoint 或 agent 写入 mount 的 task.yaml，污染宿主机 dataset。
**对策：** 强制 read-only mount (`:ro`)。entrypoint 启动时 copy 到容器内临时位置再使用：
```bash
cp "$TASK_YAML" /tmp/task_config.yaml
# 后续全部读 /tmp/task_config.yaml
```

### 2. 结果目录冲突
**风险：** 多个容器写同一个 `/tmp/results`。
**对策：** 每个 task 用独立 results 目录：
```bash
-v /tmp/results/todo-001:/logs    # task 1
-v /tmp/results/todo-002:/logs    # task 2
```
批量脚本自动用 task_id 作目录名。

### 3. 文件权限
**风险：** 容器内 root 写的 /logs 文件，宿主机普通用户读不了。
**对策：** entrypoint 结束前 chmod：
```bash
chmod -R 777 /logs 2>/dev/null
```

### 4. Colima mount 路径
**风险：** Colima 只挂载 `$HOME`，`/tmp` 可能不可用。
**对策：** 结果目录用 `~/claw-results/` 而不是 `/tmp/`：
```bash
-v ~/claw-results/todo-001:/logs
```

### 5. Fixtures 引用外部文件
**风险：** task.yaml 里的 fixtures 如果引用 PDF/图片等外部文件，volume 只 mount 了 yaml。
**对策：** 当前所有 fixtures 都是 inline JSON（内嵌在 yaml 里），不引用外部文件。如果以后需要，加第二个 volume：
```bash
-v $(pwd)/dataset/todo/fixtures:/opt/claw-harness/fixtures:ro
```

### 6. SERVICE_NAME 不匹配
**风险：** `-e SERVICE_NAME=gmail` 但 task.yaml 里是 todo 的 task，mock service 和 scoring 不匹配。
**对策：** entrypoint 自动从 task.yaml 推断 SERVICE_NAME，忽略环境变量（或做一致性检查）：
```bash
YAML_SERVICE=$(python3 -c "...")
if [ -n "$SERVICE_NAME" ] && [ "$SERVICE_NAME" != "$YAML_SERVICE" ]; then
    echo "[harness] WARNING: SERVICE_NAME=$SERVICE_NAME but task.yaml is $YAML_SERVICE" >&2
    echo "[harness] Using $YAML_SERVICE from task.yaml" >&2
fi
SERVICE_NAME="$YAML_SERVICE"
```

---

## 批量执行脚本

```bash
#!/bin/bash
# run_all.sh — 跑所有 129 tasks

IMAGE="claw-harness:base"
RESULTS_DIR="$HOME/claw-results"
KEY=$(cat config.json | python3 -c "import sys,json; print(json.load(sys.stdin)['claude'])")

mkdir -p "$RESULTS_DIR"

for task_yaml in dataset/*/todo-*.yaml dataset/*/gmail-*.yaml dataset/*/calendar-*.yaml; do
    TASK_ID=$(python3 -c "import yaml; print(yaml.safe_load(open('$task_yaml')).get('task_id','unknown'))")
    SERVICE=$(echo "$TASK_ID" | cut -d'-' -f1)
    TASK_RESULTS="$RESULTS_DIR/$TASK_ID"

    # Skip if already done
    if [ -f "$TASK_RESULTS/reward.txt" ]; then
        echo "SKIP $TASK_ID ($(cat $TASK_RESULTS/reward.txt))"
        continue
    fi

    echo -n "$TASK_ID: "

    docker run --rm \
        -e ANTHROPIC_API_KEY="$KEY" \
        -e SERVICE_NAME="$SERVICE" \
        -v "$(pwd)/$task_yaml:/opt/claw-harness/task.yaml:ro" \
        -v "$TASK_RESULTS:/logs" \
        "$IMAGE" 2>/dev/null | tail -1

done

# Summary
echo ""
echo "=== Results ==="
for d in "$RESULTS_DIR"/*/; do
    TASK_ID=$(basename "$d")
    SCORE=$(cat "$d/reward.txt" 2>/dev/null || echo "FAIL")
    echo "$TASK_ID: $SCORE"
done | sort
```

---

## 两种 base image

```bash
# 轻量版（ReAct loop，~200MB，build 30s）
docker build -f docker/Dockerfile -t claw-harness:base .

# OpenClaw 版（完整 agent，~1.5GB，build 10min）
docker build -f docker/Dockerfile.openclaw -t claw-harness:openclaw .
```

两个 image 共享相同的 volume mount 接口，只是内部 agent 不同。

---

## 实现清单

- [ ] 修改 `docker/Dockerfile`：去掉 `ARG TASK_YAML` 和 `COPY ${TASK_YAML}`
- [ ] 修改 `docker/Dockerfile.openclaw`：同上
- [ ] 修改 `docker/entrypoint_auto.sh`：
  - [ ] 添加 task.yaml 存在性检查
  - [ ] 自动推断 SERVICE_NAME
  - [ ] copy task.yaml 到 /tmp（防止写回宿主机）
  - [ ] 结束前 chmod /logs
  - [ ] SERVICE_NAME 一致性检查
- [ ] 修改 `docker/entrypoint_openclaw.sh`：同上
- [ ] 写 `scripts/run_all.sh`：批量执行脚本
- [ ] 更新 MAC_MINI_TEST.md：volume mount 用法
- [ ] 测试：同一个 image 跑 3 个不同 service 的 task
