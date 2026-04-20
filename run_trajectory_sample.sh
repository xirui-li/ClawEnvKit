#!/bin/bash
# ── Collect trajectories on a random 50-task sample ──
#
# Runs all harnesses (Haiku) + agent-loop (current models) on 50 sampled tasks.
# Results include llm_trajectory.jsonl for each task.
#
# Usage:
#   bash run_trajectory_sample.sh
#   bash run_trajectory_sample.sh --samples 20   # fewer samples

set -e

SAMPLES="${1:-50}"
DATASET="Auto-ClawEval"
RESULTS="trajectory_results"
HAIKU="anthropic/claude-haiku-4-5-20251001"

# ── Step 1: Sample tasks ──
echo "Sampling $SAMPLES tasks from $DATASET..."
SAMPLE_DIR="$RESULTS/_sample"
mkdir -p "$SAMPLE_DIR"

python3 << PYEOF
import glob, random, shutil, os, yaml
random.seed(42)

tasks = sorted(glob.glob("$DATASET/*/*.yaml"))
sample = random.sample(tasks, min($SAMPLES, len(tasks)))

os.makedirs("$SAMPLE_DIR", exist_ok=True)
for f in sample:
    c = yaml.safe_load(open(f))
    tid = c.get("task_id", os.path.basename(f).replace(".yaml",""))
    cat = os.path.basename(os.path.dirname(f))
    dst_dir = f"$SAMPLE_DIR/{cat}"
    os.makedirs(dst_dir, exist_ok=True)
    shutil.copy2(f, f"{dst_dir}/{tid}.yaml")

print(f"Sampled {len(sample)} tasks to $SAMPLE_DIR/")
PYEOF

TASK_COUNT=$(find "$SAMPLE_DIR" -name "*.yaml" -type f | wc -l | tr -d ' ')
echo "  $TASK_COUNT tasks sampled"
echo ""

# ── Step 2: Harness comparison (Haiku) ──
HARNESSES=(openclaw claudecode nanoclaw picoclaw zeroclaw copaw nemoclaw hermes)

echo "================================================"
echo "  Trajectory Collection"
echo "  Harnesses: ${#HARNESSES[@]} + agent-loop"
echo "  Model: $HAIKU"
echo "  Tasks: $TASK_COUNT"
echo "  Results: $RESULTS/"
echo "================================================"
echo ""

for harness in "${HARNESSES[@]}"; do
    echo "━━━ $harness (Haiku) ━━━"
    python3 scripts/evaluate.py \
        --harness "$harness" \
        --model "$HAIKU" \
        --dataset "$SAMPLE_DIR" \
        --results "$RESULTS" \
        --resume || echo "[WARN] $harness failed, continuing..."
    echo ""
done

# ── Step 3: Agent-loop (all current models) ──
MODELS=(
    "anthropic/claude-haiku-4-5-20251001"
    "anthropic/claude-opus-4.6"
    "anthropic/claude-sonnet-4.6"
    "openai/gpt-5.4"
    "openai/gpt-5-nano"
    "z-ai/glm-5"
    "z-ai/glm-5-turbo"
    "minimax/minimax-m2.5"
    "minimax/minimax-m2.7"
)

for model in "${MODELS[@]}"; do
    echo "━━━ agent-loop / $model ━━━"
    python3 scripts/agent_loop_eval.py \
        --model "$model" \
        --dataset "$SAMPLE_DIR" \
        --results "$RESULTS" \
        --resume || echo "[WARN] $model failed, continuing..."
    echo ""
done

# ── Step 4: Summary ──
echo "================================================"
echo "  Done. Checking trajectories..."
echo "================================================"

python3 << 'SUMMARY'
import glob, json, os

print(f"\n{'Run':<50} {'Tasks':>5} {'w/ Trajectory':>14}")
print("=" * 75)

# Docker harness results
for fw_dir in sorted(glob.glob("trajectory_results/*/")):
    fw = os.path.basename(fw_dir.rstrip("/"))
    if fw.startswith("_"): continue
    for model_dir in sorted(glob.glob(f"{fw_dir}*/")):
        model = os.path.basename(model_dir.rstrip("/"))
        total = len(glob.glob(f"{model_dir}*/grading.json"))
        has_traj = len(glob.glob(f"{model_dir}*/llm_trajectory.jsonl"))
        if total == 0: continue
        print(f"{fw}/{model:<48} {total:>5} {has_traj:>14}")

# Agent loop results
for model_dir in sorted(glob.glob("trajectory_results/agent-loop/*/")):
    model = os.path.basename(model_dir.rstrip("/"))
    total = len(glob.glob(f"{model_dir}*/result.json"))
    has_traj = sum(1 for f in glob.glob(f"{model_dir}*/result.json")
                   if json.load(open(f)).get("trajectory"))
    if total == 0: continue
    print(f"agent-loop/{model:<48} {total:>5} {has_traj:>14}")

print()
SUMMARY
