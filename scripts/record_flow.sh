#!/usr/bin/env bash
# =============================================================================
# Record Playwright Flow with a GoingToCamp Booking URL
#
# Generates a booking URL using camply, then opens Playwright codegen
# pointed at that URL. Record the flow:
#   1. Accept cookies
#   2. Login
#   3. (You'll already be on the search results page)
#   4. Switch to List view
#   5. Click an available site
#   6. Click Reserve → Confirm
#
# Usage:
#   cd ~/camply
#   bash scripts/record_flow.sh
#   bash scripts/record_flow.sh --campground -2147483567 --start-date 2026-07-03 --end-date 2026-07-05
#
# Defaults (edit below or pass as arguments):
#   Campground: Conconully (-2147483628)
#   Dates: 2026-06-19 to 2026-06-21
#   Party: 4 people, 1 tent
# =============================================================================

set -euo pipefail

cd "$(dirname "$0")/.."

# Defaults
REC_AREA=3
CAMPGROUND="-2147483628"
START_DATE="2026-06-19"
END_DATE="2026-06-21"
PARTY_SIZE=4
EQUIPMENT_ID="-32768"

# Parse optional arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --campground) CAMPGROUND="$2"; shift 2 ;;
        --start-date) START_DATE="$2"; shift 2 ;;
        --end-date) END_DATE="$2"; shift 2 ;;
        --party-size) PARTY_SIZE="$2"; shift 2 ;;
        --equipment-id) EQUIPMENT_ID="$2"; shift 2 ;;
        --rec-area) REC_AREA="$2"; shift 2 ;;
        *) echo "Unknown arg: $1"; exit 1 ;;
    esac
done

echo "============================================="
echo "  Generating Booking URL..."
echo "============================================="
echo "  Campground: $CAMPGROUND"
echo "  Dates: $START_DATE to $END_DATE"
echo "  Party: $PARTY_SIZE people"
echo "  Equipment: $EQUIPMENT_ID"
echo ""

# Generate URL using camply
BOOKING_URL=$(camply --provider GoingToCamp booking-url \
    --rec-area "$REC_AREA" \
    --campground "$CAMPGROUND" \
    --start-date "$START_DATE" \
    --end-date "$END_DATE" \
    --party-size "$PARTY_SIZE" \
    --equipment-id "$EQUIPMENT_ID" 2>/dev/null | grep "^https://")

if [[ -z "$BOOKING_URL" ]]; then
    echo "ERROR: Failed to generate booking URL"
    exit 1
fi

echo "  URL: $BOOKING_URL"
echo ""
echo "============================================="
echo "  Starting Playwright Recorder..."
echo "============================================="
echo ""
echo "  Steps to record:"
echo "    1. Accept cookies (if shown)"
echo "    2. Sign in to your account"
echo "    3. PASTE this URL into the address bar:"
echo ""
echo "       $BOOKING_URL"
echo ""
echo "    4. Switch to List view"
echo "    5. Click an available site"
echo "    6. Click Reserve → Confirm"
echo ""
echo "  Close browser when done. Output: scripts/recorded_flow.py"
echo "============================================="
echo ""

# Start at home page so user can login first, then navigate to booking URL
~/.local/share/pipx/venvs/camply/bin/python -m playwright codegen \
    --target python \
    --output scripts/recorded_flow.py \
    "https://washington.goingtocamp.com"
