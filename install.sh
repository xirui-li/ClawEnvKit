#!/bin/bash
# One-click install for ClawHarnessing
#
# Usage: curl -fsSL https://raw.githubusercontent.com/xirui-li/ClawHarnessing/main/install.sh | bash

set -e

INSTALL_DIR="${CLAWHARNESS_HOME:-$HOME/.clawharness}"
REPO="https://github.com/xirui-li/ClawHarnessing.git"

echo "🦞 Installing ClawHarnessing..."

# 1. Clone or update repo
if [ -d "$INSTALL_DIR" ]; then
    echo "  Updating existing installation..."
    cd "$INSTALL_DIR" && git pull --quiet
else
    echo "  Cloning repository..."
    git clone --quiet "$REPO" "$INSTALL_DIR"
fi

# 2. Install as editable package (required — prompts/ and mock_services/ at repo root)
echo "  Installing Python package..."
cd "$INSTALL_DIR"
pip install -e ".[all]" --quiet 2>/dev/null || \
pip3 install -e ".[all]" --quiet 2>/dev/null || \
echo "  WARNING: pip install failed. Run manually: cd $INSTALL_DIR && pip install -e '.[all]'"

# 3. Build Docker image (optional — needed for eval)
echo "  Building Docker image (this takes ~2 minutes first time)..."
if command -v docker &>/dev/null; then
    docker build -f docker/Dockerfile -t clawharness:base . --quiet 2>/dev/null || \
    docker build -f docker/Dockerfile -t clawharness:base . || \
    echo "  WARNING: Docker build failed. Make sure Docker/Colima is running."
else
    echo "  WARNING: Docker not found. Install Docker/Colima for evaluation."
fi

echo ""
echo "✅ ClawHarnessing installed!"
echo ""
echo "Next steps:"
echo "  1. Set your API key:"
echo "     export ANTHROPIC_API_KEY=sk-ant-..."
echo ""
echo "  2. Run your first evaluation:"
echo "     clawharness eval todo-001"
echo ""
echo "  3. Generate new tasks:"
echo "     clawharness generate --services gmail --count 5"
echo ""
echo "  4. Or from natural language:"
echo "     clawharness generate --request 'Test meeting scheduling'"
echo ""
