FROM python:3.11-slim

# Layer 1: System deps (cached)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl jq bash git \
    && rm -rf /var/lib/apt/lists/*

# Layer 2: Python deps (cached)
RUN pip install --no-cache-dir \
    fastapi uvicorn pyyaml

# Layer 3: Infrastructure (cached across all tasks)
COPY mock_services/ /opt/claw-harness/mock_services/
COPY scripts/grading/ /opt/claw-harness/scripts/grading/
COPY scripts/__init__.py /opt/claw-harness/scripts/__init__.py

# Layer 4: Task-specific config (changes per task)
# These are set via docker build args or volume mount
ARG TASK_YAML=task.yaml
ARG SERVICE_NAME=todo
COPY ${TASK_YAML} /opt/claw-harness/task.yaml

# Layer 5: Entrypoint
COPY docker/entrypoint.sh /opt/claw-harness/entrypoint.sh
RUN chmod +x /opt/claw-harness/entrypoint.sh

ENV SERVICE_NAME=${SERVICE_NAME}
ENV PYTHONPATH=/opt/claw-harness
WORKDIR /workspace

EXPOSE 9100

ENTRYPOINT ["/opt/claw-harness/entrypoint.sh"]
