from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from agent import run_entrypoint
from agent.config import load_config
from agent.io_utils import read_json


def test_load_config_accepts_quant_run_date_alias(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("QUANT_DATE", raising=False)
    monkeypatch.setenv("QUANT_RUN_DATE", "20260605")
    monkeypatch.setenv("QUANT_OUTPUT_ROOT", str(tmp_path / "reports"))
    monkeypatch.setenv("QUANT_KNOWLEDGE_ROOT", str(tmp_path / "knowledge_base"))
    monkeypatch.setenv("QUANT_FACTOR_LIBRARY", str(tmp_path / "factor_library"))
    monkeypatch.setenv("QUANT_DATA_ROOT", str(tmp_path / "missing_data"))

    cfg = load_config()

    assert cfg.run_date == "20260605"


def test_load_config_prefers_quant_date_over_alias(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("QUANT_DATE", "20260604")
    monkeypatch.setenv("QUANT_RUN_DATE", "20260605")
    monkeypatch.setenv("QUANT_OUTPUT_ROOT", str(tmp_path / "reports"))
    monkeypatch.setenv("QUANT_KNOWLEDGE_ROOT", str(tmp_path / "knowledge_base"))
    monkeypatch.setenv("QUANT_FACTOR_LIBRARY", str(tmp_path / "factor_library"))
    monkeypatch.setenv("QUANT_DATA_ROOT", str(tmp_path / "missing_data"))

    cfg = load_config()

    assert cfg.run_date == "20260604"


def test_load_config_rejects_invalid_quant_run_date(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("QUANT_DATE", raising=False)
    monkeypatch.setenv("QUANT_RUN_DATE", "2026-06-05")
    monkeypatch.setenv("QUANT_OUTPUT_ROOT", str(tmp_path / "reports"))
    monkeypatch.setenv("QUANT_KNOWLEDGE_ROOT", str(tmp_path / "knowledge_base"))
    monkeypatch.setenv("QUANT_FACTOR_LIBRARY", str(tmp_path / "factor_library"))
    monkeypatch.setenv("QUANT_DATA_ROOT", str(tmp_path / "missing_data"))

    with pytest.raises(ValueError, match="YYYYMMDD"):
        load_config()


def test_run_entrypoint_records_quant_run_date_alias(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("QUANT_DATE", raising=False)
    monkeypatch.setenv("QUANT_RUN_DATE", "20260605")
    monkeypatch.setenv("QUANT_OUTPUT_ROOT", str(tmp_path / "reports"))
    monkeypatch.setenv("QUANT_KNOWLEDGE_ROOT", str(tmp_path / "knowledge_base"))
    monkeypatch.setenv("QUANT_FACTOR_LIBRARY", str(tmp_path / "factor_library"))
    monkeypatch.setenv("QUANT_DATA_ROOT", str(tmp_path / "missing_data"))
    monkeypatch.setenv("QUANT_OFFLINE", "1")

    monkeypatch.setattr(run_entrypoint.daily_pipeline, "run", lambda: {"ok": True})

    assert run_entrypoint.main() == 0

    latest = read_json(tmp_path / "reports" / "run_daily_invocation_latest.json", {})
    assert latest["run_date"] == "20260605"


def test_run_entrypoint_records_successful_invocation(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("QUANT_DATE", "20260604")
    monkeypatch.setenv("QUANT_OUTPUT_ROOT", str(tmp_path / "reports"))
    monkeypatch.setenv("QUANT_KNOWLEDGE_ROOT", str(tmp_path / "knowledge_base"))
    monkeypatch.setenv("QUANT_FACTOR_LIBRARY", str(tmp_path / "factor_library"))
    monkeypatch.setenv("QUANT_DATA_ROOT", str(tmp_path / "missing_data"))
    monkeypatch.setenv("QUANT_OFFLINE", "1")

    monkeypatch.setattr(run_entrypoint.daily_pipeline, "run", lambda: {"ok": True})

    assert run_entrypoint.main() == 0

    latest = read_json(tmp_path / "reports" / "run_daily_invocation_latest.json", {})
    lines = (tmp_path / "reports" / "run_daily_invocations.jsonl").read_text(encoding="utf-8").splitlines()
    assert latest["status"] == "success"
    assert latest["exit_code"] == 0
    assert latest["run_date"] == "20260604"
    assert latest["shell_entrypoint"] is False
    assert latest["entrypoint_script_exists"] is False
    assert len(lines) == 1


def test_run_entrypoint_records_run_daily_shell_provenance(tmp_path: Path, monkeypatch) -> None:
    script_path = Path.cwd() / "run_daily.sh"
    monkeypatch.setenv("QUANT_DATE", "20260604")
    monkeypatch.setenv("QUANT_OUTPUT_ROOT", str(tmp_path / "reports"))
    monkeypatch.setenv("QUANT_KNOWLEDGE_ROOT", str(tmp_path / "knowledge_base"))
    monkeypatch.setenv("QUANT_FACTOR_LIBRARY", str(tmp_path / "factor_library"))
    monkeypatch.setenv("QUANT_DATA_ROOT", str(tmp_path / "missing_data"))
    monkeypatch.setenv("QUANT_OFFLINE", "1")
    monkeypatch.setenv("QUANT_RUN_DAILY_SH", "1")
    monkeypatch.setenv("QUANT_RUN_DAILY_SCRIPT", str(script_path))
    monkeypatch.setenv("QUANT_RUN_DAILY_COMMAND", "bash run_daily.sh")

    monkeypatch.setattr(run_entrypoint.daily_pipeline, "run", lambda: {"ok": True})

    assert run_entrypoint.main() == 0

    latest = read_json(tmp_path / "reports" / "run_daily_invocation_latest.json", {})
    assert latest["status"] == "success"
    assert latest["shell_entrypoint"] is True
    assert latest["entrypoint_script"] == str(script_path)
    assert latest["entrypoint_script_exists"] is True
    assert latest["entrypoint_command"] == "bash run_daily.sh"


def test_run_entrypoint_records_failed_invocation(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("QUANT_DATE", "20260604")
    monkeypatch.setenv("QUANT_OUTPUT_ROOT", str(tmp_path / "reports"))
    monkeypatch.setenv("QUANT_KNOWLEDGE_ROOT", str(tmp_path / "knowledge_base"))
    monkeypatch.setenv("QUANT_FACTOR_LIBRARY", str(tmp_path / "factor_library"))
    monkeypatch.setenv("QUANT_DATA_ROOT", str(tmp_path / "missing_data"))
    monkeypatch.setenv("QUANT_OFFLINE", "1")

    def fail() -> None:
        raise RuntimeError("simulated entry failure")

    monkeypatch.setattr(run_entrypoint.daily_pipeline, "run", fail)

    assert run_entrypoint.main() == 1

    latest = read_json(tmp_path / "reports" / "run_daily_invocation_latest.json", {})
    readiness = read_json(tmp_path / "reports" / "READINESS_REPORT.json", {})
    manifest = read_json(tmp_path / "reports" / "artifact_manifest_latest.json", {})
    verification = read_json(tmp_path / "reports" / "daily_logs" / "20260604" / "artifact_verification.json", {})
    verification_latest = read_json(tmp_path / "reports" / "artifact_verification_latest.json", {})
    assert latest["status"] == "error"
    assert latest["exit_code"] == 1
    assert latest["config_loaded"] is True
    assert latest["error"]["type"] == "RuntimeError"
    assert "simulated entry failure" in latest["error"]["message"]
    assert readiness["status"] == "not_production_ready"
    assert not readiness["checks"]["run_daily_invocation_success"]
    assert readiness["run_daily_invocation"]["status"] == "error"
    assert manifest["run_date"] == "20260604"
    manifest_by_path = {item.get("relative_path"): item for item in manifest["files"]}
    invocation_sha = hashlib.sha256((tmp_path / "reports" / "run_daily_invocation_latest.json").read_bytes()).hexdigest()
    assert manifest_by_path["run_daily_invocation_latest.json"]["sha256"] == invocation_sha
    assert verification["status"] == "pass"
    assert verification["manifest_generated_at"] == manifest["generated_at"]
    assert verification_latest["manifest_generated_at"] == manifest["generated_at"]
    assert readiness["checks"]["artifact_manifest_verification_passed"]
    assert readiness["checks"]["artifact_verification_latest_matches_current_verification"]
    assert readiness["artifact_manifest"]["verification"]["latest_matches_current_verification"] is True


def test_run_entrypoint_records_config_error_invocation(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("QUANT_DATE", "20260631")
    monkeypatch.setenv("QUANT_OUTPUT_ROOT", str(tmp_path / "reports"))
    monkeypatch.setenv("QUANT_KNOWLEDGE_ROOT", str(tmp_path / "knowledge_base"))
    monkeypatch.setenv("QUANT_FACTOR_LIBRARY", str(tmp_path / "factor_library"))
    monkeypatch.setenv("QUANT_DATA_ROOT", str(tmp_path / "missing_data"))
    monkeypatch.setenv("QUANT_OFFLINE", "1")

    assert run_entrypoint.main() == 1

    latest = read_json(tmp_path / "reports" / "run_daily_invocation_latest.json", {})
    manifest = read_json(tmp_path / "reports" / "artifact_manifest_latest.json", {})
    verification = read_json(tmp_path / "reports" / "artifact_verification_latest.json", {})
    assert latest["status"] == "error"
    assert latest["exit_code"] == 1
    assert latest["run_date"] == "20260631"
    assert latest["config_loaded"] is False
    assert latest["error"]["type"] == "ValueError"
    assert "YYYYMMDD" in latest["error"]["message"]
    assert latest["failure_artifact_run_date"].startswith("invalid_config_")
    failure_run_dir = Path(latest["failure_artifact_run_dir"])
    assert (failure_run_dir / "entrypoint_error.json").exists()
    assert manifest["run_date"] == latest["failure_artifact_run_date"]
    manifest_by_path = {item.get("relative_path"): item for item in manifest["files"]}
    assert "entrypoint_error.json" in manifest_by_path
    invocation_sha = hashlib.sha256((tmp_path / "reports" / "run_daily_invocation_latest.json").read_bytes()).hexdigest()
    assert manifest_by_path["run_daily_invocation_latest.json"]["sha256"] == invocation_sha
    assert verification["status"] == "pass"
    assert verification["manifest_generated_at"] == manifest["generated_at"]
