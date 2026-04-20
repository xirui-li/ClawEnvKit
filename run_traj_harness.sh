#!/bin/bash
# ── Trajectory: all harnesses × Haiku on 50 sampled tasks ──
set -e
SAMPLES="${1:-50}"
DATASET="Auto-ClawEval"
RESULTS="trajectory_results"
HAIKU="anthropic/claude-haiku-4-5-20251001"
SAMPLE_DIR="$RESULTS/_sample"

# Sample tasks (shared with agent-loop script, same seed)
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

echo "=== Harness × Haiku ($(find $SAMPLE_DIR -name '*.yaml' | wc -l | tr -d ' ') tasks) ==="
for h in openclaw claudecode nanoclaw picoclaw zeroclaw copaw nemoclaw hermes; do
    echo "━━━ $h ━━━"
    python3 scripts/evaluate.py \
        --harness "$h" --model "$HAIKU" \
        --dataset "$SAMPLE_DIR" --results "$RESULTS" \
        --resume || echo "[WARN] $h failed"
    echo ""
done
echo "Done. Results in $RESULTS/"
