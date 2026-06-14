#!/usr/bin/env bash
set -euo pipefail

JOB_ID="${1:-27558}"
INTERVAL_SECONDS="${INTERVAL_SECONDS:-1800}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$ROOT/review-stage/SHORT_TERM_MONITOR.md"
SLURM_OUT="$ROOT/reports/slurm/a100_short_term-${JOB_ID}.out"
SLURM_ERR="$ROOT/reports/slurm/a100_short_term-${JOB_ID}.err"

mkdir -p "$ROOT/review-stage"

{
  echo "# Short-Term Job Monitor"
  echo
  echo "- Job: \`$JOB_ID\`"
  echo "- Started monitor: $(date -Is)"
  echo "- Poll interval seconds: \`$INTERVAL_SECONDS\`"
  echo
} >> "$OUT"

while true; do
  {
    echo "## Poll $(date -Is)"
    echo
    echo '```text'
    squeue -j "$JOB_ID" -o '%.18i %.10P %.24j %.8u %.2t %.10M %.6D %R' || true
    echo '```'
    echo
    echo "### stdout tail"
    echo '```text'
    tail -n 80 "$SLURM_OUT" 2>/dev/null || true
    echo '```'
    echo
    echo "### stderr tail"
    echo '```text'
    tail -n 80 "$SLURM_ERR" 2>/dev/null || true
    echo '```'
    echo
  } >> "$OUT"

  if ! squeue -h -j "$JOB_ID" >/dev/null 2>&1 || [ -z "$(squeue -h -j "$JOB_ID" 2>/dev/null)" ]; then
    {
      echo "## Completion Check $(date -Is)"
      echo
      echo "Slurm job is no longer in queue. Inspect final artifacts:"
      echo
      echo "- \`checkpoints/lstm_ic_short_mf_decay_h256_l2_w10_train_log.json\`"
      echo "- \`reports/backtest_lstm_ic_short_mf_decay_h256_l2_w10/stats.json\`"
      echo "- \`reports/daily_logs/20260601_short_term_targets.csv\`"
      echo
    } >> "$OUT"
    break
  fi

  sleep "$INTERVAL_SECONDS"
done
