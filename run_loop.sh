#!/bin/bash
# ── Agent Loop evaluation (no Docker) ──
#
# Usage:
#   bash run_loop.sh                                     # all 10 models
#   bash run_loop.sh --model openai/gpt-5.4              # single model
#   bash run_loop.sh --model openai/gpt-5.4 z-ai/glm-5  # pick models
#   bash run_loop.sh --resume                            # resume interrupted
#   bash run_loop.sh --dataset dataset                   # 104 tasks

python3 scripts/agent_loop_eval.py "$@"
