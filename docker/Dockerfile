FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl jq bash git \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    fastapi uvicorn pyyaml anthropic httpx requests pypdf trafilatura

# Copy package
COPY clawenvkit/ /opt/clawenvkit/clawenvkit/
COPY mock_services/ /opt/clawenvkit/mock_services/
COPY prompts/ /opt/clawenvkit/prompts/
COPY dataset/ /opt/clawenvkit/dataset/

# Entrypoint
COPY docker/entrypoint_auto.sh /opt/clawenvkit/entrypoint_auto.sh
RUN chmod +x /opt/clawenvkit/entrypoint_auto.sh

ENV TASK_YAML=/opt/clawenvkit/task.yaml
ENV PYTHONPATH=/opt/clawenvkit
ENV PORT=9100
ENV MAX_TURNS=15
ENV MODEL=claude-sonnet-4-6

WORKDIR /workspace
RUN mkdir -p /logs

ENTRYPOINT ["/opt/clawenvkit/entrypoint_auto.sh"]
