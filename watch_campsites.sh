#!/usr/bin/env bash
# =============================================================================
# Camply Campsite Watcher Script
# Monitors campgrounds and sends Telegram notifications when sites are available.
#
# Configuration:
#   .env              - Telegram credentials (git-ignored)
#   campgrounds.conf  - Campground list and search parameters (edit freely)
#
# Usage:
#   ./watch_campsites.sh          # Start all watchers
#   ./watch_campsites.sh stop     # Stop all running watchers
#   ./watch_campsites.sh status   # Show status of running watchers
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/.env"
CONF_FILE="${SCRIPT_DIR}/campgrounds.conf"
LOG_DIR="${SCRIPT_DIR}/logs/camply"
PID_DIR="${SCRIPT_DIR}/.camply_pids"

# =============================================================================
# Load Environment & Config
# =============================================================================

if [[ ! -f "$ENV_FILE" ]]; then
    echo "ERROR: .env file not found at $ENV_FILE"
    echo "Create it with:"
    echo "  TELEGRAM_BOT_TOKEN=<your-bot-token>"
    echo "  TELEGRAM_CHAT_ID=<your-chat-id>"
    exit 1
fi
source "$ENV_FILE"
export TELEGRAM_BOT_TOKEN
export TELEGRAM_CHAT_ID

if [[ -z "${TELEGRAM_BOT_TOKEN:-}" || -z "${TELEGRAM_CHAT_ID:-}" ]]; then
    echo "ERROR: TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set in .env"
    exit 1
fi

if [[ ! -f "$CONF_FILE" ]]; then
    echo "ERROR: campgrounds.conf not found at $CONF_FILE"
    exit 1
fi

# Parse search parameters from config
START_DATE=$(grep '^START_DATE=' "$CONF_FILE" | cut -d= -f2)
END_DATE=$(grep '^END_DATE=' "$CONF_FILE" | cut -d= -f2)
NIGHTS=$(grep '^NIGHTS=' "$CONF_FILE" | cut -d= -f2)
POLLING_INTERVAL=$(grep '^POLLING_INTERVAL=' "$CONF_FILE" | cut -d= -f2)

if [[ -z "$START_DATE" || -z "$END_DATE" ]]; then
    echo "ERROR: START_DATE and END_DATE must be set in campgrounds.conf"
    exit 1
fi

mkdir -p "$LOG_DIR" "$PID_DIR"

# =============================================================================
# Parse Campgrounds from Config
# =============================================================================

declare -a RECDOTGOV_IDS=()
declare -a RECDOTGOV_NAMES=()
declare -a GTC_REC_AREAS=()
declare -a GTC_IDS=()
declare -a GTC_NAMES=()

