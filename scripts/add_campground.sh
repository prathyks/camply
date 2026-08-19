#!/usr/bin/env bash
# =============================================================================
# Add Campground to campgrounds.conf
#
# Searches for a campground by name across providers and adds it to the config.
#
# Usage:
#   ./scripts/add_campground.sh "Lake Chelan"
#   ./scripts/add_campground.sh "Ohanapecosh" --provider RecreationDotGov
#   ./scripts/add_campground.sh "Deception" --provider GoingToCamp
#
# Without --provider, searches both RecreationDotGov and GoingToCamp (WA).
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONF_FILE="${SCRIPT_DIR}/../campgrounds.conf"

# Find camply binary - check PATH first, then common install locations
CAMPLY_BIN="$(command -v camply 2>/dev/null || true)"
if [[ -z "$CAMPLY_BIN" ]]; then
    for candidate in \
        "${HOME}/.local/bin/camply" \
        "${HOME}/.local/share/pipx/venvs/camply/bin/camply" \
        "${HOME}/.local/pipx/venvs/camply/bin/camply"; do
        if [[ -x "$candidate" ]]; then
            CAMPLY_BIN="$candidate"
            break
        fi
    done
fi
if [[ -z "$CAMPLY_BIN" ]]; then
    echo "ERROR: camply not found on PATH or common install locations."
    echo "       Install with: pipx install camply"
    exit 1
fi

# Parse arguments
SEARCH_TERM=""
PROVIDER=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --provider)
            PROVIDER="$2"
            shift 2
            ;;
        *)
            SEARCH_TERM="$1"
            shift
            ;;
    esac
done

if [[ -z "$SEARCH_TERM" ]]; then
    echo "Usage: $0 <search-term> [--provider RecreationDotGov|GoingToCamp]"
    echo ""
    echo "Examples:"
    echo "  $0 \"Lake Chelan\""
    echo "  $0 \"Ohanapecosh\" --provider RecreationDotGov"
    echo "  $0 \"Deception\" --provider GoingToCamp"
    exit 1
fi

echo "============================================="
echo "  Searching for: \"$SEARCH_TERM\""
echo "============================================="
echo ""

# Collect results
declare -a RESULTS=()
declare -a RESULT_LINES=()

