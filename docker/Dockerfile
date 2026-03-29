FROM python:3.11-slim

# Layer 1: System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl jq bash git \
    && rm -rf /var/lib/apt/lists/*

# Layer 2: Python deps
RUN pip install --no-cache-dir \
    fastapi uvicorn pyyaml anthropic

# Layer 3: Infrastructure (all mock services + grading + agent)
COPY mock_services/ /opt/claw-harness/mock_services/
COPY scripts/grading/ /opt/claw-harness/scripts/grading/
COPY scripts/__init__.py /opt/claw-harness/scripts/__init__.py
COPY dataset/ /opt/claw-harness/dataset/

# Layer 4: Entrypoint
COPY docker/entrypoint_auto.sh /opt/claw-harness/entrypoint_auto.sh
RUN chmod +x /opt/claw-harness/entrypoint_auto.sh

# No COPY task.yaml — mounted via volume at runtime
# No ARG TASK_YAML / SERVICE_NAME — passed via env or auto-detected

ENV TASK_YAML=/opt/claw-harness/task.yaml
ENV PYTHONPATH=/opt/claw-harness
ENV PORT=9100
ENV MAX_TURNS=15
ENV MODEL=claude-sonnet-4-6

WORKDIR /workspace
RUN mkdir -p /logs

ENTRYPOINT ["/opt/claw-harness/entrypoint_auto.sh"]
