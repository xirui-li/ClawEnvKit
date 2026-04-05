#!/bin/bash
# Run all 10 backbone models for the paper's main table.
#
# Prerequisites:
#   1. Docker image built:
#      docker build -f docker/Dockerfile.openclaw -t clawharness:openclaw .
#
#   2. OpenRouter API key set:
#      export OPENROUTER_API_KEY=sk-or-...
#
# Usage:
#   bash scripts/run_paper_eval.sh                        # Full dataset (104 tasks)
#   bash scripts/run_paper_eval.sh --dataset dataset_mini  # Mini dataset (104 tasks, different variants)
#   bash scripts/run_paper_eval.sh --parallel 5            # 5 concurrent containers
#   bash scripts/run_paper_eval.sh --resume                # Resume interrupted run
#
# Output:
#   paper_results/
#     anthropic_claude-opus-4.6/
#       <task_id>/grading.json     per-task details
#       eval_summary.json          model summary (safety, completion, robustness, mean)
#     ...
#     paper_table.md               formatted table for paper

set -e

DATASET=${DATASET:-dataset}
PARALLEL=${PARALLEL:-10}
RESULTS_DIR=${RESULTS_DIR:-paper_results}
IMAGE=${CLAW_HARNESS_IMAGE:-clawharness:openclaw}
TIMEOUT=${TIMEOUT:-300}
RESUME=""

# Parse args
while [[ $# -gt 0 ]]; do
    case $1 in
        --dataset) DATASET="$2"; shift 2 ;;
        --parallel) PARALLEL="$2"; shift 2 ;;
        --results) RESULTS_DIR="$2"; shift 2 ;;
        --timeout) TIMEOUT="$2"; shift 2 ;;
        --resume) RESUME="--resume"; shift ;;
        *) echo "Unknown arg: $1"; exit 1 ;;
    esac
done

# Paper models (10 backbone models × 5 families)
MODELS=(
    # Anthropic
    "anthropic/claude-opus-4.6"
    "anthropic/claude-sonnet-4.6"
    # OpenAI
    "openai/gpt-5.4"
    "openai/gpt-5-nano"
    # Zhipu AI
    "z-ai/glm-5-turbo"
    "z-ai/glm-5"
    # MiniMax
    "minimax/minimax-m2.7"
    "minimax/minimax-m2.5"
    # Xiaomi
    "xiaomi/mimo-v2-pro"
    "xiaomi/mimo-v2-omni"
)

# Verify prerequisites
if [ -z "$OPENROUTER_API_KEY" ]; then
    echo "ERROR: OPENROUTER_API_KEY not set."
    echo "  export OPENROUTER_API_KEY=sk-or-..."
    exit 1
fi

if ! docker image inspect "$IMAGE" &>/dev/null; then
    echo "ERROR: Docker image '$IMAGE' not found."
    echo "  docker build -f docker/Dockerfile.openclaw -t clawharness:openclaw ."
    exit 1
fi

TASK_COUNT=$(find "$DATASET" -name "*.yaml" -not -name "generation_report.json" | wc -l | tr -d ' ')
if [ "$TASK_COUNT" -eq 0 ]; then
    echo "ERROR: No tasks found in $DATASET/"
    exit 1
fi

echo "================================================================"
echo "  ClawHarnessing Paper Evaluation"
echo "================================================================"
echo "  Image:    $IMAGE"
echo "  Dataset:  $DATASET/ ($TASK_COUNT tasks)"
echo "  Models:   ${#MODELS[@]}"
echo "  Parallel: $PARALLEL containers per model"
echo "  Results:  $RESULTS_DIR/"
echo "  Timeout:  ${TIMEOUT}s per task"
echo "================================================================"
echo ""

START_ALL=$(date +%s)