# --- Search RecreationDotGov ---
if [[ -z "$PROVIDER" || "$PROVIDER" == "RecreationDotGov" ]]; then
    echo "🔍 Searching RecreationDotGov..."
    output=$($CAMPLY_BIN campgrounds --search "$SEARCH_TERM" 2>&1 || true)

    # Parse output: extract the LAST (#ID) on each line (campground ID)
    # Rec area info is captured from lines containing ⛰
    rec_area_info=""
    while IFS= read -r line; do
        # Capture rec area from lines with ⛰
        if echo "$line" | grep -q '⛰' 2>/dev/null; then
            rec_area_info=$(echo "$line" | sed 's/.*⛰[[:space:]]*//' | sed 's/ - 🏕.*$//' | sed 's/^[[:space:]]*//' | sed 's/[[:space:]]*$//')
        fi
        # Extract the last (#ID) from the line
        cg_id=$(echo "$line" | grep -oE '\(#[0-9]+\)' | tail -1 | tr -d '(#)' || true)
        if [[ -n "$cg_id" ]]; then
            # Skip rec area IDs (typically < 100000)
            if [[ "$cg_id" -gt 100000 ]]; then
                cg_name=$(echo "$line" | sed -E 's/\(#[0-9]+\)[[:space:]]*$//' | sed 's/.*🏕[[:space:]]*//' | sed 's/^[[:space:]]*//' | sed 's/[[:space:]]*$//')
                if [[ -n "$cg_id" && -n "$cg_name" ]]; then
                    RESULTS+=("RecreationDotGov|${cg_id}|${cg_name} (${rec_area_info})")
                    RESULT_LINES+=("RecreationDotGov|${cg_id}|${cg_name} (${rec_area_info})")
                    echo "  [${#RESULTS[@]}] ${cg_name} (#${cg_id}) — ${rec_area_info}"
                fi
            fi
        fi
    done <<< "$output"

    if [[ ${#RESULTS[@]} -eq 0 || "$output" =~ "0 Matching" ]]; then
        echo "  No results on RecreationDotGov"
    fi
    echo ""
fi

# --- Search GoingToCamp (WA State Parks, rec-area 3) ---
if [[ -z "$PROVIDER" || "$PROVIDER" == "GoingToCamp" ]]; then
    echo "🔍 Searching GoingToCamp (WA State Parks)..."
    output=$($CAMPLY_BIN --provider GoingToCamp campgrounds --rec-area 3 --search "$SEARCH_TERM" 2>&1 || true)

    # Parse output: extract the LAST (#ID) on each line (campground ID, not rec area ID)
    # Lines may contain both rec area (#3) and campground (#-2147483567)
    prev_count=${#RESULTS[@]}
    while IFS= read -r line; do
        # Extract the last (#ID) from the line using grep
        cg_id=$(echo "$line" | grep -oE '\(#-?[0-9]+\)' | tail -1 | tr -d '(#)' || true)
        if [[ -n "$cg_id" ]]; then
            # Skip rec area IDs (small positive numbers like #3)
            if [[ "$cg_id" -lt -1000 || "$cg_id" -gt 1000000 ]]; then
                # Extract name: text between 🏕 and the last (#id)
                cg_name=$(echo "$line" | sed -E 's/\(#-?[0-9]+\)[[:space:]]*$//' | sed -E 's/.*\(#[0-9]+\)[[:space:]]*-?[[:space:]]*//' | sed 's/.*🏕[[:space:]]*//' | sed 's/^[[:space:]]*//' | sed 's/[[:space:]]*$//')
                if [[ -n "$cg_id" && -n "$cg_name" ]]; then
                    RESULTS+=("GoingToCamp|3|${cg_id}|${cg_name}")
                    RESULT_LINES+=("GoingToCamp|3|${cg_id}|${cg_name}")
                    echo "  [${#RESULTS[@]}] ${cg_name} (#${cg_id}) — WA State Parks"
                fi
            fi
        fi
    done <<< "$output"

    if [[ ${#RESULTS[@]} -eq $prev_count ]]; then
        echo "  No results on GoingToCamp"
    fi
    echo ""
fi

# --- No results ---
if [[ ${#RESULTS[@]} -eq 0 ]]; then
    echo "No campgrounds found for \"$SEARCH_TERM\"."
    echo "Try a different search term or check the provider."
    exit 1
fi

# --- Select which to add ---
echo "============================================="
if [[ ${#RESULTS[@]} -eq 1 ]]; then
    echo "Found 1 result."
    selected=1
else
    echo "Found ${#RESULTS[@]} results. Which to add? (enter number, or 0 to cancel)"
    read -rp "> " selected
    if [[ "$selected" == "0" || -z "$selected" ]]; then
        echo "Cancelled."
        exit 0
    fi
fi

# Validate selection
if [[ "$selected" -lt 1 || "$selected" -gt ${#RESULTS[@]} ]]; then
    echo "Invalid selection."
    exit 1
fi

selected_line="${RESULT_LINES[$((selected-1))]}"

# --- Check if already in conf ---
# Extract the ID to check for duplicates
selected_id=$(echo "$selected_line" | awk -F'|' '{if ($1=="GoingToCamp") print $3; else print $2}')
if grep -q "|${selected_id}|" "$CONF_FILE" 2>/dev/null || grep -q "|${selected_id}\$" "$CONF_FILE" 2>/dev/null; then
    echo ""
    echo "⚠️  This campground (ID: ${selected_id}) is already in campgrounds.conf!"
    exit 0
fi

# --- Add to conf ---
echo ""
echo "Adding to campgrounds.conf:"
echo "  $selected_line"
echo "$selected_line" >> "$CONF_FILE"
echo ""
echo "✅ Added! Current campgrounds:"
echo ""
grep -v "^#\|^$\|^[A-Z_]*=" "$CONF_FILE" | while IFS='|' read -r provider rest; do
    if [[ "$provider" == "RecreationDotGov" ]]; then
        id=$(echo "$rest" | cut -d'|' -f1)
        name=$(echo "$rest" | cut -d'|' -f2)
        echo "  • [RecDotGov] $name (#$id)"
    elif [[ "$provider" == "GoingToCamp" ]]; then
        rec_area=$(echo "$rest" | cut -d'|' -f1)
        id=$(echo "$rest" | cut -d'|' -f2)
        name=$(echo "$rest" | cut -d'|' -f3)
        echo "  • [GoingToCamp] $name (#$id)"
    fi
done
