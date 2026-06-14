#!/usr/bin/env bash
#SBATCH --job-name=alpha_gpu_probe
#SBATCH --partition=A800
#SBATCH --qos=normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --gres=gpu:1
#SBATCH --time=00:10:00
#SBATCH --output=reports/slurm/%x-%j.out
#SBATCH --error=reports/slurm/%x-%j.err

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"
mkdir -p reports/slurm

echo "[job] start $(date -Is)"
echo "[job] host $(hostname)"
echo "[job] partition ${SLURM_JOB_PARTITION:-unknown}"
echo "[job] gpus ${CUDA_VISIBLE_DEVICES:-unset}"

source /opt/Software/Anaconda3/etc/profile.d/conda.sh
conda activate dl

python --version
nvidia-smi

python - <<'PY'
mods = ["torch", "cupy", "cudf", "numba", "pyarrow", "pandas"]
for name in mods:
    try:
        mod = __import__(name)
        print(f"[env] {name}=OK version={getattr(mod, '__version__', '')}")
    except Exception as exc:
        print(f"[env] {name}=NO {type(exc).__name__}: {str(exc)[:160]}")

try:
    from numba import cuda
    print("[env] numba.cuda_available", cuda.is_available())
    if cuda.is_available():
        print("[env] numba.device", cuda.get_current_device().name.decode())
except Exception as exc:
    print("[env] numba.cuda_error", type(exc).__name__, str(exc)[:160])

try:
    import torch
    print("[env] torch.cuda_available", torch.cuda.is_available())
    print("[env] torch.device_count", torch.cuda.device_count())
    if torch.cuda.is_available():
        print("[env] torch.device0", torch.cuda.get_device_name(0))
except Exception as exc:
    print("[env] torch.cuda_error", type(exc).__name__, str(exc)[:160])
PY

echo "[job] done $(date -Is)"
