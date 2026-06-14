from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from .config import RunConfig, load_config
from .io_utils import ensure_dir, write_json


def _writable_check(path: Path) -> dict[str, Any]:
    ensure_dir(path)
    probe = path / ".quant_write_probe"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return {"path": str(path), "writable": True}
    except Exception as exc:
        return {"path": str(path), "writable": False, "error": str(exc)[:300]}


def _disk_check(path: Path, min_free_mb: int) -> dict[str, Any]:
    ensure_dir(path)
    usage = shutil.disk_usage(path)
    free_mb = round(usage.free / (1024 * 1024), 2)
    return {
        "path": str(path),
        "free_mb": free_mb,
        "total_mb": round(usage.total / (1024 * 1024), 2),
        "min_required_free_mb": min_free_mb,
        "ok": free_mb >= min_free_mb,
    }


def run(config: RunConfig | None = None) -> dict[str, Any]:
    cfg = config or load_config()
    writable_targets = {
        "output_root": cfg.output_root,
        "knowledge_root": cfg.knowledge_root,
        "factor_library": cfg.factor_library,
        "run_dir": cfg.run_dir,
    }
    writable = {name: _writable_check(path) for name, path in writable_targets.items()}
    disk_targets = {
        "output_root": cfg.output_root,
        "knowledge_root": cfg.knowledge_root,
        "factor_library": cfg.factor_library,
    }
    disk = {name: _disk_check(path, cfg.min_free_disk_mb) for name, path in disk_targets.items()}
    checks = {
        "required_dirs_writable": all(item["writable"] for item in writable.values()),
        "min_free_disk_ok": all(item["ok"] for item in disk.values()),
    }
    payload = {
        "agent": "preflight",
        "run_date": cfg.run_date,
        "status": "ok" if all(checks.values()) else "warning",
        "checks": checks,
        "writable": writable,
        "disk": disk,
    }
    write_json(cfg.run_dir / "preflight.json", payload)
    return payload


if __name__ == "__main__":
    run()
