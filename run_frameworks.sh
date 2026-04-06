#!/bin/bash
# ── Run all 10 frameworks with Sonnet 4.6 ──
#
# Usage:
#   bash run_frameworks.sh                    # all 10 frameworks
#   bash run_frameworks.sh --resume           # resume interrupted
#   bash run_frameworks.sh --workers 5        # change parallelism
#   bash run_frameworks.sh --dataset dataset  # smaller dataset

ARGS="$@"
MODEL="anthropic/claude-sonnet-4.6"

FRAMEWORKS=(
    # Tier 1: Native Plugin
    "openclaw"
    # Tier 2: MCP
    "claudecode"
    # Tier 3: SKILL.md + curl
    "nanoclaw"
    "ironclaw"
    "copaw"
    "picoclaw"
    "zeroclaw"
    "nemoclaw"
    "hermes"
)

echo "================================================"
echo "  Framework Comparison (model: $MODEL)"
echo "  Frameworks: ${#FRAMEWORKS[@]} + Agent Loop"
echo "================================================"
echo ""

# Tier 1-3: Docker-based
for agent in "${FRAMEWORKS[@]}"; do
    echo "--- $agent ---"
    python3 scripts/evaluate.py \
        --agent "$agent" \
        --model "$MODEL" \
        $ARGS
    echo ""
done

# Tier 4: Agent Loop (no Docker)
echo "--- agent-loop ---"
python3 scripts/agent_loop_eval.py \
    --model "$MODEL" \
    $ARGS
