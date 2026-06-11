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
CAMPLY_BIN="${HOME}/.local/share/pipx/venvs/camply/bin/camply"

# Use camply from PATH if venv binary doesn't exist
if [[ ! -x "$CAMPLY_BIN" ]]; then
    CAMPLY_BIN="camply"
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

    # Camply output wraps across lines. Join continuation lines, then parse.
    # Pattern: "⛰  Rec Area (#ID) - 🏕\n  Campground Name (#ID)"
    # Merge into single lines for parsing
    merged_output=$(echo "$output" | tr '\n' '§' | sed 's/§[[:space:]]*\([^[§]*\)(#/  \1(#/g' | tr '§' '\n')

    while IFS= read -r line; do
        # Match lines with both rec area and campground: ⛰ ... (#rec_id) - 🏕 ... (#cg_id)
        if [[ "$line" =~ ⛰ ]] && [[ "$line" =~ \#([0-9]+)\)[[:space:]]*$ ]]; then
            cg_id="${BASH_REMATCH[1]}"
            # Extract campground name (after 🏕, before (#id))
            cg_name=$(echo "$line" | sed 's/.*🏕[[:space:]]*//' | sed 's/ (#[0-9]*).*$//' | xargs)
            # Extract rec area info (after ⛰, before - 🏕)
            rec_area_info=$(echo "$line" | sed 's/.*⛰[[:space:]]*//' | sed 's/ - 🏕.*//' | xargs)

            if [[ -n "$cg_id" && -n "$cg_name" ]]; then
                RESULTS+=("RecreationDotGov|${cg_id}|${cg_name} (${rec_area_info})")
                RESULT_LINES+=("RecreationDotGov|${cg_id}|${cg_name} (${rec_area_info})")
                echo "  [${#RESULTS[@]}] ${cg_name} (#${cg_id}) — ${rec_area_info}"
            fi
        fi
    done <<< "$merged_output"

    if [[ ${#RESULTS[@]} -eq 0 || "$output" =~ "0 Matching" ]]; then
        echo "  No results on RecreationDotGov"
    fi
    echo ""
fi

# --- Search GoingToCamp (WA State Parks, rec-area 3) ---
if [[ -z "$PROVIDER" || "$PROVIDER" == "GoingToCamp" ]]; then
    echo "🔍 Searching GoingToCamp (WA State Parks)..."
    output=$($CAMPLY_BIN --provider GoingToCamp campgrounds --rec-area 3 --search "$SEARCH_TERM" 2>&1 || true)

    # Merge wrapped lines
    merged_output=$(echo "$output" | tr '\n' '§' | sed 's/§[[:space:]]*\([^[§]*\)(#/  \1(#/g' | tr '§' '\n')

    prev_count=${#RESULTS[@]}
    while IFS= read -r line; do
        if [[ "$line" =~ ⛰ ]] && [[ "$line" =~ \#(-?[0-9]+)\)[[:space:]]*$ ]]; then
            cg_id="${BASH_REMATCH[1]}"
            cg_name=$(echo "$line" | sed 's/.*🏕[[:space:]]*//' | sed 's/ (#-\?[0-9]*).*$//' | xargs)

            if [[ -n "$cg_id" && -n "$cg_name" ]]; then
                RESULTS+=("GoingToCamp|3|${cg_id}|${cg_name}")
                RESULT_LINES+=("GoingToCamp|3|${cg_id}|${cg_name}")
                echo "  [${#RESULTS[@]}] ${cg_name} (#${cg_id}) — WA State Parks"
            fi
        fi
    done <<< "$merged_output"

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
