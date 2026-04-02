FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl jq bash git \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    fastapi uvicorn pyyaml anthropic httpx trafilatura

# Copy package
COPY clawharness/ /opt/clawharness/clawharness/
COPY mock_services/ /opt/clawharness/mock_services/
COPY prompts/ /opt/clawharness/prompts/
COPY dataset/ /opt/clawharness/dataset/

# Entrypoint
COPY docker/entrypoint_auto.sh /opt/clawharness/entrypoint_auto.sh
RUN chmod +x /opt/clawharness/entrypoint_auto.sh

ENV TASK_YAML=/opt/clawharness/task.yaml
ENV PYTHONPATH=/opt/clawharness
ENV PORT=9100
ENV MAX_TURNS=15
ENV MODEL=claude-sonnet-4-6

WORKDIR /workspace
RUN mkdir -p /logs

ENTRYPOINT ["/opt/clawharness/entrypoint_auto.sh"]
