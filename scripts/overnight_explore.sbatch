#!/usr/bin/env bash
#SBATCH --job-name=overnight_explore
#SBATCH --partition=L40
#SBATCH --qos=normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:1
#SBATCH --time=12:00:00
#SBATCH --output=reports/slurm/%x-%j.out
#SBATCH --error=reports/slurm/%x-%j.err

set -euo pipefail
cd /home/lcc17/dl
mkdir -p reports/slurm reports/may_2026_validation

echo "=========================================="
echo "[overnight] start $(date -Is)"
echo "[overnight] host $(hostname)"
echo "[overnight] job ${SLURM_JOB_ID:-unknown}"
echo "=========================================="

source /opt/Software/Anaconda3/etc/profile.d/conda.sh
conda activate dl

python --version
python -c "import lightgbm; print('lightgbm', lightgbm.__version__)"
python -c "import xgboost; print('xgboost', xgboost.__version__)"
nvidia-smi 2>/dev/null | head -5 || true

# Quick sanity
pytest -q tests/test_no_leakage.py tests/test_training_pipeline.py 2>&1 | tail -3

echo ""
echo "=========================================="
echo "[overnight] running exploration pipeline"
echo "=========================================="

python scripts/overnight_pipeline.py \
  --data-dir /home/lcc17/pan_sync_20260528/A股数据 \
  --cache-dir /home/lcc17/pan_sync_20260528/shortterm_cache \
  --build-start 2025-01-01 \
  --data-end 2026-05-29 \
  --val-start 2026-05-06 \
  --val-end 2026-05-27 \
  --time-budget-min 660.0 \
  --num-threads 8 \
  --seed 42

echo ""
echo "=========================================="
echo "[overnight] done $(date -Is)"
echo "=========================================="
