#!/usr/bin/env bash
# =============================================================================
# Shell Setup Script
#
# Adds camply PATH, aliases, and environment to ~/.bashrc.
# Run once on a new machine after cloning the repo.
#
# Usage:
#   bash scripts/setup_shell.sh
# =============================================================================

set -euo pipefail

BASHRC="$HOME/.bashrc"
MARKER="# --- Camply Shell Setup ---"

# Check if already configured
if grep -q "$MARKER" "$BASHRC" 2>/dev/null; then
    echo "✅ Shell already configured (found marker in ~/.bashrc)"
    echo "   To reconfigure, remove the camply block from ~/.bashrc and re-run."
    exit 0
fi

cat >> "$BASHRC" << 'EOF'

# --- Camply Shell Setup ---
# Added by scripts/setup_shell.sh

# Camply / pipx binaries
export PATH=$PATH:$HOME/.local/bin:$HOME/.local/share/pipx/venvs/camply/bin

# Playwright display for VNC
export DISPLAY=:1

# Camply aliases
alias camply-watcher='~/.local/share/pipx/venvs/camply/bin/python ~/camply/scripts/watcher_with_cart.py'
alias camply-cart='~/.local/share/pipx/venvs/camply/bin/python ~/camply/scripts/playwright_add_to_cart.py'

# --- End Camply Shell Setup ---
EOF

echo "✅ Added to ~/.bashrc:"
echo "   • PATH (pipx + camply venv)"
echo "   • DISPLAY=:1 (for VNC)"
echo "   • camply-watcher alias"
echo "   • camply-cart alias"
echo ""
echo "Run 'source ~/.bashrc' or open a new terminal to apply."
