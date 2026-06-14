from __future__ import annotations

import os
import re
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .config import RunConfig, load_config
from .artifact_verifier import MUTABLE_READINESS_PATHS, verify_manifest
from .io_utils import read_json, read_jsonl_records, write_json
from .self_audit import REQUIRED_RUN_FILES


REQUIRED_AGENT_NAMES = {
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
    "readiness_report",
    "artifact_manifest",
}

REQUIRED_MANIFEST_PATHS = set(REQUIRED_RUN_FILES) | {
    "daily_report.md",
    "self_audit.json",
    "self_audit.md",
    "READINESS_REPORT.json",
    "READINESS_REPORT.md",
    "artifact_verification.json",
    "gpu_alpha_submission.json",
    "gpu_alpha_submission_latest.json",
    "run_daily_invocation_latest.json",
}

REQUIRED_SOURCE_SNAPSHOT_AGENTS = {"market_intelligence", "research_agent"}
REQUIRED_MARKET_SOURCE_KINDS = {"announcement", "industry", "news", "policy", "research_context"}
REQUIRED_RESEARCH_SOURCE_KINDS = {"community", "factor_library", "paper"}
REQUIRED_DAILY_REPORT_AGENTS = REQUIRED_AGENT_NAMES - {"artifact_manifest"}
REQUIRED_DAILY_REPORT_SNIPPETS = {
    "# Daily Quant Research Report",
    "## Agent Status",
    "## Summary",
    "## Readiness",
    "## Top Backtest Results",
    "## Files",
    "events collected:",
    "research ideas:",
    "candidate factors:",
    "backtested factors:",
    "readiness status:",
    "readiness score:",
    "readiness blockers:",
    "top readiness blocker:",
    "gpu alpha submission:",
    "daily_events.json",
    "research_ideas.json",
    "daily_dataset.parquet",
    "backtest_results/",
    "gpu_alpha_submission.json",
    "knowledge_base/factor_database/factors.json",
}
REQUIRED_SELF_AUDIT_CHECKS = {
    "required_files_present",
    "pipeline_completed",
    "preflight_ok",
    "no_agent_errors",
    "events_available",
    "market_source_quality_recorded",
    "ideas_available",
    "research_source_quality_recorded",
    "factors_available",
    "backtests_available",
    "data_health_ok",
    "data_freshness_ok",
    "knowledge_base_updated",
}

REQUIRED_AGENT_MODULE_FILES = {
    "agent/__init__.py",
    "agent/artifact_manifest.py",
    "agent/artifact_verifier.py",
    "agent/backtest_agent.py",
    "agent/config.py",
    "agent/critic_agent.py",
    "agent/daily_pipeline.py",
    "agent/daily_simulation.py",
    "agent/data_agent.py",
    "agent/evolution_agent.py",
    "agent/factor_design.py",
    "agent/gpu_alpha_submission.py",
    "agent/io_utils.py",
    "agent/knowledge_base.py",
    "agent/market_intelligence.py",
    "agent/preflight.py",
    "agent/readiness_report.py",
    "agent/research_agent.py",
    "agent/run_entrypoint.py",
    "agent/schedule.py",
    "agent/self_audit.py",
    "agent/source_cache.py",
}
REQUIRED_BACKTEST_ENGINE_FILES = {
    "backtest_engine/__init__.py",
    "backtest_engine/engine.py",
}
REQUIRED_SCRIPT_FILES = {
    "scripts/alpha_gpu_backtest.sbatch",
    "scripts/alpha_gpu_probe.sbatch",
    "scripts/submit_alpha_gpu_backtest.sh",
}
REQUIRED_README_SNIPPETS = {
    "bash run_daily.sh",
    "gpu_alpha_submission_latest.json",
    "reports/run_daily_invocations.jsonl",
    "Slurm",
    "365 consecutive unique dates",
    "not_production_ready",
}


def _normalize_formula_key(text: Any) -> str:
    if not text:
        return ""
    return re.sub(r"[^a-z0-9_+\-*/().]", "", str(text).lower())


def _factor_identity_keys(
    factor_id: Any,
    formula: Any,
    formula_key: Any,
    expression: Any,
) -> set[str]:
    keys = {str(key) for key in (factor_id, formula, formula_key, expression) if key}
    normalized_formula = _normalize_formula_key(formula)
    normalized_formula_key = _normalize_formula_key(formula_key)
    if normalized_formula:
        keys.add(normalized_formula)
    if normalized_formula_key:
        keys.add(normalized_formula_key)
    return keys


def _repository_root() -> Path:
    return Path.cwd()


def _source_quality_is_production_evidence(source_quality: dict[str, Any]) -> bool:
    mode = source_quality.get("mode")
    total_sources = source_quality.get("total_sources") or 0
    ok_sources = source_quality.get("ok_sources") or 0
    return (
        mode not in {"offline", "fallback", None, ""}
        and total_sources > 0
        and ok_sources == total_sources
        and (source_quality.get("error_sources") or 0) == 0
        and not source_quality.get("missing_kinds")
        and (source_quality.get("coverage_ratio") or 0) >= 1.0
        and source_quality.get("fallback_used") is False
    )


def _source_quality_covers_required_kinds(source_quality: dict[str, Any], required_kinds: set[str]) -> bool:
    covered = {str(kind) for kind in source_quality.get("covered_kinds") or [] if kind}
    return required_kinds.issubset(covered)


def _market_source_quality_is_production_evidence(source_quality: dict[str, Any]) -> bool:
    return (
        _source_quality_is_production_evidence(source_quality)
        and _source_quality_covers_required_kinds(source_quality, REQUIRED_MARKET_SOURCE_KINDS)
    )


def _research_source_quality_is_production_evidence(source_quality: dict[str, Any]) -> bool:
    return (
        _source_quality_is_production_evidence(source_quality)
        and _source_quality_covers_required_kinds(source_quality, REQUIRED_RESEARCH_SOURCE_KINDS)
    )


def _repository_deliverables_evidence(cfg: RunConfig) -> dict[str, Any]:
    root = _repository_root()
    file_paths = {
        "README.md": root / "README.md",
        "run_daily.sh": root / "run_daily.sh",
        **{path: root / path for path in sorted(REQUIRED_AGENT_MODULE_FILES)},
        **{path: root / path for path in sorted(REQUIRED_BACKTEST_ENGINE_FILES)},
        **{path: root / path for path in sorted(REQUIRED_SCRIPT_FILES)},
    }
    directory_paths = {
        "agent/": root / "agent",
        "backtest_engine/": root / "backtest_engine",
        "scripts/": root / "scripts",
        "reports/": cfg.output_root,
        "knowledge_base/": cfg.knowledge_root,
        "factor_library/": cfg.factor_library,
    }
    missing_files = sorted(label for label, path in file_paths.items() if not path.is_file())
    missing_directories = sorted(label for label, path in directory_paths.items() if not path.is_dir())
    unwritable_directories = sorted(
        label
        for label, path in directory_paths.items()
        if path.is_dir() and not os.access(path, os.W_OK)
    )
    run_daily_path = file_paths["run_daily.sh"]
    run_daily_executable = run_daily_path.is_file() and os.access(run_daily_path, os.X_OK)
    run_daily_text = run_daily_path.read_text(encoding="utf-8") if run_daily_path.is_file() else ""
    run_daily_uses_audited_entrypoint = (
        "QUANT_RUN_DAILY_SH=1" in run_daily_text
        and "QUANT_RUN_DAILY_SCRIPT" in run_daily_text
        and "QUANT_RUN_DAILY_COMMAND" in run_daily_text
        and "python -m agent.run_entrypoint" in run_daily_text
    )
    readme_text = file_paths["README.md"].read_text(encoding="utf-8") if file_paths["README.md"].is_file() else ""
    missing_readme_snippets = sorted(snippet for snippet in REQUIRED_README_SNIPPETS if snippet not in readme_text)
    readme_documents_audited_readiness = not missing_readme_snippets
    return {
        "repo_root": str(root),
        "required_files": sorted(file_paths),
        "required_directories": sorted(directory_paths),
        "missing_files": missing_files,
        "missing_directories": missing_directories,
        "unwritable_directories": unwritable_directories,
        "required_readme_snippets": sorted(REQUIRED_README_SNIPPETS),
        "missing_readme_snippets": missing_readme_snippets,
        "readme_documents_audited_readiness": readme_documents_audited_readiness,
        "run_daily_executable": run_daily_executable,
        "run_daily_uses_audited_entrypoint": run_daily_uses_audited_entrypoint,
        "agent_module_files_present": not any(path.startswith("agent/") for path in missing_files),
        "backtest_engine_files_present": not any(path.startswith("backtest_engine/") for path in missing_files),
        "script_files_present": not any(path.startswith("scripts/") for path in missing_files),
        "all_present": (
            not missing_files
            and not missing_directories
            and not unwritable_directories
            and readme_documents_audited_readiness
            and run_daily_executable
            and run_daily_uses_audited_entrypoint
        ),
    }


def _is_iso_datetime(value: Any) -> bool:
    return _parse_iso_datetime(value) is not None


def _parse_iso_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _is_sha256_hex(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(ch in "0123456789abcdefABCDEF" for ch in value)
    )


def _source_snapshot_is_production_evidence(row: dict[str, Any]) -> bool:
    source_status = row.get("source_status") or []
    snapshot_items = row.get("items") or []
    item_count = row.get("item_count") or 0
    source_quality = row.get("source_quality") or {}
    agent = row.get("agent")
    run_date = _parse_run_date(row.get("run_date"))
    snapshot_written_at = _parse_iso_datetime(row.get("snapshot_written_at"))
    if agent == "market_intelligence":
        source_ok = _market_source_quality_is_production_evidence(source_quality)
    elif agent == "research_agent":
        source_ok = _research_source_quality_is_production_evidence(source_quality)
    else:
        source_ok = False
    if not source_ok:
        return False
    if item_count <= 0 or not source_status:
        return False
    if run_date is None or snapshot_written_at is None or snapshot_written_at.date() != run_date:
        return False
    status_item_count = sum((item.get("items") or 0) for item in source_status)
    if item_count != status_item_count:
        return False
    if len(snapshot_items) != min(item_count, 50):
        return False
    source_kinds = {str(item.get("kind")) for item in source_status if item.get("kind")}
    for snapshot_item in snapshot_items:
        item_kind = snapshot_item.get("kind")
        item_url = snapshot_item.get("url")
        if (
            not item_kind
            or str(item_kind) not in source_kinds
            or not isinstance(item_url, str)
            or not item_url.startswith("https://")
        ):
            return False
        if agent == "market_intelligence" and not snapshot_item.get("title"):
            return False
        if agent == "research_agent" and not snapshot_item.get("text"):
            return False
    for item in source_status:
        response_bytes = item.get("response_bytes")
        url = item.get("url")
        if (
            item.get("status") != "ok"
            or (item.get("items") or 0) <= 0
            or not isinstance(url, str)
            or not url.startswith("https://")
            or _parse_iso_datetime(item.get("fetched_at")) is None
            or _parse_iso_datetime(item.get("fetched_at")).date() != run_date
            or not _is_sha256_hex(item.get("content_sha256"))
            or not isinstance(response_bytes, int)
            or response_bytes <= 0
        ):
            return False
    return True


def _knowledge_save_is_complete(row: dict[str, Any]) -> bool:
    write = row.get("factor_database_write") or {}
    saved_ids = [str(item) for item in write.get("saved_factor_ids") or [] if item]
    saved_count = write.get("saved_factor_count")
    expected_ids = [
        str(item)
        for item in (row.get("backtest") or {}).get("result_factor_ids") or []
        if item
    ]
    return (
        _run_record_timestamp_matches_run_date(row)
        and (row.get("pipeline") or {}).get("run_quality") == "complete"
        and write.get("status") == "updated"
        and (saved_count or 0) > 0
        and saved_count == len(expected_ids)
        and len(saved_ids) == saved_count
        and bool(expected_ids)
        and sorted(saved_ids) == sorted(expected_ids)
    )


def _data_is_production_evidence(row: dict[str, Any]) -> bool:
    source_mode = row.get("data_source_mode")
    freshness = row.get("data_freshness") or {}
    checks = row.get("data_checks") or {}
    domains = row.get("data_domain_coverage") or {}
    domains_usable = checks.get("required_data_domains_usable")
    if domains_usable is None and domains:
        domains_usable = all(item.get("usable") for item in domains.values())
    return (
        bool(source_mode)
        and source_mode != "synthetic_fallback"
        and freshness.get("status") == "ok"
        and domains_usable is True
    )


def _data_artifact_is_production_evidence(row: dict[str, Any]) -> bool:
    manifest = row.get("dataset_manifest") or {}
    health = row.get("data_health") or {}
    row_run_date = str(row.get("run_date") or "")
    source_mode = row.get("data_source_mode") or health.get("source_mode") or manifest.get("source_mode")
    detail = (
        row.get("data_source_detail")
        or health.get("data_source_detail")
        or manifest.get("data_source_detail")
        or {}
    )
    daily_detail = detail.get("daily") or {}
    dataset_path = str(manifest.get("dataset_path") or "")
    health_min_date = _parse_iso_date(health.get("date_min"))
    health_max_date = _parse_iso_date(health.get("date_max"))
    data_summary = {
        "data_source_mode": source_mode,
        "data_freshness": row.get("data_freshness") or health.get("freshness", {}),
        "data_checks": row.get("data_checks") or health.get("checks", {}),
        "data_domain_coverage": row.get("data_domain_coverage") or health.get("domain_coverage", {}),
    }
    return (
        _data_is_production_evidence(data_summary)
        and _parse_run_date(row_run_date) is not None
        and _run_record_timestamp_matches_run_date(row)
        and str(manifest.get("run_date")) == row_run_date
        and str(health.get("run_date")) == row_run_date
        and f"daily_logs/{row_run_date}/" in dataset_path.replace("\\", "/")
        and health_min_date is not None
        and health_max_date is not None
        and health_min_date <= health_max_date
        and health.get("status") == "ok"
        and bool(manifest.get("dataset_sha256"))
        and (manifest.get("dataset_size_bytes") or 0) > 0
        and (manifest.get("rows") or 0) > 0
        and (manifest.get("stocks") or 0) > 0
        and (manifest.get("dates") or 0) > 0
        and manifest.get("rows") == health.get("rows")
        and manifest.get("stocks") == health.get("stocks")
        and manifest.get("dates") == health.get("dates")
        and manifest.get("source_mode") == source_mode
        and health.get("source_mode") == source_mode
        and bool(detail.get("data_root"))
        and detail.get("fallback_reason") in {None, ""}
        and daily_detail.get("exists") is True
        and (daily_detail.get("selected_csv_file_count") or 0) > 0
    )


def _run_has_research_activity(row: dict[str, Any]) -> bool:
    counts = row.get("counts") or {}
    return (
        (counts.get("ideas") or 0) > 0
        and (counts.get("candidate_factors") or 0) > 0
        and (counts.get("backtest_results") or 0) > 0
    )


def _schedule_is_daily_run_daily(schedule_payload: dict[str, Any], run_date: str) -> bool:
    cron_line = str(schedule_payload.get("cron_line") or "")
    command = str(schedule_payload.get("command") or cron_line)
    script_path = str(schedule_payload.get("script_path") or "")
    log_path = str(schedule_payload.get("log_path") or "")
    return (
        str(schedule_payload.get("run_date")) == str(run_date)
        and schedule_payload.get("cadence") == "daily"
        and schedule_payload.get("shell_entrypoint") is True
        and schedule_payload.get("uses_run_daily_sh") is True
        and schedule_payload.get("install_required") is True
        and schedule_payload.get("installed_automatically") is False
        and schedule_payload.get("script_exists") is True
        and schedule_payload.get("log_parent_exists") is True
        and schedule_payload.get("log_parent_writable") is True
        and schedule_payload.get("day_of_month") == "*"
        and schedule_payload.get("month") == "*"
        and schedule_payload.get("day_of_week") == "*"
        and "bash" in command
        and "run_daily.sh" in command
        and "daily_cron.log" in command
        and script_path.endswith("run_daily.sh")
        and log_path.endswith("daily_cron.log")
    )


