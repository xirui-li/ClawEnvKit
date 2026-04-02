#!/bin/bash
# Experiment 1: Discriminability — Run strong (Opus) + weak (Haiku) on all tasks
#
# Usage:
#   cd claw-harnessing
#   bash paper_experiments/exp1_task_quality/run_discriminability.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
RESULTS_DIR="$SCRIPT_DIR/results"
DATASET_DIR="$PROJECT_DIR/dataset"
IMAGE="claw-harness-openclaw"

# --- Load API key ---
if [ -z "$ANTHROPIC_API_KEY" ]; then
    ANTHROPIC_API_KEY=$(python3 -c "import json; print(json.load(open('$PROJECT_DIR/config.json')).get('claude',''))" 2>/dev/null || true)
fi
if [ -z "$ANTHROPIC_API_KEY" ]; then
    echo "ERROR: No ANTHROPIC_API_KEY set"
    exit 1
fi
export ANTHROPIC_API_KEY

# --- Check Docker ---
if ! docker info > /dev/null 2>&1; then
    echo "ERROR: Docker not running. Start Colima: colima start"
    exit 1
fi

# --- Check image ---
if ! docker images --format '{{.Repository}}' | grep -q "^${IMAGE}$"; then
    echo "Building $IMAGE..."
    docker build -f "$PROJECT_DIR/docker/Dockerfile.openclaw" -t "$IMAGE" "$PROJECT_DIR"
fi

mkdir -p "$RESULTS_DIR"

# --- Models ---
STRONG_MODEL="claude-opus-4-6"
WEAK_MODEL="claude-haiku-4-5"

# --- Find all tasks ---
TASKS=$(find "$DATASET_DIR" -name "*.yaml" -not -name "generation_meta.json" | sort)
TASK_COUNT=$(echo "$TASKS" | wc -l | tr -d ' ')
echo "=== Discriminability Experiment ==="
echo "Tasks: $TASK_COUNT"
echo "Strong model: $STRONG_MODEL"
echo "Weak model: $WEAK_MODEL"
echo "Results: $RESULTS_DIR/"
echo ""

# --- Run function ---
run_model() {
    local model="$1"
    local model_label="$2"
    local csv_file="$RESULTS_DIR/disc_${model_label}.csv"

    # Create header if file doesn't exist
    if [ ! -f "$csv_file" ]; then
        echo "task_id,score,model" > "$csv_file"
    fi

    local i=0
    for task in $TASKS; do
        i=$((i + 1))
        task_id=$(python3 -c "import yaml; print(yaml.safe_load(open('$task')).get('task_id','unknown'))")

        # Skip if already done
        if grep -q "^$task_id," "$csv_file" 2>/dev/null; then
            score=$(grep "^$task_id," "$csv_file" | cut -d',' -f2)
            echo "  [$i/$TASK_COUNT] SKIP $task_id ($score)"
            continue
        fi

        echo -n "  [$i/$TASK_COUNT] $task_id ($model_label): "

        # Create trace directory
        local trace_dir="$RESULTS_DIR/traces/${model_label}/${task_id}"
        mkdir -p "$trace_dir"

        # Run in Docker
        output=$(docker run --rm --user root \
            -e ANTHROPIC_API_KEY \
            -e MODEL="$model" \
            -v "$task:/opt/clawharness/task.yaml:ro" \
            "$IMAGE" 2>&1) || true

        # Save trajectory
        echo "$output" > "$trace_dir/trajectory.log"
        echo "$output" | grep -E "^Score:|^  [✅❌]" > "$trace_dir/scoring.txt" 2>/dev/null

        # Extract score (last line matching 0.XXXX)
        score=$(echo "$output" | grep -E '^[0-9]+\.[0-9]+$' | tail -1)

        if [ -n "$score" ]; then
            echo "$score"
            echo "$task_id,$score,$model" >> "$csv_file"
        else
            # Record as missing, NOT as 0 — don't pollute data
            echo "FAIL (not recorded in CSV)"
        fi
    done

    echo ""
}

# --- Run ---
echo "=== Running $STRONG_MODEL (strong) ==="
run_model "$STRONG_MODEL" "opus"

echo "=== Running $WEAK_MODEL (weak) ==="
run_model "$WEAK_MODEL" "haiku"

# --- Compute discriminability ---
echo "=== Computing discriminability ==="
python3 << 'DISC_EOF'
import csv
import json
import os

results_dir = os.environ.get("RESULTS_DIR", "paper_experiments/exp1_task_quality/results")

def load_scores(path):
    scores = {}
    with open(path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            scores[row["task_id"]] = float(row["score"])
    return scores

opus = load_scores(f"{results_dir}/disc_opus.csv")
haiku = load_scores(f"{results_dir}/disc_haiku.csv")

# Only compare tasks that both models completed
common = set(opus.keys()) & set(haiku.keys())
print(f"\n  Opus completed: {len(opus)} tasks")
print(f"  Haiku completed: {len(haiku)} tasks")
print(f"  Both completed: {len(common)} tasks")

if not common:
    print("  No common tasks — cannot compute discriminability")
    exit(0)

# Per-task discriminability
disc_per_task = {t: opus[t] - haiku[t] for t in common}
disc_values = list(disc_per_task.values())

opus_scores = [opus[t] for t in sorted(common)]
haiku_scores = [haiku[t] for t in sorted(common)]

opus_mean = sum(opus_scores) / len(opus_scores)
haiku_mean = sum(haiku_scores) / len(haiku_scores)
disc_mean = sum(disc_values) / len(disc_values)

# Std dev
import math
opus_std = math.sqrt(sum((s - opus_mean)**2 for s in opus_scores) / len(opus_scores))
haiku_std = math.sqrt(sum((s - haiku_mean)**2 for s in haiku_scores) / len(haiku_scores))
disc_std = math.sqrt(sum((d - disc_mean)**2 for d in disc_values) / len(disc_values))

# Count how many tasks Opus > Haiku
opus_wins = sum(1 for d in disc_values if d > 0)

print(f"\n  Results:")
print(f"  Opus (strong):  mean={opus_mean:.3f} ± {opus_std:.3f}")
print(f"  Haiku (weak):   mean={haiku_mean:.3f} ± {haiku_std:.3f}")
print(f"  Disc(E) mean:   {disc_mean:.3f} ± {disc_std:.3f}")
print(f"  Opus > Haiku:   {opus_wins}/{len(common)} tasks ({opus_wins/len(common)*100:.0f}%)")

# Save
output = {
    "opus_mean": opus_mean,
    "opus_std": opus_std,
    "haiku_mean": haiku_mean,
    "haiku_std": haiku_std,
    "disc_mean": disc_mean,
    "disc_std": disc_std,
    "opus_wins": opus_wins,
    "n_common": len(common),
    "n_opus": len(opus),
    "n_haiku": len(haiku),
    "per_task": disc_per_task,
}
with open(f"{results_dir}/discriminability.json", "w") as f:
    json.dump(output, f, indent=2)

print(f"\n  Saved to {results_dir}/discriminability.json")
DISC_EOF

echo ""
echo "=== Done ==="
