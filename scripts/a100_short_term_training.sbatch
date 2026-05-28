#!/usr/bin/env bash
#SBATCH --job-name=a100_short_term
#SBATCH --partition=A100
#SBATCH --qos=normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --gres=gpu:1
#SBATCH --time=12:00:00
#SBATCH --output=reports/slurm/%x-%j.out
#SBATCH --error=reports/slurm/%x-%j.err

set -euo pipefail

cd /home/lcc17/dl
mkdir -p reports/slurm reports/daily_logs reports/backtest_lstm_ic_short_mf_h256_l2_w10

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

echo "[job] short-term competition model"
python scripts/short_term_competition_train.py \
  --data-dir /home/lcc17/pan_sync_20260528/A股数据 \
  --start 2024-01-01 \
  --train-end 2026-04-30 \
  --val-start 2026-05-06 \
  --val-end 2026-05-27 \
  --asof-date 2026-05-28 \
  --target-date 2026-06-01 \
  --tag lstm_ic_short_mf_h256_l2_w10 \
  --window 10 \
  --hidden 256 \
  --layers 2 \
  --dropout 0.25 \
  --epochs 12 \
  --batch-cap 8192

echo "[job] done $(date -Is)"
