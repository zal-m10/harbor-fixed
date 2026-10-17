#!/bin/bash
# Harbor Fixed — one-line installer.
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/zal-m10/universal-farm/main/install.sh | bash
#   or:
#   wget -qO- https://raw.githubusercontent.com/zal-m10/universal-farm/main/install.sh | bash
set -e

REPO_URL="https://github.com/zal-m10/universal-farm.git"
INSTALL_DIR="$HOME/universal-farm"

echo "=== Harbor Fixed installer ==="

# Detect Termux (Android).
IS_TERMUX=0
if [ -n "$PREFIX" ] && [ -d "$PREFIX" ] && echo "$PREFIX" | grep -q "com.termux"; then
    IS_TERMUX=1
fi

# sudo helper: only if we are not root and sudo exists.
SUDO=""
if [ "$(id -u)" -ne 0 ] && command -v sudo >/dev/null 2>&1; then
    SUDO="sudo"
fi

# 1. System dependencies.
echo "[1/5] Installing system packages..."
if [ "$IS_TERMUX" -eq 1 ]; then
    pkg update -y -qq 2>/dev/null || pkg update -y
    pkg install -y -qq python git curl 2>/dev/null || pkg install -y python git curl
elif command -v apt-get >/dev/null 2>&1; then
    $SUDO apt-get update -qq
    $SUDO apt-get install -y -qq python3 python3-venv git curl
else
    echo "apt-get not found — install python3, git, curl manually, then re-run."
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
"$PYBIN" -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q playwright requests rich

# 4. Chromium for Playwright (needed by TokenHarbor browser farm).
echo "[4/5] Installing Chromium..."
if [ "$IS_TERMUX" -eq 1 ]; then
    echo "Skipped on Termux (Chromium does not run on Android)."
    echo "TokenHarbor browser farm needs a VPS; Mistral & Dahl (pure HTTP) work on Termux."
else
    .venv/bin/python -m playwright install chromium 2>&1 | tail -1
    if command -v apt-get >/dev/null 2>&1; then
        $SUDO .venv/bin/python -m playwright install-deps chromium 2>&1 | tail -1 || true
    fi
fi

# 5. Install the `farm` command.
echo "[5/5] Installing 'farm' command..."
FARM_BIN="/usr/local/bin/farm"
FARM_SCRIPT="#!/bin/bash
cd \"$INSTALL_DIR\" || exit 1
exec \"$INSTALL_DIR/.venv/bin/python\" -m tools.tokenharbor.farm_tui \"\$@\"
"
if [ -w /usr/local/bin ]; then
    echo "$FARM_SCRIPT" | $SUDO tee "$FARM_BIN" >/dev/null
    $SUDO chmod +x "$FARM_BIN"
else
    mkdir -p "$HOME/.local/bin"
    echo "$FARM_SCRIPT" > "$HOME/.local/bin/farm"
    chmod +x "$HOME/.local/bin/farm"
    FARM_BIN="$HOME/.local/bin/farm"
    echo "Note: add \$HOME/.local/bin to your PATH if 'farm' is not found:"
    echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
fi

echo ""
echo "=== Done ==="
echo "Type  'farm'  to open the interactive menu."
echo ""
echo "First steps inside the menu:"
echo "  [1] Farm TokenHarbor -> [3] Setup email  (Tempik URL or Temp Mail)"
echo "  [6] Setup Proxy      -> user:pass@host:port (one per line)"
echo "  [7] Setup Bot Tele   -> Telegram notifications (optional)"
echo "  [1] Farm TokenHarbor -> [1] Run farm"

# 6. Verify critical files are in place (fresh-install smoke test).
echo ""
echo "[6/6] Verifying installation..."
OK=1
for f in "tools/tokenharbor/farm_tui.py" \
         "tools/tokenharbor/dahl_farm.py" \
         "tools/tokenharbor/monitors/tokenharbor_inject_monitor.py" \
         "tools/tokenharbor/monitors/mistral_inject_monitor.py" \
         "tools/tokenharbor/monitors/dahl_inject_monitor.py"; do
    if [ -f "$INSTALL_DIR/$f" ]; then
        echo "  ✓ $f"
    else
        echo "  ✗ MISSING: $f"
        OK=0
    fi
done
if [ -f "$INSTALL_DIR/tools/tokenharbor/monitors/tokenharbor_inject_monitor.py" ]; then
    chmod +x "$INSTALL_DIR"/tools/tokenharbor/monitors/*.py
fi
if [ "$OK" -eq 1 ]; then
    echo "All critical files present. Ready to farm."
else
    echo "WARNING: Some files are missing. Try: cd $INSTALL_DIR && git pull"
fi
