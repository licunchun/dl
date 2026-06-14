#!/usr/bin/env bash
# Daily data sync from USTC Pan (WebDAV via rclone).
# Usage: bash scripts/sync_data.sh
set -euo pipefail

export PATH="$HOME/.local/bin:$PATH"

REMOTE="ustc_pan:/A股数据"
LOCAL="/home/lcc17/pan_sync_20260528/A股数据"

echo "[sync] $(date -Is) pulling from USTC Pan..."

# Sync daily OHLCV (core)
rclone copy "$REMOTE/daily/" "$LOCAL/daily/" --include "*.csv" --update -v 2>&1 | tail -3

# Sync moneyflow
rclone copy "$REMOTE/moneyflow/" "$LOCAL/moneyflow/" --include "*.csv" --update -v 2>&1 | tail -3

# Sync metric (fundamentals)
rclone copy "$REMOTE/metric/" "$LOCAL/metric/" --include "*.csv" --update -v 2>&1 | tail -3

# Sync basic + trade_cal (rarely change, but keep updated)
rclone copy "$REMOTE/basic.csv" "$LOCAL/" --update 2>&1 | tail -1
rclone copy "$REMOTE/trade_cal.csv" "$LOCAL/" --update 2>&1 | tail -1

echo "[sync] done $(date -Is)"
