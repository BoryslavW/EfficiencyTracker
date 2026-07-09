#!/bin/bash
# ──────────────────────────────────────────────────────────────────────
# Valon AI — Universal Installer
#
# Detects your role and runs the right setup:
#   - Manager / Team Lead → Hub setup (dashboard + AI features)
#   - Engineer / Developer → Collector setup (background agent)
#   - Demo / Evaluation    → Hub setup with sample data
# ──────────────────────────────────────────────────────────────────────

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo ""
echo "  ╔══════════════════════════════════════╗"
echo "  ║    Valon AI — Task Analytics         ║"
echo "  ╚══════════════════════════════════════╝"
echo ""
echo "  How will you use this?"
echo ""
echo "    1) Manager / Team Lead"
echo "       Install the dashboard, analytics, and AI features."
echo "       Run this on the machine that will host the team dashboard."
echo ""
echo "    2) Engineer / Developer"
echo "       Install the background collector agent."
echo "       Runs invisibly — tracks your coding sessions and sends"
echo "       anonymous metrics to your team's Hub."
echo ""
echo "    3) Demo / Evaluation"
echo "       Set up the dashboard with pre-built sample data."
echo "       No real collectors needed — perfect for demos."
echo ""

read -p "  Choose [1/2/3]: " -n 1 -r
echo ""
echo ""

case "$REPLY" in
    1)
        bash "$SCRIPT_DIR/hub/install.sh"
        ;;
    2)
        bash "$SCRIPT_DIR/collector/collector_setup.sh"
        ;;
    3)
        bash "$SCRIPT_DIR/demo/install.sh"
        ;;
    *)
        echo "  Invalid choice. Run this script again and pick 1, 2, or 3."
        exit 1
        ;;
esac
