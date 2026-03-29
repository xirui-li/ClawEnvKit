FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl jq bash git \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    fastapi uvicorn pyyaml anthropic

# Copy package
COPY clawevalkit/ /opt/clawevalkit/clawevalkit/
COPY mock_services/ /opt/clawevalkit/mock_services/
COPY prompts/ /opt/clawevalkit/prompts/
COPY dataset/ /opt/clawevalkit/dataset/

# Entrypoint
COPY docker/entrypoint_auto.sh /opt/clawevalkit/entrypoint_auto.sh
RUN chmod +x /opt/clawevalkit/entrypoint_auto.sh

ENV TASK_YAML=/opt/clawevalkit/task.yaml
ENV PYTHONPATH=/opt/clawevalkit
ENV PORT=9100
ENV MAX_TURNS=15
ENV MODEL=claude-sonnet-4-6

WORKDIR /workspace
RUN mkdir -p /logs

ENTRYPOINT ["/opt/clawevalkit/entrypoint_auto.sh"]
