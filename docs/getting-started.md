# Getting Started

## Installation

```bash
git clone https://github.com/xirui-li/ClawHarnessing.git
cd ClawHarnessing
pip install -e .
```

## Set API Key

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

## Build Docker Image

Build once, use for all tasks:

```bash
docker build -f docker/Dockerfile -t clawharness:base .
```

## Run Your First Evaluation

```bash
clawharness eval todo-001
```

Or via Docker directly:

```bash
docker run --rm \
  -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY \
  -v ./dataset/todo/todo-001.yaml:/opt/clawharness/task.yaml:ro \
  -v /tmp/results:/logs \
  clawharness:base
```

## Check Results

```bash
cat /tmp/results/reward.txt          # 0.9200
cat /tmp/results/grading.json | python3 -m json.tool
```

## Commands

```bash
# Evaluate
clawharness eval todo-001                        # single task
clawharness eval todo-001 --model claude-3-haiku  # specific model
clawharness eval-all --service todo              # all tasks for a service
clawharness eval-all                              # all tasks

# Generate tasks (unified --services interface)
clawharness generate --services todo --count 10                      # single-service
clawharness generate --services calendar,contacts,gmail --count 5    # cross-service
clawharness generate --category workflow --count 5                   # category shortcut

# List available services and categories
clawharness services                              # 13 services
clawharness categories                            # 8 cross-service categories
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | (required) | API key for agent + LLM judge |
| `MODEL` | `claude-sonnet-4-6` | LLM model for the agent |
| `MAX_TURNS` | `15` | Maximum agent turns |
| `PORT` | `9100` | Mock service port |
| `ERROR_RATE` | `0` | Error injection rate (0.0-1.0) |

## OpenClaw Evaluation

For running OpenClaw agent inside Docker with native tool integration:

```bash
# Build OpenClaw base image (once)
cd /path/to/openclaw
docker build -t openclaw:latest .

# Build evaluation image (once)
cd /path/to/ClawHarnessing
docker build -f docker/Dockerfile.openclaw -t claw-harness-openclaw .

# Run (volume-mount any task)
docker run --rm \
  -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY \
  -v ./dataset/todo/todo-001.yaml:/opt/clawharness/task.yaml:ro \
  -v /tmp/openclaw-results:/logs \
  claw-harness-openclaw
```

See [OpenClaw Integration](agents/openclaw.md) for details.

## Multi-Agent Comparison

```bash
TASK=dataset/todo/todo-001.yaml
for agent in openclaw nanoclaw ironclaw copaw; do
    echo -n "$agent: "
    docker run --rm \
      -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY \
      -v $(pwd)/$TASK:/opt/clawharness/task.yaml:ro \
      claw-harness-$agent 2>/dev/null | tail -1
done
```
