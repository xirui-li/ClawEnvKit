# Claw Harnessing — Test Guide

## Prerequisites

- Python 3.11+
- Colima + Docker CLI (or Docker Desktop)
- `ANTHROPIC_API_KEY` environment variable (for E2E tests)

## Setup

```bash
git clone https://github.com/xirui-li/claw-harnessing.git
cd claw-harnessing
pip install -r requirements.txt
```

## 1. Unit Tests (no Docker, no API key needed)

```bash
python -m pytest tests/ -v
```

134 tests across 7 modules: schema, intent_parser, task_generator, consistency_checker, image_builder, validator, exporter.

## 2. Dry-Run Pipeline Test (no Docker, no API key needed)

Runs the full pipeline with canned responses to verify state machine logic:

```bash
python scripts/mock_claw.py --dry-run \
  --input "3 cli tasks" \
  --output ~/clawharness-dryrun
```

Verify:
```bash
# Should have 3 lines
wc -l ~/clawharness-dryrun/train.jsonl

# Check state file
python scripts/serve.py --mode=status \
  --spec=~/clawharness-dryrun/.clawharness_state.json
```

## 3. E2E Test via mock_claw.py --api (requires Docker + API key)

```bash
# Start Docker
colima start
docker ps  # verify

# Set API key
export ANTHROPIC_API_KEY=sk-ant-...

# Run full pipeline with real LLM
python scripts/mock_claw.py --api \
  --input "生成 3 个 cli-file-ops 的训练任务，easy 难度" \
  --output ~/clawharness-e2e-test
```

Verify:
```bash
# Check output JSONL
cat ~/clawharness-e2e-test/train.jsonl | python3 -m json.tool

# Each line should have: task_id, instruction, docker_image, success_criteria

# Check Docker images were built
docker images | grep clawharness

# Check pipeline status
python scripts/serve.py --mode=status \
  --spec=~/clawharness-e2e-test/.clawharness_state.json

# Verify a Docker image works
docker run --rm clawharness/cli-file-ops/cli-file-ops-001:v1 ls /workspace/
```

## 4. E2E Test via OpenClaw (full integration)

```bash
# Install as OpenClaw skill
ln -s $(pwd) ~/.openclaw/workspace/skills/clawharness

# Verify skill is detected
# (in OpenClaw session) /context list
# → clawharness should appear

# Start Docker
colima start
```

In an OpenClaw session (TUI, browser, or messaging channel), send:
```
帮我生成 3 个 cli-file-ops 的训练任务，easy 难度，输出到 ~/clawharness-e2e-test
```

The agent should:
1. Call `serve.py --mode=parse` → run LLM → `parse_ingest`
2. Loop 3x: `task_prompt` → LLM → `task_ingest` → `fs_prompt` → LLM → `fs_ingest`
3. Loop 3x: `consistency_check` (may trigger LLM for hard tasks)
4. Call `build` → 3 Docker images
5. Loop 3x: `validate_prompt` → LLM → `validate_ingest`
6. Call `export` → `~/clawharness-e2e-test/train.jsonl`

Verify output same as Section 3 above.

## 5. MetaClaw Integration (post-validation)

After a successful E2E test, plug output into MetaClaw:

```bash
metaclaw config openclaw_env_data_dir ~/clawharness-e2e-test
metaclaw config openclaw_env_split train
metaclaw start --mode rl
```

## Cleanup

```bash
# Remove test outputs
rm -rf ~/clawharness-dryrun ~/clawharness-e2e-test

# Remove Docker images
docker images | grep clawharness | awk '{print $3}' | xargs docker rmi

# Remove build artifacts
rm -rf ~/.clawharness/build/
```
