#!/bin/bash
# ──────────────────────────────────────────────────────────────────
# Valon AI — Manager / Team Lead Installer
# Double-click this file to install the dashboard on your Mac.
# ──────────────────────────────────────────────────────────────────

clear
echo ""
echo "  ╔══════════════════════════════════════╗"
echo "  ║  Valon AI — Manager Install          ║"
echo "  ╚══════════════════════════════════════╝"
echo ""

INSTALL_DIR="$HOME/ValonAI"

# Check for git
if ! command -v git &>/dev/null; then
    echo "  Git not found. Installing Xcode Command Line Tools..."
    echo "  (A popup may appear — click Install and wait.)"
    xcode-select --install 2>/dev/null
    echo ""
    echo "  After installation finishes, double-click this file again."
    read -p "  Press Enter to close..." -r
    exit 0
fi

# Clone or update
if [ -d "$INSTALL_DIR/.git" ]; then
    echo "  Updating existing installation..."
    cd "$INSTALL_DIR"
    git pull origin main 2>/dev/null || true
else
    echo "  Downloading Valon AI..."
    git clone https://github.com/BoryslavW/EfficiencyTracker.git "$INSTALL_DIR" 2>&1
fi

if [ ! -d "$INSTALL_DIR/hub" ]; then
    echo ""
    echo "  ✗ Download failed. Check your internet connection and try again."
    read -p "  Press Enter to close..." -r
    exit 1
fi

echo "  ✓ Downloaded to $INSTALL_DIR"
echo ""

# Run the hub installer
cd "$INSTALL_DIR"
bash hub/install.sh
