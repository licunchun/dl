#!/usr/bin/env bash
#SBATCH --job-name=a100_short_w5_h128
#SBATCH --partition=A100
#SBATCH --qos=normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --gres=gpu:1
#SBATCH --time=06:00:00
#SBATCH --output=reports/slurm/%x-%j.out
#SBATCH --error=reports/slurm/%x-%j.err

set -euo pipefail

cd /home/lcc17/dl
mkdir -p reports/slurm reports/daily_logs reports/backtest_lstm_ic_short_w5_h128_hl90

echo "[job] start $(date -Is)"
echo "[job] host $(hostname)"
echo "[job] cwd $(pwd)"
echo "[job] slurm job id ${SLURM_JOB_ID:-unknown}"

source /opt/Software/Anaconda3/etc/profile.d/conda.sh
conda activate dl

python --version
python - <<'PY'
import torch
print("[env] torch", torch.__version__)
print("[env] cuda_available", torch.cuda.is_available())
if torch.cuda.is_available():
    print("[env] device0", torch.cuda.get_device_name(0))
PY
nvidia-smi

echo "[job] short-term window=5 hidden=128 half-life=90"
python -u scripts/short_term_competition_train.py \
  --data-dir /home/lcc17/pan_sync_20260528/A股数据 \
  --start 2019-01-01 \
  --train-end 2026-04-30 \
  --val-start 2026-05-06 \
  --val-end 2026-05-27 \
  --asof-date 2026-05-28 \
  --target-date 2026-06-01 \
  --tag lstm_ic_short_w5_h128_hl90 \
  --window 5 \
  --hidden 128 \
  --layers 2 \
  --dropout 0.3 \
  --epochs 10 \
  --batch-cap 8192 \
  --half-life-days 90 \
  --min-date-weight 0.35

echo "[job] done $(date -Is)"