for model in "${MODELS[@]}"; do
    model_dir=$(echo "$model" | tr '/' '_')
    model_results="$RESULTS_DIR/$model_dir"

    # Skip if already completed (resume mode)
    if [ -n "$RESUME" ] && [ -f "$model_results/eval_summary.json" ]; then
        score=$(python3 -c "import json; s=json.load(open('$model_results/eval_summary.json')); print(f'{s[\"mean_score\"]:.3f}')" 2>/dev/null || echo "?")
        echo "SKIP $model (already done, score=$score)"
        continue
    fi

    echo ""
    echo "=== $model ==="
    MODEL_START=$(date +%s)

    CLAW_HARNESS_IMAGE="$IMAGE" \
    MODEL="$model" \
    OPENROUTER_API_KEY="$OPENROUTER_API_KEY" \
    bash scripts/run_eval_parallel.sh \
        --dataset "$DATASET" \
        --results "$model_results" \
        --parallel "$PARALLEL" \
        --timeout "$TIMEOUT"

    MODEL_END=$(date +%s)
    MODEL_ELAPSED=$((MODEL_END - MODEL_START))
    echo "  Time: ${MODEL_ELAPSED}s"
done

END_ALL=$(date +%s)
TOTAL_ELAPSED=$((END_ALL - START_ALL))
TOTAL_MINUTES=$((TOTAL_ELAPSED / 60))

echo ""
echo "================================================================"
echo "  All models complete (${TOTAL_MINUTES}m ${TOTAL_ELAPSED}s)"
echo "================================================================"

# Generate paper table
python3 -c "
import json
from pathlib import Path

results_dir = Path('$RESULTS_DIR')
models = [
    ('Anthropic', 'Claude Opus 4.6', 'anthropic_claude-opus-4.6'),
    ('Anthropic', 'Claude Sonnet 4.6', 'anthropic_claude-sonnet-4.6'),
    ('OpenAI', 'GPT-5.4', 'openai_gpt-5.4'),
    ('OpenAI', 'GPT-5 Nano', 'openai_gpt-5-nano'),
    ('Zhipu AI', 'GLM 5 Turbo', 'z-ai_glm-5-turbo'),
    ('Zhipu AI', 'GLM 5', 'z-ai_glm-5'),
    ('MiniMax', 'MiniMax M2.7', 'minimax_minimax-m2.7'),
    ('MiniMax', 'MiniMax M2.5', 'minimax_minimax-m2.5'),
    ('Xiaomi', 'MiMo V2 Pro', 'xiaomi_mimo-v2-pro'),
    ('Xiaomi', 'MiMo V2 Omni', 'xiaomi_mimo-v2-omni'),
]

# Markdown table
lines = ['# Paper Results: Backbone Model Scaling', '']
lines.append('| Family | Model | Safety | Completion | Robustness | Mean | Cost |')
lines.append('|---|---|---|---|---|---|---|')

total_cost = 0
for family, name, dir_name in models:
    summary_path = results_dir / dir_name / 'eval_summary.json'
    if summary_path.exists():
        s = json.load(open(summary_path))
        safety = f'{s.get(\"mean_safety\", 0):.2f}'
        completion = f'{s.get(\"mean_completion\", 0):.2f}'
        robustness = f'{s.get(\"mean_robustness\", 0):.2f}'
        mean = f'{s.get(\"mean_score\", 0):.2f}'
        # Estimate cost from tokens if available
        tasks = s.get('tasks', [])
        cost = '—'
        lines.append(f'| {family} | **{name}** | {safety} | {completion} | {robustness} | {mean} | {cost} |')
    else:
        lines.append(f'| {family} | **{name}** | — | — | — | — | — |')

lines.append('')
lines.append(f'Dataset: \`$DATASET/\` ({s.get(\"completed\", \"?\")}/{s.get(\"total_tasks\", \"?\")} tasks)')
lines.append(f'Agent: OpenClaw (\`$IMAGE\`)')
lines.append(f'Total time: ${TOTAL_MINUTES}m')

table_path = results_dir / 'paper_table.md'
with open(table_path, 'w') as f:
    f.write('\n'.join(lines))
print('\n'.join(lines))
print(f'\nSaved: {table_path}')
"
