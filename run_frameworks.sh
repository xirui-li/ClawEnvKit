#!/bin/bash
# ── Run all 10 frameworks ──
#
# Usage:
#   bash run_frameworks.sh                                    # all 10, default model
#   bash run_frameworks.sh --model anthropic/claude-haiku-4-5-20251001  # specify model
#   bash run_frameworks.sh --resume                           # resume interrupted
#   bash run_frameworks.sh --workers 5                        # change parallelism
#   bash run_frameworks.sh --dataset Auto-ClawEval-mini       # smaller dataset (104 tasks)
#   bash run_frameworks.sh --dataset Auto-ClawEval            # full dataset (1040 tasks)

set -e

# ── Parse --model from args (extract it, pass rest through) ──
MODEL=""
PASS_ARGS=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        --model)
            MODEL="$2"
            PASS_ARGS+=("--model" "$2")
            shift 2
            ;;
        *)
            PASS_ARGS+=("$1")
            shift
            ;;
    esac
done

# Default model if not specified
MODEL="${MODEL:-anthropic/claude-haiku-4-5-20251001}"
if [[ ! " ${PASS_ARGS[*]} " =~ " --model " ]]; then
    PASS_ARGS+=("--model" "$MODEL")
fi

FRAMEWORKS=(
    # Tier 1: Native Plugin
    "openclaw"
    # Tier 2: MCP
    "claudecode"
    "nanoclaw"
    "picoclaw"
    "zeroclaw"
    # Tier 3: SKILL.md + shell/curl
    "copaw"
    "nemoclaw"
    "hermes"
    # Excluded: ironclaw (native agent loop too slow, 50 iterations per task → timeout)
)

echo "================================================"
echo "  Framework Comparison"
echo "  Model: $MODEL"
echo "  Frameworks: ${#FRAMEWORKS[@]} Docker + Agent Loop"
echo "  Args: ${PASS_ARGS[*]}"
echo "================================================"
echo ""

# Docker-based frameworks
for agent in "${FRAMEWORKS[@]}"; do
    echo "━━━ $agent ━━━"
    python3 scripts/evaluate.py \
        --agent "$agent" \
        "${PASS_ARGS[@]}" || echo "[WARN] $agent failed, continuing..."
    echo ""
done

# Agent Loop (no Docker)
echo "━━━ agent-loop ━━━"
python3 scripts/evaluate.py \
    --agent agent-loop \
    "${PASS_ARGS[@]}" || echo "[WARN] agent-loop failed"

echo ""
echo "================================================"
echo "  Done. Results in eval_results/"
echo "================================================"
