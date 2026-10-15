#!/bin/bash
# TokenHarbor Farm — one-command auto installer.
# Usage: curl -O https://raw.githubusercontent.com/zal-m10/harbor-fixed/main/install.sh && bash install.sh
set -e

REPO_URL="https://github.com/zal-m10/harbor-fixed.git"
INSTALL_DIR="$HOME/harbor-fixed"

echo "=== TokenHarbor Farm installer ==="

# 1. System dependencies.
echo "[1/5] Installing system packages..."
if command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update -qq
    sudo apt-get install -y -qq python3.11 python3.11-venv git curl \
        || sudo apt-get install -y -qq python3 python3-venv git curl
else
    echo "apt-get not found — install python3.11, git, curl manually."
fi

# 2. Clone or update the repo.
echo "[2/5] Getting farm code..."
if [ -d "$INSTALL_DIR/.git" ]; then
    cd "$INSTALL_DIR" && git pull -q || true
else
    git clone -q "$REPO_URL" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

# 3. Python venv + packages.
echo "[3/5] Setting up Python environment..."
PYBIN="$(command -v python3.11 || command -v python3)"
$PYBIN -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q playwright requests rich

# 4. Chromium + OS deps for Playwright.
echo "[4/5] Installing Chromium..."
.venv/bin/python -m playwright install chromium 2>&1 | tail -1
if command -v apt-get >/dev/null 2>&1; then
    sudo .venv/bin/python -m playwright install-deps chromium 2>&1 | tail -1 || true
fi

# 5. Install the `farm` command.
echo "[5/5] Installing 'farm' command..."
FARM_BIN="/usr/local/bin/farm"
FARM_SCRIPT="#!/bin/bash
exec \"$INSTALL_DIR/.venv/bin/python\" -m tools.tokenharbor.farm_tui \"\$@\"
"
if [ -w /usr/local/bin ]; then
    echo "$FARM_SCRIPT" | sudo tee "$FARM_BIN" >/dev/null
    sudo chmod +x "$FARM_BIN"
else
    mkdir -p "$HOME/.local/bin"
    echo "$FARM_SCRIPT" > "$HOME/.local/bin/farm"
    chmod +x "$HOME/.local/bin/farm"
    FARM_BIN="$HOME/.local/bin/farm"
    echo "Note: add \$HOME/.local/bin to your PATH if 'farm' is not found."
fi

echo ""
echo "=== Done ==="
echo "Type  'farm'  to open the interactive menu."
echo ""
echo "First steps inside the menu:"
echo "  4) Setup tempik  -> enter your Tempik URL"
echo "  3) Setup proxy   -> enter user:pass@host:port (or skip)"
echo "  1) Run farm      -> start farming"
