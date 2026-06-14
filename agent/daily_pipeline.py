from __future__ import annotations

import json
import os
import copy
import shutil
import time
import traceback
from datetime import datetime, timezone
from collections.abc import Callable
from typing import Any

from .config import RunConfig, load_config
from .io_utils import append_jsonl, read_json, write_json
from . import (
    artifact_manifest,
    backtest_agent,
    critic_agent,
    data_agent,
    evolution_agent,
    factor_design,
    gpu_alpha_submission,
    knowledge_base,
    market_intelligence,
    preflight,
    readiness_report,
    research_agent,
    schedule,
    self_audit,
)


AGENTS: list[tuple[str, Callable[[RunConfig], dict[str, Any]]]] = [
    ("preflight", preflight.run),
    ("market_intelligence", market_intelligence.run),
    ("research_agent", research_agent.run),
    ("factor_design", factor_design.run),
    ("data_agent", data_agent.run),
    ("backtest_agent", backtest_agent.run),
    ("critic_agent", critic_agent.run),
    ("evolution_agent", evolution_agent.run),
    ("knowledge_base", knowledge_base.run),
]


def _safe_payload(agent_name: str) -> dict[str, Any]:
    if agent_name == "backtest_agent":
        return {"agent": agent_name, "results": []}
    if agent_name == "critic_agent":
        return {"agent": agent_name, "critiques": []}
    if agent_name == "evolution_agent":
        return {"agent": agent_name, "next_generation_factors": []}
    if agent_name == "factor_design":
        return {"agent": agent_name, "factors": []}
    if agent_name == "research_agent":
        return {"agent": agent_name, "ideas": []}
    if agent_name == "market_intelligence":
        return {"agent": agent_name, "events": []}
    if agent_name == "preflight":
        return {"agent": agent_name, "status": "error", "checks": {}}
    if agent_name == "knowledge_base":
        return {"agent": agent_name, "factors": []}
    return {"agent": agent_name}


def _gpu_submission_summary(payload: dict[str, Any]) -> str:
    status = payload.get("status", "pending")
    if payload.get("job_id"):
        return f"{status} (job {payload['job_id']})"
    if payload.get("skip_reason"):
        return f"{status} ({payload['skip_reason']})"
    if payload.get("error"):
        return f"{status} ({payload['error']})"
    return str(status)


