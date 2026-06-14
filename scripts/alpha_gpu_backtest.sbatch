#!/usr/bin/env bash
#SBATCH --job-name=alpha_gpu_backtest
#SBATCH --partition=A800
#SBATCH --qos=normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:1
#SBATCH --time=02:00:00
#SBATCH --output=reports/slurm/%x-%j.out
#SBATCH --error=reports/slurm/%x-%j.err

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"
mkdir -p reports/slurm

echo "[job] start $(date -Is)"
echo "[job] host $(hostname)"
echo "[job] job ${SLURM_JOB_ID:-unknown}"
echo "[job] cuda_visible ${CUDA_VISIBLE_DEVICES:-unset}"

source /opt/Software/Anaconda3/etc/profile.d/conda.sh
conda activate dl

python --version
nvidia-smi

python - <<'PY'
import torch
print("[env] torch", torch.__version__)
print("[env] cuda_available", torch.cuda.is_available())
print("[env] device_count", torch.cuda.device_count())
if torch.cuda.is_available():
    print("[env] device0", torch.cuda.get_device_name(0))
if not torch.cuda.is_available():
    raise SystemExit("CUDA is not available on allocated node")
PY

export ALPHA_BACKEND=torch_cuda
export ALPHA_FAST="${ALPHA_FAST:-0}"
export ALPHA_CANDIDATES="${ALPHA_CANDIDATES:-A029}"
export ALPHA_HORIZONS="${ALPHA_HORIZONS:-5}"
export ALPHA_COSTS="${ALPHA_COSTS:-5,10,20,30}"
export ALPHA_START="${ALPHA_START:-20190101}"
export ALPHA_END="${ALPHA_END:-20260528}"

echo "[job] backend ${ALPHA_BACKEND}"
echo "[job] candidates ${ALPHA_CANDIDATES}"
echo "[job] horizons ${ALPHA_HORIZONS}"
echo "[job] costs ${ALPHA_COSTS}"
echo "[job] window ${ALPHA_START}-${ALPHA_END}"

python alpha-stage/scripts/alpha_backtest.py

python - <<'PY'
import json
from pathlib import Path

for r in json.loads(Path("alpha-stage/artifacts/alpha_results.json").read_text(encoding="utf-8")):
    test = r["splits"]["test"]
    lo = test.get("long_only") or {}
    port = test.get("portfolio") or {}
    print(
        "[result]",
        r["alpha_id"],
        "rankic", test.get("rankic_mean"),
        "ls_ann", port.get("ann_return_net"),
        "lo_ann", lo.get("ann_return_net"),
        "lo_sharpe", lo.get("sharpe_net"),
    )
PY

echo "[job] done $(date -Is)"
