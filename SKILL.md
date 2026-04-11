---
name: clawenvkit
description: Generate training and evaluation environments for OpenClaw agents from natural language descriptions. Produces train.jsonl + Docker images for MetaClaw RL training.
metadata:
  openclaw:
    requires:
      bins: ["python3", "docker"]
---

# ClawEnvKit — Environment Generator

## When to activate

Activate this skill when the user asks to:
- 生成训练环境 / generate training environments
- 生成训练任务 / generate training tasks
- 创建 eval harness / create evaluation harness
- 生成 MetaClaw 任务 / generate MetaClaw tasks
- agent benchmark / 训练数据 / training data

## How it works

This skill calls `{baseDir}/scripts/serve.py` via bash to run a multi-step pipeline. The pipeline uses a JSON protocol: when it needs LLM reasoning, it returns `"status": "llm_needed"` with a prompt. You run the prompt, then pass the result back.

## Step-by-step instructions

### Step 1: Parse user intent

```bash
python3 {baseDir}/scripts/serve.py --mode=parse \
  --input="<user's description>" \
  --output="<output directory, default ~/clawenvkit-tasks>"
```

The response will be `"status": "llm_needed"` with a prompt. Run the prompt with your LLM, then call:

```bash
python3 {baseDir}/scripts/serve.py --mode=parse_ingest \
  --spec="<spec path from callback_args>" \
  --llm-response='<LLM response>'
```

You will receive a `GenerationSpec` with `task_count`, `domain`, etc. Report to the user:
> "好的，我理解了。生成 N 个 [difficulty] 难度的 [domain] 任务，输出到 [output_dir]。开始生成..."

### Step 2: Generate tasks

For each task index `i` from 0 to `task_count - 1`:

**2a. Generate instruction:**
```bash
python3 {baseDir}/scripts/serve.py --mode=task_prompt --spec="<spec path>" --index=<i>
```
→ Returns `llm_needed`. Run the prompt, then:
```bash
python3 {baseDir}/scripts/serve.py --mode=task_ingest --spec="<spec path>" --index=<i> --llm-response='<instruction>'
```

**2b. Generate filesystem + criteria:**
```bash
python3 {baseDir}/scripts/serve.py --mode=fs_prompt --spec="<spec path>" --index=<i>
```
→ Returns `llm_needed`. Run the prompt, then:
```bash
python3 {baseDir}/scripts/serve.py --mode=fs_ingest --spec="<spec path>" --index=<i> --llm-response='<JSON response>'
```

Report progress after every 5 tasks:
> "正在生成第 5/20 个任务... ✓"

### Step 3: Consistency check

For each task index `i`:
```bash
python3 {baseDir}/scripts/serve.py --mode=consistency_check --spec="<spec path>" --index=<i>
```

If the response is `"status": "llm_needed"` (hard tasks only), run the prompt and call:
```bash
python3 {baseDir}/scripts/serve.py --mode=consistency_ingest --spec="<spec path>" --index=<i> --llm-response='<JSON response>'
```

If any task fails with `"regenerate": true`, go back to Step 2 for that task index (max 3 retries).

### Step 4: Build Docker images

```bash
python3 {baseDir}/scripts/serve.py --mode=build --spec="<spec path>"
```

This builds all Docker images. Report to user:
> "Docker images 构建完成 (N/N)，开始验证..."

If `"failed" > 0`, report which tasks failed.

### Step 5: Validate tasks

For each task index `i`:
```bash
python3 {baseDir}/scripts/serve.py --mode=validate_prompt --spec="<spec path>" --index=<i>
```
→ Returns `llm_needed`. Run the prompt (as a solver), then:
```bash
python3 {baseDir}/scripts/serve.py --mode=validate_ingest --spec="<spec path>" --index=<i> --llm-response='<JSON with reasoning + actions>'
```

### Step 6: Export

```bash
python3 {baseDir}/scripts/serve.py --mode=export --spec="<spec path>" --output="<output dir>"
```

Report final results to user:
> "完成！生成了 N 个有效任务：
> - 📁 <output_dir>/train.jsonl
> - 🐳 N 个 Docker images
> - ✅ N passed, ❌ M failed validation (excluded)
>
> 可以直接用于 MetaClaw：
>   metaclaw config openclaw_env_data_dir <output_dir>
>   metaclaw start --mode rl"

## Error handling

- If any `serve.py` call returns `"status": "error"`, report the error message to the user and ask if they want to retry.
- If LLM returns malformed JSON, retry the same prompt once before reporting failure.
- If Docker is not running, tell the user: "Docker 没有运行。请先启动 Colima: `colima start`"

## Status check

At any time, you can check pipeline status:
```bash
python3 {baseDir}/scripts/serve.py --mode=status --spec="<spec path>"
```
