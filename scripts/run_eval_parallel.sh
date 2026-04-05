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

# Load API keys from config.json if not in env
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG_JSON="$SCRIPT_DIR/../config.json"
if [ -f "$CONFIG_JSON" ]; then
    for KEY_VAR in OPENROUTER_API_KEY ANTHROPIC_API_KEY OPENAI_API_KEY; do
        if [ -z "${!KEY_VAR}" ]; then
            VAL=$(python3 -c "import json; print(json.load(open('$CONFIG_JSON')).get('$KEY_VAR',''))" 2>/dev/null)
            if [ -n "$VAL" ]; then
                export "$KEY_VAR=$VAL"
            fi
        fi
    done
fi

# Build env flags
ENV_FLAGS=()
for KEY_VAR in ANTHROPIC_API_KEY OPENROUTER_API_KEY OPENAI_API_KEY MODEL; do
    VAL="${!KEY_VAR}"
    if [ -n "$VAL" ]; then
        ENV_FLAGS+=("-e" "$KEY_VAR=$VAL")
    fi
done

# Progress tracking
PROGRESS_FILE=$(mktemp)
echo "0" > "$PROGRESS_FILE"

update_progress() {
    local count
    count=$(( $(cat "$PROGRESS_FILE") + 1 ))
    echo "$count" > "$PROGRESS_FILE"
    local pct=$((count * 100 / TOTAL))
    local bar_len=$((pct / 2))
    local bar=$(printf '█%.0s' $(seq 1 $bar_len 2>/dev/null) 2>/dev/null || echo "")
    local spaces=$((50 - bar_len))
    printf "\r  [%-50s] %d/%d (%d%%)" "$bar" "$count" "$TOTAL" "$pct" >&2
}

# Function to run one task
run_task() {
    local task_yaml="$1"
    local task_name=$(basename "$task_yaml" .yaml)
    local task_dir="$RESULTS/$task_name"

    # Skip if already done
    if [ -f "$task_dir/reward.txt" ]; then
        update_progress
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
        :  # success
    elif [ $exit_code -ne 0 ]; then
        echo "0.0" > "$task_dir/reward.txt"
    else
        echo "0.0" > "$task_dir/reward.txt"
    fi
    update_progress
}

export -f run_task update_progress
export IMAGE RESULTS TIMEOUT TOTAL PROGRESS_FILE
export "${!ENV_FLAGS[@]}" 2>/dev/null || true
# Re-export env vars for subshells
for KEY_VAR in ANTHROPIC_API_KEY OPENROUTER_API_KEY OPENAI_API_KEY MODEL CLAW_HARNESS_IMAGE; do
    export "$KEY_VAR" 2>/dev/null || true
done

START=$(date +%s)

# Run in parallel using xargs
printf '%s\n' "${TASKS[@]}" | xargs -P "$PARALLEL" -I {} bash -c 'run_task "$@"' _ {}
echo "" >&2  # newline after progress bar
rm -f "$PROGRESS_FILE"

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

# Save detailed summary (reads grading.json from each task)
python3 -c "
import json
from pathlib import Path

results_dir = Path('$RESULTS')
tasks = []
for d in sorted(results_dir.iterdir()):
    if not d.is_dir(): continue
    grading = d / 'grading.json'
    reward = d / 'reward.txt'
    if grading.exists():
        try:
            g = json.load(open(grading))
            g['task'] = d.name
            tasks.append(g)
        except Exception:
            pass
    elif reward.exists():
        try:
            tasks.append({'task': d.name, 'final_score': float(reward.read_text().strip())})
        except ValueError:
            pass

n = len(tasks)
if n == 0:
    print('  No results found.')
else:
    mean = lambda key: sum(t.get(key, 0) for t in tasks) / n
    summary = {
        'total_tasks': $TOTAL,
        'completed': n,
        'image': '$IMAGE',
        'model': tasks[0].get('model', 'unknown') if tasks else 'unknown',
        'elapsed_seconds': $ELAPSED,
        # Paper table columns
        'mean_safety': round(mean('safety'), 4),
        'mean_completion': round(mean('completion'), 4),
        'mean_robustness': round(mean('robustness'), 4),
        'mean_score': round(mean('final_score'), 4),
        # Analysis
        'safety_violation_rate': round(sum(1 for t in tasks if t.get('safety', 1) < 1) / n, 4),
        'mean_tool_calls': round(mean('num_tool_calls'), 1),
        # Per-task details
        'tasks': tasks,
    }
    with open(results_dir / 'eval_summary.json', 'w') as f:
        json.dump(summary, f, indent=2)
    print(f'  Mean: safety={summary[\"mean_safety\"]:.2f} completion={summary[\"mean_completion\"]:.2f} robustness={summary[\"mean_robustness\"]:.2f} score={summary[\"mean_score\"]:.2f}')
    print(f'  Summary: {results_dir}/eval_summary.json')
"
