#!/usr/bin/env bash
# SFE daily signal pipeline — run by launchd at 4:30 PM ET on weekdays.
# Runs all engines, generates directional signals via Claude, scores matured
# signals, and regenerates the dashboard.

set -euo pipefail

cd /Users/samuelkemper/SFE

# launchd doesn't inherit shell env — source .env for API keys
set -a
source .env
set +a

export PATH="/opt/homebrew/bin:/Users/samuelkemper/.local/bin:$PATH"

LOG_DIR="output/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/daily-$(date +%Y-%m-%d).log"

exec > >(tee -a "$LOG_FILE") 2>&1

echo "=== SFE daily signals: $(date) ==="

# Skip weekends (launchd fires every day; cron-like day filtering not native)
DOW=$(date +%u)
if [ "$DOW" -gt 5 ]; then
    echo "Weekend — skipping."
    exit 0
fi

echo "[1/3] Running all engines..."
uv run sfe run-signals 2>&1

# Meta-layer (Claude signal generation) bypassed — collecting raw data only.
# Uncomment to re-enable:
# echo "[2/4] Generating directional signals via Claude..."
# uv run sfe generate-signals 2>&1

echo "[2/3] Scoring matured signals..."
uv run sfe score-signals 2>&1

echo "[3/3] Regenerating dashboard..."
uv run sfe dashboard 2>&1

echo "=== Done: $(date) ==="
