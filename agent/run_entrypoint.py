from __future__ import annotations

import os
import socket
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import artifact_manifest, artifact_verifier, daily_pipeline, readiness_report
from .config import RunConfig, load_config
from .io_utils import append_jsonl, write_json


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _base_record(started_at: str) -> dict[str, Any]:
    cfg = load_config()
    entrypoint_script = os.environ.get("QUANT_RUN_DAILY_SCRIPT")
    return {
        "started_at": started_at,
        "run_date": cfg.run_date,
        "pid": os.getpid(),
        "host": socket.gethostname(),
        "cwd": str(Path.cwd()),
        "argv": sys.argv,
        "shell_entrypoint": os.environ.get("QUANT_RUN_DAILY_SH") == "1",
        "entrypoint_script": entrypoint_script,
        "entrypoint_script_exists": Path(entrypoint_script).exists() if entrypoint_script else False,
        "entrypoint_command": os.environ.get("QUANT_RUN_DAILY_COMMAND"),
        "output_root": str(cfg.output_root),
        "knowledge_root": str(cfg.knowledge_root),
        "offline": cfg.offline,
        "config_loaded": True,
    }


def _fallback_record(started_at: str) -> dict[str, Any]:
    output_root = Path(os.environ.get("QUANT_OUTPUT_ROOT", "reports"))
    knowledge_root = Path(os.environ.get("QUANT_KNOWLEDGE_ROOT", "knowledge_base"))
    entrypoint_script = os.environ.get("QUANT_RUN_DAILY_SCRIPT")
    return {
        "started_at": started_at,
        "run_date": os.environ.get("QUANT_DATE") or os.environ.get("QUANT_RUN_DATE"),
        "pid": os.getpid(),
        "host": socket.gethostname(),
        "cwd": str(Path.cwd()),
        "argv": sys.argv,
        "shell_entrypoint": os.environ.get("QUANT_RUN_DAILY_SH") == "1",
        "entrypoint_script": entrypoint_script,
        "entrypoint_script_exists": Path(entrypoint_script).exists() if entrypoint_script else False,
        "entrypoint_command": os.environ.get("QUANT_RUN_DAILY_COMMAND"),
        "output_root": str(output_root),
        "knowledge_root": str(knowledge_root),
        "offline": os.environ.get("QUANT_OFFLINE", "0") == "1",
        "config_loaded": False,
    }


def _write_invocation(record: dict[str, Any]) -> None:
    output_root = Path(record["output_root"])
    append_jsonl(output_root / "run_daily_invocations.jsonl", record)
    write_json(output_root / "run_daily_invocation_latest.json", record)


def _fallback_artifact_run_id(started_at: str) -> str:
    safe = "".join(ch for ch in started_at if ch.isdigit())
    return f"invalid_config_{safe[:14] or 'unknown'}"


def _write_config_failure_evidence(record: dict[str, Any]) -> None:
    run_id = _fallback_artifact_run_id(str(record.get("started_at") or ""))
    output_root = Path(record["output_root"])
    cfg = RunConfig(
        run_date=run_id,
        data_root=Path(os.environ.get("QUANT_DATA_ROOT", str(Path.home() / "pan_sync_20260528"))).expanduser(),
        output_root=output_root,
        knowledge_root=Path(record["knowledge_root"]),
        factor_library=Path(os.environ.get("QUANT_FACTOR_LIBRARY", "factor_library")),
        offline=bool(record.get("offline")),
    )
    record["failure_artifact_run_date"] = run_id
    record["failure_artifact_run_dir"] = str(cfg.run_dir)
    record["failure_artifact_manifest_path"] = str(cfg.run_dir / "artifact_manifest.json")
    write_json(cfg.run_dir / "entrypoint_error.json", record)
    _write_invocation(record)
    artifact_manifest.run(cfg)
    artifact_verifier.verify_manifest(cfg)


def _refresh_success_evidence() -> None:
    cfg = load_config()
    last_summary = None
    for _ in range(5):
        payload = readiness_report.run(cfg)
        summary = daily_pipeline._readiness_summary(payload)
        if summary == last_summary:
            daily_pipeline.update_daily_report_readiness_section(cfg, payload)
            break
        daily_pipeline.update_daily_report_readiness_section(cfg, payload)
        artifact_manifest.run(cfg)
        last_summary = summary


def _refresh_failure_evidence(record: dict[str, Any]) -> None:
    if not record.get("config_loaded", True):
        try:
            _write_config_failure_evidence(record)
        except Exception as exc:
            record["failure_evidence_refresh_error"] = {
                "type": type(exc).__name__,
                "message": str(exc)[:300],
            }
            _write_invocation(record)
        return
    try:
        cfg = load_config()
        last_summary = None
        for _ in range(5):
            payload = readiness_report.run(cfg)
            summary = daily_pipeline._readiness_summary(payload)
            if summary == last_summary:
                daily_pipeline.update_daily_report_readiness_section(cfg, payload)
                break
            daily_pipeline.update_daily_report_readiness_section(cfg, payload)
            artifact_manifest.run(cfg)
            last_summary = summary
    except Exception as exc:
        record["failure_evidence_refresh_error"] = {
            "type": type(exc).__name__,
            "message": str(exc)[:300],
        }
        _write_invocation(record)


def main() -> int:
    started_at = _now()
    started = time.time()
    record: dict[str, Any] | None = None
    try:
        record = _base_record(started_at)
        daily_pipeline.run()
        record.update({
            "finished_at": _now(),
            "duration_sec": round(time.time() - started, 3),
            "exit_code": 0,
            "status": "success",
        })
        _write_invocation(record)
        _refresh_success_evidence()
        return 0
    except BaseException as exc:
        if record is None:
            record = _fallback_record(started_at)
        record.update({
            "finished_at": _now(),
            "duration_sec": round(time.time() - started, 3),
            "exit_code": 130 if isinstance(exc, KeyboardInterrupt) else 1,
            "status": "error",
            "error": {
                "type": type(exc).__name__,
                "message": str(exc)[:300],
                "traceback": traceback.format_exc(limit=12),
            },
        })
        _write_invocation(record)
        _refresh_failure_evidence(record)
        if isinstance(exc, KeyboardInterrupt):
            return 130
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
