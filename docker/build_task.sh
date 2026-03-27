#!/bin/bash
# Build a Docker image for a specific task
#
# Usage:
#   ./docker/build_task.sh dataset/todo/todo-001.yaml
#   ./docker/build_task.sh dataset/gmail/gmail-003.yaml
#
# The image will be tagged as claw-harness:<task-id>

set -e

TASK_YAML="${1:?Usage: $0 <path/to/task.yaml>}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Extract task ID and service name
TASK_ID=$(python3 -c "import yaml; print(yaml.safe_load(open('$TASK_YAML')).get('task_id','unknown'))")
SERVICE_NAME=$(echo "$TASK_ID" | cut -d'-' -f1)

echo "Building claw-harness:$TASK_ID (service: $SERVICE_NAME)"

# Build from project root
docker build \
    -f "$SCRIPT_DIR/Dockerfile" \
    --build-arg "TASK_YAML=$TASK_YAML" \
    --build-arg "SERVICE_NAME=$SERVICE_NAME" \
    -t "claw-harness:$TASK_ID" \
    "$PROJECT_ROOT"

echo ""
echo "Built: claw-harness:$TASK_ID"
echo ""
echo "Run interactive (agent connects via docker exec):"
echo "  docker run --rm --network none --name $TASK_ID claw-harness:$TASK_ID"
echo ""
echo "Then in another terminal:"
echo "  docker exec $TASK_ID curl -s http://localhost:9100/$SERVICE_NAME/..."
echo ""
echo "Grade and get results:"
echo "  docker stop $TASK_ID  # triggers grading"
echo "  docker cp $TASK_ID:/logs/ ./results/"
