#!/usr/bin/env bash
#SBATCH --job-name=explore_models
#SBATCH --partition=L40
#SBATCH --qos=normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:1
#SBATCH --time=4:00:00
#SBATCH --output=reports/slurm/%x-%j.out
#SBATCH --error=reports/slurm/%x-%j.err

set -euo pipefail

cd /home/lcc17/dl
mkdir -p reports/slurm reports/may_2026_validation

echo "[explore] start $(date -Is)"
echo "[explore] host $(hostname)"
echo "[explore] job ${SLURM_JOB_ID:-unknown}"

source /opt/Software/Anaconda3/etc/profile.d/conda.sh
conda activate dl

python --version
python -c "import lightgbm; print('lightgbm', lightgbm.__version__)"
python -c "import xgboost; print('xgboost', xgboost.__version__)"
nvidia-smi 2>/dev/null || echo "[explore] no GPU visible"

echo "[explore] git status"
git status --short --branch

echo "[explore] quick tests"
pytest -q tests/test_no_leakage.py tests/test_training_pipeline.py 2>&1 | tail -5

echo "[explore] running exploration grid"
python scripts/explore_models.py \
  --data-dir /home/lcc17/pan_sync_20260528/A股数据 \
  --cache-dir /home/lcc17/pan_sync_20260528/shortterm_cache \
  --build-start 2024-01-01 \
  --data-end 2026-05-28 \
  --val-start 2026-05-06 \
  --val-end 2026-05-27 \
  --time-budget-min 160.0 \
  --num-threads 8 \
  --seed 42

echo "[explore] done $(date -Is)"
