#!/bin/bash
# Experiment 1: Discriminability — Run strong (Opus) + weak (Haiku) on all tasks
#
# Usage:
#   cd claw-harnessing
#   bash paper_experiments/exp1_task_quality/run_discriminability.sh
#
# Prerequisites:
#   - Docker running (Colima or native)
#   - claw-harness-openclaw image built
#   - ANTHROPIC_API_KEY set in environment or config.json
#
# Output:
#   paper_experiments/exp1_task_quality/results/disc_opus.csv
#   paper_experiments/exp1_task_quality/results/disc_haiku.csv
#   paper_experiments/exp1_task_quality/results/discriminability.json

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

# --- Models to test ---
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

    echo "task_id,score,completion,safety,model" > "$csv_file"

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

        # Run in Docker
        local logs_dir="/tmp/disc_${model_label}_${task_id}"
        mkdir -p "$logs_dir"

        docker run --rm --user root \
            -e ANTHROPIC_API_KEY \
            -e MODEL="$model" \
            -v "$task:/opt/clawharness/task.yaml:ro" \
            -v "$logs_dir:/logs" \
            "$IMAGE" > /dev/null 2>&1 || true

        # Extract score
        if [ -f "$logs_dir/reward.txt" ]; then
            score=$(cat "$logs_dir/reward.txt" | tr -d ' \n')
            # Extract details
            if [ -f "$logs_dir/grading.json" ]; then
                completion=$(python3 -c "import json; print(json.load(open('$logs_dir/grading.json')).get('completion',0))" 2>/dev/null || echo "0")
                safety=$(python3 -c "import json; print(json.load(open('$logs_dir/grading.json')).get('safety',0))" 2>/dev/null || echo "0")
            else
                completion="0"
                safety="0"
            fi
            echo "$score"
            echo "$task_id,$score,$completion,$safety,$model" >> "$csv_file"
        else
            echo "FAIL"
            echo "$task_id,0,0,0,$model" >> "$csv_file"
        fi

        # Cleanup
        rm -rf "$logs_dir"
    done

    echo ""
}

# --- Run strong model ---
echo "=== Running $STRONG_MODEL (strong) ==="
run_model "$STRONG_MODEL" "opus"

# --- Run weak model ---
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

# Per-task discriminability: Disc(E) = R(opus) - R(haiku)
disc_per_task = {}
for task_id in opus:
    if task_id in haiku:
        disc_per_task[task_id] = opus[task_id] - haiku[task_id]

# Set-level: Spearman rank correlation
task_ids = sorted(disc_per_task.keys())
opus_scores = [opus[t] for t in task_ids]
haiku_scores = [haiku[t] for t in task_ids]

# Simple Spearman (rank correlation)
def rank(values):
    sorted_idx = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0] * len(values)
    for r, i in enumerate(sorted_idx):
        ranks[i] = r + 1
    return ranks

opus_ranks = rank(opus_scores)
haiku_ranks = rank(haiku_scores)
n = len(task_ids)
d_sq_sum = sum((opus_ranks[i] - haiku_ranks[i])**2 for i in range(n))
spearman = 1 - (6 * d_sq_sum) / (n * (n**2 - 1)) if n > 1 else 0

# Stats
opus_mean = sum(opus_scores) / len(opus_scores)
haiku_mean = sum(haiku_scores) / len(haiku_scores)
disc_values = list(disc_per_task.values())
disc_mean = sum(disc_values) / len(disc_values) if disc_values else 0

print(f"\nResults:")
print(f"  Tasks compared: {len(disc_per_task)}")
print(f"  Opus (strong):  mean={opus_mean:.3f}")
print(f"  Haiku (weak):   mean={haiku_mean:.3f}")
print(f"  Disc(E) mean:   {disc_mean:.3f} (Opus - Haiku)")
print(f"  Spearman rho:   {spearman:.3f}")
print(f"  Result: {'✅ PASS' if disc_mean > 0.1 else '❌ FAIL'} (mean disc > 0.1)")

# Save
output = {
    "opus_mean": opus_mean,
    "haiku_mean": haiku_mean,
    "disc_mean": disc_mean,
    "spearman_rho": spearman,
    "n_tasks": len(disc_per_task),
    "per_task": disc_per_task,
}
with open(f"{results_dir}/discriminability.json", "w") as f:
    json.dump(output, f, indent=2)

print(f"\nSaved to {results_dir}/discriminability.json")
DISC_EOF

echo ""
echo "=== Done ==="
