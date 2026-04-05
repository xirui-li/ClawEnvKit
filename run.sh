#!/bin/bash
# ── ClawHarnessing: one-command evaluation ──
#
# Usage:
#   bash run.sh                                          # all 10 models × 1039 tasks
#   bash run.sh --model openai/gpt-5.4                   # single model
#   bash run.sh --model openai/gpt-5.4 z-ai/glm-5       # pick models
#   bash run.sh --resume                                 # resume interrupted run
#   bash run.sh --agent claudecode                        # use Claude Code agent
#   bash run.sh --dataset dataset --workers 5            # smaller dataset, fewer workers
#
# Prerequisites:
#   docker build -f docker/Dockerfile.openclaw -t clawharness:openclaw .

python3 scripts/evaluate.py "$@"
