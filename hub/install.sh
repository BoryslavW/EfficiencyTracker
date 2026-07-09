#!/bin/bash
# ──────────────────────────────────────────────────────────────────────
# Valon AI — Hub Install (Manager / Team Lead)
#
# Run once after cloning the repo. Handles everything:
#   1. Checks Python 3.9+
#   2. Installs pip dependencies
#   3. Pulls Ollama model for AI features
#   4. Creates macOS desktop shortcut
#   5. Offers to generate demo data or start fresh
#   6. Launches the dashboard
# ──────────────────────────────────────────────────────────────────────

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
HUB_DIR="$SCRIPT_DIR"

echo ""
echo "  ╔══════════════════════════════════════╗"
echo "  ║    Valon AI — Hub Setup              ║"
echo "  ╚══════════════════════════════════════╝"
echo ""

# ── Step 1: Find Python ──────────────────────────────────────────────
PYTHON=""
for candidate in python3 /Library/Developer/CommandLineTools/usr/bin/python3 /usr/bin/python3 /usr/local/bin/python3; do
    if command -v "$candidate" &>/dev/null; then
        ver=$("$candidate" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null)
        major=$(echo "$ver" | cut -d. -f1)
        minor=$(echo "$ver" | cut -d. -f2)
        if [ "$major" -ge 3 ] && [ "$minor" -ge 9 ] 2>/dev/null; then
            PYTHON="$candidate"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo "  ✗ Python 3.9+ not found."
    echo "    Install from https://www.python.org/downloads/ or run:"
    echo "    xcode-select --install"
    exit 1
fi
echo "  ✓ Python: $PYTHON ($ver)"

# ── Step 2: Install pip dependencies ─────────────────────────────────
echo ""
echo "  Installing dependencies..."
"$PYTHON" -m pip install --user -q -r "$HUB_DIR/requirements.txt" 2>&1 | tail -1
echo "  ✓ Dependencies installed"

# ── Step 3: Ollama setup ─────────────────────────────────────────────
echo ""
OLLAMA_MODEL="${OLLAMA_MODEL:-qwen2.5-coder:7b}"

if command -v ollama &>/dev/null; then
    echo "  ✓ Ollama found"
    if ollama list 2>/dev/null | grep -q "$OLLAMA_MODEL"; then
        echo "  ✓ Model $OLLAMA_MODEL already pulled"
    else
        echo "  Pulling $OLLAMA_MODEL (this may take a few minutes)..."
        ollama pull "$OLLAMA_MODEL"
        echo "  ✓ Model ready"
    fi
else
    echo "  ⚠ Ollama not found — AI features (action plans, fix prompts) won't work."
    echo "    Install from https://ollama.ai and run: ollama pull $OLLAMA_MODEL"
    echo "    The dashboard will still work for all non-AI features."
fi

# ── Step 4: Desktop shortcut (macOS) ─────────────────────────────────
echo ""
if [[ "$OSTYPE" == "darwin"* ]]; then
    APP_PATH="$HOME/Desktop/Valon AI Dashboard.app"
    if [ -d "$APP_PATH" ]; then
        echo "  ✓ Desktop shortcut already exists"
    else
        osacompile -o "$APP_PATH" -e "
on run
    set appDir to \"$PROJECT_DIR\"
    set pyPath to \"$PYTHON\"
    try
        do shell script \"pgrep -f \\\"python3.*dashboard.py\\\" > /dev/null 2>&1\"
    on error
        do shell script \"cd \" & quoted form of appDir & \" && \" & quoted form of pyPath & \" hub/dashboard.py > /dev/null 2>&1 &\"
    end try
end run" 2>/dev/null
        echo "  ✓ Desktop shortcut created: ~/Desktop/Valon AI Dashboard.app"
    fi
else
    echo "  ⓘ Desktop shortcut is macOS-only (skipped)"
fi

# ── Step 5: Data setup ───────────────────────────────────────────────
echo ""
DATA_DIR="$PROJECT_DIR/data"
DEMO_DIR="$PROJECT_DIR/demo/demo_data"

if [ -f "$DATA_DIR/task_data.jsonl" ]; then
    echo "  ✓ Data already exists"
else
    if [ -d "$DEMO_DIR/startup" ]; then
        echo "  Loading demo data (Valon AI — startup preset)..."
        mkdir -p "$DATA_DIR" "$PROJECT_DIR/output"
        "$PYTHON" "$PROJECT_DIR/demo/demo_switch.py" startup
        echo "  ✓ Demo data loaded"
        echo ""
        echo "    Switch presets anytime with:"
        echo "      python3 demo/demo_switch.py fintech"
        echo "      python3 demo/demo_switch.py medtech"
    else
        echo "  Generating fresh demo data..."
        "$PYTHON" "$PROJECT_DIR/demo/generate_fake_data.py"
        echo "  ✓ Data generated"
    fi

    # Generate heatmap
    echo "  Generating analytics charts..."
    "$PYTHON" "$HUB_DIR/analytics.py" 2>/dev/null || true
    echo "  ✓ Charts ready"
fi

# ── Step 6: Launch ───────────────────────────────────────────────────
echo ""
echo "  ╔══════════════════════════════════════╗"
echo "  ║    Setup complete!                   ║"
echo "  ╚══════════════════════════════════════╝"
echo ""
echo "  To start the dashboard:"
echo "    python3 hub/dashboard.py"
echo ""
echo "  Or double-click 'Valon AI Dashboard' on your desktop."
echo ""

read -p "  Launch the dashboard now? [Y/n] " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Nn]$ ]]; then
    echo "  Done. Launch anytime with: python3 hub/dashboard.py"
else
    echo "  Starting dashboard..."
    cd "$PROJECT_DIR"
    "$PYTHON" hub/dashboard.py
fi
