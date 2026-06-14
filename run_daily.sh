#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
export QUANT_RUN_DAILY_SH=1
export QUANT_RUN_DAILY_SCRIPT="$PWD/run_daily.sh"
export QUANT_RUN_DAILY_COMMAND="bash run_daily.sh"
python -m agent.run_entrypoint
