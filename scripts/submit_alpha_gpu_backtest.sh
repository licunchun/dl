#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

export ALPHA_CANDIDATES="${ALPHA_CANDIDATES:-A029}"
export ALPHA_HORIZONS="${ALPHA_HORIZONS:-5}"
export ALPHA_COSTS="${ALPHA_COSTS:-5,10,20,30}"
export ALPHA_START="${ALPHA_START:-20190101}"
export ALPHA_END="${ALPHA_END:-20260528}"
export ALPHA_FAST="${ALPHA_FAST:-0}"
export ALPHA_BACKEND="${ALPHA_BACKEND:-torch_cuda}"

export SLURM_PARTITION="${SLURM_PARTITION:-A800}"
export SLURM_QOS="${SLURM_QOS:-normal}"
export SLURM_GPUS="${SLURM_GPUS:-1}"
export SLURM_CPUS_PER_TASK="${SLURM_CPUS_PER_TASK:-8}"
export SLURM_TIME="${SLURM_TIME:-02:00:00}"

mkdir -p reports/slurm

echo "[submit] candidates=${ALPHA_CANDIDATES}"
echo "[submit] horizons=${ALPHA_HORIZONS}"
echo "[submit] costs=${ALPHA_COSTS}"
echo "[submit] window=${ALPHA_START}-${ALPHA_END}"
echo "[submit] fast=${ALPHA_FAST}"
echo "[submit] backend=${ALPHA_BACKEND}"
echo "[submit] partition=${SLURM_PARTITION}"
echo "[submit] qos=${SLURM_QOS}"
echo "[submit] gpus=${SLURM_GPUS}"
echo "[submit] cpus_per_task=${SLURM_CPUS_PER_TASK}"
echo "[submit] time=${SLURM_TIME}"
if [ -n "${SLURM_ACCOUNT:-}" ]; then
  echo "[submit] account=${SLURM_ACCOUNT}"
fi
echo "[submit] submitting scripts/alpha_gpu_backtest.sbatch"

sbatch_args=(
  --export=ALL
  --partition="${SLURM_PARTITION}"
  --qos="${SLURM_QOS}"
  --gres="gpu:${SLURM_GPUS}"
  --cpus-per-task="${SLURM_CPUS_PER_TASK}"
  --time="${SLURM_TIME}"
)

if [ -n "${SLURM_ACCOUNT:-}" ]; then
  sbatch_args+=(--account="${SLURM_ACCOUNT}")
fi

sbatch "${sbatch_args[@]}" scripts/alpha_gpu_backtest.sbatch
