#!/usr/bin/env bash
#SBATCH --job-name=a100_regime_adapt
#SBATCH --partition=A100
#SBATCH --qos=normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --gres=gpu:1
#SBATCH --time=1-00:00:00
#SBATCH --output=reports/slurm/%x-%j.out
#SBATCH --error=reports/slurm/%x-%j.err

set -euo pipefail

cd /home/lcc17/dl
mkdir -p reports/slurm reports/may_2026_validation

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
print("[env] device_count", torch.cuda.device_count())
if torch.cuda.is_available():
    print("[env] device0", torch.cuda.get_device_name(0))
PY
nvidia-smi

echo "[job] input checks"
test -f data/features.parquet
test -f data/labels.parquet
git status --short --branch

echo "[job] tests"
pytest -q tests/test_no_leakage.py tests/test_training_pipeline.py

train_lstm_recency() {
  local tag="$1"
  shift
  echo "[job] train ${tag}"
  python -m src.train --model lstm --loss ic --tag "${tag}" "$@" \
    --epochs 8 --batch-cap 8192 --amp \
    --half-life-days 180 --min-date-weight 0.25
  echo "[job] infer ${tag} on original validation"
  python -m src.infer --model lstm --tag "${tag}" \
    --batch-cap 8192 --device cuda \
    --val-start 2025-01-01 --val-end 2026-04-30
  echo "[job] backtest ${tag} on original validation"
  python -m src.backtest --preds "checkpoints/${tag}_val_preds.parquet" \
    --out "reports/backtest_${tag}"
}

train_lstm_recency lstm_ic_recency_h256_l3_w20 \
  --hidden 256 --layers 3 --dropout 0.2 --window 20

train_lstm_recency lstm_ic_recency_h384_l2_w20 \
  --hidden 384 --layers 2 --dropout 0.2 --window 20

echo "[job] train sklearn recency linear baseline"
python scripts/train_sklearn_baseline.py \
  --tag sklearn_sgd_recency_w20 \
  --window 20 \
  --train-start 2019-01-01 \
  --train-end 2024-12-31 \
  --val-start 2025-01-01 \
  --val-end 2026-04-30 \
  --epochs 3 \
  --batch-cap 8192 \
  --half-life-days 180 \
  --min-date-weight 0.25

echo "[job] compare original validation"
python -m src.compare --tags \
  mlp_mse \
  lstm_ic_large \
  lstm_ic_h384_l2_w20 \
  lstm_ic_recency_h256_l3_w20 \
  lstm_ic_recency_h384_l2_w20 \
  sklearn_sgd_recency_w20 \
  transformer_ic_large \
  transformer_ic_mid

echo "[job] backtest sklearn original validation"
python -m src.backtest --preds checkpoints/sklearn_sgd_recency_w20_val_preds.parquet \
  --out reports/backtest_sklearn_sgd_recency_w20

echo "[job] May 2026 neural holdout"
python scripts/evaluate_may_2026.py \
  --no-future-limit-censor \
  --tags \
    lstm_ic_large \
    lstm_ic_h384_l2_w20 \
    lstm_ic_recency_h256_l3_w20 \
    lstm_ic_recency_h384_l2_w20

echo "[job] May 2026 sklearn holdout"
python scripts/evaluate_sklearn_may_2026.py \
  --no-future-limit-censor \
  --tags sklearn_sgd_recency_w20

echo "[job] done $(date -Is)"
