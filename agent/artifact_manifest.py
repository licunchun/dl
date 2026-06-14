from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import RunConfig, load_config
from .io_utils import write_json


EXCLUDED_NAMES = {"artifact_manifest.json"}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _file_record(base: Path, path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "path": str(path),
        "relative_path": str(path.relative_to(base)) if path.is_relative_to(base) else str(path),
        "size_bytes": stat.st_size,
        "mtime": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        "sha256": _sha256(path),
    }


def _collect_files(base: Path) -> list[Path]:
    if not base.exists():
        return []
    if base.is_file():
        return [base]
    files = []
    for path in sorted(base.rglob("*")):
        if path.is_file() and path.name not in EXCLUDED_NAMES:
            files.append(path)
    return files


def run(config: RunConfig | None = None) -> dict[str, Any]:
    cfg = config or load_config()
    knowledge_files = [
        cfg.knowledge_root / "factor_database" / "factors.json",
        cfg.knowledge_root / "run_history_latest.json",
        cfg.knowledge_root / "research_log_latest.json",
        cfg.knowledge_root / "source_snapshots_latest.json",
        cfg.knowledge_root / "data_health_latest.json",
    ]
    report_files = [
        cfg.output_root / "READINESS_REPORT.json",
        cfg.output_root / "READINESS_REPORT.md",
        cfg.output_root / "gpu_alpha_submission_latest.json",
        cfg.output_root / "run_daily_invocation_latest.json",
    ]
    run_files = _collect_files(cfg.run_dir)
    extra_files = [path for path in knowledge_files + report_files if path.exists()]
    records = [_file_record(cfg.run_dir, path) for path in run_files]
    records += [_file_record(cfg.output_root, path) for path in extra_files]
    payload = {
        "agent": "artifact_manifest",
        "run_date": cfg.run_date,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "file_count": len(records),
        "total_size_bytes": sum(item["size_bytes"] for item in records),
        "files": records,
    }
    write_json(cfg.run_dir / "artifact_manifest.json", payload)
    write_json(cfg.output_root / "artifact_manifest_latest.json", payload)
    return payload


if __name__ == "__main__":
    run()
