from __future__ import annotations

import hashlib
from pathlib import Path
import os
import time

import pytest

from agent.config import RunConfig
from agent import daily_pipeline, daily_simulation, gpu_alpha_submission
from agent.io_utils import read_json


def test_daily_pipeline_runs_all_agents(tmp_path: Path) -> None:
    cfg = RunConfig(
        run_date="20260604",
        data_root=tmp_path / "missing_data",
        output_root=tmp_path / "reports",
        knowledge_root=tmp_path / "knowledge_base",
        factor_library=tmp_path / "factor_library",
        offline=True,
        agent_retries=1,
    )

    outputs = daily_pipeline.run(cfg)

    assert set(outputs) == {
        "preflight",
        "market_intelligence",
        "research_agent",
        "factor_design",
        "data_agent",
        "backtest_agent",
        "critic_agent",
        "evolution_agent",
        "knowledge_base",
        "schedule",
        "self_audit",
        "gpu_alpha_submission",
        "run_history",
        "readiness_report",
        "artifact_manifest",
    }
    assert (cfg.run_dir / "daily_report.md").exists()
    assert (cfg.run_dir / "preflight.json").exists()
    assert (cfg.knowledge_root / "factor_database" / "factors.json").exists()
    assert read_json(cfg.run_dir / "pipeline_state.json", {})["status"] == "complete"
    assert (cfg.run_dir / "run_audit.json").exists()
    assert (cfg.run_dir / "self_audit.json").exists()
    assert (cfg.run_dir / "gpu_alpha_submission.json").exists()
    assert (cfg.output_root / "READINESS_REPORT.md").exists()
    assert (cfg.run_dir / "artifact_manifest.json").exists()
    assert (cfg.output_root / "artifact_manifest_latest.json").exists()
    report = (cfg.run_dir / "daily_report.md").read_text(encoding="utf-8")
    assert "long_short_ann_diag" in report
    assert "preflight:" in report
    assert "gpu alpha submission: skipped (offline_run)" in report
    assert "research source mode" in report
    history_path = cfg.knowledge_root / "run_history.jsonl"
    assert history_path.exists()
    history_lines = history_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(history_lines) == 1
    assert read_json(cfg.knowledge_root / "run_history_latest.json", {})["run_date"] == "20260604"
    latest_history = read_json(cfg.knowledge_root / "run_history_latest.json", {})
    assert latest_history["agent_status"]["readiness_report"] == "ok"
    assert latest_history["agent_status"]["artifact_manifest"] == "ok"
    manifest = read_json(cfg.run_dir / "artifact_manifest.json", {})
    manifest_paths = {item["relative_path"] for item in manifest["files"]}
    for required_path in {
        "daily_report.md",
        "preflight.json",
        "daily_events.json",
        "research_ideas.json",
        "candidate_factors.json",
        "daily_dataset.parquet",
        "dataset_manifest.json",
        "data_health.json",
        "backtest_results.json",
        "failure_analysis.md",
        "critique.json",
        "next_generation_factors.json",
        "pipeline_state.json",
        "run_audit.json",
        "schedule.json",
        "cron_example.txt",
        "self_audit.json",
        "self_audit.md",
        "gpu_alpha_submission.json",
        "READINESS_REPORT.json",
        "READINESS_REPORT.md",
        "gpu_alpha_submission_latest.json",
        "artifact_verification.json",
    }:
        assert required_path in manifest_paths
    assert str(cfg.knowledge_root / "factor_database" / "factors.json") in manifest_paths
    assert all(item["sha256"] for item in manifest["files"])
    manifest_by_path = {item["relative_path"]: item for item in manifest["files"]}
    run_audit_sha = hashlib.sha256((cfg.run_dir / "run_audit.json").read_bytes()).hexdigest()
    assert manifest_by_path["run_audit.json"]["sha256"] == run_audit_sha
    verification = read_json(cfg.run_dir / "artifact_verification.json", {})
    readiness = read_json(cfg.output_root / "READINESS_REPORT.json", {})
    assert verification["manifest_generated_at"] == manifest["generated_at"]
    assert verification["status"] == "pass"
    assert any(item.get("relative_path") == "artifact_verification.json" for item in verification["skipped_files"])
    assert readiness["artifact_manifest"]["verification"]["manifest_generated_at"] == manifest["generated_at"]
    gpu_payload = read_json(cfg.run_dir / "gpu_alpha_submission.json", {})
    assert gpu_payload["status"] == "skipped"
    assert gpu_payload["skip_reason"] == "offline_run"


