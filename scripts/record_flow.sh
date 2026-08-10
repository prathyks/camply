#!/usr/bin/env bash
# =============================================================================
# Record Playwright UI-Navigation Flow for GoingToCamp
#
# Opens Playwright codegen at the GoingToCamp home page. Record the FULL
# UI navigation flow so we capture all interaction patterns (including
# campgrounds with multiple sub-areas like Lake Wenatchee North/South).
#
# Record these steps:
#   1. Accept cookies (I Consent)
#   2. Sign in
#   3. Click "Create reservation"
#   4. Select the park
#   5. Set dates
#   6. Set party size (Add one)
#   7. Select equipment (tent)
#   8. Click "Search for availability"
#   9. Switch to List view
#   10. Expand any sub-area / site group (IMPORTANT: capture this for
#       multi-campground parks like Lake Wenatchee)
#   11. Click an available site
#   12. Click Reserve
#   13. Check "All reservation details are correct"
#   14. Click "Confirm reservation details"
#
# Usage:
#   cd ~/camply
#   bash scripts/record_flow.sh                       # -> scripts/recorded_flow.py
#   bash scripts/record_flow.sh lake_wenatchee        # -> scripts/recorded_lake_wenatchee.py
#   bash scripts/record_flow.sh conconully            # -> scripts/recorded_conconully.py
# =============================================================================

set -euo pipefail

cd "$(dirname "$0")/.."

# Output file name (defaults to recorded_flow.py)
LABEL="${1:-flow}"
OUTPUT="scripts/recorded_${LABEL}.py"

# Find camply venv python (has playwright installed)
PYTHON=""
for candidate in \
    "${HOME}/.local/share/pipx/venvs/camply/bin/python" \
    "${HOME}/.local/pipx/venvs/camply/bin/python"; do
    if [[ -x "$candidate" ]]; then
        PYTHON="$candidate"
        break
    fi
done
if [[ -z "$PYTHON" ]]; then
    echo "ERROR: camply venv python not found"
    exit 1
fi

echo "============================================="
echo "  Playwright UI-Navigation Recorder"
echo "============================================="
echo "  Output: $OUTPUT"
echo ""
echo "  Record the FULL flow via the UI:"
echo "    1. Accept cookies (I Consent)"
echo "    2. Sign in to your account"
echo "    3. Click 'Create reservation'"
echo "    4. Select the park"
echo "    5. Set dates"
echo "    6. Set party size (Add one)"
echo "    7. Select equipment (tent)"
echo "    8. Click 'Search for availability'"
echo "    9. Switch to List view"
echo "   10. Expand sub-area / site group (IMPORTANT for"
echo "       multi-campground parks like Lake Wenatchee!)"
echo "   11. Click an available site"
echo "   12. Click Reserve"
echo "   13. Check 'All reservation details are correct'"
echo "   14. Click 'Confirm reservation details'"
echo ""
echo "  Close browser when done."
echo "============================================="
echo ""

"$PYTHON" -m playwright codegen \
    --target python \
    --output "$OUTPUT" \
    "https://washington.goingtocamp.com"

echo ""
echo "✅ Recording saved to: $OUTPUT"