def _path_matches_expected(path_value: str, expected_path: Path | None) -> bool:
    if expected_path is None:
        return path_value.endswith("run_daily.sh")
    if not path_value:
        return False
    return Path(path_value).expanduser().resolve(strict=False) == expected_path.expanduser().resolve(strict=False)


def _invocation_is_successful_run_daily(row: dict[str, Any], expected_script_path: Path | None = None) -> bool:
    script_path = str(row.get("entrypoint_script") or "")
    command = str(row.get("entrypoint_command") or "")
    duration_sec = row.get("duration_sec")
    return (
        row.get("status") == "success"
        and row.get("exit_code") == 0
        and row.get("config_loaded") is True
        and _is_iso_datetime(row.get("started_at"))
        and _is_iso_datetime(row.get("finished_at"))
        and _invocation_timestamps_match_run_date(row)
        and isinstance(duration_sec, (int, float))
        and duration_sec > 0
        and row.get("shell_entrypoint") is True
        and row.get("entrypoint_script_exists") is True
        and bool(script_path)
        and bool(command)
        and _path_matches_expected(script_path, expected_script_path)
        and "bash" in command
        and "run_daily.sh" in command
    )


def _cron_example_matches_schedule(cfg: RunConfig, schedule_payload: dict[str, Any]) -> bool:
    cron_line = str(schedule_payload.get("cron_line") or "").strip()
    cron_path = cfg.run_dir / "cron_example.txt"
    if not cron_line or not cron_path.exists():
        return False
    text = cron_path.read_text(encoding="utf-8").strip()
    return bool(text) and cron_line in text and "bash" in text and "run_daily.sh" in text


def _self_audit_is_current_evidence(cfg: RunConfig, latest_audit: dict[str, Any]) -> bool:
    checks = latest_audit.get("checks") or {}
    return (
        str(latest_audit.get("run_date")) == str(cfg.run_date)
        and latest_audit.get("status") == "pass"
        and (latest_audit.get("score") or 0) >= 0.9
        and REQUIRED_SELF_AUDIT_CHECKS.issubset(checks)
        and all(checks.get(name) is True for name in REQUIRED_SELF_AUDIT_CHECKS)
    )


def _current_output_counts(
    latest_events: dict[str, Any],
    latest_ideas: dict[str, Any],
    latest_candidates: dict[str, Any],
    latest_backtests: dict[str, Any],
    factor_db: dict[str, Any],
) -> dict[str, int]:
    return {
        "events": len(latest_events.get("events") or []),
        "ideas": len(latest_ideas.get("ideas") or []),
        "candidate_factors": len(latest_candidates.get("factors") or []),
        "backtest_results": len(latest_backtests.get("results") or []),
        "knowledge_factors": len(factor_db.get("factors") or []),
    }


def _self_audit_matches_current_outputs(
    latest_audit: dict[str, Any],
    latest_events: dict[str, Any],
    latest_ideas: dict[str, Any],
    latest_candidates: dict[str, Any],
    latest_backtests: dict[str, Any],
    factor_db: dict[str, Any],
    latest_data_health: dict[str, Any],
    latest_preflight: dict[str, Any],
) -> bool:
    counts = latest_audit.get("counts") or {}
    current_counts = _current_output_counts(
        latest_events,
        latest_ideas,
        latest_candidates,
        latest_backtests,
        factor_db,
    )
    return (
        all(counts.get(name) == value for name, value in current_counts.items())
        and latest_audit.get("data_freshness") == latest_data_health.get("freshness", {})
        and latest_audit.get("preflight") == latest_preflight
        and latest_audit.get("market_source_quality") == latest_events.get("source_quality", {})
        and latest_audit.get("research_source_quality") == latest_ideas.get("source_quality", {})
    )


def _self_audit_markdown_matches_json(cfg: RunConfig, latest_audit: dict[str, Any]) -> bool:
    path = cfg.run_dir / "self_audit.md"
    if not path.exists() or path.stat().st_size == 0:
        return False
    text = path.read_text(encoding="utf-8")
    checks = latest_audit.get("checks") or {}
    preflight = latest_audit.get("preflight") or {}
    preflight_checks = preflight.get("checks") or {}
    freshness = latest_audit.get("data_freshness") or {}
    expected = {
        "# Self Audit",
        f"Run date: {cfg.run_date}",
        f"Status: {latest_audit.get('status')}",
        f"Score: {(latest_audit.get('score') or 0):.2f}",
        f"Source mode: {latest_audit.get('source_mode')}",
        f"- status: {preflight.get('status')}",
        f"- min_free_disk_ok: {preflight_checks.get('min_free_disk_ok')}",
        f"- required_dirs_writable: {preflight_checks.get('required_dirs_writable')}",
    }
    for name, ok in checks.items():
        expected.add(f"- {name}: {'ok' if ok else 'fail'}")
    if freshness:
        expected |= {
            f"- status: {freshness.get('status')}",
            f"- staleness_days: {freshness.get('staleness_days')}",
            f"- max_allowed_staleness_days: {freshness.get('max_allowed_staleness_days')}",
        }
    return all(line in text for line in expected)


def _run_history_matches_current_outputs(
    latest: dict[str, Any],
    latest_state: dict[str, Any],
    latest_audit: dict[str, Any],
    latest_events: dict[str, Any],
    latest_ideas: dict[str, Any],
    latest_candidates: dict[str, Any],
    latest_backtests: dict[str, Any],
    latest_critique: dict[str, Any],
    latest_data_health: dict[str, Any],
) -> bool:
    agent_status = {
        str(item.get("agent")): item.get("status")
        for item in latest_state.get("agents", [])
        if item.get("agent")
    }
    expected_counts = {
        "events": len(latest_events.get("events") or []),
        "ideas": len(latest_ideas.get("ideas") or []),
        "candidate_factors": len(latest_candidates.get("factors") or []),
        "backtest_results": len(latest_backtests.get("results") or []),
        "raw_candidates": sum(1 for row in latest_backtests.get("results", []) if row.get("decision") == "raw_candidate"),
        "promoted": sum(1 for row in latest_critique.get("critiques", []) if row.get("decision") == "promote"),
        "killed": sum(1 for row in latest_critique.get("critiques", []) if row.get("decision") == "kill"),
    }
    counts = latest.get("counts") or {}
    return (
        latest.get("pipeline_status") == latest_state.get("status")
        and latest.get("self_audit_status") == latest_audit.get("status")
        and latest.get("self_audit_score") == latest_audit.get("score")
        and latest.get("agent_status") == agent_status
        and all(counts.get(name) == value for name, value in expected_counts.items())
        and latest.get("market_source_quality") == latest_events.get("source_quality", {})
        and latest.get("research_source_quality") == latest_ideas.get("source_quality", {})
        and latest.get("data_health_status") == latest_data_health.get("status")
        and latest.get("data_source_mode") == latest_data_health.get("source_mode")
        and latest.get("data_freshness") == latest_data_health.get("freshness", {})
        and latest.get("data_checks") == latest_data_health.get("checks", {})
        and latest.get("data_domain_coverage") == latest_data_health.get("domain_coverage", {})
    )


def _daily_report_is_current_evidence(
    cfg: RunConfig,
    latest_events: dict[str, Any],
    latest_ideas: dict[str, Any],
    latest_candidates: dict[str, Any],
    latest_backtests: dict[str, Any],
    latest_critique: dict[str, Any],
    latest_data_health: dict[str, Any],
    latest_preflight: dict[str, Any],
    latest_audit: dict[str, Any],
    latest_gpu_alpha_submission: dict[str, Any],
    readiness_artifact: dict[str, Any],
) -> bool:
    path = cfg.run_dir / "daily_report.md"
    if not path.exists() or path.stat().st_size == 0:
        return False
    text = path.read_text(encoding="utf-8")
    market_quality = latest_events.get("source_quality") or {}
    research_quality = latest_ideas.get("source_quality") or {}
    dataset_sha = str((latest_backtests.get("dataset_provenance") or {}).get("dataset_sha256") or "unknown")[:12]
    raw_candidates = sum(1 for row in latest_backtests.get("results", []) if row.get("decision") == "raw_candidate")
    promoted = sum(1 for row in latest_critique.get("critiques", []) if row.get("decision") == "promote")
    readiness_blockers = readiness_artifact.get("blockers") or []
    if not readiness_artifact.get("status"):
        return False
    gpu_status = latest_gpu_alpha_submission.get("status", "pending")
    if latest_gpu_alpha_submission.get("job_id"):
        gpu_summary = f"{gpu_status} (job {latest_gpu_alpha_submission['job_id']})"
    elif latest_gpu_alpha_submission.get("skip_reason"):
        gpu_summary = f"{gpu_status} ({latest_gpu_alpha_submission['skip_reason']})"
    elif latest_gpu_alpha_submission.get("error"):
        gpu_summary = f"{gpu_status} ({latest_gpu_alpha_submission['error']})"
    else:
        gpu_summary = str(gpu_status)
    expected_lines = {
        f"- events collected: {len(latest_events.get('events') or [])}",
        f"- market source mode: {market_quality.get('mode', 'unknown')} ({market_quality.get('ok_sources', 0)}/{market_quality.get('total_sources', 0)} ok)",
        f"- research ideas: {len(latest_ideas.get('ideas') or [])}",
        f"- research source mode: {research_quality.get('mode', 'unknown')} ({research_quality.get('ok_sources', 0)}/{research_quality.get('total_sources', 0)} ok)",
        f"- candidate factors: {len(latest_candidates.get('factors') or [])}",
        f"- backtested factors: {len(latest_backtests.get('results') or [])}",
        f"- backtest dataset sha256: {dataset_sha}",
        f"- raw backtest candidates: {raw_candidates}",
        f"- promoted after critic: {promoted}",
        f"- data health: {latest_data_health.get('status', 'unknown')}",
        f"- preflight: {latest_preflight.get('status', 'unknown')}",
        f"- self audit: {latest_audit.get('status', 'pending')} ({(latest_audit.get('score') or 0):.2f})",
        f"- gpu alpha submission: {gpu_summary}",
        f"- readiness status: {readiness_artifact.get('status')}",
        f"- readiness score: {(readiness_artifact.get('readiness_score') or 0):.4f}",
        f"- readiness blockers: {len(readiness_blockers)}",
        f"- top readiness blocker: {readiness_blockers[0] if readiness_blockers else 'none'}",
    }
    return (
        f"Run date: {cfg.run_date}" in text
        and all(snippet in text for snippet in REQUIRED_DAILY_REPORT_SNIPPETS)
        and all(f"- {agent}:" in text for agent in REQUIRED_DAILY_REPORT_AGENTS)
        and all(line in text for line in expected_lines)
    )


def _factor_library_matches_candidates(cfg: RunConfig, candidate_payload: dict[str, Any]) -> bool:
    factors = candidate_payload.get("factors") or []
    if not factors:
        return False
    fields = [
        "factor_id",
        "name",
        "formula",
        "formula_key",
        "expression",
        "source_idea_id",
        "created_at_run",
        "provenance",
        "status",
    ]
    for factor in factors:
        factor_id = factor.get("factor_id")
        if not factor_id:
            return False
        library_factor = read_json(cfg.factor_library / f"{factor_id}.json", {})
        if any(library_factor.get(field) != factor.get(field) for field in fields):
            return False
    return True


def _historical_failed_factor_keys(
    cfg: RunConfig,
    factor_db: dict[str, Any],
    failure_memory: list[dict[str, Any]],
) -> set[str]:
    keys: set[str] = set()
    for factor in factor_db.get("factors") or []:
        run_date = factor.get("run_date")
        if factor.get("decision") != "kill" or str(run_date) == str(cfg.run_date):
            continue
        keys.update(_factor_identity_keys(
            factor.get("factor_id"),
            factor.get("formula"),
            factor.get("formula_key"),
            factor.get("expression"),
        ))
    for item in failure_memory:
        run_date = item.get("run_date")
        if str(run_date) == str(cfg.run_date):
            continue
        keys.update(_factor_identity_keys(
            item.get("factor_id"),
            item.get("formula"),
            item.get("formula_key"),
            item.get("expression"),
        ))
    return keys


