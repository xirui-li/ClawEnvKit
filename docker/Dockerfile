FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl jq bash git \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    fastapi uvicorn pyyaml anthropic

# Copy package
COPY claw_harness/ /opt/claw-harness/claw_harness/
COPY mock_services/ /opt/claw-harness/mock_services/
COPY prompts/ /opt/claw-harness/prompts/
COPY dataset/ /opt/claw-harness/dataset/

# Entrypoint
COPY docker/entrypoint_auto.sh /opt/claw-harness/entrypoint_auto.sh
RUN chmod +x /opt/claw-harness/entrypoint_auto.sh

ENV TASK_YAML=/opt/claw-harness/task.yaml
ENV PYTHONPATH=/opt/claw-harness
ENV PORT=9100
ENV MAX_TURNS=15
ENV MODEL=claude-sonnet-4-6

WORKDIR /workspace
RUN mkdir -p /logs

ENTRYPOINT ["/opt/claw-harness/entrypoint_auto.sh"]
