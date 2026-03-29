#!/bin/bash
# claw-harness — unified CLI for Claw Harnessing
#
# Usage:
#   claw-harness run todo-001                    # run single task
#   claw-harness run todo-001 --model gpt-4o     # with specific model
#   claw-harness run-all todo                    # run all tasks for a service
#   claw-harness run-all                         # run all 129 tasks
#   claw-harness generate --service gmail --count 5
#   claw-harness services                        # list available services

set -e

BASE_DIR="${CLAW_HARNESS_HOME:-$HOME/.claw-harness}"
IMAGE="${CLAW_HARNESS_IMAGE:-claw-harness:base}"
RESULTS_DIR="${CLAW_HARNESS_RESULTS:-$HOME/claw-results}"

# Check API key
check_key() {
    if [ -z "$ANTHROPIC_API_KEY" ]; then
        # Try config.json
        if [ -f "$BASE_DIR/config.json" ]; then
            ANTHROPIC_API_KEY=$(python3 -c "import json; print(json.load(open('$BASE_DIR/config.json')).get('claude',''))" 2>/dev/null)
            export ANTHROPIC_API_KEY
        fi
        if [ -z "$ANTHROPIC_API_KEY" ]; then
            echo "ERROR: ANTHROPIC_API_KEY not set" >&2
            echo "  export ANTHROPIC_API_KEY=sk-ant-..." >&2
            exit 1
        fi
    fi
}

# Find task yaml by short name
find_task() {
    local task_name="$1"
    local service=$(echo "$task_name" | sed 's/-[0-9]*$//')

    # Try exact path first
    if [ -f "$task_name" ]; then
        echo "$task_name"
        return
    fi

    # Try dataset directory
    local yaml_path="$BASE_DIR/dataset/$service/$task_name.yaml"
    if [ -f "$yaml_path" ]; then
        echo "$yaml_path"
        return
    fi

    echo "ERROR: Task not found: $task_name" >&2
    echo "  Looked in: $yaml_path" >&2
    exit 1
}

case "${1:-help}" in
    run)
        # claw-harness run todo-001 [--model claude-sonnet-4-6]
        TASK_NAME="${2:?Usage: claw-harness run <task-id> [--model <model>]}"
        MODEL="${MODEL:-claude-sonnet-4-6}"

        # Parse --model flag
        shift 2
        while [ $# -gt 0 ]; do
            case "$1" in
                --model) MODEL="$2"; shift 2 ;;
                *) shift ;;
            esac
        done

        check_key
        TASK_YAML=$(find_task "$TASK_NAME")
        SERVICE=$(python3 -c "import yaml; print(yaml.safe_load(open('$TASK_YAML')).get('task_id','').split('-')[0])")

        TASK_RESULTS="$RESULTS_DIR/$TASK_NAME"
        mkdir -p "$TASK_RESULTS"

        echo "🦞 Running $TASK_NAME (model: $MODEL)"

        docker run --rm \
            -e ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY" \
            -e MODEL="$MODEL" \
            -v "$TASK_YAML:/opt/claw-harness/task.yaml:ro" \
            -v "$TASK_RESULTS:/logs" \
            "$IMAGE" 2>&1

        echo ""
        echo "Results: $TASK_RESULTS/"
        ;;

    run-all)
        # claw-harness run-all [service] [--model claude-sonnet-4-6]
        SERVICE_FILTER="${2:-}"
        MODEL="${MODEL:-claude-sonnet-4-6}"

        # Parse --model flag
        shift
        while [ $# -gt 0 ]; do
            case "$1" in
                --model) MODEL="$2"; shift 2 ;;
                *) shift ;;
            esac
        done

        check_key

        # Find all task yamls
        if [ -n "$SERVICE_FILTER" ] && [ "$SERVICE_FILTER" != "--model" ]; then
            TASK_FILES=$(find "$BASE_DIR/dataset/$SERVICE_FILTER" -name "*.yaml" 2>/dev/null | sort)
        else
            TASK_FILES=$(find "$BASE_DIR/dataset" -name "*.yaml" -not -name "train.jsonl" 2>/dev/null | sort)
        fi

        TOTAL=$(echo "$TASK_FILES" | wc -l | tr -d ' ')
        DONE=0
        SCORES=""

        echo "🦞 Running $TOTAL tasks (model: $MODEL)"
        echo ""

        for TASK_YAML in $TASK_FILES; do
            TASK_ID=$(python3 -c "import yaml; print(yaml.safe_load(open('$TASK_YAML')).get('task_id','unknown'))")
            TASK_RESULTS="$RESULTS_DIR/$TASK_ID"

            # Skip if already done
            if [ -f "$TASK_RESULTS/reward.txt" ]; then
                SCORE=$(cat "$TASK_RESULTS/reward.txt")
                echo "  SKIP $TASK_ID ($SCORE)"
                SCORES="$SCORES$SCORE\n"
                DONE=$((DONE + 1))
                continue
            fi

            mkdir -p "$TASK_RESULTS"
            DONE=$((DONE + 1))

            echo -n "  [$DONE/$TOTAL] $TASK_ID: "

            SCORE=$(docker run --rm \
                -e ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY" \
                -e MODEL="$MODEL" \
                -v "$TASK_YAML:/opt/claw-harness/task.yaml:ro" \
                -v "$TASK_RESULTS:/logs" \
                "$IMAGE" 2>/dev/null | tail -1)

            echo "$SCORE"
            SCORES="$SCORES$SCORE\n"
        done

        # Summary
        echo ""
        echo "=== Summary ==="
        AVG=$(echo -e "$SCORES" | awk '{s+=$1; n++} END {printf "%.2f", s/n}')
        echo "  Tasks: $TOTAL"
        echo "  Average score: $AVG"
        echo "  Results: $RESULTS_DIR/"
        ;;

    generate)
        # claw-harness generate --service gmail --count 5
        shift
        cd "$BASE_DIR"
        python3 -m scripts.grading.cli generate "$@"
        ;;

    services)
        cd "$BASE_DIR"
        python3 -m scripts.grading.cli services
        ;;

    help|--help|-h|"")
        echo "🦞 Claw Harnessing — AI Agent Evaluation"
        echo ""
        echo "Usage:"
        echo "  claw-harness run <task-id> [--model <model>]   Run single task"
        echo "  claw-harness run-all [service] [--model <m>]   Run all tasks"
        echo "  claw-harness generate --service <s> --count N  Generate tasks"
        echo "  claw-harness services                          List services"
        echo ""
        echo "Examples:"
        echo "  claw-harness run todo-001"
        echo "  claw-harness run gmail-003 --model claude-3-haiku-20240307"
        echo "  claw-harness run-all helpdesk"
        echo "  claw-harness run-all --model claude-sonnet-4-6"
        echo "  claw-harness generate --service calendar --count 10"
        echo ""
        echo "Environment:"
        echo "  ANTHROPIC_API_KEY    API key (required)"
        echo "  MODEL                Default model (claude-sonnet-4-6)"
        echo "  CLAW_HARNESS_HOME   Install dir ($BASE_DIR)"
        echo "  CLAW_HARNESS_RESULTS Results dir ($RESULTS_DIR)"
        ;;

    *)
        echo "Unknown command: $1" >&2
        echo "Run 'claw-harness help' for usage" >&2
        exit 1
        ;;
esac
