#!/bin/bash
# Run evaluation on all tasks in parallel.
#
# Usage:
#   CLAW_HARNESS_IMAGE=claw-harness-openclaw bash scripts/run_eval_parallel.sh
#   CLAW_HARNESS_IMAGE=claw-harness-openclaw bash scripts/run_eval_parallel.sh --parallel 10
#   CLAW_HARNESS_IMAGE=claw-harness-openclaw bash scripts/run_eval_parallel.sh --dataset dataset_scaled --parallel 20
#
# Requirements:
#   - CLAW_HARNESS_IMAGE env var (Docker image with agent)
#   - ANTHROPIC_API_KEY or OPENROUTER_API_KEY env var
#   - Docker running

set -e

PARALLEL=${PARALLEL:-10}
DATASET=${DATASET:-dataset}
RESULTS=${RESULTS:-results}
IMAGE=${CLAW_HARNESS_IMAGE:-""}
TIMEOUT=${TIMEOUT:-300}

# Parse args
while [[ $# -gt 0 ]]; do
    case $1 in
        --parallel) PARALLEL="$2"; shift 2 ;;
        --dataset) DATASET="$2"; shift 2 ;;
        --results) RESULTS="$2"; shift 2 ;;
        --timeout) TIMEOUT="$2"; shift 2 ;;
        *) echo "Unknown arg: $1"; exit 1 ;;
    esac
done

if [ -z "$IMAGE" ]; then
    echo "ERROR: CLAW_HARNESS_IMAGE not set."
    echo "  export CLAW_HARNESS_IMAGE=claw-harness-openclaw"
    exit 1
fi

# Collect all task yamls
TASKS=($(find "$DATASET" -name "*.yaml" -not -name "generation_report.json" | sort))
TOTAL=${#TASKS[@]}

if [ "$TOTAL" -eq 0 ]; then
    echo "No tasks found in $DATASET/"
    exit 1
fi

mkdir -p "$RESULTS"

echo "=== Parallel Evaluation ==="
echo "  Image:    $IMAGE"
echo "  Dataset:  $DATASET/ ($TOTAL tasks)"
echo "  Results:  $RESULTS/"
echo "  Parallel: $PARALLEL"
echo "  Timeout:  ${TIMEOUT}s"
echo ""

# Build env flags
ENV_FLAGS=()
for KEY_VAR in ANTHROPIC_API_KEY OPENROUTER_API_KEY OPENAI_API_KEY MODEL; do
    VAL="${!KEY_VAR}"
    if [ -n "$VAL" ]; then
        ENV_FLAGS+=("-e" "$KEY_VAR=$VAL")
    fi
done

# Function to run one task
run_task() {
    local task_yaml="$1"
    local task_name=$(basename "$task_yaml" .yaml)
    local task_dir="$RESULTS/$task_name"

    # Skip if already done
    if [ -f "$task_dir/reward.txt" ]; then
        echo "SKIP $task_name ($(cat "$task_dir/reward.txt"))"
        return 0
    fi

    mkdir -p "$task_dir"

    # Run Docker
    local abs_yaml="$(cd "$(dirname "$task_yaml")" && pwd)/$(basename "$task_yaml")"
    local abs_results="$(cd "$(dirname "$task_dir")" && pwd)/$(basename "$task_dir")"

    timeout "$TIMEOUT" docker run --rm \
        "${ENV_FLAGS[@]}" \
        -v "$abs_yaml:/opt/clawharness/task.yaml:ro" \
        -v "$abs_results:/logs" \
        "$IMAGE" 2>/dev/null

    local exit_code=$?

    if [ -f "$task_dir/reward.txt" ]; then
        local score=$(cat "$task_dir/reward.txt")
        echo "DONE $task_name → $score"
    elif [ $exit_code -ne 0 ]; then
        echo "0.0" > "$task_dir/reward.txt"
        echo "FAIL $task_name (exit $exit_code)"
    else
        echo "0.0" > "$task_dir/reward.txt"
        echo "FAIL $task_name (no reward)"
    fi
}

export -f run_task
export IMAGE RESULTS TIMEOUT
export "${!ENV_FLAGS[@]}" 2>/dev/null || true
# Re-export env vars for subshells
for KEY_VAR in ANTHROPIC_API_KEY OPENROUTER_API_KEY OPENAI_API_KEY MODEL CLAW_HARNESS_IMAGE; do
    export "$KEY_VAR" 2>/dev/null || true
done

START=$(date +%s)

# Run in parallel using xargs
printf '%s\n' "${TASKS[@]}" | xargs -P "$PARALLEL" -I {} bash -c 'run_task "$@"' _ {}

END=$(date +%s)
ELAPSED=$((END - START))
MINUTES=$((ELAPSED / 60))

# Summary
echo ""
echo "=== Summary ==="
echo "  Time: ${MINUTES}m ${ELAPSED}s"

SCORES=()
DONE=0
FAILED=0
for task_yaml in "${TASKS[@]}"; do
    task_name=$(basename "$task_yaml" .yaml)
    reward="$RESULTS/$task_name/reward.txt"
    if [ -f "$reward" ]; then
        score=$(cat "$reward")
        SCORES+=("$score")
        DONE=$((DONE + 1))
        if [ "$score" = "0.0" ] || [ "$score" = "0.00" ]; then
            FAILED=$((FAILED + 1))
        fi
    fi
done

echo "  Completed: $DONE/$TOTAL"
echo "  Failed (0.0): $FAILED"

if [ ${#SCORES[@]} -gt 0 ]; then
    AVG=$(python3 -c "scores=[${SCORES[*]// /,}]; print(f'{sum(scores)/len(scores):.3f}')" 2>/dev/null || echo "?")
    echo "  Average score: $AVG"
fi

# Save summary
python3 -c "
import json, os
from pathlib import Path

results_dir = Path('$RESULTS')
scores = []
for d in sorted(results_dir.iterdir()):
    reward = d / 'reward.txt'
    if reward.exists():
        try:
            scores.append({'task': d.name, 'score': float(reward.read_text().strip())})
        except ValueError:
            pass

summary = {
    'total_tasks': $TOTAL,
    'completed': len(scores),
    'mean_score': sum(s['score'] for s in scores) / len(scores) if scores else 0,
    'image': '$IMAGE',
    'elapsed_seconds': $ELAPSED,
    'scores': scores,
}
with open(results_dir / 'eval_summary.json', 'w') as f:
    json.dump(summary, f, indent=2)
print(f'  Summary: {results_dir}/eval_summary.json')
"
