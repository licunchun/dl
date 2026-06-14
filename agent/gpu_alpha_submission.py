from __future__ import annotations

import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import RunConfig, load_config
from .io_utils import write_json


SBATCH_JOB_RE = re.compile(r"Submitted batch job\s+(\d+)")
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _env_snapshot() -> dict[str, Any]:
    keys = [
        "ALPHA_CANDIDATES",
        "ALPHA_HORIZONS",
        "ALPHA_COSTS",
        "ALPHA_START",
        "ALPHA_END",
        "ALPHA_FAST",
        "ALPHA_BACKEND",
        "ALPHA_MAX_EXIT_DELAY_DAYS",
        "SLURM_PARTITION",
        "SLURM_QOS",
        "SLURM_GPUS",
        "SLURM_CPUS_PER_TASK",
        "SLURM_TIME",
        "SLURM_ACCOUNT",
    ]
    return {key: os.environ.get(key) for key in keys if os.environ.get(key) is not None}


def _write_payload(cfg: RunConfig, payload: dict[str, Any]) -> dict[str, Any]:
    write_json(cfg.run_dir / "gpu_alpha_submission.json", payload)
    write_json(cfg.output_root / "gpu_alpha_submission_latest.json", payload)
    return payload


def run(config: RunConfig | None = None) -> dict[str, Any]:
    cfg = config or load_config()
    cfg.run_dir.mkdir(parents=True, exist_ok=True)
    script = PROJECT_ROOT / "scripts" / "submit_alpha_gpu_backtest.sh"
    payload: dict[str, Any] = {
        "agent": "gpu_alpha_submission",
        "run_date": cfg.run_date,
        "created_at": _now(),
        "enabled": os.environ.get("QUANT_GPU_ALPHA_ENABLED", "1") != "0",
        "offline": cfg.offline,
        "project_root": str(PROJECT_ROOT),
        "script": str(script),
        "script_exists": script.exists(),
        "sbatch_path": shutil.which("sbatch"),
        "env": _env_snapshot(),
        "status": "pending",
        "submitted": False,
        "job_id": None,
    }
    if not payload["enabled"]:
        payload.update({"status": "skipped", "skip_reason": "QUANT_GPU_ALPHA_ENABLED=0"})
        return _write_payload(cfg, payload)
    if cfg.offline and os.environ.get("QUANT_GPU_ALPHA_ALLOW_OFFLINE", "0") != "1":
        payload.update({"status": "skipped", "skip_reason": "offline_run"})
        return _write_payload(cfg, payload)
    if not script.exists():
        payload.update({"status": "error", "error": "missing_submit_script"})
        return _write_payload(cfg, payload)
    if not payload["sbatch_path"]:
        payload.update({"status": "skipped", "skip_reason": "sbatch_not_found"})
        return _write_payload(cfg, payload)

    cmd = ["bash", str(script)]
    payload["command"] = cmd
    started = datetime.now(timezone.utc)
    try:
        proc = subprocess.run(
            cmd,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=PROJECT_ROOT,
            timeout=float(os.environ.get("QUANT_GPU_SUBMIT_TIMEOUT_SEC", "60")),
        )
    except subprocess.TimeoutExpired as exc:
        payload.update({
            "status": "error",
            "error": "submit_timeout",
            "stdout": (exc.stdout or "")[:4000],
            "stderr": (exc.stderr or "")[:4000],
        })
        return _write_payload(cfg, payload)

    stdout = proc.stdout or ""
    stderr = proc.stderr or ""
    match = SBATCH_JOB_RE.search(stdout + "\n" + stderr)
    payload.update({
        "finished_at": _now(),
        "duration_sec": round((datetime.now(timezone.utc) - started).total_seconds(), 3),
        "returncode": proc.returncode,
        "stdout": stdout[:4000],
        "stderr": stderr[:4000],
        "job_id": match.group(1) if match else None,
    })
    if proc.returncode == 0 and match:
        payload.update({"status": "submitted", "submitted": True})
    elif proc.returncode == 0:
        payload.update({"status": "submitted_unparsed", "submitted": True})
    else:
        payload.update({"status": "error", "error": "submit_command_failed"})
    return _write_payload(cfg, payload)


if __name__ == "__main__":
    run()