while IFS= read -r line; do
    # Skip comments and blank lines
    [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue
    # Skip parameter lines
    [[ "$line" =~ ^[A-Z_]+= ]] && continue

    provider=$(echo "$line" | cut -d'|' -f1)

    if [[ "$provider" == "RecreationDotGov" ]]; then
        cg_id=$(echo "$line" | cut -d'|' -f2)
        cg_name=$(echo "$line" | cut -d'|' -f3)
        RECDOTGOV_IDS+=("$cg_id")
        RECDOTGOV_NAMES+=("$cg_name")
    elif [[ "$provider" == "GoingToCamp" ]]; then
        rec_area=$(echo "$line" | cut -d'|' -f2)
        cg_id=$(echo "$line" | cut -d'|' -f3)
        cg_name=$(echo "$line" | cut -d'|' -f4)
        GTC_REC_AREAS+=("$rec_area")
        GTC_IDS+=("$cg_id")
        GTC_NAMES+=("$cg_name")
    fi
done < "$CONF_FILE"

# =============================================================================
# Functions
# =============================================================================

stop_watchers() {
    echo "Stopping all camply watchers..."
    local stopped=0
    if [[ -d "$PID_DIR" ]]; then
        for pid_file in "$PID_DIR"/*.pid; do
            [[ -f "$pid_file" ]] || continue
            pid=$(cat "$pid_file")
            if kill -0 "$pid" 2>/dev/null; then
                kill "$pid"
                echo "  Stopped PID $pid ($(basename "$pid_file" .pid))"
                ((stopped++))
            fi
            rm -f "$pid_file"
        done
    fi
    if [[ $stopped -eq 0 ]]; then
        echo "  No watchers were running."
    else
        echo "  Stopped $stopped watcher(s)."
    fi
}

show_status() {
    echo "============================================="
    echo "  Camply Watcher Status"
    echo "============================================="
    echo "  Dates:  $START_DATE to $END_DATE"
    echo "  Nights: $NIGHTS consecutive"
    echo "---------------------------------------------"
    if [[ -d "$PID_DIR" ]]; then
        local running=0
        for pid_file in "$PID_DIR"/*.pid; do
            [[ -f "$pid_file" ]] || continue
            pid=$(cat "$pid_file")
            name=$(basename "$pid_file" .pid)
            if kill -0 "$pid" 2>/dev/null; then
                echo "  ✅ $name (PID $pid) - running"
                ((running++))
            else
                echo "  ❌ $name (PID $pid) - stopped"
                rm -f "$pid_file"
            fi
        done
        if [[ $running -eq 0 ]]; then
            echo "  No watchers running."
        fi
    else
        echo "  No watchers running."
    fi
    echo "============================================="
}

start_watchers() {
    echo "============================================="
    echo "  Camply Campsite Watcher"
    echo "============================================="
    echo "  Dates:    $START_DATE to $END_DATE"
    echo "  Nights:   $NIGHTS consecutive"
    echo "  Polling:  every ${POLLING_INTERVAL} minutes"
    echo "  Notify:   Telegram"
    echo "============================================="
    echo ""

    # --- RecreationDotGov Watcher ---
    if [[ ${#RECDOTGOV_IDS[@]} -gt 0 ]]; then
        local recdotgov_args=""
        for cg_id in "${RECDOTGOV_IDS[@]}"; do
            recdotgov_args+="--campground $cg_id "
        done

        echo "Starting RecreationDotGov watcher..."
        for name in "${RECDOTGOV_NAMES[@]}"; do
            echo "  • $name"
        done

        camply campsites \
            $recdotgov_args \
            --start-date "$START_DATE" \
            --end-date "$END_DATE" \
            --nights "$NIGHTS" \
            --notifications telegram \
            --search-forever \
            --polling-interval "$POLLING_INTERVAL" \
            > "$LOG_DIR/recdotgov_$(date +%Y%m%d_%H%M%S).log" 2>&1 &
        echo $! > "$PID_DIR/recdotgov.pid"
        echo "  ➜ Started (PID $!)"
        echo ""
    fi

    # --- GoingToCamp Watcher ---
    # Group by rec_area (in case you add parks from different states later)
    if [[ ${#GTC_IDS[@]} -gt 0 ]]; then
        declare -A gtc_groups=()
        for i in "${!GTC_IDS[@]}"; do
            rec_area="${GTC_REC_AREAS[$i]}"
            gtc_groups["$rec_area"]+="--campground ${GTC_IDS[$i]} "
        done

        for rec_area in "${!gtc_groups[@]}"; do
            echo "Starting GoingToCamp watcher (rec-area $rec_area)..."
            for i in "${!GTC_REC_AREAS[@]}"; do
                if [[ "${GTC_REC_AREAS[$i]}" == "$rec_area" ]]; then
                    echo "  • ${GTC_NAMES[$i]}"
                fi
            done

            camply --provider GoingToCamp campsites \
                --rec-area "$rec_area" \
                ${gtc_groups[$rec_area]} \
                --start-date "$START_DATE" \
                --end-date "$END_DATE" \
                --nights "$NIGHTS" \
                --notifications telegram \
                --search-forever \
                --polling-interval "$POLLING_INTERVAL" \
                > "$LOG_DIR/goingtocamp_${rec_area}_$(date +%Y%m%d_%H%M%S).log" 2>&1 &
            echo $! > "$PID_DIR/goingtocamp_${rec_area}.pid"
            echo "  ➜ Started (PID $!)"
            echo ""
        done
    fi

    echo "============================================="
    echo "  Watchers running in background!"
    echo "  Logs:   $LOG_DIR/"
    echo "  Stop:   ./watch_campsites.sh stop"
    echo "  Status: ./watch_campsites.sh status"
    echo "============================================="
}

# =============================================================================
# Main
# =============================================================================

case "${1:-start}" in
    stop)
        stop_watchers
        ;;
    status)
        show_status
        ;;
    start|"")
        stop_watchers 2>/dev/null || true
        start_watchers
        ;;
    *)
        echo "Usage: $0 [start|stop|status]"
        exit 1
        ;;
esac
