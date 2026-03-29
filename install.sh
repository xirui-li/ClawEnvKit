#!/bin/bash
# One-click install for Claw Harnessing
#
# Usage: curl -fsSL https://raw.githubusercontent.com/xirui-li/claw-harnessing/main/install.sh | bash

set -e

INSTALL_DIR="${CLAW_HARNESS_HOME:-$HOME/.claw-harness}"
REPO="https://github.com/xirui-li/claw-harnessing.git"

echo "🦞 Installing Claw Harnessing..."

# 1. Clone or update repo
if [ -d "$INSTALL_DIR" ]; then
    echo "  Updating existing installation..."
    cd "$INSTALL_DIR" && git pull --quiet
else
    echo "  Cloning repository..."
    git clone --quiet "$REPO" "$INSTALL_DIR"
fi

# 2. Install Python dependencies
echo "  Installing Python dependencies..."
pip install --quiet -r "$INSTALL_DIR/requirements.txt" 2>/dev/null || \
pip3 install --quiet -r "$INSTALL_DIR/requirements.txt" 2>/dev/null || \
echo "  WARNING: pip install failed. Install manually: pip install -r $INSTALL_DIR/requirements.txt"

pip install --quiet fastapi uvicorn pyyaml anthropic 2>/dev/null || \
pip3 install --quiet fastapi uvicorn pyyaml anthropic 2>/dev/null || true

# 3. Build Docker image
echo "  Building Docker image (this takes ~2 minutes first time)..."
if command -v docker &>/dev/null; then
    cd "$INSTALL_DIR"
    docker build -f docker/Dockerfile -t claw-harness:base . --quiet 2>/dev/null || \
    docker build -f docker/Dockerfile -t claw-harness:base . || \
    echo "  WARNING: Docker build failed. Make sure Docker is running."
else
    echo "  WARNING: Docker not found. Install Docker/Colima first."
fi

# 4. Install CLI
echo "  Installing CLI..."
chmod +x "$INSTALL_DIR/scripts/claw_harness_cli.sh"
mkdir -p "$HOME/.local/bin"
ln -sf "$INSTALL_DIR/scripts/claw_harness_cli.sh" "$HOME/.local/bin/claw-harness"

# Add to PATH if needed
if ! echo "$PATH" | grep -q "$HOME/.local/bin"; then
    echo "  Adding ~/.local/bin to PATH..."
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.bashrc" 2>/dev/null
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.zshrc" 2>/dev/null
    export PATH="$HOME/.local/bin:$PATH"
fi

echo ""
echo "✅ Claw Harnessing installed!"
echo ""
echo "Next steps:"
echo "  1. Set your API key:"
echo "     export ANTHROPIC_API_KEY=sk-ant-..."
echo ""
echo "  2. Run your first evaluation:"
echo "     claw-harness run todo-001"
echo ""
echo "  3. Run all tasks:"
echo "     claw-harness run-all todo"
echo ""
echo "  4. Generate new tasks:"
echo "     claw-harness generate --service gmail --count 5"
