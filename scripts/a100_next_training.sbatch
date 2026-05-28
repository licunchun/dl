#!/usr/bin/env bash
#SBATCH --job-name=a100_next_training
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
mkdir -p reports/slurm reports/backtest_lstm_ic_large_best
mkdir -p reports/backtest_lstm_ic_h384_l2_w20 reports/backtest_lstm_ic_h384_l3_w20
mkdir -p reports/backtest_lstm_ic_h256_l3_w40 reports/backtest_lstm_ic_final_h384_l2_w20

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
test -f checkpoints/lstm_ic_large.pt
git status --short --branch

echo "[job] tests"
pytest -q tests/test_no_leakage.py tests/test_training_pipeline.py

echo "[job] re-infer current best lstm_ic_large"
python -m src.infer --model lstm --tag lstm_ic_large \
  --batch-cap 8192 --device cuda \
  --val-start 2025-01-01 --val-end 2026-04-30

echo "[job] compare current best"
python -m src.compare --tags mlp_mse lstm_ic_large transformer_ic_large transformer_ic_mid

echo "[job] backtest current best"
python -m src.backtest --preds checkpoints/lstm_ic_large_val_preds.parquet \
  --out reports/backtest_lstm_ic_large_best

train_and_infer_original_split() {
  local tag="$1"
  shift
  echo "[job] train ${tag}"
  python -m src.train --model lstm --loss ic --tag "${tag}" "$@" \
    --epochs 8 --batch-cap 8192 --amp
  echo "[job] re-infer ${tag}"
  python -m src.infer --model lstm --tag "${tag}" \
    --batch-cap 8192 --device cuda \
    --val-start 2025-01-01 --val-end 2026-04-30
  echo "[job] backtest ${tag}"
  python -m src.backtest --preds "checkpoints/${tag}_val_preds.parquet" \
    --out "reports/backtest_${tag}"
}

train_and_infer_original_split lstm_ic_h384_l2_w20 \
  --hidden 384 --layers 2 --dropout 0.2 --window 20

train_and_infer_original_split lstm_ic_h384_l3_w20 \
  --hidden 384 --layers 3 --dropout 0.2 --window 20

train_and_infer_original_split lstm_ic_h256_l3_w40 \
  --hidden 256 --layers 3 --dropout 0.2 --window 40

echo "[job] train expanded final candidate"
python -m src.train --model lstm --loss ic --tag lstm_ic_final_h384_l2_w20 \
  --hidden 384 --layers 2 --dropout 0.2 --window 20 \
  --train-start 2019-01-01 --train-end 2026-02-27 \
  --val-start 2026-03-02 --val-end 2026-04-30 \
  --epochs 8 --batch-cap 8192 --amp

echo "[job] re-infer expanded final candidate"
python -m src.infer --model lstm --tag lstm_ic_final_h384_l2_w20 \
  --window 20 --batch-cap 8192 --device cuda \
  --val-start 2026-03-02 --val-end 2026-04-30

echo "[job] backtest expanded final candidate"
python -m src.backtest --preds checkpoints/lstm_ic_final_h384_l2_w20_val_preds.parquet \
  --out reports/backtest_lstm_ic_final_h384_l2_w20

echo "[job] final compare"
python -m src.compare --tags \
  mlp_mse \
  lstm_ic_large \
  lstm_ic_h384_l2_w20 \
  lstm_ic_h384_l3_w20 \
  lstm_ic_h256_l3_w40 \
  transformer_ic_large \
  transformer_ic_mid

echo "[job] done $(date -Is)"
