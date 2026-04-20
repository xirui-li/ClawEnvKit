#!/bin/bash
# ── Trajectory: agent-loop × all models on 50 sampled tasks ──
set -e
SAMPLES="${1:-50}"
DATASET="Auto-ClawEval"
RESULTS="trajectory_results"
SAMPLE_DIR="$RESULTS/_sample"

# Sample tasks (same seed as harness script)
mkdir -p "$SAMPLE_DIR"
python3 << PYEOF
import glob, random, shutil, os, yaml
random.seed(42)
tasks = sorted(glob.glob("$DATASET/*/*.yaml"))
sample = random.sample(tasks, min($SAMPLES, len(tasks)))
for f in sample:
    c = yaml.safe_load(open(f))
    tid = c.get("task_id", os.path.basename(f).replace(".yaml",""))
    cat = os.path.basename(os.path.dirname(f))
    dst = f"$SAMPLE_DIR/{cat}"
    os.makedirs(dst, exist_ok=True)
    shutil.copy2(f, f"{dst}/{tid}.yaml")
print(f"Sampled {len(sample)} tasks")
PYEOF

echo "=== Agent Loop × all models ($(find $SAMPLE_DIR -name '*.yaml' | wc -l | tr -d ' ') tasks) ==="
for m in anthropic/claude-haiku-4-5-20251001 anthropic/claude-opus-4.6 anthropic/claude-sonnet-4.6 \
         openai/gpt-5.4 openai/gpt-5-nano z-ai/glm-5 z-ai/glm-5-turbo \
         minimax/minimax-m2.5 minimax/minimax-m2.7; do
    echo "━━━ $m ━━━"
    python3 scripts/agent_loop_eval.py \
        --model "$m" --dataset "$SAMPLE_DIR" \
        --results "$RESULTS" --resume || echo "[WARN] $m failed"
    echo ""
done
echo "Done. Results in $RESULTS/"