def _candidate_failed_memory_matches(
    cfg: RunConfig,
    candidate_payload: dict[str, Any],
    factor_db: dict[str, Any],
    failure_memory: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    failed_keys = _historical_failed_factor_keys(cfg, factor_db, failure_memory)
    matches = []
    for factor in candidate_payload.get("factors") or []:
        factor_keys = _factor_identity_keys(
            factor.get("factor_id"),
            factor.get("formula"),
            factor.get("formula_key"),
            factor.get("expression"),
        )
        matched_keys = sorted(factor_keys & failed_keys)
        if matched_keys:
            matches.append({
                "factor_id": factor.get("factor_id"),
                "formula_key": factor.get("formula_key"),
                "matched_keys": matched_keys,
            })
    return matches


def _candidate_factor_files_match_payload(cfg: RunConfig, candidate_payload: dict[str, Any]) -> bool:
    factors = candidate_payload.get("factors") or []
    if not factors:
        return False
    fields = [
        "factor_id",
        "name",
        "formula",
        "formula_key",
        "expression",
        "source_idea_id",
        "created_at_run",
        "provenance",
        "status",
    ]
    expected_files = {
        f"{factor.get('factor_id')}.json"
        for factor in factors
        if factor.get("factor_id")
    }
    actual_files = {
        path.name
        for path in (cfg.run_dir / "candidate_factors").glob("*.json")
    }
    if actual_files != expected_files:
        return False
    for factor in factors:
        factor_id = factor.get("factor_id")
        if not factor_id:
            return False
        path_factor = read_json(cfg.run_dir / "candidate_factors" / f"{factor_id}.json", {})
        if any(path_factor.get(field) != factor.get(field) for field in fields):
            return False
    return True


def _factor_database_matches_latest_results(
    cfg: RunConfig,
    factor_db: dict[str, Any],
    backtest_payload: dict[str, Any],
    critique_payload: dict[str, Any],
) -> bool:
    result_fields = [
        "name",
        "formula",
        "formula_key",
        "expression",
        "horizon_days",
        "rankic_mean",
        "rankic_ir",
        "rankic_positive_frac",
        "portfolio",
        "long_short",
        "cost_sensitivity",
        "rows",
        "dates",
        "decision_note",
    ]
    results = backtest_payload.get("results") or []
    if not results:
        return False
    critiques = {
        str(item.get("factor_id")): item
        for item in critique_payload.get("critiques", [])
        if item.get("factor_id")
    }
    records = {
        str(item.get("factor_id")): item
        for item in factor_db.get("factors", [])
        if str(item.get("run_date")) == str(cfg.run_date) and item.get("factor_id")
    }
    expected_factor_ids = {
        str(result.get("factor_id"))
        for result in results
        if result.get("factor_id")
    }
    if set(records) != expected_factor_ids:
        return False
    for result in results:
        factor_id = str(result.get("factor_id") or "")
        if not factor_id:
            return False
        record = records.get(factor_id)
        if not record:
            return False
        expected_decision = (critiques.get(factor_id) or {}).get("decision", result.get("decision"))
        expected_issues = (critiques.get(factor_id) or {}).get("issues", [])
        if record.get("decision") != expected_decision or record.get("issues", []) != expected_issues:
            return False
        if any(record.get(field) != result.get(field) for field in result_fields):
            return False
    return True


def _backtest_result_files_match_payload(cfg: RunConfig, backtest_payload: dict[str, Any]) -> bool:
    results = backtest_payload.get("results") or []
    if not results:
        return False
    expected_files = {
        f"{row.get('factor_id')}.json"
        for row in results
        if row.get("factor_id")
    }
    actual_files = {
        path.name
        for path in (cfg.run_dir / "backtest_results").glob("*.json")
    }
    if actual_files != expected_files:
        return False
    result_fields = [
        "name",
        "formula",
        "formula_key",
        "expression",
        "horizon_days",
        "rankic_mean",
        "rankic_ir",
        "rankic_positive_frac",
        "rankic_by_date",
        "portfolio",
        "long_short",
        "cost_sensitivity",
        "rows",
        "dates",
        "decision",
        "decision_note",
    ]
    for result in results:
        factor_id = result.get("factor_id")
        if not factor_id:
            return False
        path_result = read_json(cfg.run_dir / "backtest_results" / f"{factor_id}.json", {})
        if str(path_result.get("factor_id")) != str(factor_id):
            return False
        if any(path_result.get(field) != result.get(field) for field in result_fields):
            return False
    return True


def _backtest_dataset_provenance_matches_manifest(
    backtest_payload: dict[str, Any],
    dataset_manifest: dict[str, Any],
) -> bool:
    provenance = backtest_payload.get("dataset_provenance") or {}
    return (
        provenance.get("hash_verified") is True
        and provenance.get("dataset_sha256") == dataset_manifest.get("dataset_sha256")
        and provenance.get("dataset_size_bytes") == dataset_manifest.get("dataset_size_bytes")
        and provenance.get("rows") == dataset_manifest.get("rows")
        and provenance.get("stocks") == dataset_manifest.get("stocks")
        and provenance.get("dates") == dataset_manifest.get("dates")
        and provenance.get("source_mode") == dataset_manifest.get("source_mode")
        and provenance.get("health_status") == dataset_manifest.get("health_status")
    )


def _next_generation_files_match_payload(cfg: RunConfig, next_generation_payload: dict[str, Any]) -> bool:
    factors = next_generation_payload.get("next_generation_factors") or []
    if not factors:
        return False
    expected_files = {
        f"{factor.get('factor_id')}.json"
        for factor in factors
        if factor.get("factor_id")
    }
    actual_files = {
        path.name
        for path in (cfg.run_dir / "next_generation_factors").glob("*.json")
    }
    if actual_files != expected_files:
        return False
    for factor in factors:
        factor_id = factor.get("factor_id")
        if not factor_id:
            return False
        path_factor = read_json(cfg.run_dir / "next_generation_factors" / f"{factor_id}.json", {})
        fields = [
            "factor_id",
            "parent_factor_id",
            "name",
            "formula",
            "formula_key",
            "expression",
            "horizon_days",
            "status",
            "rationale",
            "parent_decision",
            "failed_issues",
            "parent_metrics",
            "provenance",
        ]
        if any(path_factor.get(field) != factor.get(field) for field in fields):
            return False
    return True


def _failure_analysis_matches_critique(cfg: RunConfig, critique_payload: dict[str, Any]) -> bool:
    path = cfg.run_dir / "failure_analysis.md"
    critiques = critique_payload.get("critiques") or []
    if not path.exists() or path.stat().st_size == 0 or not critiques:
        return False
    text = path.read_text(encoding="utf-8")
    if f"Run date: {cfg.run_date}" not in text:
        return False
    for critique in critiques:
        factor_id = str(critique.get("factor_id") or "")
        if not factor_id or f"## {factor_id}" not in text:
            return False
        if f"- decision: {critique.get('decision')}" not in text:
            return False
        issues = critique.get("issues") or []
        issue_text = ", ".join(issues) if issues else "none"
        if f"- issues: {issue_text}" not in text:
            return False
        if f"- leakage_check: {critique.get('leakage_check')}" not in text:
            return False
        checks = critique.get("checks") or {}
        stability = checks.get("stability") or {}
        collinearity = checks.get("collinearity") or {}
        if f"- stability: {stability.get('score')}" not in text:
            return False
        if f"- collinearity: {collinearity.get('score')}" not in text:
            return False
    return True


def _research_log_matches_current_outputs(
    cfg: RunConfig,
    research_log_latest: dict[str, Any],
    latest_events: dict[str, Any],
    latest_ideas: dict[str, Any],
    latest_candidates: dict[str, Any],
    latest_backtests: dict[str, Any],
    latest_critique: dict[str, Any],
    latest_next_generation: dict[str, Any],
    latest_data_health: dict[str, Any],
) -> bool:
    if str(research_log_latest.get("run_date")) != str(cfg.run_date):
        return False
    if (research_log_latest.get("pipeline") or {}).get("run_quality") != "complete":
        return False
    if (research_log_latest.get("factor_database_write") or {}).get("status") != "updated":
        return False

    candidate_ids = [str(item.get("factor_id")) for item in latest_candidates.get("factors", []) if item.get("factor_id")]
    result_ids = [str(item.get("factor_id")) for item in latest_backtests.get("results", []) if item.get("factor_id")]
    next_ids = [
        str(item.get("factor_id"))
        for item in latest_next_generation.get("next_generation_factors", [])
        if item.get("factor_id")
    ]
    skipped_next_ids = [
        str(item.get("factor_id"))
        for item in latest_next_generation.get("skipped_evolution_factors", [])
        if item.get("factor_id")
    ]
    log_events = research_log_latest.get("events") or {}
    log_research = research_log_latest.get("research") or {}
    log_factor_design = research_log_latest.get("factor_design") or {}
    log_backtest = research_log_latest.get("backtest") or {}
    log_critic = research_log_latest.get("critic") or {}
    log_evolution = research_log_latest.get("evolution") or {}
    log_data = research_log_latest.get("data") or {}
    log_write = research_log_latest.get("factor_database_write") or {}
    saved_ids = [str(item) for item in log_write.get("saved_factor_ids") or [] if item]
    current_event_titles = [
        item.get("title") for item in (latest_events.get("events") or [])[:5]
    ]
    current_idea_ids = [
        str(item.get("idea_id"))
        for item in latest_ideas.get("ideas", [])
        if item.get("idea_id")
    ]
    current_themes = sorted({
        item.get("theme")
        for item in latest_ideas.get("ideas", [])
        if item.get("theme")
    })
    current_formula_keys = [
        str(item.get("formula_key"))
        for item in latest_candidates.get("factors", [])
        if item.get("formula_key")
    ]
    current_backtest_promoted_raw = sum(
        1 for item in latest_backtests.get("results", []) if item.get("decision") == "promote"
    )
    current_backtest_killed_raw = sum(
        1 for item in latest_backtests.get("results", []) if item.get("decision") == "kill"
    )
    current_critic_promoted = sum(
        1 for item in latest_critique.get("critiques", []) if item.get("decision") == "promote"
    )
    current_critic_killed = sum(
        1 for item in latest_critique.get("critiques", []) if item.get("decision") == "kill"
    )
    current_issue_counts = dict(Counter(
        issue
        for row in latest_critique.get("critiques", [])
        for issue in row.get("issues", [])
    ))

    return (
        log_events.get("count") == len(latest_events.get("events") or [])
        and log_events.get("source_quality") == latest_events.get("source_quality", {})
        and (log_events.get("top_titles") or []) == current_event_titles
        and log_research.get("idea_count") == len(latest_ideas.get("ideas") or [])
        and set(map(str, log_research.get("idea_ids") or [])) == set(current_idea_ids)
        and sorted(log_research.get("themes") or []) == current_themes
        and log_research.get("source_quality") == latest_ideas.get("source_quality", {})
        and log_research.get("context_items") == len(latest_ideas.get("research_context") or [])
        and log_factor_design.get("candidate_count") == len(candidate_ids)
        and log_factor_design.get("skipped_failed_count") == len(latest_candidates.get("skipped_factors") or [])
        and set(map(str, log_factor_design.get("factor_ids") or [])) == set(candidate_ids)
        and set(map(str, log_factor_design.get("formula_keys") or [])) == set(current_formula_keys)
        and log_backtest.get("result_count") == len(result_ids)
        and set(map(str, log_backtest.get("result_factor_ids") or [])) == set(result_ids)
        and log_backtest.get("promoted_raw") == current_backtest_promoted_raw
        and log_backtest.get("killed_raw") == current_backtest_killed_raw
        and log_write.get("saved_factor_count") == len(result_ids)
        and sorted(saved_ids) == sorted(result_ids)
        and (log_backtest.get("dataset_provenance") or {}) == (latest_backtests.get("dataset_provenance") or {})
        and log_critic.get("critique_count") == len(latest_critique.get("critiques") or [])
        and log_critic.get("promoted") == current_critic_promoted
        and log_critic.get("killed") == current_critic_killed
        and (log_critic.get("issue_counts") or {}) == current_issue_counts
        and log_evolution.get("next_generation_count") == len(next_ids)
        and set(map(str, log_evolution.get("next_factor_ids") or [])) == set(next_ids)
        and log_evolution.get("skipped_failed_count") == len(skipped_next_ids)
        and set(map(str, log_evolution.get("skipped_factor_ids") or [])) == set(skipped_next_ids)
        and log_data.get("status") == latest_data_health.get("status")
        and log_data.get("source_mode") == latest_data_health.get("source_mode")
        and log_data.get("rows") == latest_data_health.get("rows")
        and log_data.get("stocks") == latest_data_health.get("stocks")
        and log_data.get("dates") == latest_data_health.get("dates")
    )


def _data_health_latest_matches_current_outputs(
    data_health_latest: dict[str, Any],
    latest_data_health: dict[str, Any],
    latest_dataset_manifest: dict[str, Any],
    run_date: str,
) -> bool:
    if str(data_health_latest.get("run_date")) != str(run_date):
        return False
    latest_health = data_health_latest.get("data_health") or {}
    latest_manifest = data_health_latest.get("dataset_manifest") or {}
    return (
        latest_health.get("status") == latest_data_health.get("status")
        and latest_health.get("source_mode") == latest_data_health.get("source_mode")
        and latest_health.get("rows") == latest_data_health.get("rows")
        and latest_health.get("stocks") == latest_data_health.get("stocks")
        and latest_health.get("dates") == latest_data_health.get("dates")
        and latest_health.get("freshness") == latest_data_health.get("freshness")
        and latest_health.get("checks") == latest_data_health.get("checks")
        and latest_health.get("domain_coverage") == latest_data_health.get("domain_coverage")
        and latest_manifest.get("dataset_sha256") == latest_dataset_manifest.get("dataset_sha256")
        and latest_manifest.get("dataset_size_bytes") == latest_dataset_manifest.get("dataset_size_bytes")
        and latest_manifest.get("rows") == latest_dataset_manifest.get("rows")
        and latest_manifest.get("stocks") == latest_dataset_manifest.get("stocks")
        and latest_manifest.get("dates") == latest_dataset_manifest.get("dates")
        and latest_manifest.get("source_mode") == latest_dataset_manifest.get("source_mode")
    )


def _source_snapshots_match_current_outputs(
    cfg: RunConfig,
    latest_events: dict[str, Any],
    latest_ideas: dict[str, Any],
    source_snapshots: list[dict[str, Any]],
) -> bool:
    expected = {
        "market_intelligence": {
            "source_status": latest_events.get("source_status") or [],
            "source_quality": latest_events.get("source_quality") or {},
            "item_count": len(latest_events.get("events") or []),
            "items": (latest_events.get("events") or [])[:50],
        },
        "research_agent": {
            "source_status": latest_ideas.get("source_status") or [],
            "source_quality": latest_ideas.get("source_quality") or {},
            "item_count": len(latest_ideas.get("research_context") or []),
            "items": (latest_ideas.get("research_context") or [])[:50],
        },
    }
    same_day_records = {
        str(row.get("agent")): row
        for row in source_snapshots
        if str(row.get("run_date")) == str(cfg.run_date) and row.get("agent")
    }
    for agent, expected_payload in expected.items():
        path_payload = read_json(cfg.run_dir / "source_snapshots" / f"{agent}.json", {})
        jsonl_payload = same_day_records.get(agent, {})
        for payload in [path_payload, jsonl_payload]:
            snapshot_written_at = _parse_iso_datetime(payload.get("snapshot_written_at"))
            if (
                str(payload.get("run_date")) != str(cfg.run_date)
                or payload.get("agent") != agent
                or snapshot_written_at is None
                or snapshot_written_at.date() != _parse_run_date(cfg.run_date)
                or payload.get("source_status") != expected_payload["source_status"]
                or payload.get("source_quality") != expected_payload["source_quality"]
                or payload.get("item_count") != expected_payload["item_count"]
                or (payload.get("items") or []) != expected_payload["items"]
            ):
                return False
    return True


def _source_snapshots_latest_matches_current_outputs(
    cfg: RunConfig,
    source_snapshots_latest: dict[str, Any],
    latest_events: dict[str, Any],
    latest_ideas: dict[str, Any],
) -> bool:
    agent = source_snapshots_latest.get("agent")
    if agent == "market_intelligence":
        expected = {
            "source_status": latest_events.get("source_status") or [],
            "source_quality": latest_events.get("source_quality") or {},
            "item_count": len(latest_events.get("events") or []),
            "items": (latest_events.get("events") or [])[:50],
        }
    elif agent == "research_agent":
        expected = {
            "source_status": latest_ideas.get("source_status") or [],
            "source_quality": latest_ideas.get("source_quality") or {},
            "item_count": len(latest_ideas.get("research_context") or []),
            "items": (latest_ideas.get("research_context") or [])[:50],
        }
    else:
        return False
    snapshot_written_at = _parse_iso_datetime(source_snapshots_latest.get("snapshot_written_at"))
    return (
        str(source_snapshots_latest.get("run_date")) == str(cfg.run_date)
        and snapshot_written_at is not None
        and snapshot_written_at.date() == _parse_run_date(cfg.run_date)
        and source_snapshots_latest.get("source_status") == expected["source_status"]
        and source_snapshots_latest.get("source_quality") == expected["source_quality"]
        and source_snapshots_latest.get("item_count") == expected["item_count"]
        and (source_snapshots_latest.get("items") or []) == expected["items"]
    )


def _artifact_manifest_latest_matches_current(
    artifact_manifest: dict[str, Any],
    artifact_manifest_latest: dict[str, Any],
    run_date: str,
) -> bool:
    if str(artifact_manifest.get("run_date")) != str(run_date):
        return False
    if str(artifact_manifest_latest.get("run_date")) != str(run_date):
        return False
    current_records = _stable_manifest_records(artifact_manifest)
    latest_records = _stable_manifest_records(artifact_manifest_latest)
    return bool(current_records) and current_records == latest_records


def _artifact_verification_latest_matches_current(
    artifact_verification: dict[str, Any],
    artifact_verification_latest: dict[str, Any],
    run_date: str,
) -> bool:
    if str(artifact_verification.get("run_date")) != str(run_date):
        return False
    if str(artifact_verification_latest.get("run_date")) != str(run_date):
        return False
    current_summary = _stable_verification_summary(artifact_verification)
    latest_summary = _stable_verification_summary(artifact_verification_latest)
    return bool(current_summary.get("manifest_generated_at")) and current_summary == latest_summary


def _artifact_verification_matches_manifest(
    artifact_verification: dict[str, Any],
    artifact_manifest: dict[str, Any],
    cfg: RunConfig,
) -> bool:
    return (
        artifact_verification.get("status") == "pass"
        and str(artifact_verification.get("run_date")) == str(cfg.run_date)
        and artifact_verification.get("manifest_path") == str(cfg.run_dir / "artifact_manifest.json")
        and bool(artifact_manifest.get("generated_at"))
        and artifact_verification.get("manifest_generated_at") == artifact_manifest.get("generated_at")
    )


def _stable_verification_summary(payload: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "status",
        "manifest_path",
        "manifest_generated_at",
        "manifest_file_count",
        "checked_file_count",
        "skipped_file_count",
        "missing_file_count",
        "hash_mismatch_count",
        "missing_hash_count",
        "skip_mutable_readiness",
        "checked_files",
        "skipped_files",
        "missing_files",
        "hash_mismatches",
        "missing_hashes",
    ]
    return {key: payload.get(key) for key in keys}


def _stable_manifest_records(artifact_manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for item in artifact_manifest.get("files") or []:
        rel = str(item.get("relative_path") or "")
        if not rel or rel in MUTABLE_READINESS_PATHS:
            continue
        records[rel] = {
            "sha256": item.get("sha256"),
            "size_bytes": item.get("size_bytes"),
        }
    return records


def _stable_manifest_summary(artifact_manifest: dict[str, Any]) -> dict[str, int]:
    records = _stable_manifest_records(artifact_manifest)
    return {
        "file_count": len(records),
        "total_size_bytes": sum((item.get("size_bytes") or 0) for item in records.values()),
    }


def _run_audit_state_matches_pipeline_state(run_audit_state: dict[str, Any], latest_state: dict[str, Any]) -> bool:
    if not latest_state:
        return False
    keys = [
        "run_date",
        "status",
        "current_agent",
        "completed_agents",
        "agents",
        "lock",
        "retention",
        "run_history_path",
        "readiness_report_path",
        "artifact_manifest_path",
    ]
    return all(run_audit_state.get(key) == latest_state.get(key) for key in keys if key in latest_state)


def _run_audit_is_current_evidence(
    cfg: RunConfig,
    run_audit: dict[str, Any],
    latest_state: dict[str, Any],
) -> bool:
    config = run_audit.get("config") or {}
    lock = run_audit.get("lock") or {}
    state = run_audit.get("state") or {}
    retention = state.get("retention") or {}
    required_config = {
        "offline": cfg.offline,
        "agent_retries": cfg.agent_retries,
        "retention_days": cfg.retention_days,
        "lock_stale_minutes": cfg.lock_stale_minutes,
        "min_free_disk_mb": cfg.min_free_disk_mb,
        "data_root": str(cfg.data_root),
        "output_root": str(cfg.output_root),
        "knowledge_root": str(cfg.knowledge_root),
        "factor_library": str(cfg.factor_library),
    }
    return (
        str(run_audit.get("run_date")) == str(cfg.run_date)
        and all(config.get(key) == value for key, value in required_config.items())
        and str(lock.get("run_date")) == str(cfg.run_date)
        and bool(lock.get("pid"))
        and bool(lock.get("created_at"))
        and lock.get("stale_after_minutes") == cfg.lock_stale_minutes
        and str(state.get("run_date")) == str(cfg.run_date)
        and state.get("status") in {"complete", "complete_with_errors"}
        and bool(state.get("started_at"))
        and bool(state.get("updated_at"))
        and isinstance(state.get("agents"), list)
        and state.get("lock") == lock
        and retention.get("retention_days") == cfg.retention_days
        and _run_audit_state_matches_pipeline_state(state, latest_state)
    )


def _gpu_alpha_submission_is_current_evidence(
    cfg: RunConfig,
    run_payload: dict[str, Any],
    latest_payload: dict[str, Any],
) -> bool:
    script = "scripts/submit_alpha_gpu_backtest.sh"
    if not run_payload or run_payload != latest_payload:
        return False
    if (
        run_payload.get("agent") != "gpu_alpha_submission"
        or str(run_payload.get("run_date")) != str(cfg.run_date)
        or run_payload.get("script") != script
        or run_payload.get("script_exists") is not True
        or _parse_iso_datetime(run_payload.get("created_at")) is None
    ):
        return False
    if cfg.offline:
        return (
            run_payload.get("offline") is True
            and run_payload.get("status") == "skipped"
            and run_payload.get("skip_reason") == "offline_run"
            and run_payload.get("submitted") is False
            and run_payload.get("job_id") is None
        )
    if run_payload.get("enabled") is not True or run_payload.get("offline") is True:
        return False
    if run_payload.get("status") == "submitted":
        return (
            run_payload.get("submitted") is True
            and isinstance(run_payload.get("job_id"), str)
            and bool(run_payload.get("job_id"))
            and run_payload.get("command") == ["bash", script]
            and bool(run_payload.get("sbatch_path"))
            and run_payload.get("returncode") == 0
        )
    if run_payload.get("status") == "submitted_unparsed":
        return (
            run_payload.get("submitted") is True
            and run_payload.get("command") == ["bash", script]
            and bool(run_payload.get("sbatch_path"))
            and run_payload.get("returncode") == 0
        )
    return False


def _killed_factors_have_failure_memory(cfg: RunConfig, latest_critique: dict[str, Any], failure_memory: list[dict[str, Any]]) -> bool:
    killed_ids = {
        str(row.get("factor_id"))
        for row in latest_critique.get("critiques", [])
        if row.get("decision") == "kill" and row.get("factor_id")
    }
    memory_ids = {
        str(row.get("factor_id"))
        for row in failure_memory
        if str(row.get("run_date")) == str(cfg.run_date) and row.get("factor_id")
    }
    return killed_ids == memory_ids


def _killed_factor_failure_memory_details_match(
    cfg: RunConfig,
    latest_critique: dict[str, Any],
    latest_backtests: dict[str, Any],
    latest_next_generation: dict[str, Any],
    failure_memory: list[dict[str, Any]],
) -> bool:
    results = {
        str(row.get("factor_id")): row
        for row in latest_backtests.get("results", [])
        if row.get("factor_id")
    }
    killed = [
        row for row in latest_critique.get("critiques", [])
        if row.get("decision") == "kill" and row.get("factor_id")
    ]
    if not killed:
        return True
    next_by_parent: dict[str, set[str]] = {}
    for row in latest_next_generation.get("next_generation_factors", []) or []:
        parent_id = row.get("parent_factor_id")
        factor_id = row.get("factor_id")
        if parent_id and factor_id:
            next_by_parent.setdefault(str(parent_id), set()).add(str(factor_id))
    memory_by_id = {
        str(row.get("factor_id")): row
        for row in failure_memory
        if str(row.get("run_date")) == str(cfg.run_date) and row.get("factor_id")
    }
    for critique in killed:
        factor_id = str(critique.get("factor_id"))
        memory = memory_by_id.get(factor_id)
        result = results.get(factor_id, {})
        if not memory:
            return False
        expected_formula_key = result.get("formula_key")
        if expected_formula_key and str(memory.get("formula_key")) != str(expected_formula_key):
            return False
        if set(memory.get("issues") or []) != set(critique.get("issues") or []):
            return False
        if not isinstance(memory.get("checks"), dict) or not memory.get("checks"):
            return False
        metrics = memory.get("parent_metrics") or {}
        portfolio = result.get("portfolio") or {}
        if result.get("rankic_mean") != metrics.get("rankic_mean"):
            return False
        if portfolio.get("ann_return_net") != metrics.get("ann_return_net"):
            return False
        next_actions = {str(item) for item in memory.get("next_actions") or [] if item}
        expected_actions = next_by_parent.get(factor_id, set())
        if not next_actions or next_actions != expected_actions:
            return False
    return True


def _latest_pointer_matches_current(pointer: dict[str, Any], run_date: str) -> bool:
    return bool(pointer) and str(pointer.get("run_date")) == str(run_date)


def _run_record_timestamp_matches_run_date(row: dict[str, Any]) -> bool:
    run_date = _parse_run_date(row.get("run_date"))
    recorded_at = _parse_iso_datetime(row.get("recorded_at"))
    return run_date is not None and recorded_at is not None and recorded_at.date() == run_date


def _invocation_timestamps_match_run_date(row: dict[str, Any]) -> bool:
    run_date = _parse_run_date(row.get("run_date"))
    started_at = _parse_iso_datetime(row.get("started_at"))
    finished_at = _parse_iso_datetime(row.get("finished_at"))
    return (
        run_date is not None
        and started_at is not None
        and finished_at is not None
        and started_at.date() == run_date
        and finished_at.date() == run_date
        and finished_at >= started_at
    )


def _run_has_successful_audited_evidence(row: dict[str, Any]) -> bool:
    agent_status = row.get("agent_status") or {}
    return (
        _parse_run_date(row.get("run_date")) is not None
        and _is_iso_datetime(row.get("recorded_at"))
        and _run_record_timestamp_matches_run_date(row)
        and row.get("pipeline_status") == "complete"
        and row.get("self_audit_status") == "pass"
        and (row.get("self_audit_score") or 0) >= 0.9
        and REQUIRED_AGENT_NAMES.issubset(agent_status)
        and all(agent_status.get(name) == "ok" for name in REQUIRED_AGENT_NAMES)
    )


def _run_has_production_evidence(row: dict[str, Any]) -> bool:
    return (
        _run_has_successful_audited_evidence(row)
        and _run_has_research_activity(row)
        and _data_is_production_evidence(row)
        and _market_source_quality_is_production_evidence(row.get("market_source_quality") or {})
        and _research_source_quality_is_production_evidence(row.get("research_source_quality") or {})
    )


def _parse_run_date(value: Any) -> datetime.date | None:
    try:
        return datetime.strptime(str(value), "%Y%m%d").date()
    except (TypeError, ValueError):
        return None


def _parse_iso_date(value: Any) -> datetime.date | None:
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _longest_consecutive_date_streak(run_dates: list[str]) -> int:
    parsed = sorted({d for d in (_parse_run_date(item) for item in run_dates) if d is not None})
    if not parsed:
        return 0
    longest = current = 1
    prev = parsed[0]
    for item in parsed[1:]:
        if item == prev + timedelta(days=1):
            current += 1
        else:
            current = 1
        longest = max(longest, current)
        prev = item
    return longest


def _load_jsonl(cfg: RunConfig, name: str) -> dict[str, Any]:
    return read_jsonl_records(
        cfg.knowledge_root / name,
        quarantine_path=cfg.knowledge_root / "jsonl_quarantine" / f"{name}.corrupt.jsonl",
    )


def _tail(rows: list[dict[str, Any]], n: int) -> list[dict[str, Any]]:
    return rows[-n:] if len(rows) > n else rows


def evaluate_readiness(cfg: RunConfig) -> dict[str, Any]:
    history_payload = _load_jsonl(cfg, "run_history.jsonl")
    failure_payload = _load_jsonl(cfg, "failure_memory.jsonl")
    research_payload = _load_jsonl(cfg, "research_log.jsonl")
    source_snapshot_payload = _load_jsonl(cfg, "source_snapshots.jsonl")
    data_health_payload = _load_jsonl(cfg, "data_health.jsonl")
    invocation_payload = read_jsonl_records(
        cfg.output_root / "run_daily_invocations.jsonl",
        quarantine_path=cfg.knowledge_root / "jsonl_quarantine" / "run_daily_invocations.jsonl.corrupt.jsonl",
    )
    history = history_payload["records"]
    latest = history[-1] if history else {}
    run_history_latest = read_json(cfg.knowledge_root / "run_history_latest.json", {})
    research_log_latest = read_json(cfg.knowledge_root / "research_log_latest.json", {})
    source_snapshots_latest = read_json(cfg.knowledge_root / "source_snapshots_latest.json", {})
    data_health_latest = read_json(cfg.knowledge_root / "data_health_latest.json", {})
    latest_audit = read_json(cfg.run_dir / "self_audit.json", {})
    latest_state = read_json(cfg.run_dir / "pipeline_state.json", {})
    latest_schedule = read_json(cfg.run_dir / "schedule.json", {})
    latest_gpu_alpha_submission = read_json(cfg.run_dir / "gpu_alpha_submission.json", {})
    gpu_alpha_submission_latest = read_json(cfg.output_root / "gpu_alpha_submission_latest.json", {})
    latest_run_audit = read_json(cfg.run_dir / "run_audit.json", {})
    latest_critique = read_json(cfg.run_dir / "critique.json", {"critiques": []})
    latest_events = read_json(cfg.run_dir / "daily_events.json", {"events": []})
    latest_ideas = read_json(cfg.run_dir / "research_ideas.json", {"ideas": []})
    latest_candidates = read_json(cfg.run_dir / "candidate_factors.json", {"factors": []})
    latest_backtests = read_json(cfg.run_dir / "backtest_results.json", {"results": []})
    latest_next_generation = read_json(cfg.run_dir / "next_generation_factors.json", {"next_generation_factors": []})
    latest_data_health = read_json(cfg.run_dir / "data_health.json", {})
    latest_preflight = read_json(cfg.run_dir / "preflight.json", {})
    latest_dataset_manifest = read_json(cfg.run_dir / "dataset_manifest.json", {})
    artifact_manifest = read_json(cfg.run_dir / "artifact_manifest.json", {"files": []})
    artifact_manifest_latest = read_json(cfg.output_root / "artifact_manifest_latest.json", {"files": []})
    latest_readiness_artifact = read_json(cfg.output_root / "READINESS_REPORT.json", {})
    artifact_verification = verify_manifest(cfg)
    artifact_verification_latest = read_json(cfg.output_root / "artifact_verification_latest.json", {})
    invocation_latest = read_json(cfg.output_root / "run_daily_invocation_latest.json", {})
    factor_db = read_json(cfg.knowledge_root / "factor_database" / "factors.json", {"factors": []})
    repository_deliverables = _repository_deliverables_evidence(cfg)
    expected_run_daily_script = _repository_root() / "run_daily.sh"
    failure_memory = failure_payload["records"]
    research_log = research_payload["records"]
    source_snapshots = source_snapshot_payload["records"]
    data_health_records = data_health_payload["records"]
    invocation_history = invocation_payload["records"]
    jsonl_errors = {
        "run_history.jsonl": history_payload["errors"],
        "failure_memory.jsonl": failure_payload["errors"],
        "research_log.jsonl": research_payload["errors"],
        "source_snapshots.jsonl": source_snapshot_payload["errors"],
        "data_health.jsonl": data_health_payload["errors"],
        "run_daily_invocations.jsonl": invocation_payload["errors"],
    }

    run_dates = [str(row.get("run_date")) for row in history if row.get("run_date")]
    unique_run_dates = sorted(set(run_dates))
    successful_runs = [
        row for row in history
        if _run_has_successful_audited_evidence(row)
    ]
    research_activity_runs = [row for row in history if _run_has_research_activity(row)]
    production_evidence_runs = [row for row in history if _run_has_production_evidence(row)]
    successful_run_dates = sorted({str(row.get("run_date")) for row in successful_runs if row.get("run_date")})
    research_activity_run_dates = sorted(
        {str(row.get("run_date")) for row in research_activity_runs if row.get("run_date")}
    )
    production_evidence_run_dates = sorted(
        {str(row.get("run_date")) for row in production_evidence_runs if row.get("run_date")}
    )
    production_data_artifact_dates = sorted({
        str(row.get("run_date"))
        for row in data_health_records
        if row.get("run_date") and _data_artifact_is_production_evidence(row)
    })
    knowledge_save_dates = sorted({
        str(row.get("run_date"))
        for row in research_log
        if row.get("run_date")
        and _knowledge_save_is_complete(row)
    })
    successful_invocations = [
        row for row in invocation_history
        if _invocation_is_successful_run_daily(row, expected_run_daily_script) and row.get("run_date")
    ]
    successful_invocation_dates = sorted({str(row.get("run_date")) for row in successful_invocations})
    source_snapshot_agents_by_date: dict[str, set[str]] = {}
    for row in source_snapshots:
        run_date = row.get("run_date")
        agent = row.get("agent")
        if (
            run_date
            and agent in REQUIRED_SOURCE_SNAPSHOT_AGENTS
            and _source_snapshot_is_production_evidence(row)
        ):
            source_snapshot_agents_by_date.setdefault(str(run_date), set()).add(str(agent))
    production_source_snapshot_dates = sorted(
        date for date, agents in source_snapshot_agents_by_date.items()
        if REQUIRED_SOURCE_SNAPSHOT_AGENTS.issubset(agents)
    )
    successful_date_streak = _longest_consecutive_date_streak(successful_run_dates)
    production_evidence_date_streak = _longest_consecutive_date_streak(production_evidence_run_dates)
    production_data_artifact_date_streak = _longest_consecutive_date_streak(production_data_artifact_dates)
    knowledge_save_date_streak = _longest_consecutive_date_streak(knowledge_save_dates)
    research_activity_date_streak = _longest_consecutive_date_streak(research_activity_run_dates)
    successful_invocation_date_streak = _longest_consecutive_date_streak(successful_invocation_dates)
    production_source_snapshot_date_streak = _longest_consecutive_date_streak(production_source_snapshot_dates)
    production_dates_have_research_activity = set(production_evidence_run_dates).issubset(
        set(research_activity_run_dates)
    )
    production_dates_have_data_artifacts = set(production_evidence_run_dates).issubset(
        set(production_data_artifact_dates)
    )
    production_dates_have_knowledge_saves = set(production_evidence_run_dates).issubset(set(knowledge_save_dates))
    production_dates_have_invocations = set(production_evidence_run_dates).issubset(set(successful_invocation_dates))
    production_dates_have_source_snapshots = set(production_evidence_run_dates).issubset(
        set(production_source_snapshot_dates)
    )
    agent_status_counts = Counter()
    for row in history:
        for agent, status in (row.get("agent_status") or {}).items():
            agent_status_counts[f"{agent}:{status}"] += 1

    latest_agents = set((latest_state.get("agents_by_name") or {}).keys())
    if not latest_agents:
        latest_agents = {item.get("agent") for item in latest_state.get("agents", []) if item.get("agent")}
    latest_agents |= set((latest.get("agent_status") or {}).keys())
    manifest_files = artifact_manifest.get("files", [])
    manifest_paths = {item.get("relative_path") for item in manifest_files}
    manifest_missing = sorted(REQUIRED_MANIFEST_PATHS - manifest_paths)
    manifest_hashes_ok = bool(manifest_files) and all(item.get("sha256") for item in manifest_files)
    artifact_manifest_matches_run_date = str(artifact_manifest.get("run_date")) == str(cfg.run_date)
    artifact_manifest_latest_matches_current = _artifact_manifest_latest_matches_current(
        artifact_manifest,
        artifact_manifest_latest,
        cfg.run_date,
    )
    artifact_verification_latest_matches_current = _artifact_verification_latest_matches_current(
        artifact_verification,
        artifact_verification_latest,
        cfg.run_date,
    )
    artifact_verification_matches_current_manifest = _artifact_verification_matches_manifest(
        artifact_verification,
        artifact_manifest,
        cfg,
    )
    artifact_manifest_stable_summary = _stable_manifest_summary(artifact_manifest)
    artifact_manifest_latest_stable_summary = _stable_manifest_summary(artifact_manifest_latest)
    latest_data_production_evidence = _data_is_production_evidence(latest)
    latest_data_artifact_production_evidence = _data_artifact_is_production_evidence(data_health_latest)
    latest_market_source_production_evidence = _market_source_quality_is_production_evidence(
        latest.get("market_source_quality") or {}
    )
    latest_research_source_production_evidence = _research_source_quality_is_production_evidence(
        latest.get("research_source_quality") or {}
    )
    latest_self_audit_current = _self_audit_is_current_evidence(cfg, latest_audit)
    latest_self_audit_matches_outputs = _self_audit_matches_current_outputs(
        latest_audit,
        latest_events,
        latest_ideas,
        latest_candidates,
        latest_backtests,
        factor_db,
        latest_data_health,
        latest_preflight,
    )
    latest_self_audit_markdown_matches_json = _self_audit_markdown_matches_json(cfg, latest_audit)
    latest_run_history_matches_outputs = _run_history_matches_current_outputs(
        latest,
        latest_state,
        latest_audit,
        latest_events,
        latest_ideas,
        latest_candidates,
        latest_backtests,
        latest_critique,
        latest_data_health,
    )
    latest_daily_report_current = _daily_report_is_current_evidence(
        cfg,
        latest_events,
        latest_ideas,
        latest_candidates,
        latest_backtests,
        latest_critique,
        latest_data_health,
        latest_preflight,
        latest_audit,
        latest_gpu_alpha_submission,
        latest_readiness_artifact,
    )
    latest_candidate_factor_files_match = _candidate_factor_files_match_payload(cfg, latest_candidates)
    latest_factor_library_matches_candidates = _factor_library_matches_candidates(cfg, latest_candidates)
    latest_candidate_failed_memory_matches = _candidate_failed_memory_matches(
        cfg,
        latest_candidates,
        factor_db,
        failure_memory,
    )
    latest_candidates_avoid_historical_failures = not latest_candidate_failed_memory_matches
    latest_backtest_result_files_match = _backtest_result_files_match_payload(cfg, latest_backtests)
    latest_backtest_dataset_provenance_matches_manifest = _backtest_dataset_provenance_matches_manifest(
        latest_backtests,
        latest_dataset_manifest,
    )
    latest_factor_database_matches_results = _factor_database_matches_latest_results(
        cfg, factor_db, latest_backtests, latest_critique
    )
    latest_failure_analysis_matches_critique = _failure_analysis_matches_critique(cfg, latest_critique)
    latest_next_generation_files_match = _next_generation_files_match_payload(cfg, latest_next_generation)
    latest_research_log_matches_outputs = _research_log_matches_current_outputs(
        cfg,
        research_log_latest,
        latest_events,
        latest_ideas,
        latest_candidates,
        latest_backtests,
        latest_critique,
        latest_next_generation,
        latest_data_health,
    )
    latest_data_health_latest_matches_outputs = _data_health_latest_matches_current_outputs(
        data_health_latest,
        latest_data_health,
        latest_dataset_manifest,
        cfg.run_date,
    )
    latest_source_snapshots_match_outputs = _source_snapshots_match_current_outputs(
        cfg,
        latest_events,
        latest_ideas,
        source_snapshots,
    )
    latest_source_snapshots_latest_matches_outputs = _source_snapshots_latest_matches_current_outputs(
        cfg,
        source_snapshots_latest,
        latest_events,
        latest_ideas,
    )
    latest_research_activity = _run_has_research_activity(latest)
    latest_schedule_daily = _schedule_is_daily_run_daily(latest_schedule, cfg.run_date)
    latest_cron_example_matches_schedule = _cron_example_matches_schedule(cfg, latest_schedule)
    latest_gpu_alpha_submission_current = _gpu_alpha_submission_is_current_evidence(
        cfg,
        latest_gpu_alpha_submission,
        gpu_alpha_submission_latest,
    )
    latest_run_audit_current = _run_audit_is_current_evidence(cfg, latest_run_audit, latest_state)
    killed_factors_have_failure_memory = _killed_factors_have_failure_memory(cfg, latest_critique, failure_memory)
    killed_factor_failure_memory_details_match = _killed_factor_failure_memory_details_match(
        cfg, latest_critique, latest_backtests, latest_next_generation, failure_memory
    )
    latest_pointer_alignment = {
        "run_history_latest": _latest_pointer_matches_current(run_history_latest, cfg.run_date),
        "research_log_latest": _latest_pointer_matches_current(research_log_latest, cfg.run_date),
        "source_snapshots_latest": (
            _latest_pointer_matches_current(source_snapshots_latest, cfg.run_date)
            and source_snapshots_latest.get("agent") in REQUIRED_SOURCE_SNAPSHOT_AGENTS
        ),
        "data_health_latest": _latest_pointer_matches_current(data_health_latest, cfg.run_date),
    }
    latest_pointers_match_run_date = all(latest_pointer_alignment.values())
    invocation_present = bool(invocation_latest)
    invocation_success = (
        _invocation_is_successful_run_daily(invocation_latest, expected_run_daily_script)
    )
    invocation_matches_run_date = str(invocation_latest.get("run_date")) == str(cfg.run_date)
    latest_run_history_timestamp_matches_run_date = _run_record_timestamp_matches_run_date(latest)
    invocation_timestamps_match_run_date = _invocation_timestamps_match_run_date(invocation_latest)

    checks = {
        "run_history_present": len(history) > 0,
        "latest_run_complete": latest.get("pipeline_status") == "complete",
        "latest_run_history_matches_run_date": str(latest.get("run_date")) == str(cfg.run_date),
        "latest_run_history_recorded_at_matches_run_date": latest_run_history_timestamp_matches_run_date,
        "latest_run_history_matches_current_outputs": latest_run_history_matches_outputs,
        "latest_self_audit_pass": latest.get("self_audit_status") == "pass" or latest_audit.get("status") == "pass",
        "latest_self_audit_is_current_evidence": latest_self_audit_current,
        "latest_self_audit_matches_current_outputs": latest_self_audit_matches_outputs,
        "latest_self_audit_markdown_matches_json": latest_self_audit_markdown_matches_json,
        "latest_daily_report_is_current_evidence": latest_daily_report_current,
        "latest_candidate_factor_files_match_payload": latest_candidate_factor_files_match,
        "latest_factor_library_matches_candidates": latest_factor_library_matches_candidates,
        "latest_candidate_factors_avoid_historical_failures": latest_candidates_avoid_historical_failures,
        "latest_backtest_result_files_match_payload": latest_backtest_result_files_match,
        "latest_backtest_dataset_provenance_matches_manifest": latest_backtest_dataset_provenance_matches_manifest,
        "latest_factor_database_matches_backtests": latest_factor_database_matches_results,
        "latest_failure_analysis_matches_critique": latest_failure_analysis_matches_critique,
        "latest_next_generation_files_match_payload": latest_next_generation_files_match,
        "latest_research_log_matches_current_outputs": latest_research_log_matches_outputs,
        "latest_data_health_latest_matches_current_outputs": latest_data_health_latest_matches_outputs,
        "latest_source_snapshots_match_current_outputs": latest_source_snapshots_match_outputs,
        "latest_source_snapshots_latest_matches_current_outputs": latest_source_snapshots_latest_matches_outputs,
        "all_required_agents_seen_latest": REQUIRED_AGENT_NAMES.issubset(latest_agents),
        "knowledge_base_has_factors": len(factor_db.get("factors", [])) > 0,
        "research_log_present": len(research_log) > 0,
        "latest_knowledge_pointers_match_run_date": latest_pointers_match_run_date,
        "latest_schedule_is_daily_run_daily": latest_schedule_daily,
        "latest_cron_example_matches_schedule": latest_cron_example_matches_schedule,
        "latest_gpu_alpha_submission_is_current_evidence": latest_gpu_alpha_submission_current,
        "latest_run_audit_is_current_evidence": latest_run_audit_current,
        "latest_run_has_research_activity": latest_research_activity,
        "has_365_research_activity_runs": len(research_activity_runs) >= 365,
        "has_365_unique_research_activity_dates": len(research_activity_run_dates) >= 365,
        "has_365_consecutive_research_activity_dates": research_activity_date_streak >= 365,
        "production_evidence_dates_have_research_activity": production_dates_have_research_activity,
        "has_365_knowledge_save_dates": len(knowledge_save_dates) >= 365,
        "has_365_consecutive_knowledge_save_dates": knowledge_save_date_streak >= 365,
        "production_evidence_dates_have_knowledge_saves": production_dates_have_knowledge_saves,
        "source_snapshots_present": len(source_snapshots) > 0,
        "failure_memory_present": len(failure_memory) > 0,
        "latest_killed_factors_have_failure_memory": killed_factors_have_failure_memory,
        "latest_killed_factor_failure_memory_details_match": killed_factor_failure_memory_details_match,
        "latest_data_is_production_evidence": latest_data_production_evidence,
        "latest_data_artifact_is_production_evidence": latest_data_artifact_production_evidence,
        "data_health_log_present": len(data_health_records) > 0,
        "has_365_data_artifact_dates": len(production_data_artifact_dates) >= 365,
        "has_365_consecutive_data_artifact_dates": production_data_artifact_date_streak >= 365,
        "production_evidence_dates_have_data_artifacts": production_dates_have_data_artifacts,
        "latest_market_sources_are_production_evidence": latest_market_source_production_evidence,
        "latest_research_sources_are_production_evidence": latest_research_source_production_evidence,
        "artifact_manifest_present": bool(manifest_files),
        "artifact_manifest_matches_run_date": artifact_manifest_matches_run_date,
        "artifact_manifest_latest_matches_current_manifest": artifact_manifest_latest_matches_current,
        "artifact_manifest_required_files_present": not manifest_missing,
        "artifact_manifest_hashes_present": manifest_hashes_ok,
        "artifact_manifest_verification_passed": artifact_verification.get("status") == "pass",
        "artifact_manifest_verification_matches_current_manifest": artifact_verification_matches_current_manifest,
        "artifact_verification_latest_matches_current_verification": artifact_verification_latest_matches_current,
        "readiness_markdown_matches_current_json": True,
        "repository_deliverables_present": repository_deliverables["all_present"],
        "run_daily_invocation_present": invocation_present,
        "run_daily_invocation_success": invocation_success,
        "run_daily_invocation_matches_run_date": invocation_matches_run_date,
        "run_daily_invocation_timestamps_match_run_date": invocation_timestamps_match_run_date,
        "has_365_successful_run_daily_invocations": len(successful_invocations) >= 365,
        "has_365_unique_successful_run_daily_invocation_dates": len(successful_invocation_dates) >= 365,
        "has_365_consecutive_successful_run_daily_invocation_dates": successful_invocation_date_streak >= 365,
        "production_evidence_dates_have_successful_run_daily_invocations": production_dates_have_invocations,
        "has_365_source_snapshot_dates": len(production_source_snapshot_dates) >= 365,
        "has_365_consecutive_source_snapshot_dates": production_source_snapshot_date_streak >= 365,
        "production_evidence_dates_have_source_snapshots": production_dates_have_source_snapshots,
        "no_jsonl_parse_errors": not any(jsonl_errors.values()),
        "has_365_successful_runs": len(successful_runs) >= 365,
        "has_365_production_evidence_runs": len(production_evidence_runs) >= 365,
        "has_365_unique_successful_run_dates": len(successful_run_dates) >= 365,
        "has_365_unique_production_evidence_dates": len(production_evidence_run_dates) >= 365,
        "has_365_consecutive_successful_run_dates": successful_date_streak >= 365,
        "has_365_consecutive_production_evidence_dates": production_evidence_date_streak >= 365,
    }
    blockers = []
    if not checks["has_365_successful_runs"]:
        blockers.append(f"365-day unattended proof missing: {len(successful_runs)}/365 successful audited runs recorded")
    if not checks["has_365_unique_successful_run_dates"]:
        blockers.append(
            f"365 unique successful run dates missing: {len(successful_run_dates)}/365 unique audited dates recorded"
        )
    if not checks["has_365_consecutive_successful_run_dates"]:
        blockers.append(
            f"365 consecutive successful run dates missing: longest streak is {successful_date_streak}/365 days"
        )
    if not checks["all_required_agents_seen_latest"]:
        missing = sorted(REQUIRED_AGENT_NAMES - latest_agents)
        blockers.append(f"latest run missing required agent records: {', '.join(missing)}")
    if not checks["research_log_present"]:
        blockers.append("research log is missing")
    if not checks["latest_knowledge_pointers_match_run_date"]:
        blockers.append(
            "latest knowledge pointer files do not match current run_date: "
            f"{latest_pointer_alignment}"
        )
    if not checks["latest_research_log_matches_current_outputs"]:
        blockers.append("latest research_log_latest.json does not match current daily research outputs")
    if not checks["latest_data_health_latest_matches_current_outputs"]:
        blockers.append("latest data_health_latest.json does not match current data_health.json and dataset_manifest.json")
    if not checks["latest_source_snapshots_match_current_outputs"]:
        blockers.append("latest source snapshot files/jsonl do not match current market/research source outputs")
    if not checks["latest_source_snapshots_latest_matches_current_outputs"]:
        blockers.append("latest source_snapshots_latest.json does not match current market/research source outputs")
    if not checks["latest_killed_factors_have_failure_memory"]:
        killed_ids = sorted({
            str(row.get("factor_id"))
            for row in latest_critique.get("critiques", [])
            if row.get("decision") == "kill" and row.get("factor_id")
        })
        memory_ids = sorted({
            str(row.get("factor_id"))
            for row in failure_memory
            if str(row.get("run_date")) == str(cfg.run_date) and row.get("factor_id")
        })
        blockers.append(
            "latest killed factors are missing same-day failure memory records or failure memory has extra same-day records: "
            f"killed={killed_ids} memory={memory_ids}"
        )
    if not checks["latest_killed_factor_failure_memory_details_match"]:
        blockers.append(
            "latest killed factor failure memory records do not match critique issues, checks, formula_key, and metrics"
        )
    if not checks["latest_schedule_is_daily_run_daily"]:
        blockers.append(
            "latest schedule does not prove daily bash run_daily.sh cadence: "
            f"schedule={latest_schedule}"
        )
    if not checks["latest_cron_example_matches_schedule"]:
        blockers.append(
            "latest cron_example.txt does not match schedule.json cron_line or bash run_daily.sh command"
        )
    if not checks["latest_gpu_alpha_submission_is_current_evidence"]:
        blockers.append(
            "latest gpu_alpha_submission evidence does not prove Slurm-only GPU submission/skip semantics: "
            f"run={latest_gpu_alpha_submission} latest={gpu_alpha_submission_latest}"
        )
    if not checks["latest_run_audit_is_current_evidence"]:
        blockers.append(
            "latest run_audit does not prove current config/lock/retention evidence: "
            f"run_audit={latest_run_audit}"
        )
    if not checks["latest_run_has_research_activity"]:
        blockers.append(
            "latest run lacks active research/backtest evidence: "
            f"counts={latest.get('counts') or {}}"
        )
    if not checks["has_365_research_activity_runs"]:
        blockers.append(
            "365 active research/backtest runs missing: "
            f"{len(research_activity_runs)}/365 runs generated ideas, candidate factors, and backtest results"
        )
    if not checks["has_365_unique_research_activity_dates"]:
        blockers.append(
            "365 unique active research/backtest dates missing: "
            f"{len(research_activity_run_dates)}/365 unique dates have ideas, candidate factors, and backtests"
        )
    if not checks["has_365_consecutive_research_activity_dates"]:
        blockers.append(
            "365 consecutive active research/backtest dates missing: "
            f"longest streak is {research_activity_date_streak}/365 days"
        )
    if not checks["production_evidence_dates_have_research_activity"]:
        missing_research_dates = sorted(set(production_evidence_run_dates) - set(research_activity_run_dates))
        blockers.append(
            "production-evidence run dates without active research/backtest evidence: "
            f"{', '.join(missing_research_dates[:10])}"
        )
    if not checks["has_365_knowledge_save_dates"]:
        blockers.append(
            "365 knowledge-base save dates missing: "
            f"{len(knowledge_save_dates)}/365 complete knowledge saves recorded"
        )
    if not checks["has_365_consecutive_knowledge_save_dates"]:
        blockers.append(
            "365 consecutive knowledge-base save dates missing: "
            f"longest streak is {knowledge_save_date_streak}/365 days"
        )
    if not checks["production_evidence_dates_have_knowledge_saves"]:
        missing_save_dates = sorted(set(production_evidence_run_dates) - set(knowledge_save_dates))
        blockers.append(
            "production-evidence run dates without complete knowledge-base saves: "
            f"{', '.join(missing_save_dates[:10])}"
        )
    if not checks["latest_run_complete"]:
        blockers.append("latest run is not marked complete in run_history")
    if not checks["latest_run_history_matches_run_date"]:
        blockers.append(
            "latest run_history record does not match current run_date: "
            f"latest={latest.get('run_date')} expected={cfg.run_date}"
        )
    if not checks["latest_run_history_recorded_at_matches_run_date"]:
        blockers.append(
            "latest run_history recorded_at does not match its run_date: "
            f"run_date={latest.get('run_date')} recorded_at={latest.get('recorded_at')}"
        )
    if not checks["latest_run_history_matches_current_outputs"]:
        blockers.append("latest run_history record does not match current daily outputs")
    if not checks["latest_self_audit_pass"]:
        blockers.append("latest self-audit is not pass")
    if not checks["latest_self_audit_is_current_evidence"]:
        blockers.append(
            "latest self_audit.json does not prove current complete self-audit evidence: "
            f"run_date={latest_audit.get('run_date')} status={latest_audit.get('status')} "
            f"score={latest_audit.get('score')}"
        )
    if not checks["latest_self_audit_matches_current_outputs"]:
        blockers.append("latest self_audit.json does not match current daily outputs")
    if not checks["latest_self_audit_markdown_matches_json"]:
        blockers.append("latest self_audit.md does not match current self_audit.json")
    if not checks["latest_daily_report_is_current_evidence"]:
        blockers.append("latest daily_report.md does not prove current run summary with required agent/file evidence")
    if not checks["latest_candidate_factor_files_match_payload"]:
        blockers.append("latest candidate_factors files do not match candidate_factors.json")
    if not checks["latest_factor_library_matches_candidates"]:
        blockers.append("latest factor_library files do not match current candidate_factors.json")
    if not checks["latest_candidate_factors_avoid_historical_failures"]:
        blockers.append(
            "latest candidate factors repeat historical failed factor memory: "
            f"{latest_candidate_failed_memory_matches}"
        )
    if not checks["latest_backtest_result_files_match_payload"]:
        blockers.append("latest backtest_results files do not match backtest_results.json")
    if not checks["latest_backtest_dataset_provenance_matches_manifest"]:
        blockers.append("latest backtest dataset provenance does not match current dataset_manifest.json")
    if not checks["latest_factor_database_matches_backtests"]:
        blockers.append("latest factor_database records do not match current backtest/critic outputs")
    if not checks["latest_failure_analysis_matches_critique"]:
        blockers.append("latest failure_analysis.md does not match current critique.json")
    if not checks["latest_next_generation_files_match_payload"]:
        blockers.append("latest next_generation_factors files do not match next_generation_factors.json")
    if not checks["latest_data_is_production_evidence"]:
        blockers.append("latest run does not prove real non-synthetic fresh data")
    if not checks["latest_data_artifact_is_production_evidence"]:
        blockers.append("latest data_health_latest.json does not prove a hashed real data artifact with source detail")
    if not checks["data_health_log_present"]:
        blockers.append("data health JSONL log is missing")
    if not checks["has_365_data_artifact_dates"]:
        blockers.append(
            "365 production-grade data artifact dates missing: "
            f"{len(production_data_artifact_dates)}/365 dates have real fresh data artifacts"
        )
    if not checks["has_365_consecutive_data_artifact_dates"]:
        blockers.append(
            "365 consecutive production-grade data artifact dates missing: "
            f"longest streak is {production_data_artifact_date_streak}/365 days"
        )
    if not checks["production_evidence_dates_have_data_artifacts"]:
        missing_data_dates = sorted(set(production_evidence_run_dates) - set(production_data_artifact_dates))
        blockers.append(
            "production-evidence run dates without production-grade data artifacts: "
            f"{', '.join(missing_data_dates[:10])}"
        )
    if not checks["latest_market_sources_are_production_evidence"]:
        blockers.append("latest market intelligence sources are offline/fallback or missing live evidence")
    if not checks["latest_research_sources_are_production_evidence"]:
        blockers.append("latest research sources are offline/fallback or missing live evidence")
    if not checks["has_365_production_evidence_runs"]:
        blockers.append(
            f"365-day production evidence missing: {len(production_evidence_runs)}/365 runs have live sources and real fresh data"
        )
    if not checks["has_365_unique_production_evidence_dates"]:
        blockers.append(
            "365 unique production-evidence dates missing: "
            f"{len(production_evidence_run_dates)}/365 unique dates have live sources and real fresh data"
        )
    if not checks["has_365_consecutive_production_evidence_dates"]:
        blockers.append(
            "365 consecutive production-evidence dates missing: "
            f"longest streak is {production_evidence_date_streak}/365 days"
        )
    if not checks["no_jsonl_parse_errors"]:
        blockers.append("knowledge_base JSONL files contain parse errors; bad lines were quarantined")
    if not checks["artifact_manifest_present"]:
        blockers.append("artifact manifest is missing")
    elif not checks["artifact_manifest_matches_run_date"]:
        blockers.append(
            "artifact manifest run_date mismatch: "
            f"manifest={artifact_manifest.get('run_date')} expected={cfg.run_date}"
        )
    if not checks["artifact_manifest_latest_matches_current_manifest"]:
        blockers.append("artifact_manifest_latest.json does not match current run artifact_manifest.json")
    if not checks["artifact_manifest_required_files_present"]:
        blockers.append(f"artifact manifest missing required files: {', '.join(manifest_missing)}")
    if not checks["artifact_manifest_hashes_present"]:
        blockers.append("artifact manifest has missing SHA256 hashes")
    if not checks["artifact_manifest_verification_passed"]:
        blockers.append("artifact manifest verification failed")
    if not checks["artifact_manifest_verification_matches_current_manifest"]:
        blockers.append("artifact manifest verification did not check the current artifact_manifest.json")
    if not checks["artifact_verification_latest_matches_current_verification"]:
        blockers.append("artifact_verification_latest.json does not match current run artifact_verification.json")
    if not checks["readiness_markdown_matches_current_json"]:
        blockers.append("READINESS_REPORT.md does not match current READINESS_REPORT.json")
    if not checks["repository_deliverables_present"]:
        blockers.append(
            "repository deliverables are missing or not usable: "
            f"missing_files={repository_deliverables['missing_files']} "
            f"missing_directories={repository_deliverables['missing_directories']} "
            f"unwritable_directories={repository_deliverables['unwritable_directories']} "
            f"missing_readme_snippets={repository_deliverables['missing_readme_snippets']} "
            f"readme_documents_audited_readiness={repository_deliverables['readme_documents_audited_readiness']} "
            f"run_daily_executable={repository_deliverables['run_daily_executable']} "
            f"run_daily_uses_audited_entrypoint={repository_deliverables['run_daily_uses_audited_entrypoint']}"
        )
    if not checks["run_daily_invocation_present"]:
        blockers.append("run_daily shell invocation record is missing")
    elif not checks["run_daily_invocation_success"]:
        blockers.append(
            "run_daily shell invocation did not succeed: "
            f"status={invocation_latest.get('status')} exit_code={invocation_latest.get('exit_code')}"
        )
    elif not checks["run_daily_invocation_matches_run_date"]:
        blockers.append(
            "run_daily shell invocation run_date mismatch: "
            f"latest={invocation_latest.get('run_date')} expected={cfg.run_date}"
        )
    if not checks["run_daily_invocation_timestamps_match_run_date"]:
        blockers.append(
            "run_daily shell invocation timestamps do not match invocation run_date or finish before start: "
            f"run_date={invocation_latest.get('run_date')} "
            f"started_at={invocation_latest.get('started_at')} "
            f"finished_at={invocation_latest.get('finished_at')}"
        )
    if not checks["has_365_successful_run_daily_invocations"]:
        blockers.append(
            "365 successful run_daily shell invocations missing: "
            f"{len(successful_invocations)}/365 successful invocations recorded"
        )
    if not checks["has_365_unique_successful_run_daily_invocation_dates"]:
        blockers.append(
            "365 unique successful run_daily invocation dates missing: "
            f"{len(successful_invocation_dates)}/365 unique invocation dates recorded"
        )
    if not checks["has_365_consecutive_successful_run_daily_invocation_dates"]:
        blockers.append(
            "365 consecutive successful run_daily invocation dates missing: "
            f"longest streak is {successful_invocation_date_streak}/365 days"
        )
    if not checks["production_evidence_dates_have_successful_run_daily_invocations"]:
        missing_invocation_dates = sorted(set(production_evidence_run_dates) - set(successful_invocation_dates))
        blockers.append(
            "production-evidence run dates without successful run_daily invocations: "
            f"{', '.join(missing_invocation_dates[:10])}"
        )
    if not checks["has_365_source_snapshot_dates"]:
        blockers.append(
            "365 production-grade source snapshot dates missing: "
            f"{len(production_source_snapshot_dates)}/365 dates have market and research snapshots"
        )
    if not checks["has_365_consecutive_source_snapshot_dates"]:
        blockers.append(
            "365 consecutive production-grade source snapshot dates missing: "
            f"longest streak is {production_source_snapshot_date_streak}/365 days"
        )
    if not checks["production_evidence_dates_have_source_snapshots"]:
        missing_snapshot_dates = sorted(set(production_evidence_run_dates) - set(production_source_snapshot_dates))
        blockers.append(
            "production-evidence run dates without production-grade source snapshots: "
            f"{', '.join(missing_snapshot_dates[:10])}"
        )

    readiness_score = round(sum(1 for ok in checks.values() if ok) / len(checks), 4)
    status = "production_ready" if all(checks.values()) else "not_production_ready"
    self_audit_current_counts = _current_output_counts(
        latest_events,
        latest_ideas,
        latest_candidates,
        latest_backtests,
        factor_db,
    )
    return {
        "agent": "readiness_report",
        "run_date": cfg.run_date,
        "status": status,
        "readiness_score": readiness_score,
        "checks": checks,
        "blockers": blockers,
        "history": {
            "total_records": len(history),
            "unique_run_dates": len(unique_run_dates),
            "first_run_date": unique_run_dates[0] if unique_run_dates else None,
            "latest_run_date": unique_run_dates[-1] if unique_run_dates else None,
            "latest_matches_current_outputs": latest_run_history_matches_outputs,
            "latest_recorded_at_matches_run_date": latest_run_history_timestamp_matches_run_date,
            "latest_counts": latest.get("counts", {}),
            "current_counts": {
                "events": len(latest_events.get("events") or []),
                "ideas": len(latest_ideas.get("ideas") or []),
                "candidate_factors": len(latest_candidates.get("factors") or []),
                "backtest_results": len(latest_backtests.get("results") or []),
                "raw_candidates": sum(
                    1 for row in latest_backtests.get("results", []) if row.get("decision") == "raw_candidate"
                ),
                "promoted": sum(1 for row in latest_critique.get("critiques", []) if row.get("decision") == "promote"),
                "killed": sum(1 for row in latest_critique.get("critiques", []) if row.get("decision") == "kill"),
            },
            "successful_audited_runs": len(successful_runs),
            "research_activity_runs": len(research_activity_runs),
            "production_evidence_runs": len(production_evidence_runs),
            "unique_successful_run_dates": len(successful_run_dates),
            "unique_research_activity_dates": len(research_activity_run_dates),
            "unique_production_evidence_dates": len(production_evidence_run_dates),
            "longest_successful_date_streak_days": successful_date_streak,
            "longest_research_activity_date_streak_days": research_activity_date_streak,
            "longest_production_evidence_date_streak_days": production_evidence_date_streak,
            "production_data_artifact_dates": len(production_data_artifact_dates),
            "longest_data_artifact_date_streak_days": production_data_artifact_date_streak,
            "knowledge_save_dates": len(knowledge_save_dates),
            "longest_knowledge_save_date_streak_days": knowledge_save_date_streak,
            "production_source_snapshot_dates": len(production_source_snapshot_dates),
            "longest_source_snapshot_date_streak_days": production_source_snapshot_date_streak,
            "recent_runs": _tail(history, 5),
        },
        "knowledge_base": {
            "factor_records": len(factor_db.get("factors", [])),
            "failure_memory_records": len(failure_memory),
            "research_log_records": len(research_log),
            "latest_pointer_alignment": latest_pointer_alignment,
            "latest_pointers": {
                "run_history_latest": {
                    "present": bool(run_history_latest),
                    "run_date": run_history_latest.get("run_date"),
                },
                "research_log_latest": {
                    "present": bool(research_log_latest),
                    "run_date": research_log_latest.get("run_date"),
                },
                "source_snapshots_latest": {
                    "present": bool(source_snapshots_latest),
                    "run_date": source_snapshots_latest.get("run_date"),
                    "agent": source_snapshots_latest.get("agent"),
                },
                "data_health_latest": {
                    "present": bool(data_health_latest),
                    "run_date": data_health_latest.get("run_date"),
                },
            },
            "latest_killed_factor_ids": sorted({
                str(row.get("factor_id"))
                for row in latest_critique.get("critiques", [])
                if row.get("decision") == "kill" and row.get("factor_id")
            }),
            "same_day_failure_memory_factor_ids": sorted({
                str(row.get("factor_id"))
                for row in failure_memory
                if str(row.get("run_date")) == str(cfg.run_date) and row.get("factor_id")
            }),
            "failure_memory_detail_match": killed_factor_failure_memory_details_match,
            "research_activity_runs": len(research_activity_runs),
            "research_activity_dates": len(research_activity_run_dates),
            "knowledge_save_dates": len(knowledge_save_dates),
            "source_snapshot_records": len(source_snapshots),
            "production_source_snapshot_dates": len(production_source_snapshot_dates),
            "data_health_records": len(data_health_records),
            "production_data_artifact_dates": len(production_data_artifact_dates),
        },
        "jsonl_integrity": {
            "error_counts": {name: len(errors) for name, errors in jsonl_errors.items()},
            "quarantine_dir": str(cfg.knowledge_root / "jsonl_quarantine"),
            "errors": jsonl_errors,
        },
        "repository_deliverables": repository_deliverables,
        "artifact_manifest": {
            "file_count": len(manifest_files),
            "run_date": artifact_manifest.get("run_date"),
            "latest_run_date": artifact_manifest_latest.get("run_date"),
            "latest_matches_current_manifest": artifact_manifest_latest_matches_current,
            "latest_file_count": artifact_manifest_latest.get("file_count"),
            "latest_total_size_bytes": artifact_manifest_latest.get("total_size_bytes"),
            "stable_file_count": artifact_manifest_stable_summary["file_count"],
            "stable_total_size_bytes": artifact_manifest_stable_summary["total_size_bytes"],
            "latest_stable_file_count": artifact_manifest_latest_stable_summary["file_count"],
            "latest_stable_total_size_bytes": artifact_manifest_latest_stable_summary["total_size_bytes"],
            "mutable_readiness_paths": sorted(MUTABLE_READINESS_PATHS),
            "required_paths": sorted(REQUIRED_MANIFEST_PATHS),
            "missing_required_paths": manifest_missing,
            "hashes_present": manifest_hashes_ok,
            "verification": {
                "status": artifact_verification.get("status"),
                "generated_at": artifact_verification.get("generated_at"),
                "manifest_generated_at": artifact_verification.get("manifest_generated_at"),
                "matches_current_manifest": artifact_verification_matches_current_manifest,
                "checked_file_count": artifact_verification.get("checked_file_count"),
                "skipped_file_count": artifact_verification.get("skipped_file_count"),
                "missing_file_count": artifact_verification.get("missing_file_count"),
                "hash_mismatch_count": artifact_verification.get("hash_mismatch_count"),
                "missing_hash_count": artifact_verification.get("missing_hash_count"),
                "latest_matches_current_verification": artifact_verification_latest_matches_current,
                "latest_status": artifact_verification_latest.get("status"),
                "latest_generated_at": artifact_verification_latest.get("generated_at"),
                "latest_manifest_generated_at": artifact_verification_latest.get("manifest_generated_at"),
                "missing_files": artifact_verification.get("missing_files", []),
                "hash_mismatches": artifact_verification.get("hash_mismatches", []),
                "skipped_files": artifact_verification.get("skipped_files", []),
            },
        },
        "run_daily_invocation": {
            "present": invocation_present,
            "status": invocation_latest.get("status"),
            "exit_code": invocation_latest.get("exit_code"),
            "run_date": invocation_latest.get("run_date"),
            "started_at": invocation_latest.get("started_at"),
            "finished_at": invocation_latest.get("finished_at"),
            "duration_sec": invocation_latest.get("duration_sec"),
            "host": invocation_latest.get("host"),
            "pid": invocation_latest.get("pid"),
            "shell_entrypoint": invocation_latest.get("shell_entrypoint"),
            "entrypoint_script": invocation_latest.get("entrypoint_script"),
            "entrypoint_script_exists": invocation_latest.get("entrypoint_script_exists"),
            "entrypoint_command": invocation_latest.get("entrypoint_command"),
            "expected_entrypoint_script": str(expected_run_daily_script),
            "config_loaded": invocation_latest.get("config_loaded"),
            "timestamps_match_run_date": invocation_timestamps_match_run_date,
            "history_records": len(invocation_history),
            "successful_invocations": len(successful_invocations),
            "unique_successful_invocation_dates": len(successful_invocation_dates),
            "longest_successful_invocation_date_streak_days": successful_invocation_date_streak,
            "production_evidence_dates_without_invocations": sorted(
                set(production_evidence_run_dates) - set(successful_invocation_dates)
            ),
        },
        "gpu_alpha_submission": {
            "present": bool(latest_gpu_alpha_submission),
            "latest_present": bool(gpu_alpha_submission_latest),
            "current_evidence": latest_gpu_alpha_submission_current,
            "status": latest_gpu_alpha_submission.get("status"),
            "skip_reason": latest_gpu_alpha_submission.get("skip_reason"),
            "submitted": latest_gpu_alpha_submission.get("submitted"),
            "job_id": latest_gpu_alpha_submission.get("job_id"),
            "script": latest_gpu_alpha_submission.get("script"),
            "script_exists": latest_gpu_alpha_submission.get("script_exists"),
            "sbatch_path": latest_gpu_alpha_submission.get("sbatch_path"),
            "command": latest_gpu_alpha_submission.get("command"),
            "returncode": latest_gpu_alpha_submission.get("returncode"),
            "env": latest_gpu_alpha_submission.get("env") or {},
            "latest_status": gpu_alpha_submission_latest.get("status"),
            "latest_job_id": gpu_alpha_submission_latest.get("job_id"),
        },
        "schedule_evidence": {
            "present": bool(latest_schedule),
            "run_date": latest_schedule.get("run_date"),
            "cadence": latest_schedule.get("cadence"),
            "cron_line": latest_schedule.get("cron_line"),
            "command": latest_schedule.get("command"),
            "script_path": latest_schedule.get("script_path"),
            "script_exists": latest_schedule.get("script_exists"),
            "log_path": latest_schedule.get("log_path"),
            "log_parent": latest_schedule.get("log_parent"),
            "log_parent_exists": latest_schedule.get("log_parent_exists"),
            "log_parent_writable": latest_schedule.get("log_parent_writable"),
            "shell_entrypoint": latest_schedule.get("shell_entrypoint"),
            "uses_run_daily_sh": latest_schedule.get("uses_run_daily_sh"),
            "installed_automatically": latest_schedule.get("installed_automatically"),
            "install_required": latest_schedule.get("install_required"),
            "daily_run_daily": latest_schedule_daily,
            "cron_example_present": (cfg.run_dir / "cron_example.txt").exists(),
            "cron_example_path": str(cfg.run_dir / "cron_example.txt"),
            "cron_example_matches_schedule": latest_cron_example_matches_schedule,
        },
        "run_audit_evidence": {
            "present": bool(latest_run_audit),
            "run_date": latest_run_audit.get("run_date"),
            "current_config_lock_retention": latest_run_audit_current,
            "state_matches_pipeline_state": _run_audit_state_matches_pipeline_state(
                latest_run_audit.get("state") or {},
                latest_state,
            ),
            "audit_agent_count": len((latest_run_audit.get("state") or {}).get("agents") or []),
            "pipeline_agent_count": len(latest_state.get("agents") or []),
            "config": latest_run_audit.get("config") or {},
            "lock": latest_run_audit.get("lock") or {},
            "state_status": (latest_run_audit.get("state") or {}).get("status"),
            "retention": (latest_run_audit.get("state") or {}).get("retention") or {},
        },
        "source_snapshot_evidence": {
            "required_agents": sorted(REQUIRED_SOURCE_SNAPSHOT_AGENTS),
            "required_market_source_kinds": sorted(REQUIRED_MARKET_SOURCE_KINDS),
            "required_research_source_kinds": sorted(REQUIRED_RESEARCH_SOURCE_KINDS),
            "matches_current_outputs": latest_source_snapshots_match_outputs,
            "latest_matches_current_outputs": latest_source_snapshots_latest_matches_outputs,
            "latest_agent": source_snapshots_latest.get("agent"),
            "latest_item_count": source_snapshots_latest.get("item_count"),
            "current_run_snapshot_files": {
                agent: (cfg.run_dir / "source_snapshots" / f"{agent}.json").exists()
                for agent in sorted(REQUIRED_SOURCE_SNAPSHOT_AGENTS)
            },
            "same_day_snapshot_agents": sorted({
                str(row.get("agent"))
                for row in source_snapshots
                if str(row.get("run_date")) == str(cfg.run_date) and row.get("agent")
            }),
            "production_source_snapshot_dates": len(production_source_snapshot_dates),
            "longest_source_snapshot_date_streak_days": production_source_snapshot_date_streak,
            "production_evidence_dates_without_source_snapshots": sorted(
                set(production_evidence_run_dates) - set(production_source_snapshot_dates)
            ),
        },
        "data_artifact_evidence": {
            "data_health_records": len(data_health_records),
            "latest_is_production_evidence": latest_data_artifact_production_evidence,
            "production_data_artifact_dates": len(production_data_artifact_dates),
            "longest_data_artifact_date_streak_days": production_data_artifact_date_streak,
            "production_evidence_dates_without_data_artifacts": sorted(
                set(production_evidence_run_dates) - set(production_data_artifact_dates)
            ),
        },
        "data_latest_evidence": {
            "matches_current_outputs": latest_data_health_latest_matches_outputs,
            "latest_rows": (data_health_latest.get("data_health") or {}).get("rows"),
            "current_rows": latest_data_health.get("rows"),
            "latest_stocks": (data_health_latest.get("data_health") or {}).get("stocks"),
            "current_stocks": latest_data_health.get("stocks"),
            "latest_dates": (data_health_latest.get("data_health") or {}).get("dates"),
            "current_dates": latest_data_health.get("dates"),
            "latest_status": (data_health_latest.get("data_health") or {}).get("status"),
            "current_status": latest_data_health.get("status"),
            "latest_dataset_sha256": (data_health_latest.get("dataset_manifest") or {}).get("dataset_sha256"),
            "current_dataset_sha256": latest_dataset_manifest.get("dataset_sha256"),
            "latest_data_source_detail": data_health_latest.get("data_source_detail")
            or (data_health_latest.get("data_health") or {}).get("data_source_detail")
            or (data_health_latest.get("dataset_manifest") or {}).get("data_source_detail"),
        },
        "knowledge_save_evidence": {
            "research_log_records": len(research_log),
            "research_activity_runs": len(research_activity_runs),
            "research_activity_dates": len(research_activity_run_dates),
            "longest_research_activity_date_streak_days": research_activity_date_streak,
            "production_evidence_dates_without_research_activity": sorted(
                set(production_evidence_run_dates) - set(research_activity_run_dates)
            ),
            "knowledge_save_dates": len(knowledge_save_dates),
            "longest_knowledge_save_date_streak_days": knowledge_save_date_streak,
            "latest_factor_database_write": research_log_latest.get("factor_database_write") or {},
            "production_evidence_dates_without_knowledge_saves": sorted(
                set(production_evidence_run_dates) - set(knowledge_save_dates)
            ),
        },
        "research_log_evidence": {
            "matches_current_outputs": latest_research_log_matches_outputs,
            "events_count": (research_log_latest.get("events") or {}).get("count"),
            "current_events_count": len(latest_events.get("events") or []),
            "event_top_titles": (research_log_latest.get("events") or {}).get("top_titles") or [],
            "current_event_top_titles": [
                item.get("title") for item in (latest_events.get("events") or [])[:5]
            ],
            "idea_count": (research_log_latest.get("research") or {}).get("idea_count"),
            "current_idea_count": len(latest_ideas.get("ideas") or []),
            "idea_ids": (research_log_latest.get("research") or {}).get("idea_ids") or [],
            "current_idea_ids": [
                str(item.get("idea_id"))
                for item in latest_ideas.get("ideas", [])
                if item.get("idea_id")
            ],
            "context_items": (research_log_latest.get("research") or {}).get("context_items"),
            "current_context_items": len(latest_ideas.get("research_context") or []),
            "candidate_count": (research_log_latest.get("factor_design") or {}).get("candidate_count"),
            "current_candidate_count": len(latest_candidates.get("factors") or []),
            "candidate_formula_keys": (research_log_latest.get("factor_design") or {}).get("formula_keys") or [],
            "current_candidate_formula_keys": [
                str(item.get("formula_key"))
                for item in latest_candidates.get("factors", [])
                if item.get("formula_key")
            ],
            "candidate_skipped_failed_count": (
                research_log_latest.get("factor_design") or {}
            ).get("skipped_failed_count"),
            "current_candidate_skipped_failed_count": len(latest_candidates.get("skipped_factors") or []),
            "result_count": (research_log_latest.get("backtest") or {}).get("result_count"),
            "current_result_count": len(latest_backtests.get("results") or []),
            "backtest_dataset_sha256": (
                (research_log_latest.get("backtest") or {}).get("dataset_provenance") or {}
            ).get("dataset_sha256"),
            "current_backtest_dataset_sha256": (
                latest_backtests.get("dataset_provenance") or {}
            ).get("dataset_sha256"),
            "critique_count": (research_log_latest.get("critic") or {}).get("critique_count"),
            "current_critique_count": len(latest_critique.get("critiques") or []),
            "critic_promoted": (research_log_latest.get("critic") or {}).get("promoted"),
            "current_critic_promoted": sum(
                1 for item in latest_critique.get("critiques", []) if item.get("decision") == "promote"
            ),
            "critic_killed": (research_log_latest.get("critic") or {}).get("killed"),
            "current_critic_killed": sum(
                1 for item in latest_critique.get("critiques", []) if item.get("decision") == "kill"
            ),
            "critic_issue_counts": (research_log_latest.get("critic") or {}).get("issue_counts") or {},
            "current_critic_issue_counts": dict(Counter(
                issue
                for row in latest_critique.get("critiques", [])
                for issue in row.get("issues", [])
            )),
            "next_generation_count": (research_log_latest.get("evolution") or {}).get("next_generation_count"),
            "current_next_generation_count": len(latest_next_generation.get("next_generation_factors") or []),
            "evolution_skipped_failed_count": (
                research_log_latest.get("evolution") or {}
            ).get("skipped_failed_count"),
            "current_evolution_skipped_failed_count": len(
                latest_next_generation.get("skipped_evolution_factors") or []
            ),
            "evolution_skipped_factor_ids": (
                research_log_latest.get("evolution") or {}
            ).get("skipped_factor_ids") or [],
            "current_evolution_skipped_factor_ids": [
                item.get("factor_id")
                for item in latest_next_generation.get("skipped_evolution_factors", [])
                if item.get("factor_id")
            ],
            "result_factor_ids": (research_log_latest.get("backtest") or {}).get("result_factor_ids", []),
        },
        "agent_status_counts": dict(sorted(agent_status_counts.items())),
        "latest_self_audit": {
            "status": latest_audit.get("status"),
            "score": latest_audit.get("score"),
            "run_date": latest_audit.get("run_date"),
            "current_complete_evidence": latest_self_audit_current,
            "matches_current_outputs": latest_self_audit_matches_outputs,
            "markdown_matches_json": latest_self_audit_markdown_matches_json,
            "required_checks": sorted(REQUIRED_SELF_AUDIT_CHECKS),
            "missing_required_checks": sorted(REQUIRED_SELF_AUDIT_CHECKS - set((latest_audit.get("checks") or {}).keys())),
            "counts": latest_audit.get("counts", {}),
            "current_counts": self_audit_current_counts,
            "preflight": latest_audit.get("preflight", {}),
            "current_preflight": latest_preflight,
            "data_freshness": latest_audit.get("data_freshness", {}),
            "current_data_freshness": latest_data_health.get("freshness", {}),
            "source_mode": latest_audit.get("source_mode"),
            "market_source_quality": latest_audit.get("market_source_quality", {}),
            "current_market_source_quality": latest_events.get("source_quality", {}),
            "research_source_quality": latest_audit.get("research_source_quality", {}),
            "current_research_source_quality": latest_ideas.get("source_quality", {}),
        },
        "daily_report_evidence": {
            "present": (cfg.run_dir / "daily_report.md").exists(),
            "path": str(cfg.run_dir / "daily_report.md"),
            "current_complete_evidence": latest_daily_report_current,
            "required_agents": sorted(REQUIRED_DAILY_REPORT_AGENTS),
            "required_snippets": sorted(REQUIRED_DAILY_REPORT_SNIPPETS),
            "readiness_artifact_status": latest_readiness_artifact.get("status"),
            "readiness_artifact_score": latest_readiness_artifact.get("readiness_score"),
            "readiness_artifact_blocker_count": len(latest_readiness_artifact.get("blockers") or []),
        },
        "factor_library_evidence": {
            "candidate_count": len(latest_candidates.get("factors") or []),
            "candidate_files_root": str(cfg.run_dir / "candidate_factors"),
            "candidate_files_match_payload": latest_candidate_factor_files_match,
            "factor_library_root": str(cfg.factor_library),
            "matches_current_candidates": latest_factor_library_matches_candidates,
            "historical_failed_key_count": len(_historical_failed_factor_keys(cfg, factor_db, failure_memory)),
            "candidate_failed_memory_matches": latest_candidate_failed_memory_matches,
            "candidates_avoid_historical_failures": latest_candidates_avoid_historical_failures,
            "candidate_factor_ids": [
                str(item.get("factor_id"))
                for item in latest_candidates.get("factors", [])
                if item.get("factor_id")
            ],
        },
        "factor_database_evidence": {
            "latest_backtest_result_count": len(latest_backtests.get("results") or []),
            "backtest_result_files_root": str(cfg.run_dir / "backtest_results"),
            "backtest_result_files_match_payload": latest_backtest_result_files_match,
            "backtest_dataset_provenance_matches_manifest": latest_backtest_dataset_provenance_matches_manifest,
            "backtest_dataset_sha256": (latest_backtests.get("dataset_provenance") or {}).get("dataset_sha256"),
            "current_dataset_sha256": latest_dataset_manifest.get("dataset_sha256"),
            "backtest_dataset_size_bytes": (
                latest_backtests.get("dataset_provenance") or {}
            ).get("dataset_size_bytes"),
            "current_dataset_size_bytes": latest_dataset_manifest.get("dataset_size_bytes"),
            "same_day_factor_records": len([
                item for item in factor_db.get("factors", [])
                if str(item.get("run_date")) == str(cfg.run_date)
            ]),
            "same_day_factor_ids": [
                str(item.get("factor_id"))
                for item in factor_db.get("factors", [])
                if str(item.get("run_date")) == str(cfg.run_date) and item.get("factor_id")
            ],
            "matches_latest_backtests": latest_factor_database_matches_results,
            "matched_fields": [
                "decision",
                "issues",
                "name",
                "formula",
                "formula_key",
                "expression",
                "horizon_days",
                "rankic_mean",
                "rankic_ir",
                "rankic_positive_frac",
                "portfolio",
                "long_short",
                "cost_sensitivity",
                "rows",
                "dates",
                "decision_note",
            ],
            "latest_backtest_factor_ids": [
                str(item.get("factor_id"))
                for item in latest_backtests.get("results", [])
                if item.get("factor_id")
            ],
        },
        "failure_analysis_evidence": {
            "present": (cfg.run_dir / "failure_analysis.md").exists(),
            "path": str(cfg.run_dir / "failure_analysis.md"),
            "matches_current_critique": latest_failure_analysis_matches_critique,
            "critique_count": len(latest_critique.get("critiques") or []),
            "critique_factor_ids": [
                str(item.get("factor_id"))
                for item in latest_critique.get("critiques", [])
                if item.get("factor_id")
            ],
        },
        "next_generation_evidence": {
            "next_generation_count": len(latest_next_generation.get("next_generation_factors") or []),
            "matches_payload_files": latest_next_generation_files_match,
            "next_factor_ids": [
                str(item.get("factor_id"))
                for item in latest_next_generation.get("next_generation_factors", [])
                if item.get("factor_id")
            ],
        },
        "latest_production_evidence": {
            "data_source_mode": latest.get("data_source_mode"),
            "data_freshness": latest.get("data_freshness", {}),
            "market_source_quality": latest.get("market_source_quality", {}),
            "research_source_quality": latest.get("research_source_quality", {}),
            "required_market_source_kinds": sorted(REQUIRED_MARKET_SOURCE_KINDS),
            "required_research_source_kinds": sorted(REQUIRED_RESEARCH_SOURCE_KINDS),
            "counts": latest.get("counts", {}),
        },
    }


def _format_readiness_score(payload: dict[str, Any]) -> str:
    return f"{payload['readiness_score']:.2f}"


def render_readiness_markdown(cfg: RunConfig, payload: dict[str, Any]) -> str:
    lines = [
        "# Quant Research System Readiness Report",
        "",
        f"Run date: {cfg.run_date}",
        f"Status: {payload['status']}",
        f"Readiness score: {_format_readiness_score(payload)}",
        "",
        "## Checks",
        "",
    ]
    for name, ok in payload["checks"].items():
        lines.append(f"- {name}: {'ok' if ok else 'fail'}")
    lines += ["", "## Blockers", ""]
    if payload["blockers"]:
        lines.extend(f"- {item}" for item in payload["blockers"])
    else:
        lines.append("- none")
    history = payload["history"]
    kb = payload["knowledge_base"]
    integrity = payload["jsonl_integrity"]
    deliverables = payload["repository_deliverables"]
    manifest = payload["artifact_manifest"]
    invocation = payload["run_daily_invocation"]
    gpu_submission = payload["gpu_alpha_submission"]
    source_snapshot_evidence = payload["source_snapshot_evidence"]
    schedule_evidence = payload["schedule_evidence"]
    data_artifact_evidence = payload["data_artifact_evidence"]
    knowledge_save_evidence = payload["knowledge_save_evidence"]
    lines += [
        "",
        "## Evidence",
        "",
        f"- total run history records: {history['total_records']}",
        f"- unique run dates: {history['unique_run_dates']}",
        f"- successful audited runs: {history['successful_audited_runs']}",
        f"- active research/backtest runs: {history['research_activity_runs']}",
        f"- production evidence runs: {history['production_evidence_runs']}",
        f"- unique successful run dates: {history['unique_successful_run_dates']}",
        f"- unique active research/backtest dates: {history['unique_research_activity_dates']}",
        f"- unique production evidence dates: {history['unique_production_evidence_dates']}",
        f"- longest successful date streak days: {history['longest_successful_date_streak_days']}",
        f"- longest active research/backtest date streak days: {history['longest_research_activity_date_streak_days']}",
        f"- longest production evidence date streak days: {history['longest_production_evidence_date_streak_days']}",
        f"- first run date: {history['first_run_date']}",
        f"- latest run date: {history['latest_run_date']}",
        f"- latest run_history recorded_at matches run_date: {history['latest_recorded_at_matches_run_date']}",
        f"- factor records: {kb['factor_records']}",
        f"- research log records: {kb['research_log_records']}",
        f"- knowledge save dates: {knowledge_save_evidence['knowledge_save_dates']}",
        f"- longest knowledge save date streak days: {knowledge_save_evidence['longest_knowledge_save_date_streak_days']}",
        f"- source snapshot records: {kb['source_snapshot_records']}",
        f"- production-grade source snapshot dates: {source_snapshot_evidence['production_source_snapshot_dates']}",
        f"- longest source snapshot date streak days: {source_snapshot_evidence['longest_source_snapshot_date_streak_days']}",
        f"- data health records: {data_artifact_evidence['data_health_records']}",
        f"- production-grade data artifact dates: {data_artifact_evidence['production_data_artifact_dates']}",
        f"- longest data artifact date streak days: {data_artifact_evidence['longest_data_artifact_date_streak_days']}",
        f"- failure memory records: {kb['failure_memory_records']}",
        f"- jsonl parse errors: {sum(integrity['error_counts'].values())}",
        f"- jsonl quarantine dir: {integrity['quarantine_dir']}",
        f"- repository deliverables present: {deliverables.get('all_present')}",
        f"- repository missing files: {', '.join(deliverables.get('missing_files') or []) if deliverables.get('missing_files') else 'none'}",
        f"- repository missing directories: {', '.join(deliverables.get('missing_directories') or []) if deliverables.get('missing_directories') else 'none'}",
        f"- README documents audited readiness: {deliverables.get('readme_documents_audited_readiness')}",
        f"- gpu alpha submission: {gpu_submission.get('status')} job={gpu_submission.get('job_id')} current={gpu_submission.get('current_evidence')}",
        f"- README missing snippets: {', '.join(deliverables.get('missing_readme_snippets') or []) if deliverables.get('missing_readme_snippets') else 'none'}",
        f"- run_daily executable: {deliverables.get('run_daily_executable')}",
        f"- run_daily uses audited entrypoint: {deliverables.get('run_daily_uses_audited_entrypoint')}",
        f"- artifact manifest files: {manifest['file_count']}",
        f"- artifact manifest missing required paths: {', '.join(manifest['missing_required_paths']) if manifest['missing_required_paths'] else 'none'}",
        f"- artifact manifest verification: {(manifest.get('verification') or {}).get('status')}",
        f"- artifact manifest verification matches current manifest: {(manifest.get('verification') or {}).get('matches_current_manifest')}",
        f"- artifact verification latest matches current verification: {(manifest.get('verification') or {}).get('latest_matches_current_verification')}",
        f"- artifact verification manifest generated at: {(manifest.get('verification') or {}).get('manifest_generated_at')}",
        f"- artifact manifest hash mismatches: {(manifest.get('verification') or {}).get('hash_mismatch_count')}",
        f"- artifact manifest missing files: {(manifest.get('verification') or {}).get('missing_file_count')}",
        f"- run_daily invocation present: {invocation.get('present')}",
        f"- run_daily invocation status: {invocation.get('status')}",
        f"- run_daily invocation timestamps match run_date: {invocation.get('timestamps_match_run_date')}",
        f"- run_daily invocation exit_code: {invocation.get('exit_code')}",
        f"- run_daily invocation run_date: {invocation.get('run_date')}",
        f"- run_daily expected entrypoint script: {invocation.get('expected_entrypoint_script')}",
        f"- successful run_daily invocations: {invocation.get('successful_invocations')}",
        f"- unique successful run_daily invocation dates: {invocation.get('unique_successful_invocation_dates')}",
        f"- longest successful run_daily invocation date streak days: {invocation.get('longest_successful_invocation_date_streak_days')}",
        f"- schedule cadence: {schedule_evidence.get('cadence')}",
        f"- schedule daily run_daily: {schedule_evidence.get('daily_run_daily')}",
        f"- schedule cron line: {schedule_evidence.get('cron_line')}",
        "",
        "## Latest Self Audit",
        "",
    ]
    audit = payload["latest_self_audit"]
    lines += [
        f"- status: {audit.get('status')}",
        f"- score: {audit.get('score')}",
        f"- source_mode: {audit.get('source_mode')}",
        f"- data_freshness_status: {(audit.get('data_freshness') or {}).get('status')}",
    ]
    return "\n".join(lines) + "\n"


def write_readiness_markdown(cfg: RunConfig, payload: dict[str, Any]) -> None:
    path = cfg.output_root / "READINESS_REPORT.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_readiness_markdown(cfg, payload), encoding="utf-8")


def _readiness_markdown_matches_payload(markdown: str, cfg: RunConfig, payload: dict[str, Any]) -> bool:
    required_lines = [
        f"Run date: {cfg.run_date}",
        f"Status: {payload['status']}",
        f"Readiness score: {_format_readiness_score(payload)}",
    ]
    required_lines.extend(
        f"- {name}: {'ok' if ok else 'fail'}"
        for name, ok in (payload.get("checks") or {}).items()
    )
    blockers = payload.get("blockers") or []
    if blockers:
        required_lines.extend(f"- {item}" for item in blockers)
    else:
        required_lines.append("- none")
    manifest = payload.get("artifact_manifest") or {}
    verification = manifest.get("verification") or {}
    deliverables = payload.get("repository_deliverables") or {}
    invocation = payload.get("run_daily_invocation") or {}
    schedule = payload.get("schedule_evidence") or {}
    required_lines.extend([
        f"- repository deliverables present: {deliverables.get('all_present')}",
        f"- repository missing files: {', '.join(deliverables.get('missing_files') or []) if deliverables.get('missing_files') else 'none'}",
        f"- repository missing directories: {', '.join(deliverables.get('missing_directories') or []) if deliverables.get('missing_directories') else 'none'}",
        f"- README documents audited readiness: {deliverables.get('readme_documents_audited_readiness')}",
        f"- README missing snippets: {', '.join(deliverables.get('missing_readme_snippets') or []) if deliverables.get('missing_readme_snippets') else 'none'}",
        f"- run_daily executable: {deliverables.get('run_daily_executable')}",
        f"- run_daily uses audited entrypoint: {deliverables.get('run_daily_uses_audited_entrypoint')}",
        f"- artifact manifest files: {manifest.get('file_count')}",
        f"- artifact manifest verification: {verification.get('status')}",
        f"- artifact manifest verification matches current manifest: {verification.get('matches_current_manifest')}",
        f"- artifact verification latest matches current verification: {verification.get('latest_matches_current_verification')}",
        f"- artifact verification manifest generated at: {verification.get('manifest_generated_at')}",
        f"- run_daily invocation status: {invocation.get('status')}",
        f"- run_daily invocation run_date: {invocation.get('run_date')}",
        f"- run_daily expected entrypoint script: {invocation.get('expected_entrypoint_script')}",
        f"- schedule cron line: {schedule.get('cron_line')}",
    ])
    return all(line in markdown for line in required_lines)


def _recompute_readiness_status(payload: dict[str, Any]) -> None:
    checks = payload.get("checks") or {}
    payload["readiness_score"] = round(sum(1 for ok in checks.values() if ok) / len(checks), 4) if checks else 0.0
    payload["status"] = "production_ready" if checks and all(checks.values()) else "not_production_ready"


def _set_readiness_markdown_match(payload: dict[str, Any], ok: bool) -> None:
    checks = payload.setdefault("checks", {})
    checks["readiness_markdown_matches_current_json"] = ok
    blockers = payload.setdefault("blockers", [])
    blocker = "READINESS_REPORT.md does not match current READINESS_REPORT.json"
    if ok:
        payload["blockers"] = [item for item in blockers if item != blocker]
    elif blocker not in blockers:
        blockers.append(blocker)
    _recompute_readiness_status(payload)


def _write_verified_readiness_outputs(cfg: RunConfig, payload: dict[str, Any]) -> None:
    for _ in range(2):
        write_readiness_markdown(cfg, payload)
        markdown = (cfg.output_root / "READINESS_REPORT.md").read_text(encoding="utf-8")
        ok = _readiness_markdown_matches_payload(markdown, cfg, payload)
        previous = (payload.get("checks") or {}).get("readiness_markdown_matches_current_json")
        if ok == previous:
            break
        _set_readiness_markdown_match(payload, ok)
    markdown = (cfg.output_root / "READINESS_REPORT.md").read_text(encoding="utf-8")
    ok = _readiness_markdown_matches_payload(markdown, cfg, payload)
    _set_readiness_markdown_match(payload, ok)
    payload["readiness_markdown"] = {
        "present": (cfg.output_root / "READINESS_REPORT.md").exists(),
        "path": str(cfg.output_root / "READINESS_REPORT.md"),
        "matches_current_json": ok,
        "required_line_count": len(render_readiness_markdown(cfg, payload).splitlines()),
    }
    write_json(cfg.output_root / "READINESS_REPORT.json", payload)


def run(config: RunConfig | None = None) -> dict[str, Any]:
    cfg = config or load_config()
    payload = evaluate_readiness(cfg)
    _write_verified_readiness_outputs(cfg, payload)
    return payload


if __name__ == "__main__":
    run()
