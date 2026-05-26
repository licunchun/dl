#!/usr/bin/env bash
#SBATCH --job-name=dl_a100_full
#SBATCH --partition=A100
#SBATCH --qos=normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --gres=gpu:1
#SBATCH --time=3-00:00:00
#SBATCH --output=reports/slurm/%x-%j.out
#SBATCH --error=reports/slurm/%x-%j.err

set -euo pipefail

cd /home/lcc17/dl
mkdir -p reports/slurm reports/backtest_lstm_ic_large reports/backtest_transformer_ic_large reports/backtest_transformer_ic_mid

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

echo "[job] cache check / rebuild"
python -m src.train --rebuild-cache --model mlp --loss mse --epochs 0

echo "[job] tests"
pytest -q tests/test_no_leakage.py tests/test_training_pipeline.py

echo "[job] train mlp_mse baseline"
python -m src.train --model mlp --loss mse --tag mlp_mse \
  --epochs 8 --batch-cap 8192

echo "[job] train lstm_ic_large"
python -m src.train --model lstm --loss ic --tag lstm_ic_large \
  --hidden 256 --layers 3 --dropout 0.2 \
  --epochs 8 --batch-cap 8192 --amp

echo "[job] train transformer_ic_large"
python -m src.train --model transformer --loss ic --tag transformer_ic_large \
  --d-model 256 --heads 8 --layers 4 --dropout 0.2 \
  --epochs 8 --batch-cap 8192 --amp

if [[ "${RUN_OPTIONAL_MID:-1}" == "1" ]]; then
  echo "[job] train transformer_ic_mid"
  python -m src.train --model transformer --loss ic --tag transformer_ic_mid \
    --d-model 128 --heads 8 --layers 4 --dropout 0.15 \
    --epochs 8 --batch-cap 8192 --amp
fi

echo "[job] compare"
python -m src.compare --tags mlp_mse lstm_ic_large transformer_ic_large transformer_ic_mid

echo "[job] backtest lstm_ic_large"
python -m src.backtest --preds checkpoints/lstm_ic_large_val_preds.parquet \
  --out reports/backtest_lstm_ic_large

echo "[job] backtest transformer_ic_large"
python -m src.backtest --preds checkpoints/transformer_ic_large_val_preds.parquet \
  --out reports/backtest_transformer_ic_large

if [[ "${RUN_OPTIONAL_MID:-1}" == "1" ]]; then
  echo "[job] backtest transformer_ic_mid"
  python -m src.backtest --preds checkpoints/transformer_ic_mid_val_preds.parquet \
    --out reports/backtest_transformer_ic_mid
fi

echo "[job] done $(date -Is)"
