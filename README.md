# Claw Harnessing

Automated environment generator for OpenClaw-compatible agents. Takes a natural language description (e.g., "Generate 20 git workflow tasks, easy to hard") and produces `train.jsonl` task files + Docker images that MetaClaw's RL training loop can consume directly.

## Install

```bash
git clone https://github.com/xirui-li/claw-harnessing.git
cd claw-harnessing
pip install -r requirements.txt
```

## Install as OpenClaw skill

```bash
ln -s ~/XIRUILI/Research/Codebase/claw-harnessing ~/.openclaw/workspace/skills/clawharness
```

## Requirements

- Python 3.11+
- Colima + Docker CLI
- OpenClaw (for skill mode) or `mock_claw.py` (for standalone dev)
