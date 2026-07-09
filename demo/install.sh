#!/bin/bash
# ──────────────────────────────────────────────────────────────────────
# Valon AI — Demo Setup
#
# For evaluation / demo day only. Sets up everything needed to run
# the dashboard with pre-built sample data — no real collectors needed.
# ──────────────────────────────────────────────────────────────────────

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo ""
echo "  ╔══════════════════════════════════════╗"
echo "  ║    Valon AI — Demo Setup             ║"
echo "  ╚══════════════════════════════════════╝"
echo ""

# Delegate to hub install (handles Python, deps, Ollama, shortcut)
bash "$PROJECT_DIR/hub/install.sh"