def _write_daily_report(cfg: RunConfig, outputs: dict[str, Any], statuses: list[dict[str, Any]]) -> None:
    lines = [
        "# Daily Quant Research Report",
        "",
        f"Run date: {cfg.run_date}",
        "",
        "## Agent Status",
        "",
    ]
    for item in statuses:
        line = f"- {item['agent']}: {item['status']}"
        if item.get("error"):
            line += f" - {item['error']}"
        lines.append(line)
    lines += ["", "## Summary", ""]
    events = outputs.get("market_intelligence", {}).get("events", [])
    ideas = outputs.get("research_agent", {}).get("ideas", [])
    factors = outputs.get("factor_design", {}).get("factors", [])
    skipped_factors = outputs.get("factor_design", {}).get("skipped_factors", [])
    results = outputs.get("backtest_agent", {}).get("results", [])
    dataset_provenance = outputs.get("backtest_agent", {}).get("dataset_provenance", {})
    raw_candidates = [r for r in results if r.get("decision") == "raw_candidate"]
    critiques = outputs.get("critic_agent", {}).get("critiques", [])
    promoted = [r for r in critiques if r.get("decision") == "promote"]
    data_health = outputs.get("data_agent", {}).get("health_status", "unknown")
    self_audit_payload = outputs.get("self_audit", {})
    gpu_submission = outputs.get("gpu_alpha_submission", {})
    market_quality = outputs.get("market_intelligence", {}).get("source_quality", {})
    research_quality = outputs.get("research_agent", {}).get("source_quality", {})
    preflight_status = outputs.get("preflight", {}).get("status", "unknown")
    readiness_payload = outputs.get("readiness_report", {})
    readiness_blockers = readiness_payload.get("blockers") or []
    lines += [
        f"- events collected: {len(events)}",
        f"- market source mode: {market_quality.get('mode', 'unknown')} ({market_quality.get('ok_sources', 0)}/{market_quality.get('total_sources', 0)} ok)",
        f"- research ideas: {len(ideas)}",
        f"- research source mode: {research_quality.get('mode', 'unknown')} ({research_quality.get('ok_sources', 0)}/{research_quality.get('total_sources', 0)} ok)",
        f"- candidate factors: {len(factors)}",
        f"- skipped failed factors: {len(skipped_factors)}",
        f"- backtested factors: {len(results)}",
        f"- backtest dataset sha256: {str(dataset_provenance.get('dataset_sha256') or 'unknown')[:12]}",
        f"- raw backtest candidates: {len(raw_candidates)}",
        f"- promoted after critic: {len(promoted)}",
        f"- data health: {data_health}",
        f"- preflight: {preflight_status}",
        f"- self audit: {self_audit_payload.get('status', 'pending')} ({self_audit_payload.get('score', 0):.2f})",
        f"- gpu alpha submission: {_gpu_submission_summary(gpu_submission)}",
        "",
        "## Readiness",
        "",
        f"- readiness status: {readiness_payload.get('status', 'pending')}",
        f"- readiness score: {(readiness_payload.get('readiness_score') or 0):.4f}",
        f"- readiness blockers: {len(readiness_blockers)}",
        f"- top readiness blocker: {readiness_blockers[0] if readiness_blockers else 'none'}",
        "",
        "## Top Backtest Results",
        "",
        "| factor | decision | RankIC | long_only_ann | long_short_ann_diag | Sharpe | turnover |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for r in sorted(results, key=lambda x: (x.get("rankic_mean") or -9), reverse=True)[:10]:
        p = r.get("portfolio") or {}
        ls = r.get("long_short") or {}
        lines.append(
            f"| {r.get('factor_id')} | {r.get('decision')} | {(r.get('rankic_mean') or 0):.5f} | "
            f"{(p.get('ann_return_net') or 0):.5f} | {(ls.get('ann_return_net') or 0):.5f} | {(p.get('sharpe_net') or 0):.3f} | "
            f"{(p.get('turnover_mean') or 0):.3f} |"
        )
    lines += [
        "",
        "## Files",
        "",
        "- `daily_events.json`",
        "- `preflight.json`",
        "- `research_ideas.json`",
        "- `candidate_factors/`",
        "- `daily_dataset.parquet`",
        "- `data_health.json`",
        "- `backtest_results/`",
        "- `failure_analysis.md`",
        "- `next_generation_factors/`",
        "- `knowledge_base/factor_database/factors.json`",
        "- `pipeline_state.json`",
        "- `self_audit.json`",
        "- `gpu_alpha_submission.json`",
        "- `schedule.json`",
        "- `cron_example.txt`",
        "- `knowledge_base/run_history.jsonl`",
        "- `reports/READINESS_REPORT.md`",
    ]
    (cfg.run_dir / "daily_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _readiness_summary(payload: dict[str, Any]) -> tuple[Any, ...]:
    blockers = payload.get("blockers") or []
    return (
        payload.get("status"),
        round(float(payload.get("readiness_score") or 0), 4),
        len(blockers),
        blockers[0] if blockers else "none",
    )


def update_daily_report_readiness_section(cfg: RunConfig, readiness_payload: dict[str, Any]) -> None:
    path = cfg.run_dir / "daily_report.md"
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    start_marker = "## Readiness\n\n"
    end_marker = "\n## Top Backtest Results"
    start = text.find(start_marker)
    end = text.find(end_marker)
    if start < 0 or end < 0 or end <= start:
        return
    blockers = readiness_payload.get("blockers") or []
    section = (
        "## Readiness\n\n"
        f"- readiness status: {readiness_payload.get('status', 'pending')}\n"
        f"- readiness score: {(readiness_payload.get('readiness_score') or 0):.4f}\n"
        f"- readiness blockers: {len(blockers)}\n"
        f"- top readiness blocker: {blockers[0] if blockers else 'none'}\n"
    )
    path.write_text(text[:start] + section + text[end:], encoding="utf-8")


def _refresh_readiness_report_and_manifest(
    cfg: RunConfig,
    outputs: dict[str, Any],
    statuses: list[dict[str, Any]],
    readiness_status: dict[str, Any],
    max_rounds: int = 5,
) -> None:
    last_summary: tuple[Any, ...] | None = None
    for _ in range(max_rounds):
        readiness_started = time.time()
        readiness_payload = readiness_report.run(cfg)
        outputs["readiness_report"] = readiness_payload
        readiness_status["duration_sec"] = round(
            (readiness_status.get("duration_sec") or 0) + time.time() - readiness_started,
            3,
        )
        summary = _readiness_summary(readiness_payload)
        if summary == last_summary:
            update_daily_report_readiness_section(cfg, readiness_payload)
            break

        _write_daily_report(cfg, outputs, statuses)
        manifest_started = time.time()
        manifest_payload = artifact_manifest.run(cfg)
        outputs["artifact_manifest"] = manifest_payload
        statuses[-1]["duration_sec"] = round((statuses[-1]["duration_sec"] or 0) + time.time() - manifest_started, 3)
        last_summary = summary


def _build_run_history_record(cfg: RunConfig, outputs: dict[str, Any], statuses: list[dict[str, Any]]) -> dict[str, Any]:
    results = outputs.get("backtest_agent", {}).get("results", [])
    critiques = outputs.get("critic_agent", {}).get("critiques", [])
    data_health = outputs.get("data_agent", {})
    data_health_file = read_json(cfg.run_dir / "data_health.json", {})
    audit = outputs.get("self_audit", {})
    record = {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "run_date": cfg.run_date,
        "pipeline_status": "complete_with_errors" if any(s["status"] != "ok" for s in statuses) else "complete",
        "agent_status": {s["agent"]: s["status"] for s in statuses},
        "self_audit_status": audit.get("status"),
        "self_audit_score": audit.get("score"),
        "source_mode": audit.get("source_mode"),
        "market_source_quality": outputs.get("market_intelligence", {}).get("source_quality", {}),
        "research_source_quality": outputs.get("research_agent", {}).get("source_quality", {}),
        "data_health_status": data_health.get("health_status"),
        "data_source_mode": data_health.get("source_mode"),
        "data_freshness": data_health_file.get("freshness", {}),
        "data_checks": data_health_file.get("checks", {}),
        "data_domain_coverage": data_health_file.get("domain_coverage", {}),
        "counts": {
            "events": len(outputs.get("market_intelligence", {}).get("events", [])),
            "ideas": len(outputs.get("research_agent", {}).get("ideas", [])),
            "candidate_factors": len(outputs.get("factor_design", {}).get("factors", [])),
            "backtest_results": len(results),
            "raw_candidates": sum(1 for r in results if r.get("decision") == "raw_candidate"),
            "promoted": sum(1 for c in critiques if c.get("decision") == "promote"),
            "killed": sum(1 for c in critiques if c.get("decision") == "kill"),
        },
    }
    return record


def _append_run_history(cfg: RunConfig, outputs: dict[str, Any], statuses: list[dict[str, Any]]) -> dict[str, Any]:
    record = _build_run_history_record(cfg, outputs, statuses)
    append_jsonl(cfg.knowledge_root / "run_history.jsonl", record)
    write_json(cfg.knowledge_root / "run_history_latest.json", record)
    return record


def _replace_latest_run_history_record(cfg: RunConfig, outputs: dict[str, Any], statuses: list[dict[str, Any]]) -> dict[str, Any]:
    record = _build_run_history_record(cfg, outputs, statuses)
    path = cfg.knowledge_root / "run_history.jsonl"
    if not path.exists():
        append_jsonl(path, record)
        write_json(cfg.knowledge_root / "run_history_latest.json", record)
        return record

    lines = path.read_text(encoding="utf-8").splitlines()
    replacement = json.dumps(record, ensure_ascii=False, sort_keys=True)
    replaced = False
    for idx in range(len(lines) - 1, -1, -1):
        line = lines[idx]
        if not line.strip():
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict) and str(parsed.get("run_date")) == str(cfg.run_date):
            lines[idx] = replacement
            replaced = True
            break
    if not replaced:
        lines.append(replacement)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    tmp_path.replace(path)
    write_json(cfg.knowledge_root / "run_history_latest.json", record)
    return record


def _lock_age_seconds(lock_path) -> float | None:
    try:
        return max(0.0, time.time() - lock_path.stat().st_mtime)
    except FileNotFoundError:
        return None


def _read_lock_payload(lock_path) -> dict[str, Any]:
    try:
        text = lock_path.read_text(encoding="utf-8", errors="ignore")
    except FileNotFoundError:
        return {}
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {"raw": text[:300]}
    except json.JSONDecodeError:
        return {"raw": text[:300]}


def _acquire_lock(cfg: RunConfig) -> tuple[Any, dict[str, Any]]:
    lock_path = cfg.output_root / ".quant_daily.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    recovered_stale = False
    stale_age_seconds = None
    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        stale_age_seconds = _lock_age_seconds(lock_path)
        stale_after = max(0, cfg.lock_stale_minutes) * 60
        if stale_age_seconds is not None and stale_after > 0 and stale_age_seconds >= stale_after:
            try:
                lock_path.unlink()
                recovered_stale = True
            except FileNotFoundError:
                recovered_stale = True
            try:
                fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                raise RuntimeError(f"daily pipeline lock exists after stale cleanup race: {lock_path}")
        else:
            current = _read_lock_payload(lock_path)
            raise RuntimeError(
                f"daily pipeline lock exists: {lock_path}; age_sec={stale_age_seconds}; "
                f"stale_after_sec={stale_after}; lock={current}"
            )
    lock_info = {
        "pid": os.getpid(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "run_date": cfg.run_date,
        "stale_after_minutes": cfg.lock_stale_minutes,
        "recovered_stale_lock": recovered_stale,
        "stale_lock_age_seconds": round(stale_age_seconds, 3) if stale_age_seconds is not None else None,
    }
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(json.dumps(lock_info, ensure_ascii=False, sort_keys=True))
    return lock_path, lock_info


def _release_lock(lock_path, lock_info: dict[str, Any]) -> None:
    current = _read_lock_payload(lock_path)
    if current.get("pid") != lock_info.get("pid") or current.get("created_at") != lock_info.get("created_at"):
        return
    try:
        lock_path.unlink()
    except FileNotFoundError:
        pass


def _write_pipeline_state(
    cfg: RunConfig,
    status: str,
    statuses: list[dict[str, Any]],
    lock_info: dict[str, Any],
    started_at: str,
    current_agent: str | None = None,
    retention: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    state = {
        "run_date": cfg.run_date,
        "status": status,
        "started_at": started_at,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "current_agent": current_agent,
        "completed_agents": [item.get("agent") for item in statuses],
        "agents": copy.deepcopy(statuses),
        "lock": copy.deepcopy(lock_info),
    }
    if retention is not None:
        state["retention"] = retention
    if extra:
        state.update(extra)
    write_json(cfg.run_dir / "pipeline_state.json", state)
    return state


def _write_run_audit(
    cfg: RunConfig,
    lock_info: dict[str, Any],
    state: dict[str, Any],
) -> dict[str, Any]:
    payload = {
        "run_date": cfg.run_date,
        "config": {
            "offline": cfg.offline,
            "agent_retries": cfg.agent_retries,
            "retention_days": cfg.retention_days,
            "lock_stale_minutes": cfg.lock_stale_minutes,
            "min_free_disk_mb": cfg.min_free_disk_mb,
            "data_root": str(cfg.data_root),
            "output_root": str(cfg.output_root),
            "knowledge_root": str(cfg.knowledge_root),
            "factor_library": str(cfg.factor_library),
        },
        "lock": copy.deepcopy(lock_info),
        "state": copy.deepcopy(state),
    }
    write_json(cfg.run_dir / "run_audit.json", payload)
    return payload


def _run_agent_with_retries(agent_name: str, agent_fn: Callable[[RunConfig], dict[str, Any]], cfg: RunConfig) -> tuple[dict[str, Any], dict[str, Any]]:
    attempts = max(1, cfg.agent_retries + 1)
    last_exc: Exception | None = None
    failed_attempts: list[dict[str, Any]] = []
    for attempt in range(1, attempts + 1):
        started = time.time()
        try:
            payload = agent_fn(cfg)
            status = {
                "agent": agent_name,
                "status": "ok",
                "attempt": attempt,
                "duration_sec": round(time.time() - started, 3),
            }
            if failed_attempts:
                status["retries"] = copy.deepcopy(failed_attempts)
            return payload, status
        except Exception as exc:
            last_exc = exc
            failed_attempt = {
                "attempt": attempt,
                "duration_sec": round(time.time() - started, 3),
                "error": str(exc)[:300],
                "traceback": traceback.format_exc(limit=8),
            }
            failed_attempts.append(failed_attempt)
            if attempt < attempts:
                time.sleep(min(0.5 * attempt, 2.0))
            else:
                status = {
                    "agent": agent_name,
                    "status": "error",
                    "attempt": attempt,
                    "duration_sec": round(time.time() - started, 3),
                    "error": str(exc)[:300],
                    "traceback": traceback.format_exc(limit=8),
                    "retries": copy.deepcopy(failed_attempts),
                }
                write_json(cfg.run_dir / "errors" / f"{agent_name}.json", status)
                return _safe_payload(agent_name), status
    raise RuntimeError(f"unreachable retry state for {agent_name}: {last_exc}")


def _apply_retention(cfg: RunConfig) -> dict[str, Any]:
    logs_root = cfg.output_root / "daily_logs"
    removed: list[str] = []
    if cfg.retention_days <= 0 or not logs_root.exists():
        return {"retention_days": cfg.retention_days, "removed": removed}
    cutoff = time.time() - cfg.retention_days * 86400
    for path in logs_root.iterdir():
        if not path.is_dir() or path == cfg.run_dir:
            continue
        try:
            if path.stat().st_mtime < cutoff:
                shutil.rmtree(path)
                removed.append(str(path))
        except FileNotFoundError:
            continue
    return {"retention_days": cfg.retention_days, "removed": removed}


def run(config: RunConfig | None = None) -> dict[str, Any]:
    cfg = config or load_config()
    cfg.run_dir.mkdir(parents=True, exist_ok=True)
    lock_path, lock_info = _acquire_lock(cfg)
    started_at = datetime.now(timezone.utc).isoformat()
    outputs: dict[str, Any] = {}
    statuses: list[dict[str, Any]] = []
    active_agent: str | None = None
    try:
        _write_pipeline_state(cfg, "running", statuses, lock_info, started_at)
        try:
            for agent_name, agent_fn in AGENTS:
                active_agent = agent_name
                _write_pipeline_state(cfg, "running", statuses, lock_info, started_at, current_agent=agent_name)
                payload, status = _run_agent_with_retries(agent_name, agent_fn, cfg)
                outputs[agent_name] = payload
                statuses.append(status)
                active_agent = None
                _write_pipeline_state(cfg, "running", statuses, lock_info, started_at)
            retention = _apply_retention(cfg)
            state = _write_pipeline_state(
                cfg,
                "complete_with_errors" if any(s["status"] != "ok" for s in statuses) else "complete",
                statuses,
                lock_info,
                started_at,
                retention=retention,
            )
            _write_run_audit(cfg, lock_info, state)
            for agent_name, agent_fn in (
                ("schedule", schedule.run),
                ("self_audit", self_audit.run),
                ("gpu_alpha_submission", gpu_alpha_submission.run),
            ):
                active_agent = agent_name
                _write_pipeline_state(
                    cfg,
                    "running",
                    statuses,
                    lock_info,
                    started_at,
                    current_agent=agent_name,
                    retention=retention,
                )
                payload, status = _run_agent_with_retries(agent_name, agent_fn, cfg)
                outputs[agent_name] = payload
                statuses.append(status)
                active_agent = None
                _write_pipeline_state(cfg, "running", statuses, lock_info, started_at, retention=retention)
            history_record = _append_run_history(cfg, outputs, statuses)
            outputs["run_history"] = history_record
            active_agent = "readiness_report"
            _write_pipeline_state(
                cfg,
                "running",
                statuses,
                lock_info,
                started_at,
                current_agent="readiness_report",
                retention=retention,
                extra={"run_history_path": str(cfg.knowledge_root / "run_history.jsonl")},
            )
            readiness_payload, readiness_status = _run_agent_with_retries("readiness_report", readiness_report.run, cfg)
            outputs["readiness_report"] = readiness_payload
            statuses.append(readiness_status)
            active_agent = None
            final_status = "complete_with_errors" if any(s["status"] != "ok" for s in statuses) else state["status"]
            final_state = _write_pipeline_state(
                cfg,
                final_status,
                statuses,
                lock_info,
                started_at,
                retention=retention,
                extra={
                    "run_history_path": str(cfg.knowledge_root / "run_history.jsonl"),
                    "readiness_report_path": str(cfg.output_root / "READINESS_REPORT.md"),
                },
            )
            _write_daily_report(cfg, outputs, statuses)
            manifest_started = time.time()
            statuses.append({
                "agent": "artifact_manifest",
                "status": "ok",
                "attempt": 1,
                "duration_sec": None,
            })
            final_state = _write_pipeline_state(
                cfg,
                final_status,
                statuses,
                lock_info,
                started_at,
                retention=retention,
                extra={
                    "run_history_path": str(cfg.knowledge_root / "run_history.jsonl"),
                    "readiness_report_path": str(cfg.output_root / "READINESS_REPORT.md"),
                    "artifact_manifest_path": str(cfg.run_dir / "artifact_manifest.json"),
                },
            )
            manifest_payload = artifact_manifest.run(cfg)
            outputs["artifact_manifest"] = manifest_payload
            statuses[-1]["duration_sec"] = round(time.time() - manifest_started, 3)
            final_readiness_started = time.time()
            final_readiness_payload = readiness_report.run(cfg)
            outputs["readiness_report"] = final_readiness_payload
            readiness_status["duration_sec"] = round(
                (readiness_status.get("duration_sec") or 0) + time.time() - final_readiness_started,
                3,
            )
            manifest_started = time.time()
            manifest_payload = artifact_manifest.run(cfg)
            outputs["artifact_manifest"] = manifest_payload
            statuses[-1]["duration_sec"] = round((statuses[-1]["duration_sec"] or 0) + time.time() - manifest_started, 3)
            history_record = _replace_latest_run_history_record(cfg, outputs, statuses)
            outputs["run_history"] = history_record
            final_readiness_started = time.time()
            final_readiness_payload = readiness_report.run(cfg)
            outputs["readiness_report"] = final_readiness_payload
            readiness_status["duration_sec"] = round(
                (readiness_status.get("duration_sec") or 0) + time.time() - final_readiness_started,
                3,
            )
            manifest_started = time.time()
            manifest_payload = artifact_manifest.run(cfg)
            outputs["artifact_manifest"] = manifest_payload
            statuses[-1]["duration_sec"] = round((statuses[-1]["duration_sec"] or 0) + time.time() - manifest_started, 3)
            final_state = _write_pipeline_state(
                cfg,
                final_status,
                statuses,
                lock_info,
                started_at,
                retention=retention,
                extra={
                    "run_history_path": str(cfg.knowledge_root / "run_history.jsonl"),
                    "readiness_report_path": str(cfg.output_root / "READINESS_REPORT.md"),
                    "artifact_manifest_path": str(cfg.run_dir / "artifact_manifest.json"),
                },
            )
            _write_run_audit(cfg, lock_info, final_state)
            _refresh_readiness_report_and_manifest(cfg, outputs, statuses, readiness_status)
        except BaseException as exc:
            interrupted_state = _write_pipeline_state(
                cfg,
                "interrupted",
                statuses,
                lock_info,
                started_at,
                current_agent=active_agent,
                extra={
                    "error": {
                        "type": type(exc).__name__,
                        "message": str(exc)[:300],
                        "traceback": traceback.format_exc(limit=8),
                    }
                },
            )
            _write_run_audit(cfg, lock_info, interrupted_state)
            raise
    finally:
        _release_lock(lock_path, lock_info)
    return outputs


if __name__ == "__main__":
    run()
