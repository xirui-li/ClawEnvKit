#!/bin/bash
# ── Run one or all evaluation harnesses ──
#
# Usage:
#   bash run_harnesses.sh                                    # all 9 harnesses, default model
#   bash run_harnesses.sh --harness picoclaw                 # one harness only
#   bash run_harnesses.sh --harness openclaw --resume        # one harness, resume
#   bash run_harnesses.sh --model anthropic/claude-sonnet-4.6
#   bash run_harnesses.sh --resume
#   bash run_harnesses.sh --workers 5
#   bash run_harnesses.sh --dataset Auto-ClawEval-mini       # 104-task curated set
#   bash run_harnesses.sh --dataset Auto-ClawEval            # 1040-task full set (default)
#
# Available harnesses:
#   openclaw    claudecode  nanoclaw    picoclaw   zeroclaw
#   copaw       nemoclaw    hermes      agent-loop
#   ironclaw                                       (excluded by default — too slow)

set -e

# ── Parse --model and --harness from args (extract them, pass rest through) ──
MODEL=""
SELECTED_HARNESS=""
PASS_ARGS=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        --model)
            MODEL="$2"
            PASS_ARGS+=("--model" "$2")
            shift 2
            ;;
        --harness|--agent)
            SELECTED_HARNESS="$2"
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

ALL_HARNESSES=(
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

# If --harness is set, validate and run only that one
if [[ -n "$SELECTED_HARNESS" ]]; then
    VALID_HARNESSES=("${ALL_HARNESSES[@]}" "ironclaw" "agent-loop")
    if [[ ! " ${VALID_HARNESSES[*]} " =~ " ${SELECTED_HARNESS} " ]]; then
        echo "ERROR: unknown harness '${SELECTED_HARNESS}'"
        echo "Valid: ${VALID_HARNESSES[*]}"
        exit 1
    fi
    HARNESSES=("$SELECTED_HARNESS")
else
    HARNESSES=("${ALL_HARNESSES[@]}")
fi

echo "================================================"
echo "  Harness Evaluation"
echo "  Model:    $MODEL"
echo "  Harnesses: ${#HARNESSES[@]} (${HARNESSES[*]})"
echo "  Args:     ${PASS_ARGS[*]}"
echo "================================================"
echo ""

# Docker-based harnesses
for harness in "${HARNESSES[@]}"; do
    if [[ "$harness" == "agent-loop" ]]; then
        continue  # handled below
    fi
    echo "━━━ $harness ━━━"
    python3 scripts/evaluate.py \
        --agent "$harness" \
        "${PASS_ARGS[@]}" || echo "[WARN] $harness failed, continuing..."
    echo ""
done

# Agent Loop (no Docker) — only when running all OR explicitly selected
if [[ -z "$SELECTED_HARNESS" || "$SELECTED_HARNESS" == "agent-loop" ]]; then
    echo "━━━ agent-loop ━━━"
    python3 scripts/evaluate.py \
        --agent agent-loop \
        "${PASS_ARGS[@]}" || echo "[WARN] agent-loop failed"
fi

echo ""
echo "================================================"
echo "  Done. Results in eval_results/"
echo "================================================"