def test_gpu_alpha_submission_uses_sbatch_and_records_job_id(tmp_path: Path, monkeypatch) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    sbatch = fake_bin / "sbatch"
    sbatch.write_text("#!/usr/bin/env bash\nprintf 'Submitted batch job 12345\\n'\n", encoding="utf-8")
    sbatch.chmod(0o755)
    monkeypatch.setenv("PATH", f"{fake_bin}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setenv("ALPHA_CANDIDATES", "A029")
    monkeypatch.setenv("ALPHA_HORIZONS", "1,5,10,20")
    monkeypatch.setenv("SLURM_PARTITION", "A800")
    monkeypatch.setenv("SLURM_QOS", "normal")
    monkeypatch.setenv("QUANT_GPU_SUBMIT_TIMEOUT_SEC", "10")
    monkeypatch.chdir(tmp_path)

    cfg = RunConfig(
        run_date="20260604",
        data_root=tmp_path / "missing_data",
        output_root=tmp_path / "reports",
        knowledge_root=tmp_path / "knowledge_base",
        factor_library=tmp_path / "factor_library",
        offline=False,
    )

    payload = gpu_alpha_submission.run(cfg)

    assert payload["status"] == "submitted"
    assert payload["submitted"] is True
    assert payload["job_id"] == "12345"
    assert Path(payload["script"]).is_absolute()
    assert payload["script_exists"] is True
    assert payload["env"]["ALPHA_HORIZONS"] == "1,5,10,20"
    latest = read_json(cfg.output_root / "gpu_alpha_submission_latest.json", {})
    assert latest["job_id"] == "12345"


def test_daily_pipeline_records_agent_error_and_continues(tmp_path: Path, monkeypatch) -> None:
    cfg = RunConfig(
        run_date="20260604",
        data_root=tmp_path / "missing_data",
        output_root=tmp_path / "reports",
        knowledge_root=tmp_path / "knowledge_base",
        factor_library=tmp_path / "factor_library",
        offline=True,
        agent_retries=0,
    )

    def fail_data_agent(config):
        raise RuntimeError("simulated data failure")

    monkeypatch.setattr(daily_pipeline.data_agent, "run", fail_data_agent)
    monkeypatch.setattr(daily_pipeline, "AGENTS", [
        ("market_intelligence", daily_pipeline.market_intelligence.run),
        ("research_agent", daily_pipeline.research_agent.run),
        ("factor_design", daily_pipeline.factor_design.run),
        ("data_agent", fail_data_agent),
        ("backtest_agent", daily_pipeline.backtest_agent.run),
        ("critic_agent", daily_pipeline.critic_agent.run),
        ("evolution_agent", daily_pipeline.evolution_agent.run),
        ("knowledge_base", daily_pipeline.knowledge_base.run),
    ])

    outputs = daily_pipeline.run(cfg)
    state = read_json(cfg.run_dir / "pipeline_state.json", {})
    report = (cfg.run_dir / "daily_report.md").read_text(encoding="utf-8")

    assert outputs["data_agent"]["agent"] == "data_agent"
    assert state["status"] == "complete_with_errors"
    error_payload = read_json(cfg.run_dir / "errors" / "data_agent.json", {})
    assert error_payload["agent"] == "data_agent"
    assert error_payload["retries"][0]["attempt"] == 1
    assert "simulated data failure" in error_payload["retries"][0]["error"]
    assert "data_agent: error" in report
    manifest = read_json(cfg.run_dir / "artifact_manifest.json", {})
    manifest_by_path = {item["relative_path"]: item for item in manifest["files"]}
    for relative_path in ("daily_report.md", "run_audit.json", "errors/data_agent.json"):
        path = cfg.run_dir / relative_path
        actual_sha = hashlib.sha256(path.read_bytes()).hexdigest()
        assert manifest_by_path[relative_path]["sha256"] == actual_sha
    verification = read_json(cfg.run_dir / "artifact_verification.json", {})
    readiness = read_json(cfg.output_root / "READINESS_REPORT.json", {})
    assert verification["manifest_generated_at"] == manifest["generated_at"]
    assert verification["status"] == "pass"
    assert "artifact_verification.json" in manifest_by_path
    assert any(item.get("relative_path") == "artifact_verification.json" for item in verification["skipped_files"])
    assert readiness["checks"]["latest_daily_report_is_current_evidence"]
    assert readiness["checks"]["artifact_manifest_verification_passed"]
    assert readiness["artifact_manifest"]["verification"]["manifest_generated_at"] == manifest["generated_at"]
    latest_log = read_json(cfg.knowledge_root / "research_log_latest.json", {})
    factor_db = read_json(cfg.knowledge_root / "factor_database" / "factors.json", {})
    assert latest_log["pipeline"]["run_quality"] == "incomplete"
    assert latest_log["pipeline"]["has_agent_errors"]
    assert latest_log["factor_database_write"]["status"] == "skipped"
    assert factor_db.get("factors", []) == []


def test_daily_pipeline_retries_transient_agent_failure(tmp_path: Path, monkeypatch) -> None:
    cfg = RunConfig(
        run_date="20260604",
        data_root=tmp_path / "missing_data",
        output_root=tmp_path / "reports",
        knowledge_root=tmp_path / "knowledge_base",
        factor_library=tmp_path / "factor_library",
        offline=True,
        agent_retries=1,
    )
    calls = {"n": 0}
    original_market = daily_pipeline.market_intelligence.run

    def flaky_market(config):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("transient")
        return original_market(config)

    monkeypatch.setattr(daily_pipeline, "AGENTS", [
        ("market_intelligence", flaky_market),
        ("research_agent", daily_pipeline.research_agent.run),
        ("factor_design", daily_pipeline.factor_design.run),
        ("data_agent", daily_pipeline.data_agent.run),
        ("backtest_agent", daily_pipeline.backtest_agent.run),
        ("critic_agent", daily_pipeline.critic_agent.run),
        ("evolution_agent", daily_pipeline.evolution_agent.run),
        ("knowledge_base", daily_pipeline.knowledge_base.run),
    ])

    daily_pipeline.run(cfg)
    state = read_json(cfg.run_dir / "pipeline_state.json", {})

    assert calls["n"] == 2
    assert state["status"] == "complete"
    assert state["agents"][0]["attempt"] == 2
    assert state["agents"][0]["retries"][0]["attempt"] == 1
    assert "transient" in state["agents"][0]["retries"][0]["error"]
    assert not (cfg.run_dir / "errors" / "market_intelligence.json").exists()


def test_daily_pipeline_appends_run_history_across_dates(tmp_path: Path) -> None:
    base = {
        "data_root": tmp_path / "missing_data",
        "output_root": tmp_path / "reports",
        "knowledge_root": tmp_path / "knowledge_base",
        "factor_library": tmp_path / "factor_library",
        "offline": True,
        "agent_retries": 1,
    }
    daily_pipeline.run(RunConfig(run_date="20260604", **base))
    daily_pipeline.run(RunConfig(run_date="20260605", **base))

    lines = (tmp_path / "knowledge_base" / "run_history.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    latest = read_json(tmp_path / "knowledge_base" / "run_history_latest.json", {})
    assert latest["run_date"] == "20260605"
    assert latest["agent_status"]["readiness_report"] == "ok"
    assert latest["agent_status"]["artifact_manifest"] == "ok"


def test_daily_simulation_runs_multiple_isolated_days(tmp_path: Path) -> None:
    cfg = RunConfig(
        run_date="20260604",
        data_root=tmp_path / "missing_data",
        output_root=tmp_path / "reports",
        knowledge_root=tmp_path / "knowledge_base",
        factor_library=tmp_path / "factor_library",
        offline=True,
        agent_retries=1,
        retention_days=370,
        lock_stale_minutes=77,
        min_free_disk_mb=1,
    )

    payload = daily_simulation.run_simulation(cfg, days=3)

    assert payload["status"] == "simulation_pass"
    assert payload["uses_shell_entrypoint"] is False
    assert payload["production_ready_evidence"] is False
    assert payload["evidence_scope"] == "local_simulation_only"
    assert payload["history_lines"] == 3
    assert payload["latest_run_date"] == "20260606"
    assert (cfg.output_root / "multi_day_simulation.json").exists()
    for run_date in payload["run_dates"]:
        run_dir = cfg.output_root / "daily_logs" / run_date
        assert (run_dir / "daily_report.md").exists()
        assert read_json(run_dir / "pipeline_state.json", {})["run_date"] == run_date
        audit = read_json(run_dir / "run_audit.json", {})
        assert audit["config"]["lock_stale_minutes"] == 77
        assert audit["config"]["min_free_disk_mb"] == 1
    generated_counts = [item["candidate_factors"] for item in payload["runs"]]
    assert generated_counts[0] > generated_counts[-1]


def test_daily_pipeline_retention_removes_old_runs(tmp_path: Path) -> None:
    old_run = tmp_path / "reports" / "daily_logs" / "20200101"
    old_run.mkdir(parents=True)
    (old_run / "daily_report.md").write_text("old", encoding="utf-8")
    old_time = time.time() - 10 * 86400
    os.utime(old_run, (old_time, old_time))
    cfg = RunConfig(
        run_date="20260604",
        data_root=tmp_path / "missing_data",
        output_root=tmp_path / "reports",
        knowledge_root=tmp_path / "knowledge_base",
        factor_library=tmp_path / "factor_library",
        offline=True,
        retention_days=1,
    )

    daily_pipeline.run(cfg)
    state = read_json(cfg.run_dir / "pipeline_state.json", {})

    assert not old_run.exists()
    assert state["retention"]["removed"]


def test_daily_pipeline_blocks_when_lock_is_fresh(tmp_path: Path) -> None:
    cfg = RunConfig(
        run_date="20260604",
        data_root=tmp_path / "missing_data",
        output_root=tmp_path / "reports",
        knowledge_root=tmp_path / "knowledge_base",
        factor_library=tmp_path / "factor_library",
        offline=True,
        lock_stale_minutes=60,
    )
    cfg.output_root.mkdir(parents=True)
    lock_path = cfg.output_root / ".quant_daily.lock"
    lock_path.write_text('{"pid":999999,"created_at":"2026-06-04T00:00:00Z"}', encoding="utf-8")

    with pytest.raises(RuntimeError, match="daily pipeline lock exists"):
        daily_pipeline.run(cfg)


def test_daily_pipeline_recovers_stale_lock(tmp_path: Path) -> None:
    cfg = RunConfig(
        run_date="20260604",
        data_root=tmp_path / "missing_data",
        output_root=tmp_path / "reports",
        knowledge_root=tmp_path / "knowledge_base",
        factor_library=tmp_path / "factor_library",
        offline=True,
        lock_stale_minutes=1,
    )
    cfg.output_root.mkdir(parents=True)
    lock_path = cfg.output_root / ".quant_daily.lock"
    lock_path.write_text("old pid format", encoding="utf-8")
    old_time = time.time() - 3600
    os.utime(lock_path, (old_time, old_time))

    daily_pipeline.run(cfg)
    state = read_json(cfg.run_dir / "pipeline_state.json", {})
    audit = read_json(cfg.run_dir / "run_audit.json", {})

    assert state["status"] == "complete"
    assert state["lock"]["recovered_stale_lock"]
    assert audit["lock"]["recovered_stale_lock"]
    assert not lock_path.exists()


def test_daily_pipeline_writes_interrupted_checkpoint_on_uncaught_exception(tmp_path: Path, monkeypatch) -> None:
    cfg = RunConfig(
        run_date="20260604",
        data_root=tmp_path / "missing_data",
        output_root=tmp_path / "reports",
        knowledge_root=tmp_path / "knowledge_base",
        factor_library=tmp_path / "factor_library",
        offline=True,
    )

    def interrupt(config):
        raise KeyboardInterrupt("simulated interrupt")

    monkeypatch.setattr(daily_pipeline, "AGENTS", [
        ("market_intelligence", daily_pipeline.market_intelligence.run),
        ("fatal_agent", interrupt),
    ])

    with pytest.raises(KeyboardInterrupt):
        daily_pipeline.run(cfg)
    state = read_json(cfg.run_dir / "pipeline_state.json", {})
    audit = read_json(cfg.run_dir / "run_audit.json", {})

    assert state["status"] == "interrupted"
    assert state["current_agent"] == "fatal_agent"
    assert state["completed_agents"] == ["market_intelligence"]
    assert state["error"]["type"] == "KeyboardInterrupt"
    assert audit["run_date"] == cfg.run_date
    assert audit["state"] == state
    assert audit["state"]["status"] == "interrupted"
    assert audit["state"]["current_agent"] == "fatal_agent"
    assert audit["state"]["error"]["type"] == "KeyboardInterrupt"
    assert not (cfg.output_root / ".quant_daily.lock").exists()


def test_daily_pipeline_records_preflight_warning_without_stopping(tmp_path: Path) -> None:
    cfg = RunConfig(
        run_date="20260604",
        data_root=tmp_path / "missing_data",
        output_root=tmp_path / "reports",
        knowledge_root=tmp_path / "knowledge_base",
        factor_library=tmp_path / "factor_library",
        offline=True,
        min_free_disk_mb=10**12,
    )

    outputs = daily_pipeline.run(cfg)
    preflight = read_json(cfg.run_dir / "preflight.json", {})

    assert read_json(cfg.run_dir / "pipeline_state.json", {})["status"] == "complete"
    assert outputs["preflight"]["status"] == "warning"
    assert preflight["checks"]["required_dirs_writable"]
    assert not preflight["checks"]["min_free_disk_ok"]
    assert outputs["self_audit"]["status"] == "warning"
