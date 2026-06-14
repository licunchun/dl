from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from agent.config import RunConfig
from agent import artifact_manifest, daily_pipeline, readiness_report, self_audit
from agent.artifact_verifier import verify_manifest
from agent.io_utils import append_jsonl, read_json, write_json


def _write_latest_from_jsonl(jsonl_path: Path, latest_path: Path) -> None:
    if latest_path.exists() or not jsonl_path.exists():
        return
    latest = None
    for line in jsonl_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            latest = json.loads(line)
        except json.JSONDecodeError:
            continue
    if isinstance(latest, dict):
        write_json(latest_path, latest)


def _current_self_audit_payload(cfg: RunConfig) -> dict:
    preflight = {"status": "ok", "checks": {"min_free_disk_ok": True, "required_dirs_writable": True}}
    events = _daily_events_payload(cfg)
    ideas = _research_ideas_payload(cfg)
    return {
        "agent": "self_audit",
        "run_date": cfg.run_date,
        "status": "pass",
        "score": 1.0,
        "checks": {name: True for name in readiness_report.REQUIRED_SELF_AUDIT_CHECKS},
        "source_mode": "live",
        "counts": {
            "events": len(events["events"]),
            "ideas": len(ideas["ideas"]),
            "candidate_factors": 1,
            "backtest_results": 1,
            "knowledge_factors": 1,
        },
        "data_freshness": {
            "status": "ok",
            "staleness_days": 0,
            "max_allowed_staleness_days": 7,
            "note": "",
        },
        "preflight": preflight,
        "market_source_quality": events["source_quality"],
        "research_source_quality": ideas["source_quality"],
    }


def _current_self_audit_markdown_text(cfg: RunConfig) -> str:
    payload = _current_self_audit_payload(cfg)
    preflight = payload["preflight"]
    freshness = payload["data_freshness"]
    lines = [
        "# Self Audit",
        "",
        f"Run date: {cfg.run_date}",
        f"Status: {payload['status']}",
        f"Score: {payload['score']:.2f}",
        f"Source mode: {payload['source_mode']}",
        "",
        "## Checks",
        "",
    ]
    for name, ok in payload["checks"].items():
        lines.append(f"- {name}: {'ok' if ok else 'fail'}")
    lines += [
        "",
        "## Preflight",
        "",
        f"- status: {preflight.get('status')}",
        f"- min_free_disk_ok: {preflight.get('checks', {}).get('min_free_disk_ok')}",
        f"- required_dirs_writable: {preflight.get('checks', {}).get('required_dirs_writable')}",
        "",
        "## Data Freshness",
        "",
        f"- status: {freshness.get('status')}",
        f"- staleness_days: {freshness.get('staleness_days')}",
        f"- max_allowed_staleness_days: {freshness.get('max_allowed_staleness_days')}",
    ]
    return "\n".join(lines) + "\n"


def _current_daily_report_text(cfg: RunConfig) -> str:
    events = _daily_events_payload(cfg)
    ideas = _research_ideas_payload(cfg)
    market_quality = events["source_quality"]
    research_quality = ideas["source_quality"]
    agent_lines = "\n".join(
        f"- {agent}: ok" for agent in sorted(readiness_report.REQUIRED_DAILY_REPORT_AGENTS)
    )
    return (
        "# Daily Quant Research Report\n\n"
        f"Run date: {cfg.run_date}\n\n"
        "## Agent Status\n\n"
        f"{agent_lines}\n\n"
        "## Summary\n\n"
        f"- events collected: {len(events['events'])}\n"
        f"- market source mode: live ({market_quality['ok_sources']}/{market_quality['total_sources']} ok)\n"
        f"- research ideas: {len(ideas['ideas'])}\n"
        f"- research source mode: live ({research_quality['ok_sources']}/{research_quality['total_sources']} ok)\n"
        "- candidate factors: 1\n"
        "- skipped failed factors: 0\n"
        "- backtested factors: 1\n"
        "- backtest dataset sha256: test-dataset\n"
        "- raw backtest candidates: 1\n"
        "- promoted after critic: 0\n"
        "- data health: ok\n"
        "- preflight: ok\n"
        "- self audit: pass (1.00)\n"
        "- gpu alpha submission: skipped (offline_run)\n\n"
        "## Readiness\n\n"
        "- readiness status: production_ready\n"
        "- readiness score: 1.0000\n"
        "- readiness blockers: 0\n"
        "- top readiness blocker: none\n\n"
        "## Top Backtest Results\n\n"
        "| factor | decision | RankIC | long_only_ann | long_short_ann_diag | Sharpe | turnover |\n"
        "|---|---|---:|---:|---:|---:|---:|\n"
        "| F1 | raw_candidate | 0.01000 | 0.02000 | 0.00100 | 1.000 | 0.100 |\n\n"
        "## Files\n\n"
        "- `daily_events.json`\n"
        "- `preflight.json`\n"
        "- `research_ideas.json`\n"
        "- `candidate_factors/`\n"
        "- `daily_dataset.parquet`\n"
        "- `data_health.json`\n"
        "- `backtest_results/`\n"
        "- `failure_analysis.md`\n"
        "- `next_generation_factors/`\n"
        "- `knowledge_base/factor_database/factors.json`\n"
        "- `pipeline_state.json`\n"
        "- `self_audit.json`\n"
        "- `gpu_alpha_submission.json`\n"
        "- `schedule.json`\n"
        "- `cron_example.txt`\n"
        "- `knowledge_base/run_history.jsonl`\n"
        "- `reports/READINESS_REPORT.md`\n"
    )


def _source_status_payload(kind: str = "news", run_date: str = "20260605") -> list[dict]:
    return [{
        "name": "source",
        "kind": kind,
        "url": "https://example.com",
        "status": "ok",
        "items": 1,
        "response_bytes": 128,
        "content_sha256": "a" * 64,
        "fetched_at": f"{run_date[:4]}-{run_date[4:6]}-{run_date[6:]}T00:00:00+00:00",
        "latency_sec": 0.1,
    }]


def _source_status_payloads(kinds: list[str], run_date: str = "20260605") -> list[dict]:
    return [item for kind in kinds for item in _source_status_payload(kind, run_date)]


def _source_quality_payload(kinds: list[str] | str | None = None) -> dict:
    if isinstance(kinds, str):
        kinds = [kinds]
    kinds = kinds or ["news"]
    return {
        "mode": "live",
        "total_sources": len(kinds),
        "ok_sources": len(kinds),
        "error_sources": 0,
        "coverage_ratio": 1.0,
        "covered_kinds": sorted(kinds),
        "missing_kinds": [],
        "fallback_used": False,
    }


def _source_items(cfg: RunConfig, kinds: list[str], text_key: str) -> list[dict]:
    rows = []
    for kind in kinds:
        if text_key == "title":
            rows.append({
                "date": cfg.run_date,
                "source": "source",
                "kind": kind,
                "title": f"{kind} event",
                "url": "https://example.com",
            })
        else:
            rows.append({
                "source": "source",
                "kind": kind,
                "text": f"{kind} research context",
                "url": "https://example.com",
            })
    return rows


def _daily_events_payload(cfg: RunConfig) -> dict:
    kinds = sorted(readiness_report.REQUIRED_MARKET_SOURCE_KINDS)
    return {
        "agent": "market_intelligence",
        "run_date": cfg.run_date,
        "source_status": _source_status_payloads(kinds, cfg.run_date),
        "source_quality": _source_quality_payload(kinds),
        "events": _source_items(cfg, kinds, "title"),
    }


def _research_ideas_payload(cfg: RunConfig) -> dict:
    kinds = sorted(readiness_report.REQUIRED_RESEARCH_SOURCE_KINDS)
    return {
        "agent": "research_agent",
        "run_date": cfg.run_date,
        "ideas": [{"idea_id": "R1"}],
        "research_context": _source_items(cfg, kinds, "text"),
        "source_status": _source_status_payloads(kinds, cfg.run_date),
        "source_quality": _source_quality_payload(kinds),
    }


def _source_snapshot_payload(cfg: RunConfig, agent: str, run_date: str | None = None) -> dict:
    run_date = run_date or cfg.run_date
    if agent == "market_intelligence":
        source_status = _source_status_payloads(sorted(readiness_report.REQUIRED_MARKET_SOURCE_KINDS), run_date)
        source_quality = _source_quality_payload(sorted(readiness_report.REQUIRED_MARKET_SOURCE_KINDS))
        items = _daily_events_payload(cfg)["events"]
    else:
        source_status = _source_status_payloads(sorted(readiness_report.REQUIRED_RESEARCH_SOURCE_KINDS), run_date)
        source_quality = _source_quality_payload(sorted(readiness_report.REQUIRED_RESEARCH_SOURCE_KINDS))
        items = _research_ideas_payload(cfg)["research_context"]
    return {
        "run_date": run_date,
        "agent": agent,
        "snapshot_written_at": f"{run_date[:4]}-{run_date[4:6]}-{run_date[6:]}T00:00:01+00:00",
        "source_status": source_status,
        "source_quality": source_quality,
        "item_count": len(items),
        "items": items,
    }


def _candidate_factor_payload(cfg: RunConfig) -> dict:
    factor = {
        "factor_id": "F1",
        "name": "Test factor",
        "formula": "rank(ret_5)",
        "formula_key": "rank(ret_5)",
        "expression": "ret_5_rank",
        "created_at_run": cfg.run_date,
        "status": "candidate",
    }
    return {"run_date": cfg.run_date, "factors": [factor]}


def _backtest_results_payload(cfg: RunConfig) -> dict:
    factor = _candidate_factor_payload(cfg)["factors"][0]
    manifest = _dataset_manifest_payload(cfg)
    return {
        "run_date": cfg.run_date,
        "dataset_provenance": {
            "dataset_path": manifest["dataset_path"],
            "dataset_sha256": manifest["dataset_sha256"],
            "dataset_size_bytes": manifest["dataset_size_bytes"],
            "rows": manifest["rows"],
            "stocks": manifest["stocks"],
            "dates": manifest["dates"],
            "source_mode": manifest["source_mode"],
            "health_status": manifest["health_status"],
            "hash_verified": True,
        },
        "results": [{
            **factor,
            "horizon_days": 5,
            "rankic_mean": 0.01,
            "rankic_ir": 0.5,
            "rankic_positive_frac": 0.55,
            "rankic_by_date": [
                {"trade_date": "2026-06-01", "rankic": 0.01},
                {"trade_date": "2026-06-02", "rankic": 0.02},
            ],
            "portfolio": {"ann_return_net": 0.02, "turnover_mean": 0.1, "max_drawdown": -0.05},
            "long_short": {
                "portfolio_type": "long_short_diagnostic_not_directly_tradable",
                "ann_return_net": 0.001,
                "turnover_mean": 0.2,
                "max_drawdown": -0.02,
            },
            "cost_sensitivity": {
                "5": {"ann_return_net": 0.025},
                "10": {"ann_return_net": 0.02},
                "20": {"ann_return_net": 0.01},
            },
            "rows": 1000,
            "dates": 20,
            "decision_note": "raw_candidate_after_cost_controls",
            "decision": "raw_candidate",
        }],
    }


def _critique_payload(cfg: RunConfig) -> dict:
    return {
        "run_date": cfg.run_date,
        "critiques": [{
            "factor_id": "F1",
            "decision": "kill",
            "issues": ["weak_rankic_stability"],
            "checks": {"leakage": {"score": "pass"}},
            "leakage_check": "pass",
        }],
    }


def _failure_analysis_text(cfg: RunConfig) -> str:
    critique = _critique_payload(cfg)["critiques"][0]
    return (
        "# Failure Analysis\n\n"
        f"Run date: {cfg.run_date}\n\n"
        f"## {critique['factor_id']}\n\n"
        f"- decision: {critique['decision']}\n"
        f"- issues: {', '.join(critique['issues']) if critique['issues'] else 'none'}\n"
        f"- leakage_check: {critique['leakage_check']}\n"
        "- stability: None\n"
        "- collinearity: None\n"
    )


def _factor_database_payload(cfg: RunConfig) -> dict:
    result = _backtest_results_payload(cfg)["results"][0]
    critique = _critique_payload(cfg)["critiques"][0]
    return {
        "factors": [{
            "run_date": cfg.run_date,
            "factor_id": result["factor_id"],
            "name": result["name"],
            "formula": result["formula"],
            "formula_key": result["formula_key"],
            "expression": result["expression"],
            "horizon_days": result["horizon_days"],
            "rankic_mean": result["rankic_mean"],
            "rankic_ir": result["rankic_ir"],
            "rankic_positive_frac": result["rankic_positive_frac"],
            "portfolio": result["portfolio"],
            "long_short": result["long_short"],
            "cost_sensitivity": result["cost_sensitivity"],
            "rows": result["rows"],
            "dates": result["dates"],
            "decision_note": result["decision_note"],
            "decision": critique["decision"],
            "issues": critique["issues"],
            "run_quality": "complete",
        }]
    }


def _failure_memory_payload(cfg: RunConfig) -> dict:
    result = _backtest_results_payload(cfg)["results"][0]
    critique = _critique_payload(cfg)["critiques"][0]
    portfolio = result["portfolio"]
    return {
        "run_date": cfg.run_date,
        "factor_id": result["factor_id"],
        "formula": result["formula"],
        "formula_key": result["formula_key"],
        "expression": result["expression"],
        "issues": critique["issues"],
        "checks": critique["checks"],
        "parent_metrics": {
            "rankic_mean": result["rankic_mean"],
            "ann_return_net": portfolio["ann_return_net"],
            "turnover_mean": portfolio["turnover_mean"],
            "max_drawdown": portfolio["max_drawdown"],
        },
        "next_actions": ["F1_PIVOT_DEF"],
    }


def _gpu_alpha_submission_payload(cfg: RunConfig, **overrides) -> dict:
    payload = {
        "agent": "gpu_alpha_submission",
        "run_date": cfg.run_date,
        "created_at": f"{cfg.run_date[:4]}-{cfg.run_date[4:6]}-{cfg.run_date[6:]}T00:00:04+00:00",
        "enabled": True,
        "offline": True,
        "script": "scripts/submit_alpha_gpu_backtest.sh",
        "script_exists": True,
        "sbatch_path": None,
        "env": {},
        "status": "skipped",
        "submitted": False,
        "job_id": None,
        "skip_reason": "offline_run",
    }
    payload.update(overrides)
    return payload


def _next_generation_payload(cfg: RunConfig) -> dict:
    factor = {
        "factor_id": "F1_PIVOT_DEF",
        "parent_factor_id": "F1",
        "formula": "(rank(ret_5)) * rank(low_vol)",
        "formula_key": "(rank(ret_5))*rank(low_vol)",
        "expression": "ret_5_rank",
        "status": "repair_candidate",
    }
    return {
        "run_date": cfg.run_date,
        "next_generation_factors": [factor],
        "skipped_evolution_factors": [],
    }


def _data_domain_coverage_payload() -> dict:
    return {
        "ohlcv": {"usable": True},
        "financial_metric": {"usable": True},
        "industry": {"usable": True},
        "moneyflow": {"usable": True},
        "risk_flags": {"usable": True},
        "derived_features": {"usable": True},
    }


def _data_source_detail_payload(cfg: RunConfig) -> dict:
    daily_root = cfg.data_root / "A股数据" / "daily"
    return {
        "data_root": str(cfg.data_root),
        "start": "20250511",
        "end": cfg.run_date,
        "daily": {
            "path": str(daily_root),
            "exists": True,
            "csv_file_count": 420,
            "selected_csv_file_count": 20,
            "selected_sample": [str(daily_root / "20260604.csv")],
        },
        "metric": {"path": str(cfg.data_root / "A股数据" / "metric"), "exists": True, "selected_csv_file_count": 20},
        "moneyflow": {"path": str(cfg.data_root / "A股数据" / "moneyflow"), "exists": True, "selected_csv_file_count": 20},
        "stock_st": {"path": str(cfg.data_root / "A股数据" / "stock_st"), "exists": True, "selected_csv_file_count": 20},
        "basic": {"path": str(cfg.data_root / "A股数据" / "basic.csv"), "exists": True},
        "fallback_reason": None,
    }


def _dataset_manifest_payload(cfg: RunConfig) -> dict:
    return {
        "agent": "data_agent",
        "run_date": cfg.run_date,
        "dataset_path": str(cfg.run_dir / "daily_dataset.parquet"),
        "rows": 1000,
        "stocks": 100,
        "dates": 20,
        "source_mode": "local_csv",
        "health_status": "ok",
        "dataset_sha256": "test-dataset-sha256",
        "dataset_size_bytes": 24,
        "data_source_detail": _data_source_detail_payload(cfg),
    }


def _data_health_payload(cfg: RunConfig) -> dict:
    checks = {
        "has_rows": True,
        "has_required_columns": True,
        "no_duplicate_keys": True,
        "has_multiple_dates": True,
        "has_multiple_stocks": True,
        "data_freshness_ok": True,
        "required_data_domains_usable": True,
    }
    return {
        "agent": "data_agent",
        "run_date": cfg.run_date,
        "source_mode": "local_csv",
        "rows": 1000,
        "stocks": 100,
        "dates": 20,
        "date_min": "2026-05-01",
        "date_max": "2026-06-04",
        "freshness": {"status": "ok", "staleness_days": 0, "max_allowed_staleness_days": 7, "note": ""},
        "missing_required_columns": [],
        "domain_coverage": _data_domain_coverage_payload(),
        "duplicate_keys": 0,
        "null_rates": {},
        "checks": checks,
        "status": "ok",
        "data_source_detail": _data_source_detail_payload(cfg),
    }


def _data_health_latest_payload(cfg: RunConfig, run_date: str | None = None) -> dict:
    run_date = run_date or cfg.run_date
    health = _data_health_payload(cfg)
    manifest = _dataset_manifest_payload(cfg)
    health["run_date"] = run_date
    manifest["run_date"] = run_date
    manifest["dataset_path"] = str(cfg.output_root / "daily_logs" / run_date / "daily_dataset.parquet")
    return {
        "run_date": run_date,
        "recorded_at": f"{run_date[:4]}-{run_date[4:6]}-{run_date[6:]}T00:00:04+00:00",
        "agent": "data_agent",
        "dataset_manifest": manifest,
        "data_health": health,
        "data_source_mode": health["source_mode"],
        "data_freshness": health["freshness"],
        "data_checks": health["checks"],
        "data_domain_coverage": health["domain_coverage"],
    }


def _research_log_payload(cfg: RunConfig, run_date: str | None = None) -> dict:
    run_date = run_date or cfg.run_date
    events = _daily_events_payload(cfg)
    ideas = _research_ideas_payload(cfg)
    candidates = _candidate_factor_payload(cfg)["factors"]
    backtest_payload = _backtest_results_payload(cfg)
    backtests = backtest_payload["results"]
    critiques = _critique_payload(cfg)["critiques"]
    next_generation = _next_generation_payload(cfg)["next_generation_factors"]
    return {
        "run_date": run_date,
        "recorded_at": f"{run_date[:4]}-{run_date[4:6]}-{run_date[6:]}T00:00:03+00:00",
        "pipeline": {"run_quality": "complete", "pipeline_status": "running"},
        "events": {
            "count": len(events["events"]),
            "top_titles": [item["title"] for item in events["events"][:5]],
            "source_quality": events["source_quality"],
        },
        "research": {
            "idea_count": len(ideas["ideas"]),
            "idea_ids": ["R1"],
            "themes": [],
            "source_quality": ideas["source_quality"],
            "context_items": len(ideas["research_context"]),
        },
        "factor_design": {
            "candidate_count": len(candidates),
            "skipped_failed_count": 0,
            "factor_ids": [item["factor_id"] for item in candidates],
            "formula_keys": [item["formula_key"] for item in candidates],
            "failed_memory_audit": {},
        },
        "backtest": {
            "result_count": len(backtests),
            "result_factor_ids": [item["factor_id"] for item in backtests],
            "dataset_provenance": backtest_payload["dataset_provenance"],
            "promoted_raw": 0,
            "killed_raw": 0,
            "top_rankic": [{
                "factor_id": item["factor_id"],
                "rankic_mean": item["rankic_mean"],
                "ann_return_net": item["portfolio"]["ann_return_net"],
            } for item in backtests],
        },
        "critic": {
            "critique_count": len(critiques),
            "promoted": 0,
            "killed": 1,
            "issue_counts": {"weak_rankic_stability": 1},
        },
        "evolution": {
            "next_generation_count": len(next_generation),
            "skipped_failed_count": 0,
            "next_factor_ids": [item["factor_id"] for item in next_generation],
            "skipped_factor_ids": [],
        },
        "data": {
            "status": _data_health_payload(cfg)["status"],
            "source_mode": _data_health_payload(cfg)["source_mode"],
            "rows": _data_health_payload(cfg)["rows"],
            "stocks": _data_health_payload(cfg)["stocks"],
            "dates": _data_health_payload(cfg)["dates"],
            "freshness": _data_health_payload(cfg)["freshness"],
        },
        "factor_database_write": {
            "status": "updated",
            "reason": "pipeline_complete",
            "saved_factor_count": len(backtests),
            "saved_factor_ids": [item["factor_id"] for item in backtests],
        },
    }


def _write_failure_memory(cfg: RunConfig, payload: dict | None = None) -> None:
    payload = payload or _failure_memory_payload(cfg)
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    (cfg.knowledge_root / "failure_memory.jsonl").parent.mkdir(parents=True, exist_ok=True)
    (cfg.knowledge_root / "failure_memory.jsonl").write_text(f"{text}\n", encoding="utf-8")


def _write_minimal_manifest(cfg: RunConfig, invocation: dict | bool | None = None) -> None:
    (cfg.run_dir / "daily_report.md").write_text(_current_daily_report_text(cfg), encoding="utf-8")
    (cfg.run_dir / "self_audit.md").write_text(_current_self_audit_markdown_text(cfg), encoding="utf-8")
    next_generation_payload = _next_generation_payload(cfg)
    repo_root = Path.cwd()
    run_daily_path = repo_root / "run_daily.sh"
    log_path = repo_root / "reports" / "daily_cron.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    placeholder_json = {
        "preflight.json": {"status": "ok", "checks": {"min_free_disk_ok": True, "required_dirs_writable": True}},
        "daily_events.json": _daily_events_payload(cfg),
        "research_ideas.json": _research_ideas_payload(cfg),
        "candidate_factors.json": _candidate_factor_payload(cfg),
        "dataset_manifest.json": _dataset_manifest_payload(cfg),
        "data_health.json": _data_health_payload(cfg),
        "backtest_results.json": _backtest_results_payload(cfg),
        "critique.json": _critique_payload(cfg),
        "next_generation_factors.json": next_generation_payload,
        "pipeline_state.json": {"status": "complete"},
        "run_audit.json": {
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
            "lock": {
                "pid": 123,
                "created_at": "2026-06-04T00:00:00+00:00",
                "run_date": cfg.run_date,
                "stale_after_minutes": cfg.lock_stale_minutes,
                "recovered_stale_lock": False,
                "stale_lock_age_seconds": None,
            },
            "state": {
                "run_date": cfg.run_date,
                "status": "complete",
                "started_at": "2026-06-04T00:00:00+00:00",
                "updated_at": "2026-06-04T00:01:00+00:00",
                "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
                "lock": {
                    "pid": 123,
                    "created_at": "2026-06-04T00:00:00+00:00",
                    "run_date": cfg.run_date,
                    "stale_after_minutes": cfg.lock_stale_minutes,
                    "recovered_stale_lock": False,
                    "stale_lock_age_seconds": None,
                },
                "retention": {"retention_days": cfg.retention_days, "removed": []},
            },
        },
        "schedule.json": {
            "agent": "schedule",
            "run_date": cfg.run_date,
            "cadence": "daily",
            "shell_entrypoint": True,
            "uses_run_daily_sh": True,
            "installed_automatically": False,
            "install_required": True,
            "day_of_month": "*",
            "month": "*",
            "day_of_week": "*",
            "repo_root": str(repo_root),
            "command": f"cd {repo_root} && bash {run_daily_path} >> {log_path} 2>&1",
            "script_path": str(run_daily_path),
            "script_exists": run_daily_path.exists(),
            "log_path": str(log_path),
            "log_parent": str(log_path.parent),
            "log_parent_exists": log_path.parent.exists(),
            "log_parent_writable": True,
            "cron_line": f"30 18 * * * cd {repo_root} && bash {run_daily_path} >> {log_path} 2>&1",
        },
        "gpu_alpha_submission.json": _gpu_alpha_submission_payload(cfg),
        "self_audit.json": _current_self_audit_payload(cfg),
    }
    for name, payload in placeholder_json.items():
        path = cfg.run_dir / name
        if not path.exists():
            write_json(path, payload)
    candidate_payload = _candidate_factor_payload(cfg)
    write_json(cfg.run_dir / "candidate_factors.json", candidate_payload)
    write_json(cfg.run_dir / "daily_events.json", _daily_events_payload(cfg))
    write_json(cfg.run_dir / "research_ideas.json", _research_ideas_payload(cfg))
    for factor in candidate_payload["factors"]:
        write_json(cfg.run_dir / "candidate_factors" / f"{factor['factor_id']}.json", factor)
    write_json(cfg.factor_library / f"{factor['factor_id']}.json", factor)
    backtest_payload = _backtest_results_payload(cfg)
    write_json(cfg.run_dir / "backtest_results.json", backtest_payload)
    for result in backtest_payload["results"]:
        write_json(cfg.run_dir / "backtest_results" / f"{result['factor_id']}.json", result)
    write_json(cfg.run_dir / "critique.json", _critique_payload(cfg))
    write_json(cfg.run_dir / "next_generation_factors.json", next_generation_payload)
    for factor in next_generation_payload["next_generation_factors"]:
        write_json(cfg.run_dir / "next_generation_factors" / f"{factor['factor_id']}.json", factor)
    write_json(cfg.knowledge_root / "factor_database" / "factors.json", _factor_database_payload(cfg))
    write_json(cfg.run_dir / "self_audit.json", _current_self_audit_payload(cfg))
    write_json(cfg.run_dir / "dataset_manifest.json", _dataset_manifest_payload(cfg))
    write_json(cfg.run_dir / "data_health.json", _data_health_payload(cfg))
    for agent in ["market_intelligence", "research_agent"]:
        write_json(cfg.run_dir / "source_snapshots" / f"{agent}.json", _source_snapshot_payload(cfg, agent))
    dataset_path = cfg.run_dir / "daily_dataset.parquet"
    if not dataset_path.exists():
        dataset_path.write_bytes(b"test parquet placeholder")
    failure_path = cfg.run_dir / "failure_analysis.md"
    if not failure_path.exists():
        failure_path.write_text(_failure_analysis_text(cfg), encoding="utf-8")
    cron_path = cfg.run_dir / "cron_example.txt"
    if not cron_path.exists():
        schedule_payload = read_json(cfg.run_dir / "schedule.json", {})
        cron_path.write_text(
            "# Example daily cron entry. Review before installing with crontab -e.\n"
            f"{schedule_payload.get('cron_line')}\n",
            encoding="utf-8",
        )
    (cfg.output_root / "READINESS_REPORT.md").parent.mkdir(parents=True, exist_ok=True)
    (cfg.output_root / "READINESS_REPORT.md").write_text("# Readiness\n", encoding="utf-8")
    write_json(cfg.output_root / "READINESS_REPORT.json", {
        "status": "production_ready",
        "readiness_score": 1.0,
        "blockers": [],
    })
    if invocation is not False:
        record = {
            "run_date": cfg.run_date,
            "started_at": f"{cfg.run_date[:4]}-{cfg.run_date[4:6]}-{cfg.run_date[6:]}T00:00:00+00:00",
            "finished_at": f"{cfg.run_date[:4]}-{cfg.run_date[4:6]}-{cfg.run_date[6:]}T00:00:01+00:00",
            "status": "success",
            "exit_code": 0,
            "duration_sec": 1.0,
            "host": "test-host",
            "pid": 123,
            "config_loaded": True,
            "shell_entrypoint": True,
            "entrypoint_script": str(run_daily_path),
            "entrypoint_script_exists": True,
            "entrypoint_command": "bash run_daily.sh",
        }
        if isinstance(invocation, dict):
            record.update(invocation)
        write_json(cfg.output_root / "run_daily_invocation_latest.json", record)
    write_json(
        cfg.output_root / "gpu_alpha_submission_latest.json",
        read_json(cfg.run_dir / "gpu_alpha_submission.json", {}),
    )
    _write_latest_from_jsonl(cfg.knowledge_root / "run_history.jsonl", cfg.knowledge_root / "run_history_latest.json")
    _write_latest_from_jsonl(cfg.knowledge_root / "research_log.jsonl", cfg.knowledge_root / "research_log_latest.json")
    _write_latest_from_jsonl(cfg.knowledge_root / "source_snapshots.jsonl", cfg.knowledge_root / "source_snapshots_latest.json")
    _write_latest_from_jsonl(cfg.knowledge_root / "data_health.jsonl", cfg.knowledge_root / "data_health_latest.json")
    artifact_manifest.run(cfg)
    verify_manifest(cfg)
    artifact_manifest.run(cfg)


def _production_run_record(run_date: str, agent_status: dict[str, str]) -> dict:
    market_kinds = sorted(readiness_report.REQUIRED_MARKET_SOURCE_KINDS)
    research_kinds = sorted(readiness_report.REQUIRED_RESEARCH_SOURCE_KINDS)
    event_count = len(readiness_report.REQUIRED_MARKET_SOURCE_KINDS)
    market_source_quality = {
        "mode": "live",
        "total_sources": len(market_kinds),
        "ok_sources": len(market_kinds),
        "error_sources": 0,
        "coverage_ratio": 1.0,
        "covered_kinds": market_kinds,
        "missing_kinds": [],
        "fallback_used": False,
    }
    research_source_quality = {
        **market_source_quality,
        "total_sources": len(research_kinds),
        "ok_sources": len(research_kinds),
        "covered_kinds": research_kinds,
    }
    data_freshness = {
        "status": "ok",
        "staleness_days": 0,
        "max_allowed_staleness_days": 7,
        "note": "",
    }
    data_checks = {
        "has_rows": True,
        "has_required_columns": True,
        "no_duplicate_keys": True,
        "has_multiple_dates": True,
        "has_multiple_stocks": True,
        "data_freshness_ok": True,
        "required_data_domains_usable": True,
    }
    return {
        "run_date": run_date,
        "recorded_at": f"{run_date[:4]}-{run_date[4:6]}-{run_date[6:]}T00:00:02+00:00",
        "pipeline_status": "complete",
        "self_audit_status": "pass",
        "self_audit_score": 1.0,
        "agent_status": agent_status,
        "market_source_quality": market_source_quality,
        "research_source_quality": research_source_quality,
        "data_health_status": "ok",
        "data_source_mode": "local_csv",
        "data_freshness": data_freshness,
        "data_checks": data_checks,
        "data_domain_coverage": {
            "ohlcv": {"usable": True},
            "financial_metric": {"usable": True},
            "industry": {"usable": True},
            "moneyflow": {"usable": True},
            "risk_flags": {"usable": True},
            "derived_features": {"usable": True},
        },
        "counts": {
            "events": event_count,
            "ideas": 1,
            "candidate_factors": 1,
            "backtest_results": 1,
            "raw_candidates": 1,
            "promoted": 0,
            "killed": 1,
        },
    }


def _write_successful_invocations(
    cfg: RunConfig,
    run_dates: list[str],
    entrypoint_script: Path | None = None,
) -> None:
    entrypoint_script = entrypoint_script or (Path.cwd() / "run_daily.sh")
    for i, run_date in enumerate(run_dates):
        append_jsonl(cfg.output_root / "run_daily_invocations.jsonl", {
            "run_date": run_date,
            "started_at": f"{run_date[:4]}-{run_date[4:6]}-{run_date[6:]}T00:00:00+00:00",
            "finished_at": f"{run_date[:4]}-{run_date[4:6]}-{run_date[6:]}T00:00:01+00:00",
            "status": "success",
            "exit_code": 0,
            "duration_sec": 1.0,
            "host": "test-host",
            "pid": 1000 + i,
            "config_loaded": True,
            "shell_entrypoint": True,
            "entrypoint_script": str(entrypoint_script),
            "entrypoint_script_exists": True,
            "entrypoint_command": "bash run_daily.sh",
        })


def _write_production_source_snapshots(cfg: RunConfig, run_dates: list[str]) -> None:
    for run_date in run_dates:
        for agent in ["market_intelligence", "research_agent"]:
            append_jsonl(cfg.knowledge_root / "source_snapshots.jsonl", _source_snapshot_payload(cfg, agent, run_date))


def _write_production_data_artifacts(cfg: RunConfig, run_dates: list[str]) -> None:
    for run_date in run_dates:
        append_jsonl(cfg.knowledge_root / "data_health.jsonl", _data_health_latest_payload(cfg, run_date))
    write_json(cfg.knowledge_root / "data_health_latest.json", _data_health_latest_payload(cfg, run_dates[-1]))


def _write_complete_knowledge_saves(cfg: RunConfig, run_dates: list[str]) -> None:
    for run_date in run_dates:
        append_jsonl(cfg.knowledge_root / "research_log.jsonl", {
            "run_date": run_date,
            "recorded_at": f"{run_date[:4]}-{run_date[4:6]}-{run_date[6:]}T00:00:03+00:00",
            "pipeline": {"run_quality": "complete", "pipeline_status": "running"},
            "research": {"idea_count": 1},
            "backtest": {"result_count": 1, "result_factor_ids": ["F1"]},
            "factor_database_write": {
                "status": "updated",
                "reason": "pipeline_complete",
                "saved_factor_count": 1,
                "saved_factor_ids": ["F1"],
            },
        })
    if run_dates[-1] == cfg.run_date:
        write_json(cfg.knowledge_root / "research_log_latest.json", _research_log_payload(cfg))
    else:
        write_json(cfg.knowledge_root / "research_log_latest.json", {
            "run_date": run_dates[-1],
            "recorded_at": f"{run_dates[-1][:4]}-{run_dates[-1][4:6]}-{run_dates[-1][6:]}T00:00:03+00:00",
            "pipeline": {"run_quality": "complete"},
            "backtest": {"result_count": 1, "result_factor_ids": ["F1"]},
            "factor_database_write": {
                "status": "updated",
                "saved_factor_count": 1,
                "saved_factor_ids": ["F1"],
            },
        })


def _run_date(offset_days: int, start: date = date(2025, 1, 1)) -> str:
    return (start + timedelta(days=offset_days)).strftime("%Y%m%d")


def _run_dates_ending_at(end_yyyymmdd: str, days: int = 365) -> list[str]:
    end = date.fromisoformat(f"{end_yyyymmdd[:4]}-{end_yyyymmdd[4:6]}-{end_yyyymmdd[6:]}")
    start = end - timedelta(days=days - 1)
    return [(start + timedelta(days=i)).strftime("%Y%m%d") for i in range(days)]


def _cfg(tmp_path: Path) -> RunConfig:
    return RunConfig(
        run_date="20260604",
        data_root=tmp_path / "missing_data",
        output_root=tmp_path / "reports",
        knowledge_root=tmp_path / "knowledge_base",
        factor_library=tmp_path / "factor_library",
        offline=True,
    )


def _write_fake_repository_deliverables(
    root: Path,
    include_readme: bool = True,
    readme_documents_readiness: bool = True,
    audited_entrypoint: bool = True,
) -> None:
    if include_readme:
        readme = "# Test README\n"
        if readme_documents_readiness:
            readme += (
                "\n"
                "Run the daily research system with `bash run_daily.sh`.\n"
                "The shell entrypoint records evidence in `reports/run_daily_invocations.jsonl`.\n"
                "GPU alpha acceleration uses Slurm and records evidence in `gpu_alpha_submission_latest.json`.\n"
                "Production readiness requires 365 consecutive unique dates with audited evidence.\n"
                "Until that proof exists, `READINESS_REPORT` remains `not_production_ready`.\n"
            )
        (root / "README.md").write_text(readme, encoding="utf-8")
    run_daily = root / "run_daily.sh"
    if audited_entrypoint:
        run_daily.write_text(
            "#!/usr/bin/env bash\n"
            "export QUANT_RUN_DAILY_SH=1\n"
            "export QUANT_RUN_DAILY_SCRIPT=\"$PWD/run_daily.sh\"\n"
            "export QUANT_RUN_DAILY_COMMAND=\"bash run_daily.sh\"\n"
            "python -m agent.run_entrypoint\n",
            encoding="utf-8",
        )
    else:
        run_daily.write_text("#!/usr/bin/env bash\npython -m agent.daily_pipeline\n", encoding="utf-8")
    run_daily.chmod(0o755)
    for rel in readiness_report.REQUIRED_AGENT_MODULE_FILES:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# test module\n", encoding="utf-8")
    for rel in readiness_report.REQUIRED_BACKTEST_ENGINE_FILES:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# test module\n", encoding="utf-8")
    for rel in readiness_report.REQUIRED_SCRIPT_FILES:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
        if path.suffix == ".sh":
            path.chmod(0o755)


def test_self_audit_passes_after_full_pipeline(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)

    outputs = daily_pipeline.run(cfg)

    audit = outputs["self_audit"]
    assert audit["status"] == "pass"
    assert audit["score"] >= 0.9
    assert (cfg.run_dir / "self_audit.json").exists()
    assert (cfg.run_dir / "self_audit.md").exists()
    readiness = outputs["readiness_report"]
    assert readiness["status"] == "not_production_ready"
    assert not readiness["checks"]["has_365_successful_runs"]
    assert not readiness["checks"]["latest_data_is_production_evidence"]
    assert not readiness["checks"]["latest_market_sources_are_production_evidence"]
    assert not readiness["checks"]["latest_research_sources_are_production_evidence"]
    assert not readiness["checks"]["has_365_production_evidence_runs"]
    assert "365-day unattended proof missing" in readiness["blockers"][0]
    assert (cfg.output_root / "READINESS_REPORT.json").exists()
    assert (cfg.output_root / "READINESS_REPORT.md").exists()


def test_self_audit_warns_when_required_files_missing(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)

    audit = self_audit.run(cfg)

    assert audit["status"] == "warning"
    assert not audit["checks"]["required_files_present"]


def test_readiness_requires_365_successful_audited_runs(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    run_dates = _run_dates_ending_at(cfg.run_date)
    for i in range(365):
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", _production_run_record(run_dates[i], agent_status))
    _write_successful_invocations(cfg, run_dates)
    _write_production_data_artifacts(cfg, run_dates)
    write_json(cfg.knowledge_root / "factor_database" / "factors.json", {
        "factors": [{"factor_id": "F1", "decision": "kill"}]
    })
    _write_failure_memory(cfg)
    _write_complete_knowledge_saves(cfg, run_dates)
    _write_production_source_snapshots(cfg, run_dates)
    write_json(cfg.run_dir / "self_audit.json", {"status": "pass", "score": 1.0})
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    _write_minimal_manifest(cfg)

    payload = readiness_report.run(cfg)

    assert payload["status"] == "production_ready"
    assert payload["checks"]["has_365_successful_runs"]
    assert payload["checks"]["latest_run_history_matches_run_date"]
    assert payload["checks"]["latest_run_history_recorded_at_matches_run_date"]
    assert payload["checks"]["latest_run_history_matches_current_outputs"]
    assert payload["checks"]["has_365_production_evidence_runs"]
    assert payload["checks"]["has_365_unique_successful_run_dates"]
    assert payload["checks"]["has_365_unique_production_evidence_dates"]
    assert payload["checks"]["has_365_consecutive_successful_run_dates"]
    assert payload["checks"]["has_365_consecutive_production_evidence_dates"]
    assert payload["checks"]["research_log_present"]
    assert payload["checks"]["latest_schedule_is_daily_run_daily"]
    assert payload["checks"]["latest_cron_example_matches_schedule"]
    assert payload["checks"]["latest_daily_report_is_current_evidence"]
    assert payload["checks"]["latest_candidate_factor_files_match_payload"]
    assert payload["checks"]["latest_factor_library_matches_candidates"]
    assert payload["checks"]["latest_candidate_factors_avoid_historical_failures"]
    assert payload["checks"]["latest_backtest_result_files_match_payload"]
    assert payload["checks"]["latest_backtest_dataset_provenance_matches_manifest"]
    assert payload["checks"]["latest_factor_database_matches_backtests"]
    assert payload["checks"]["latest_failure_analysis_matches_critique"]
    assert payload["checks"]["latest_next_generation_files_match_payload"]
    assert payload["checks"]["latest_research_log_matches_current_outputs"]
    assert payload["checks"]["latest_data_health_latest_matches_current_outputs"]
    assert payload["checks"]["latest_source_snapshots_match_current_outputs"]
    assert payload["checks"]["latest_gpu_alpha_submission_is_current_evidence"]
    assert payload["gpu_alpha_submission"]["current_evidence"]
    assert payload["gpu_alpha_submission"]["status"] == "skipped"
    assert payload["gpu_alpha_submission"]["skip_reason"] == "offline_run"
    assert payload["checks"]["artifact_manifest_latest_matches_current_manifest"]
    assert payload["checks"]["artifact_manifest_verification_matches_current_manifest"]
    assert payload["checks"]["artifact_verification_latest_matches_current_verification"]
    assert payload["checks"]["readiness_markdown_matches_current_json"]
    assert payload["readiness_markdown"]["matches_current_json"]
    assert payload["checks"]["repository_deliverables_present"]
    assert payload["repository_deliverables"]["all_present"]
    assert payload["repository_deliverables"]["run_daily_executable"]
    assert payload["repository_deliverables"]["run_daily_uses_audited_entrypoint"]
    assert payload["repository_deliverables"]["readme_documents_audited_readiness"]
    assert payload["repository_deliverables"]["missing_readme_snippets"] == []
    assert payload["checks"]["latest_self_audit_matches_current_outputs"]
    assert payload["checks"]["latest_killed_factor_failure_memory_details_match"]
    assert payload["history"]["latest_matches_current_outputs"]
    assert payload["history"]["latest_recorded_at_matches_run_date"]
    assert payload["factor_library_evidence"]["candidate_failed_memory_matches"] == []
    assert payload["factor_library_evidence"]["candidates_avoid_historical_failures"]
    assert payload["checks"]["latest_run_has_research_activity"]
    assert payload["checks"]["has_365_research_activity_runs"]
    assert payload["checks"]["has_365_unique_research_activity_dates"]
    assert payload["checks"]["has_365_consecutive_research_activity_dates"]
    assert payload["checks"]["production_evidence_dates_have_research_activity"]
    assert payload["checks"]["has_365_knowledge_save_dates"]
    assert payload["checks"]["has_365_consecutive_knowledge_save_dates"]
    assert payload["checks"]["production_evidence_dates_have_knowledge_saves"]
    assert payload["checks"]["data_health_log_present"]
    assert payload["checks"]["has_365_data_artifact_dates"]
    assert payload["checks"]["has_365_consecutive_data_artifact_dates"]
    assert payload["checks"]["production_evidence_dates_have_data_artifacts"]
    assert payload["checks"]["run_daily_invocation_present"]
    assert payload["checks"]["run_daily_invocation_success"]
    assert payload["checks"]["run_daily_invocation_matches_run_date"]
    assert payload["checks"]["run_daily_invocation_timestamps_match_run_date"]
    assert payload["run_daily_invocation"]["timestamps_match_run_date"]
    assert payload["run_daily_invocation"]["expected_entrypoint_script"] == str(Path.cwd() / "run_daily.sh")
    assert payload["checks"]["has_365_successful_run_daily_invocations"]
    assert payload["checks"]["has_365_unique_successful_run_daily_invocation_dates"]
    assert payload["checks"]["has_365_consecutive_successful_run_daily_invocation_dates"]
    assert payload["checks"]["production_evidence_dates_have_successful_run_daily_invocations"]
    assert payload["checks"]["has_365_source_snapshot_dates"]
    assert payload["checks"]["has_365_consecutive_source_snapshot_dates"]
    assert payload["checks"]["production_evidence_dates_have_source_snapshots"]
    assert payload["blockers"] == []
    markdown = (cfg.output_root / "READINESS_REPORT.md").read_text(encoding="utf-8")
    assert "- artifact manifest verification matches current manifest: True" in markdown
    assert "- artifact verification latest matches current verification: True" in markdown
    assert "- artifact verification manifest generated at:" in markdown
    assert "- readiness_markdown_matches_current_json: ok" in markdown
    assert "- repository_deliverables_present: ok" in markdown
    assert "- latest_run_history_recorded_at_matches_run_date: ok" in markdown
    assert "- run_daily_invocation_timestamps_match_run_date: ok" in markdown
    assert "- latest run_history recorded_at matches run_date: True" in markdown
    assert "- run_daily invocation timestamps match run_date: True" in markdown
    assert "- repository deliverables present: True" in markdown
    assert "- README documents audited readiness: True" in markdown
    assert "- README missing snippets: none" in markdown
    assert "- run_daily uses audited entrypoint: True" in markdown
    assert "- gpu alpha submission: skipped job=None current=True" in markdown


def test_readiness_blocks_stale_gpu_alpha_submission_latest(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    run_dates = _run_dates_ending_at(cfg.run_date)
    for run_date in run_dates:
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", _production_run_record(run_date, agent_status))
    _write_successful_invocations(cfg, run_dates)
    _write_production_data_artifacts(cfg, run_dates)
    write_json(cfg.knowledge_root / "factor_database" / "factors.json", {
        "factors": [{"factor_id": "F1", "decision": "kill"}]
    })
    _write_failure_memory(cfg)
    _write_complete_knowledge_saves(cfg, run_dates)
    _write_production_source_snapshots(cfg, run_dates)
    _write_minimal_manifest(cfg)
    stale = _gpu_alpha_submission_payload(cfg, run_date="20260603")
    write_json(cfg.output_root / "gpu_alpha_submission_latest.json", stale)
    artifact_manifest.run(cfg)
    verify_manifest(cfg)
    artifact_manifest.run(cfg)

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert not payload["checks"]["latest_gpu_alpha_submission_is_current_evidence"]
    assert "latest gpu_alpha_submission evidence does not prove Slurm-only GPU submission/skip semantics" in "\n".join(payload["blockers"])


def test_readiness_blocks_missing_repository_deliverable(tmp_path: Path, monkeypatch) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    run_dates = _run_dates_ending_at(cfg.run_date)
    for run_date in run_dates:
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", _production_run_record(run_date, agent_status))
    _write_successful_invocations(cfg, run_dates)
    _write_production_data_artifacts(cfg, run_dates)
    _write_complete_knowledge_saves(cfg, run_dates)
    _write_production_source_snapshots(cfg, run_dates)
    write_json(cfg.knowledge_root / "factor_database" / "factors.json", {
        "factors": [{"factor_id": "F1", "decision": "kill"}]
    })
    _write_failure_memory(cfg)
    write_json(cfg.run_dir / "self_audit.json", {"status": "pass", "score": 1.0})
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    _write_minimal_manifest(cfg)
    repo_root = tmp_path / "repo_without_readme"
    repo_root.mkdir()
    _write_fake_repository_deliverables(repo_root, include_readme=False)
    monkeypatch.setattr(readiness_report, "_repository_root", lambda: repo_root)

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert not payload["checks"]["repository_deliverables_present"]
    assert "README.md" in payload["repository_deliverables"]["missing_files"]
    assert "repository deliverables are missing or not usable" in "\n".join(payload["blockers"])


def test_readiness_blocks_run_daily_without_audited_entrypoint(tmp_path: Path, monkeypatch) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    run_dates = _run_dates_ending_at(cfg.run_date)
    for run_date in run_dates:
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", _production_run_record(run_date, agent_status))
    _write_successful_invocations(cfg, run_dates)
    _write_production_data_artifacts(cfg, run_dates)
    _write_complete_knowledge_saves(cfg, run_dates)
    _write_production_source_snapshots(cfg, run_dates)
    write_json(cfg.knowledge_root / "factor_database" / "factors.json", {
        "factors": [{"factor_id": "F1", "decision": "kill"}]
    })
    _write_failure_memory(cfg)
    write_json(cfg.run_dir / "self_audit.json", {"status": "pass", "score": 1.0})
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    _write_minimal_manifest(cfg)
    repo_root = tmp_path / "repo_bypasses_entrypoint"
    repo_root.mkdir()
    _write_fake_repository_deliverables(repo_root, audited_entrypoint=False)
    monkeypatch.setattr(readiness_report, "_repository_root", lambda: repo_root)

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert not payload["checks"]["repository_deliverables_present"]
    assert payload["repository_deliverables"]["run_daily_executable"]
    assert not payload["repository_deliverables"]["run_daily_uses_audited_entrypoint"]
    assert "run_daily_uses_audited_entrypoint=False" in "\n".join(payload["blockers"])


def test_readiness_blocks_missing_required_support_module(tmp_path: Path, monkeypatch) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    run_dates = _run_dates_ending_at(cfg.run_date)
    for run_date in run_dates:
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", _production_run_record(run_date, agent_status))
    _write_successful_invocations(cfg, run_dates)
    _write_production_data_artifacts(cfg, run_dates)
    _write_complete_knowledge_saves(cfg, run_dates)
    _write_production_source_snapshots(cfg, run_dates)
    write_json(cfg.knowledge_root / "factor_database" / "factors.json", {
        "factors": [{"factor_id": "F1", "decision": "kill"}]
    })
    _write_failure_memory(cfg)
    _write_minimal_manifest(cfg)
    repo_root = tmp_path / "repo_missing_support_module"
    repo_root.mkdir()
    _write_fake_repository_deliverables(repo_root)
    (repo_root / "agent" / "gpu_alpha_submission.py").unlink()
    monkeypatch.setattr(readiness_report, "_repository_root", lambda: repo_root)

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert not payload["checks"]["repository_deliverables_present"]
    assert "agent/gpu_alpha_submission.py" in payload["repository_deliverables"]["missing_files"]
    assert "repository deliverables are missing or not usable" in "\n".join(payload["blockers"])


def test_readiness_blocks_missing_required_slurm_script(tmp_path: Path, monkeypatch) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    run_dates = _run_dates_ending_at(cfg.run_date)
    for run_date in run_dates:
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", _production_run_record(run_date, agent_status))
    _write_successful_invocations(cfg, run_dates)
    _write_production_data_artifacts(cfg, run_dates)
    _write_complete_knowledge_saves(cfg, run_dates)
    _write_production_source_snapshots(cfg, run_dates)
    write_json(cfg.knowledge_root / "factor_database" / "factors.json", {
        "factors": [{"factor_id": "F1", "decision": "kill"}]
    })
    _write_failure_memory(cfg)
    _write_minimal_manifest(cfg)
    repo_root = tmp_path / "repo_missing_slurm_script"
    repo_root.mkdir()
    _write_fake_repository_deliverables(repo_root)
    (repo_root / "scripts" / "submit_alpha_gpu_backtest.sh").unlink()
    monkeypatch.setattr(readiness_report, "_repository_root", lambda: repo_root)

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert not payload["checks"]["repository_deliverables_present"]
    assert "scripts/submit_alpha_gpu_backtest.sh" in payload["repository_deliverables"]["missing_files"]
    assert not payload["repository_deliverables"]["script_files_present"]


def test_readiness_blocks_readme_without_audited_readiness_docs(tmp_path: Path, monkeypatch) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    run_dates = _run_dates_ending_at(cfg.run_date)
    for run_date in run_dates:
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", _production_run_record(run_date, agent_status))
    _write_successful_invocations(cfg, run_dates)
    _write_production_data_artifacts(cfg, run_dates)
    _write_complete_knowledge_saves(cfg, run_dates)
    _write_production_source_snapshots(cfg, run_dates)
    write_json(cfg.knowledge_root / "factor_database" / "factors.json", {
        "factors": [{"factor_id": "F1", "decision": "kill"}]
    })
    _write_failure_memory(cfg)
    write_json(cfg.run_dir / "self_audit.json", {"status": "pass", "score": 1.0})
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    _write_minimal_manifest(cfg)
    repo_root = tmp_path / "repo_with_weak_readme"
    repo_root.mkdir()
    _write_fake_repository_deliverables(repo_root, readme_documents_readiness=False)
    monkeypatch.setattr(readiness_report, "_repository_root", lambda: repo_root)

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert not payload["checks"]["repository_deliverables_present"]
    assert not payload["repository_deliverables"]["readme_documents_audited_readiness"]
    assert "bash run_daily.sh" in payload["repository_deliverables"]["missing_readme_snippets"]
    assert "gpu_alpha_submission_latest.json" in payload["repository_deliverables"]["missing_readme_snippets"]
    assert "readme_documents_audited_readiness=False" in "\n".join(payload["blockers"])


def test_readiness_blocks_mismatched_markdown_renderer(tmp_path: Path, monkeypatch) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    run_dates = _run_dates_ending_at(cfg.run_date)
    for run_date in run_dates:
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", _production_run_record(run_date, agent_status))
    _write_successful_invocations(cfg, run_dates)
    _write_production_data_artifacts(cfg, run_dates)
    _write_complete_knowledge_saves(cfg, run_dates)
    _write_production_source_snapshots(cfg, run_dates)
    write_json(cfg.knowledge_root / "factor_database" / "factors.json", {
        "factors": [{"factor_id": "F1", "decision": "kill"}]
    })
    _write_failure_memory(cfg)
    write_json(cfg.run_dir / "self_audit.json", {"status": "pass", "score": 1.0})
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    _write_minimal_manifest(cfg)

    def stale_markdown(config, payload):
        return "# Quant Research System Readiness Report\n\nRun date: 20260603\nStatus: stale\n"

    monkeypatch.setattr(readiness_report, "render_readiness_markdown", stale_markdown)

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert not payload["checks"]["readiness_markdown_matches_current_json"]
    assert not payload["readiness_markdown"]["matches_current_json"]
    assert "READINESS_REPORT.md does not match current READINESS_REPORT.json" in "\n".join(payload["blockers"])


def test_readiness_blocks_non_daily_schedule(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    run_dates = _run_dates_ending_at(cfg.run_date)
    for run_date in run_dates:
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", _production_run_record(run_date, agent_status))
    _write_successful_invocations(cfg, run_dates)
    _write_production_data_artifacts(cfg, run_dates)
    _write_complete_knowledge_saves(cfg, run_dates)
    _write_production_source_snapshots(cfg, run_dates)
    write_json(cfg.knowledge_root / "factor_database" / "factors.json", {
        "factors": [{"factor_id": "F1", "decision": "kill"}]
    })
    (cfg.knowledge_root / "failure_memory.jsonl").write_text('{"factor_id":"F1"}\n', encoding="utf-8")
    write_json(cfg.run_dir / "self_audit.json", {"status": "pass", "score": 1.0})
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    _write_minimal_manifest(cfg)
    schedule_path = cfg.run_dir / "schedule.json"
    schedule_payload = read_json(schedule_path, {})
    schedule_payload.update({
        "cadence": "weekday",
        "day_of_week": "1-5",
        "cron_line": "30 18 * * 1-5 cd /repo && bash /repo/run_daily.sh",
    })
    write_json(schedule_path, schedule_payload)
    artifact_manifest.run(cfg)

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert not payload["checks"]["latest_schedule_is_daily_run_daily"]
    assert "latest schedule does not prove daily bash run_daily.sh cadence" in "\n".join(payload["blockers"])
    assert payload["schedule_evidence"]["daily_run_daily"] is False


def test_readiness_blocks_stale_schedule_run_date(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    daily_pipeline.run(cfg)
    schedule_path = cfg.run_dir / "schedule.json"
    schedule_payload = read_json(schedule_path, {})
    schedule_payload["run_date"] = "20260603"
    write_json(schedule_path, schedule_payload)
    artifact_manifest.run(cfg)

    payload = readiness_report.run(cfg)

    assert not payload["checks"]["latest_schedule_is_daily_run_daily"]
    assert payload["schedule_evidence"]["daily_run_daily"] is False
    assert payload["schedule_evidence"]["run_date"] == "20260603"
    assert "latest schedule does not prove daily bash run_daily.sh cadence" in "\n".join(payload["blockers"])


def test_readiness_blocks_schedule_with_missing_run_daily_script(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    run_dates = _run_dates_ending_at(cfg.run_date)
    for run_date in run_dates:
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", _production_run_record(run_date, agent_status))
    _write_successful_invocations(cfg, run_dates)
    _write_production_data_artifacts(cfg, run_dates)
    _write_complete_knowledge_saves(cfg, run_dates)
    _write_production_source_snapshots(cfg, run_dates)
    write_json(cfg.knowledge_root / "factor_database" / "factors.json", {
        "factors": [{"factor_id": "F1", "decision": "kill"}]
    })
    (cfg.knowledge_root / "failure_memory.jsonl").write_text('{"factor_id":"F1"}\n', encoding="utf-8")
    write_json(cfg.run_dir / "self_audit.json", {"status": "pass", "score": 1.0})
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    _write_minimal_manifest(cfg)
    schedule_path = cfg.run_dir / "schedule.json"
    schedule_payload = read_json(schedule_path, {})
    schedule_payload["script_path"] = str(tmp_path / "missing" / "run_daily.sh")
    schedule_payload["script_exists"] = False
    write_json(schedule_path, schedule_payload)
    artifact_manifest.run(cfg)

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert not payload["checks"]["latest_schedule_is_daily_run_daily"]
    assert payload["schedule_evidence"]["script_exists"] is False
    assert "latest schedule does not prove daily bash run_daily.sh cadence" in "\n".join(payload["blockers"])


def test_readiness_blocks_schedule_with_unusable_cron_log_dir(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    run_dates = _run_dates_ending_at(cfg.run_date)
    for run_date in run_dates:
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", _production_run_record(run_date, agent_status))
    _write_successful_invocations(cfg, run_dates)
    _write_production_data_artifacts(cfg, run_dates)
    _write_complete_knowledge_saves(cfg, run_dates)
    _write_production_source_snapshots(cfg, run_dates)
    write_json(cfg.knowledge_root / "factor_database" / "factors.json", {
        "factors": [{"factor_id": "F1", "decision": "kill"}]
    })
    (cfg.knowledge_root / "failure_memory.jsonl").write_text(
        f'{{"run_date":"{cfg.run_date}","factor_id":"F1","formula_key":"rank(ret_5)"}}\n',
        encoding="utf-8",
    )
    write_json(cfg.run_dir / "self_audit.json", {"status": "pass", "score": 1.0})
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    _write_minimal_manifest(cfg)
    schedule_path = cfg.run_dir / "schedule.json"
    schedule_payload = read_json(schedule_path, {})
    missing_log = tmp_path / "missing_reports" / "daily_cron.log"
    schedule_payload["log_path"] = str(missing_log)
    schedule_payload["log_parent"] = str(missing_log.parent)
    schedule_payload["log_parent_exists"] = False
    schedule_payload["log_parent_writable"] = False
    schedule_payload["command"] = schedule_payload["command"].replace(
        "daily_cron.log",
        str(missing_log),
    )
    schedule_payload["cron_line"] = schedule_payload["cron_line"].replace(
        "daily_cron.log",
        str(missing_log),
    )
    write_json(schedule_path, schedule_payload)
    artifact_manifest.run(cfg)

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert not payload["checks"]["latest_schedule_is_daily_run_daily"]
    assert payload["schedule_evidence"]["log_parent_exists"] is False
    assert payload["schedule_evidence"]["log_parent_writable"] is False
    assert "latest schedule does not prove daily bash run_daily.sh cadence" in "\n".join(payload["blockers"])


def test_readiness_blocks_cron_example_that_does_not_match_schedule(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    run_dates = _run_dates_ending_at(cfg.run_date)
    for run_date in run_dates:
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", _production_run_record(run_date, agent_status))
    _write_successful_invocations(cfg, run_dates)
    _write_production_data_artifacts(cfg, run_dates)
    _write_complete_knowledge_saves(cfg, run_dates)
    _write_production_source_snapshots(cfg, run_dates)
    write_json(cfg.knowledge_root / "factor_database" / "factors.json", {
        "factors": [{"factor_id": "F1", "decision": "kill"}]
    })
    (cfg.knowledge_root / "failure_memory.jsonl").write_text(
        f'{{"run_date":"{cfg.run_date}","factor_id":"F1","formula_key":"rank(ret_5)"}}\n',
        encoding="utf-8",
    )
    write_json(cfg.run_dir / "self_audit.json", {"status": "pass", "score": 1.0})
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    _write_minimal_manifest(cfg)
    (cfg.run_dir / "cron_example.txt").write_text(
        "# stale weekday cron entry\n"
        "30 18 * * 1-5 cd /old && bash /old/run_daily.sh >> reports/daily_cron.log 2>&1\n",
        encoding="utf-8",
    )
    artifact_manifest.run(cfg)

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert payload["checks"]["latest_schedule_is_daily_run_daily"]
    assert not payload["checks"]["latest_cron_example_matches_schedule"]
    assert payload["schedule_evidence"]["cron_example_present"] is True
    assert payload["schedule_evidence"]["cron_example_matches_schedule"] is False
    assert "latest cron_example.txt does not match schedule.json cron_line" in "\n".join(payload["blockers"])


def test_readiness_blocks_stale_daily_report_evidence(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    run_dates = _run_dates_ending_at(cfg.run_date)
    for run_date in run_dates:
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", _production_run_record(run_date, agent_status))
    _write_successful_invocations(cfg, run_dates)
    _write_production_data_artifacts(cfg, run_dates)
    _write_complete_knowledge_saves(cfg, run_dates)
    _write_production_source_snapshots(cfg, run_dates)
    write_json(cfg.knowledge_root / "factor_database" / "factors.json", {
        "factors": [{"factor_id": "F1", "decision": "kill"}]
    })
    (cfg.knowledge_root / "failure_memory.jsonl").write_text(
        f'{{"run_date":"{cfg.run_date}","factor_id":"F1","formula_key":"rank(ret_5)"}}\n',
        encoding="utf-8",
    )
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    _write_minimal_manifest(cfg)
    (cfg.run_dir / "daily_report.md").write_text(
        "# Daily Quant Research Report\n\nRun date: 20260603\n\n## Summary\n\n- events collected: 3\n",
        encoding="utf-8",
    )
    artifact_manifest.run(cfg)

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert not payload["checks"]["latest_daily_report_is_current_evidence"]
    assert payload["daily_report_evidence"]["present"] is True
    assert payload["daily_report_evidence"]["current_complete_evidence"] is False
    assert "latest daily_report.md does not prove current run summary" in "\n".join(payload["blockers"])


def test_readiness_blocks_daily_report_count_mismatch(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    run_dates = _run_dates_ending_at(cfg.run_date)
    for run_date in run_dates:
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", _production_run_record(run_date, agent_status))
    _write_successful_invocations(cfg, run_dates)
    _write_production_data_artifacts(cfg, run_dates)
    _write_complete_knowledge_saves(cfg, run_dates)
    _write_production_source_snapshots(cfg, run_dates)
    _write_failure_memory(cfg)
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    _write_minimal_manifest(cfg)
    report = (cfg.run_dir / "daily_report.md").read_text(encoding="utf-8")
    report = report.replace("- backtested factors: 1\n", "- backtested factors: 999\n")
    (cfg.run_dir / "daily_report.md").write_text(report, encoding="utf-8")
    artifact_manifest.run(cfg)

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert not payload["checks"]["latest_daily_report_is_current_evidence"]
    assert payload["daily_report_evidence"]["current_complete_evidence"] is False
    assert "latest daily_report.md does not prove current run summary" in "\n".join(payload["blockers"])


def test_readiness_blocks_daily_report_without_readiness_summary(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    run_dates = _run_dates_ending_at(cfg.run_date)
    for run_date in run_dates:
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", _production_run_record(run_date, agent_status))
    _write_successful_invocations(cfg, run_dates)
    _write_production_data_artifacts(cfg, run_dates)
    _write_complete_knowledge_saves(cfg, run_dates)
    _write_production_source_snapshots(cfg, run_dates)
    _write_failure_memory(cfg)
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    _write_minimal_manifest(cfg)
    report = (cfg.run_dir / "daily_report.md").read_text(encoding="utf-8")
    report = report.replace(
        "## Readiness\n\n"
        "- readiness status: production_ready\n"
        "- readiness score: 1.0000\n"
        "- readiness blockers: 0\n"
        "- top readiness blocker: none\n\n",
        "",
    )
    (cfg.run_dir / "daily_report.md").write_text(report, encoding="utf-8")
    artifact_manifest.run(cfg)

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert not payload["checks"]["latest_daily_report_is_current_evidence"]
    assert payload["daily_report_evidence"]["current_complete_evidence"] is False
    assert "latest daily_report.md does not prove current run summary" in "\n".join(payload["blockers"])


def test_readiness_blocks_daily_report_readiness_summary_mismatch(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    run_dates = _run_dates_ending_at(cfg.run_date)
    for run_date in run_dates:
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", _production_run_record(run_date, agent_status))
    _write_successful_invocations(cfg, run_dates)
    _write_production_data_artifacts(cfg, run_dates)
    _write_complete_knowledge_saves(cfg, run_dates)
    _write_production_source_snapshots(cfg, run_dates)
    _write_failure_memory(cfg)
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    _write_minimal_manifest(cfg)
    report = (cfg.run_dir / "daily_report.md").read_text(encoding="utf-8")
    report = report.replace("- readiness blockers: 0\n", "- readiness blockers: 7\n")
    (cfg.run_dir / "daily_report.md").write_text(report, encoding="utf-8")
    artifact_manifest.run(cfg)

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert not payload["checks"]["latest_daily_report_is_current_evidence"]
    assert payload["daily_report_evidence"]["current_complete_evidence"] is False
    assert "latest daily_report.md does not prove current run summary" in "\n".join(payload["blockers"])


def test_readiness_blocks_factor_library_mismatch(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    run_dates = _run_dates_ending_at(cfg.run_date)
    for run_date in run_dates:
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", _production_run_record(run_date, agent_status))
    _write_successful_invocations(cfg, run_dates)
    _write_production_data_artifacts(cfg, run_dates)
    _write_complete_knowledge_saves(cfg, run_dates)
    _write_production_source_snapshots(cfg, run_dates)
    write_json(cfg.knowledge_root / "factor_database" / "factors.json", {
        "factors": [{"factor_id": "F1", "decision": "kill"}]
    })
    (cfg.knowledge_root / "failure_memory.jsonl").write_text(
        f'{{"run_date":"{cfg.run_date}","factor_id":"F1","formula_key":"rank(ret_5)"}}\n',
        encoding="utf-8",
    )
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    _write_minimal_manifest(cfg)
    stale_factor = read_json(cfg.factor_library / "F1.json", {})
    stale_factor["created_at_run"] = "20260603"
    write_json(cfg.factor_library / "F1.json", stale_factor)
    artifact_manifest.run(cfg)

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert not payload["checks"]["latest_factor_library_matches_candidates"]
    assert payload["factor_library_evidence"]["candidate_count"] == 1
    assert payload["factor_library_evidence"]["matches_current_candidates"] is False
    assert "latest factor_library files do not match current candidate_factors.json" in "\n".join(payload["blockers"])


def test_readiness_blocks_factor_library_formula_mismatch(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    run_dates = _run_dates_ending_at(cfg.run_date)
    for run_date in run_dates:
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", _production_run_record(run_date, agent_status))
    _write_successful_invocations(cfg, run_dates)
    _write_production_data_artifacts(cfg, run_dates)
    _write_complete_knowledge_saves(cfg, run_dates)
    _write_production_source_snapshots(cfg, run_dates)
    _write_failure_memory(cfg)
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    _write_minimal_manifest(cfg)
    stale_factor = read_json(cfg.factor_library / "F1.json", {})
    stale_factor["formula"] = "rank(stale_ret_5)"
    write_json(cfg.factor_library / "F1.json", stale_factor)
    artifact_manifest.run(cfg)

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert not payload["checks"]["latest_factor_library_matches_candidates"]
    assert payload["factor_library_evidence"]["candidate_count"] == 1
    assert payload["factor_library_evidence"]["matches_current_candidates"] is False
    assert "latest factor_library files do not match current candidate_factors.json" in "\n".join(payload["blockers"])


def test_readiness_blocks_candidate_factor_file_mismatch(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    run_dates = _run_dates_ending_at(cfg.run_date)
    for run_date in run_dates:
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", _production_run_record(run_date, agent_status))
    _write_successful_invocations(cfg, run_dates)
    _write_production_data_artifacts(cfg, run_dates)
    _write_complete_knowledge_saves(cfg, run_dates)
    _write_production_source_snapshots(cfg, run_dates)
    write_json(cfg.knowledge_root / "factor_database" / "factors.json", {
        "factors": [{"factor_id": "F1", "decision": "kill"}]
    })
    (cfg.knowledge_root / "failure_memory.jsonl").write_text(
        f'{{"run_date":"{cfg.run_date}","factor_id":"F1","formula_key":"rank(ret_5)"}}\n',
        encoding="utf-8",
    )
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    _write_minimal_manifest(cfg)
    stale_factor = read_json(cfg.run_dir / "candidate_factors" / "F1.json", {})
    stale_factor["formula_key"] = "stale_candidate_formula_key"
    write_json(cfg.run_dir / "candidate_factors" / "F1.json", stale_factor)
    artifact_manifest.run(cfg)

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert not payload["checks"]["latest_candidate_factor_files_match_payload"]
    assert payload["factor_library_evidence"]["candidate_files_match_payload"] is False
    assert payload["factor_library_evidence"]["matches_current_candidates"] is True
    assert "latest candidate_factors files do not match candidate_factors.json" in "\n".join(payload["blockers"])


def test_readiness_blocks_candidate_factor_file_formula_mismatch(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    run_dates = _run_dates_ending_at(cfg.run_date)
    for run_date in run_dates:
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", _production_run_record(run_date, agent_status))
    _write_successful_invocations(cfg, run_dates)
    _write_production_data_artifacts(cfg, run_dates)
    _write_complete_knowledge_saves(cfg, run_dates)
    _write_production_source_snapshots(cfg, run_dates)
    _write_failure_memory(cfg)
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    _write_minimal_manifest(cfg)
    stale_factor = read_json(cfg.run_dir / "candidate_factors" / "F1.json", {})
    stale_factor["formula"] = "rank(stale_ret_5)"
    write_json(cfg.run_dir / "candidate_factors" / "F1.json", stale_factor)
    artifact_manifest.run(cfg)

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert not payload["checks"]["latest_candidate_factor_files_match_payload"]
    assert payload["factor_library_evidence"]["candidate_files_match_payload"] is False
    assert payload["factor_library_evidence"]["matches_current_candidates"] is True
    assert "latest candidate_factors files do not match candidate_factors.json" in "\n".join(payload["blockers"])


def test_readiness_blocks_extra_stale_candidate_factor_file(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    run_dates = _run_dates_ending_at(cfg.run_date)
    for run_date in run_dates:
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", _production_run_record(run_date, agent_status))
    _write_successful_invocations(cfg, run_dates)
    _write_production_data_artifacts(cfg, run_dates)
    _write_complete_knowledge_saves(cfg, run_dates)
    _write_production_source_snapshots(cfg, run_dates)
    write_json(cfg.knowledge_root / "factor_database" / "factors.json", {
        "factors": [{"factor_id": "F1", "decision": "kill"}]
    })
    (cfg.knowledge_root / "failure_memory.jsonl").write_text(
        f'{{"run_date":"{cfg.run_date}","factor_id":"F1","formula_key":"rank(ret_5)"}}\n',
        encoding="utf-8",
    )
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    _write_minimal_manifest(cfg)
    write_json(cfg.run_dir / "candidate_factors" / "STALE.json", {
        "factor_id": "STALE",
        "formula_key": "stale",
    })
    artifact_manifest.run(cfg)

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert not payload["checks"]["latest_candidate_factor_files_match_payload"]
    assert payload["factor_library_evidence"]["candidate_files_match_payload"] is False
    assert payload["factor_library_evidence"]["matches_current_candidates"] is True
    assert "latest candidate_factors files do not match candidate_factors.json" in "\n".join(payload["blockers"])


def test_readiness_blocks_candidate_repeating_historical_failed_formula(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    run_dates = _run_dates_ending_at(cfg.run_date)
    for run_date in run_dates:
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", _production_run_record(run_date, agent_status))
    _write_successful_invocations(cfg, run_dates)
    _write_production_data_artifacts(cfg, run_dates)
    _write_complete_knowledge_saves(cfg, run_dates)
    _write_production_source_snapshots(cfg, run_dates)
    current_failure = _failure_memory_payload(cfg)
    historical_failure = {
        "run_date": "20260603",
        "factor_id": "OLD_FAILED_FACTOR",
        "formula_key": current_failure["formula_key"],
    }
    (cfg.knowledge_root / "failure_memory.jsonl").parent.mkdir(parents=True, exist_ok=True)
    (cfg.knowledge_root / "failure_memory.jsonl").write_text(
        json.dumps(historical_failure, ensure_ascii=False, sort_keys=True) + "\n"
        + json.dumps(current_failure, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    _write_minimal_manifest(cfg)

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert not payload["checks"]["latest_candidate_factors_avoid_historical_failures"]
    assert payload["factor_library_evidence"]["candidates_avoid_historical_failures"] is False
    assert payload["factor_library_evidence"]["candidate_failed_memory_matches"][0]["factor_id"] == "F1"
    assert current_failure["formula_key"] in payload["factor_library_evidence"]["candidate_failed_memory_matches"][0]["matched_keys"]
    assert "latest candidate factors repeat historical failed factor memory" in "\n".join(payload["blockers"])


def test_readiness_blocks_factor_database_mismatch(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    run_dates = _run_dates_ending_at(cfg.run_date)
    for run_date in run_dates:
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", _production_run_record(run_date, agent_status))
    _write_successful_invocations(cfg, run_dates)
    _write_production_data_artifacts(cfg, run_dates)
    _write_complete_knowledge_saves(cfg, run_dates)
    _write_production_source_snapshots(cfg, run_dates)
    (cfg.knowledge_root / "failure_memory.jsonl").write_text(
        f'{{"run_date":"{cfg.run_date}","factor_id":"F1","formula_key":"rank(ret_5)"}}\n',
        encoding="utf-8",
    )
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    _write_minimal_manifest(cfg)
    stale_db = _factor_database_payload(cfg)
    stale_db["factors"][0]["run_date"] = "20260603"
    write_json(cfg.knowledge_root / "factor_database" / "factors.json", stale_db)
    artifact_manifest.run(cfg)

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert not payload["checks"]["latest_factor_database_matches_backtests"]
    assert payload["factor_database_evidence"]["latest_backtest_result_count"] == 1
    assert payload["factor_database_evidence"]["same_day_factor_records"] == 0
    assert payload["factor_database_evidence"]["matches_latest_backtests"] is False
    assert "latest factor_database records do not match current backtest/critic outputs" in "\n".join(payload["blockers"])


def test_readiness_blocks_factor_database_portfolio_mismatch(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    run_dates = _run_dates_ending_at(cfg.run_date)
    for run_date in run_dates:
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", _production_run_record(run_date, agent_status))
    _write_successful_invocations(cfg, run_dates)
    _write_production_data_artifacts(cfg, run_dates)
    _write_complete_knowledge_saves(cfg, run_dates)
    _write_production_source_snapshots(cfg, run_dates)
    _write_failure_memory(cfg)
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    _write_minimal_manifest(cfg)
    stale_db = _factor_database_payload(cfg)
    stale_db["factors"][0]["portfolio"]["ann_return_net"] = 999
    write_json(cfg.knowledge_root / "factor_database" / "factors.json", stale_db)
    artifact_manifest.run(cfg)

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert not payload["checks"]["latest_factor_database_matches_backtests"]
    assert payload["checks"]["latest_backtest_result_files_match_payload"]
    assert payload["checks"]["latest_backtest_dataset_provenance_matches_manifest"]
    assert payload["factor_database_evidence"]["same_day_factor_records"] == 1
    assert payload["factor_database_evidence"]["matches_latest_backtests"] is False
    assert "portfolio" in payload["factor_database_evidence"]["matched_fields"]
    assert "latest factor_database records do not match current backtest/critic outputs" in "\n".join(
        payload["blockers"]
    )


def test_readiness_blocks_factor_database_cost_sensitivity_mismatch(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    run_dates = _run_dates_ending_at(cfg.run_date)
    for run_date in run_dates:
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", _production_run_record(run_date, agent_status))
    _write_successful_invocations(cfg, run_dates)
    _write_production_data_artifacts(cfg, run_dates)
    _write_complete_knowledge_saves(cfg, run_dates)
    _write_production_source_snapshots(cfg, run_dates)
    _write_failure_memory(cfg)
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    _write_minimal_manifest(cfg)
    stale_db = _factor_database_payload(cfg)
    stale_db["factors"][0]["cost_sensitivity"]["20"]["ann_return_net"] = 999
    write_json(cfg.knowledge_root / "factor_database" / "factors.json", stale_db)
    artifact_manifest.run(cfg)

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert not payload["checks"]["latest_factor_database_matches_backtests"]
    assert payload["factor_database_evidence"]["matches_latest_backtests"] is False
    assert "cost_sensitivity" in payload["factor_database_evidence"]["matched_fields"]
    assert "latest factor_database records do not match current backtest/critic outputs" in "\n".join(
        payload["blockers"]
    )


def test_readiness_blocks_backtest_result_file_mismatch(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    run_dates = _run_dates_ending_at(cfg.run_date)
    for run_date in run_dates:
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", _production_run_record(run_date, agent_status))
    _write_successful_invocations(cfg, run_dates)
    _write_production_data_artifacts(cfg, run_dates)
    _write_complete_knowledge_saves(cfg, run_dates)
    _write_production_source_snapshots(cfg, run_dates)
    _write_failure_memory(cfg)
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    _write_minimal_manifest(cfg)
    stale_result = read_json(cfg.run_dir / "backtest_results" / "F1.json", {})
    stale_result["rankic_mean"] = 999
    write_json(cfg.run_dir / "backtest_results" / "F1.json", stale_result)
    artifact_manifest.run(cfg)

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert not payload["checks"]["latest_backtest_result_files_match_payload"]
    assert payload["checks"]["latest_factor_database_matches_backtests"]
    assert payload["factor_database_evidence"]["backtest_result_files_match_payload"] is False
    assert "latest backtest_results files do not match backtest_results.json" in "\n".join(payload["blockers"])


def test_readiness_blocks_backtest_result_file_missing_cost_evidence(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    run_dates = _run_dates_ending_at(cfg.run_date)
    for run_date in run_dates:
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", _production_run_record(run_date, agent_status))
    _write_successful_invocations(cfg, run_dates)
    _write_production_data_artifacts(cfg, run_dates)
    _write_complete_knowledge_saves(cfg, run_dates)
    _write_production_source_snapshots(cfg, run_dates)
    _write_failure_memory(cfg)
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    _write_minimal_manifest(cfg)
    stale_result = read_json(cfg.run_dir / "backtest_results" / "F1.json", {})
    stale_result.pop("cost_sensitivity", None)
    write_json(cfg.run_dir / "backtest_results" / "F1.json", stale_result)
    artifact_manifest.run(cfg)

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert not payload["checks"]["latest_backtest_result_files_match_payload"]
    assert payload["checks"]["latest_factor_database_matches_backtests"]
    assert payload["factor_database_evidence"]["backtest_result_files_match_payload"] is False
    assert "latest backtest_results files do not match backtest_results.json" in "\n".join(payload["blockers"])


def test_readiness_blocks_extra_stale_backtest_result_file(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    run_dates = _run_dates_ending_at(cfg.run_date)
    for run_date in run_dates:
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", _production_run_record(run_date, agent_status))
    _write_successful_invocations(cfg, run_dates)
    _write_production_data_artifacts(cfg, run_dates)
    _write_complete_knowledge_saves(cfg, run_dates)
    _write_production_source_snapshots(cfg, run_dates)
    _write_failure_memory(cfg)
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    _write_minimal_manifest(cfg)
    write_json(cfg.run_dir / "backtest_results" / "STALE.json", {
        "factor_id": "STALE",
        "rankic_mean": 999,
    })
    artifact_manifest.run(cfg)

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert not payload["checks"]["latest_backtest_result_files_match_payload"]
    assert payload["checks"]["latest_factor_database_matches_backtests"]
    assert payload["factor_database_evidence"]["backtest_result_files_match_payload"] is False
    assert "latest backtest_results files do not match backtest_results.json" in "\n".join(payload["blockers"])


def test_readiness_blocks_backtest_dataset_provenance_mismatch(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    run_dates = _run_dates_ending_at(cfg.run_date)
    for run_date in run_dates:
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", _production_run_record(run_date, agent_status))
    _write_successful_invocations(cfg, run_dates)
    _write_production_data_artifacts(cfg, run_dates)
    _write_complete_knowledge_saves(cfg, run_dates)
    _write_production_source_snapshots(cfg, run_dates)
    _write_failure_memory(cfg)
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    _write_minimal_manifest(cfg)
    stale_backtests = read_json(cfg.run_dir / "backtest_results.json", {})
    stale_backtests["dataset_provenance"]["dataset_sha256"] = "stale-dataset-sha256"
    write_json(cfg.run_dir / "backtest_results.json", stale_backtests)
    artifact_manifest.run(cfg)

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert not payload["checks"]["latest_backtest_dataset_provenance_matches_manifest"]
    assert payload["checks"]["latest_backtest_result_files_match_payload"]
    assert payload["checks"]["latest_factor_database_matches_backtests"]
    assert payload["factor_database_evidence"]["backtest_dataset_provenance_matches_manifest"] is False
    assert payload["factor_database_evidence"]["backtest_dataset_sha256"] == "stale-dataset-sha256"
    assert payload["factor_database_evidence"]["current_dataset_sha256"] == "test-dataset-sha256"
    assert "latest backtest dataset provenance does not match current dataset_manifest.json" in "\n".join(
        payload["blockers"]
    )


def test_readiness_blocks_extra_same_day_factor_database_record(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    run_dates = _run_dates_ending_at(cfg.run_date)
    for run_date in run_dates:
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", _production_run_record(run_date, agent_status))
    _write_successful_invocations(cfg, run_dates)
    _write_production_data_artifacts(cfg, run_dates)
    _write_complete_knowledge_saves(cfg, run_dates)
    _write_production_source_snapshots(cfg, run_dates)
    _write_failure_memory(cfg)
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    _write_minimal_manifest(cfg)
    factor_db = read_json(cfg.knowledge_root / "factor_database" / "factors.json", {})
    stale_record = dict(factor_db["factors"][0])
    stale_record["factor_id"] = "STALE_SAME_DAY"
    factor_db["factors"].append(stale_record)
    write_json(cfg.knowledge_root / "factor_database" / "factors.json", factor_db)
    artifact_manifest.run(cfg)

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert not payload["checks"]["latest_factor_database_matches_backtests"]
    assert payload["checks"]["latest_backtest_result_files_match_payload"]
    assert payload["factor_database_evidence"]["matches_latest_backtests"] is False
    assert payload["factor_database_evidence"]["latest_backtest_factor_ids"] == ["F1"]
    assert payload["factor_database_evidence"]["same_day_factor_ids"] == ["F1", "STALE_SAME_DAY"]
    assert "latest factor_database records do not match current backtest/critic outputs" in "\n".join(
        payload["blockers"]
    )


def test_readiness_blocks_failure_analysis_mismatch(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    run_dates = _run_dates_ending_at(cfg.run_date)
    for run_date in run_dates:
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", _production_run_record(run_date, agent_status))
    _write_successful_invocations(cfg, run_dates)
    _write_production_data_artifacts(cfg, run_dates)
    _write_complete_knowledge_saves(cfg, run_dates)
    _write_production_source_snapshots(cfg, run_dates)
    _write_failure_memory(cfg)
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    _write_minimal_manifest(cfg)
    (cfg.run_dir / "failure_analysis.md").write_text(
        "# Failure Analysis\n\nRun date: 20260603\n\n## STALE\n\n- decision: kill\n",
        encoding="utf-8",
    )
    artifact_manifest.run(cfg)

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert payload["checks"]["latest_factor_database_matches_backtests"]
    assert not payload["checks"]["latest_failure_analysis_matches_critique"]
    assert payload["failure_analysis_evidence"]["matches_current_critique"] is False
    assert payload["failure_analysis_evidence"]["critique_factor_ids"] == ["F1"]
    assert "latest failure_analysis.md does not match current critique.json" in "\n".join(payload["blockers"])


def test_readiness_blocks_next_generation_file_mismatch(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    run_dates = _run_dates_ending_at(cfg.run_date)
    for run_date in run_dates:
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", _production_run_record(run_date, agent_status))
    _write_successful_invocations(cfg, run_dates)
    _write_production_data_artifacts(cfg, run_dates)
    _write_complete_knowledge_saves(cfg, run_dates)
    _write_production_source_snapshots(cfg, run_dates)
    _write_failure_memory(cfg)
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    _write_minimal_manifest(cfg)
    stale_factor = read_json(cfg.run_dir / "next_generation_factors" / "F1_PIVOT_DEF.json", {})
    stale_factor["formula_key"] = "stale_formula_key"
    write_json(cfg.run_dir / "next_generation_factors" / "F1_PIVOT_DEF.json", stale_factor)
    artifact_manifest.run(cfg)

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert not payload["checks"]["latest_next_generation_files_match_payload"]
    assert payload["next_generation_evidence"]["matches_payload_files"] is False
    assert payload["next_generation_evidence"]["next_factor_ids"] == ["F1_PIVOT_DEF"]
    assert "latest next_generation_factors files do not match next_generation_factors.json" in "\n".join(payload["blockers"])


def test_readiness_blocks_next_generation_file_formula_mismatch(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    run_dates = _run_dates_ending_at(cfg.run_date)
    for run_date in run_dates:
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", _production_run_record(run_date, agent_status))
    _write_successful_invocations(cfg, run_dates)
    _write_production_data_artifacts(cfg, run_dates)
    _write_complete_knowledge_saves(cfg, run_dates)
    _write_production_source_snapshots(cfg, run_dates)
    _write_failure_memory(cfg)
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    _write_minimal_manifest(cfg)
    stale_factor = read_json(cfg.run_dir / "next_generation_factors" / "F1_PIVOT_DEF.json", {})
    stale_factor["formula"] = "rank(stale_formula)"
    write_json(cfg.run_dir / "next_generation_factors" / "F1_PIVOT_DEF.json", stale_factor)
    artifact_manifest.run(cfg)

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert not payload["checks"]["latest_next_generation_files_match_payload"]
    assert payload["next_generation_evidence"]["matches_payload_files"] is False
    assert payload["next_generation_evidence"]["next_factor_ids"] == ["F1_PIVOT_DEF"]
    assert "latest next_generation_factors files do not match next_generation_factors.json" in "\n".join(payload["blockers"])


def test_readiness_blocks_extra_stale_next_generation_file(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    run_dates = _run_dates_ending_at(cfg.run_date)
    for run_date in run_dates:
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", _production_run_record(run_date, agent_status))
    _write_successful_invocations(cfg, run_dates)
    _write_production_data_artifacts(cfg, run_dates)
    _write_complete_knowledge_saves(cfg, run_dates)
    _write_production_source_snapshots(cfg, run_dates)
    _write_failure_memory(cfg)
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    _write_minimal_manifest(cfg)
    write_json(cfg.run_dir / "next_generation_factors" / "STALE_NEXT.json", {
        "factor_id": "STALE_NEXT",
        "parent_factor_id": "STALE",
        "formula_key": "stale_next",
        "status": "repair_candidate",
    })
    artifact_manifest.run(cfg)

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert not payload["checks"]["latest_next_generation_files_match_payload"]
    assert payload["next_generation_evidence"]["matches_payload_files"] is False
    assert payload["next_generation_evidence"]["next_factor_ids"] == ["F1_PIVOT_DEF"]
    assert "latest next_generation_factors files do not match next_generation_factors.json" in "\n".join(payload["blockers"])


def test_readiness_blocks_research_log_mismatch(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    run_dates = _run_dates_ending_at(cfg.run_date)
    for run_date in run_dates:
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", _production_run_record(run_date, agent_status))
    _write_successful_invocations(cfg, run_dates)
    _write_production_data_artifacts(cfg, run_dates)
    _write_complete_knowledge_saves(cfg, run_dates)
    _write_production_source_snapshots(cfg, run_dates)
    _write_failure_memory(cfg)
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    _write_minimal_manifest(cfg)
    stale_log = _research_log_payload(cfg)
    stale_log["backtest"]["result_factor_ids"] = ["STALE_FACTOR"]
    write_json(cfg.knowledge_root / "research_log_latest.json", stale_log)
    artifact_manifest.run(cfg)

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert not payload["checks"]["latest_research_log_matches_current_outputs"]
    assert payload["research_log_evidence"]["matches_current_outputs"] is False
    assert payload["research_log_evidence"]["result_factor_ids"] == ["STALE_FACTOR"]
    assert "latest research_log_latest.json does not match current daily research outputs" in "\n".join(payload["blockers"])


def test_readiness_blocks_research_log_factor_design_summary_mismatch(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    run_dates = _run_dates_ending_at(cfg.run_date)
    for run_date in run_dates:
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", _production_run_record(run_date, agent_status))
    _write_successful_invocations(cfg, run_dates)
    _write_production_data_artifacts(cfg, run_dates)
    _write_complete_knowledge_saves(cfg, run_dates)
    _write_production_source_snapshots(cfg, run_dates)
    _write_failure_memory(cfg)
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    _write_minimal_manifest(cfg)
    stale_log = _research_log_payload(cfg)
    stale_log["events"]["top_titles"] = ["stale event title"]
    stale_log["factor_design"]["formula_keys"] = ["stale_formula_key"]
    stale_log["factor_design"]["skipped_failed_count"] = 99
    write_json(cfg.knowledge_root / "research_log_latest.json", stale_log)
    artifact_manifest.run(cfg)

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert not payload["checks"]["latest_research_log_matches_current_outputs"]
    assert payload["research_log_evidence"]["matches_current_outputs"] is False
    assert payload["research_log_evidence"]["event_top_titles"] == ["stale event title"]
    assert payload["research_log_evidence"]["candidate_formula_keys"] == ["stale_formula_key"]
    assert payload["research_log_evidence"]["candidate_skipped_failed_count"] == 99
    assert "latest research_log_latest.json does not match current daily research outputs" in "\n".join(payload["blockers"])


def test_readiness_blocks_research_log_dataset_provenance_mismatch(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    run_dates = _run_dates_ending_at(cfg.run_date)
    for run_date in run_dates:
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", _production_run_record(run_date, agent_status))
    _write_successful_invocations(cfg, run_dates)
    _write_production_data_artifacts(cfg, run_dates)
    _write_complete_knowledge_saves(cfg, run_dates)
    _write_production_source_snapshots(cfg, run_dates)
    _write_failure_memory(cfg)
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    _write_minimal_manifest(cfg)
    stale_log = _research_log_payload(cfg)
    stale_log["backtest"]["dataset_provenance"]["dataset_sha256"] = "stale-research-log-dataset-sha256"
    write_json(cfg.knowledge_root / "research_log_latest.json", stale_log)
    artifact_manifest.run(cfg)

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert not payload["checks"]["latest_research_log_matches_current_outputs"]
    assert payload["checks"]["latest_backtest_dataset_provenance_matches_manifest"]
    assert payload["research_log_evidence"]["matches_current_outputs"] is False
    assert payload["research_log_evidence"]["backtest_dataset_sha256"] == "stale-research-log-dataset-sha256"
    assert payload["research_log_evidence"]["current_backtest_dataset_sha256"] == "test-dataset-sha256"
    assert "latest research_log_latest.json does not match current daily research outputs" in "\n".join(
        payload["blockers"]
    )


def test_readiness_blocks_research_log_critic_summary_mismatch(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    run_dates = _run_dates_ending_at(cfg.run_date)
    for run_date in run_dates:
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", _production_run_record(run_date, agent_status))
    _write_successful_invocations(cfg, run_dates)
    _write_production_data_artifacts(cfg, run_dates)
    _write_complete_knowledge_saves(cfg, run_dates)
    _write_production_source_snapshots(cfg, run_dates)
    _write_failure_memory(cfg)
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    _write_minimal_manifest(cfg)
    stale_log = _research_log_payload(cfg)
    stale_log["critic"]["killed"] = 0
    stale_log["critic"]["promoted"] = 1
    stale_log["critic"]["issue_counts"] = {}
    write_json(cfg.knowledge_root / "research_log_latest.json", stale_log)
    artifact_manifest.run(cfg)

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert not payload["checks"]["latest_research_log_matches_current_outputs"]
    assert payload["research_log_evidence"]["matches_current_outputs"] is False
    assert payload["research_log_evidence"]["critique_count"] == 1
    assert payload["research_log_evidence"]["current_critique_count"] == 1
    assert "latest research_log_latest.json does not match current daily research outputs" in "\n".join(
        payload["blockers"]
    )


def test_readiness_blocks_research_log_evolution_skipped_summary_mismatch(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    run_dates = _run_dates_ending_at(cfg.run_date)
    for run_date in run_dates:
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", _production_run_record(run_date, agent_status))
    _write_successful_invocations(cfg, run_dates)
    _write_production_data_artifacts(cfg, run_dates)
    _write_complete_knowledge_saves(cfg, run_dates)
    _write_production_source_snapshots(cfg, run_dates)
    _write_failure_memory(cfg)
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    _write_minimal_manifest(cfg)
    stale_log = _research_log_payload(cfg)
    stale_log["evolution"]["skipped_failed_count"] = 1
    stale_log["evolution"]["skipped_factor_ids"] = ["STALE_SKIPPED_EVOLUTION"]
    write_json(cfg.knowledge_root / "research_log_latest.json", stale_log)
    artifact_manifest.run(cfg)

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert not payload["checks"]["latest_research_log_matches_current_outputs"]
    assert payload["research_log_evidence"]["matches_current_outputs"] is False
    assert payload["research_log_evidence"]["evolution_skipped_failed_count"] == 1
    assert payload["research_log_evidence"]["current_evolution_skipped_failed_count"] == 0
    assert payload["research_log_evidence"]["evolution_skipped_factor_ids"] == ["STALE_SKIPPED_EVOLUTION"]
    assert payload["research_log_evidence"]["current_evolution_skipped_factor_ids"] == []
    assert "latest research_log_latest.json does not match current daily research outputs" in "\n".join(
        payload["blockers"]
    )


def test_readiness_blocks_data_health_latest_mismatch(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    run_dates = _run_dates_ending_at(cfg.run_date)
    for run_date in run_dates:
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", _production_run_record(run_date, agent_status))
    _write_successful_invocations(cfg, run_dates)
    _write_production_data_artifacts(cfg, run_dates)
    _write_complete_knowledge_saves(cfg, run_dates)
    _write_production_source_snapshots(cfg, run_dates)
    _write_failure_memory(cfg)
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    _write_minimal_manifest(cfg)
    stale_latest = _data_health_latest_payload(cfg)
    stale_latest["dataset_manifest"]["dataset_sha256"] = "stale-sha256"
    write_json(cfg.knowledge_root / "data_health_latest.json", stale_latest)
    artifact_manifest.run(cfg)

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert not payload["checks"]["latest_data_health_latest_matches_current_outputs"]
    assert payload["data_latest_evidence"]["matches_current_outputs"] is False
    assert payload["data_latest_evidence"]["latest_dataset_sha256"] == "stale-sha256"
    assert "latest data_health_latest.json does not match current data_health.json" in "\n".join(payload["blockers"])


def test_readiness_blocks_source_snapshots_latest_mismatch(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    run_dates = _run_dates_ending_at(cfg.run_date)
    for run_date in run_dates:
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", _production_run_record(run_date, agent_status))
    _write_successful_invocations(cfg, run_dates)
    _write_production_data_artifacts(cfg, run_dates)
    _write_complete_knowledge_saves(cfg, run_dates)
    _write_production_source_snapshots(cfg, run_dates)
    _write_failure_memory(cfg)
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    _write_minimal_manifest(cfg)
    stale_latest = read_json(cfg.knowledge_root / "source_snapshots_latest.json", {})
    stale_latest["item_count"] = 999
    write_json(cfg.knowledge_root / "source_snapshots_latest.json", stale_latest)
    artifact_manifest.run(cfg)

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert payload["checks"]["latest_source_snapshots_match_current_outputs"]
    assert not payload["checks"]["latest_source_snapshots_latest_matches_current_outputs"]
    assert payload["source_snapshot_evidence"]["latest_matches_current_outputs"] is False
    assert payload["source_snapshot_evidence"]["latest_item_count"] == 999
    assert "latest source_snapshots_latest.json does not match current market/research source outputs" in "\n".join(
        payload["blockers"]
    )


def test_readiness_blocks_data_artifact_without_manifest_hash(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    run_dates = _run_dates_ending_at(cfg.run_date)
    for run_date in run_dates:
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", _production_run_record(run_date, agent_status))
    _write_successful_invocations(cfg, run_dates)
    _write_production_data_artifacts(cfg, run_dates)
    _write_complete_knowledge_saves(cfg, run_dates)
    _write_production_source_snapshots(cfg, run_dates)
    _write_failure_memory(cfg)
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    _write_minimal_manifest(cfg)
    data_health_path = cfg.knowledge_root / "data_health.jsonl"
    rows = [json.loads(line) for line in data_health_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    rows[0]["dataset_manifest"].pop("dataset_sha256", None)
    data_health_path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows) + "\n",
        encoding="utf-8",
    )
    artifact_manifest.run(cfg)

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert payload["checks"]["has_365_successful_runs"]
    assert not payload["checks"]["has_365_data_artifact_dates"]
    assert payload["data_artifact_evidence"]["production_data_artifact_dates"] == 364
    assert "365 production-grade data artifact dates missing" in "\n".join(payload["blockers"])


def test_readiness_blocks_data_artifact_date_mismatch(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    run_dates = _run_dates_ending_at(cfg.run_date)
    for run_date in run_dates:
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", _production_run_record(run_date, agent_status))
    _write_successful_invocations(cfg, run_dates)
    _write_production_data_artifacts(cfg, run_dates)
    _write_complete_knowledge_saves(cfg, run_dates)
    _write_production_source_snapshots(cfg, run_dates)
    _write_failure_memory(cfg)
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    _write_minimal_manifest(cfg)
    data_health_path = cfg.knowledge_root / "data_health.jsonl"
    rows = [json.loads(line) for line in data_health_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    rows[0]["dataset_manifest"]["run_date"] = run_dates[1]
    data_health_path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows) + "\n",
        encoding="utf-8",
    )
    artifact_manifest.run(cfg)

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert payload["checks"]["has_365_successful_runs"]
    assert not payload["checks"]["has_365_data_artifact_dates"]
    assert payload["data_artifact_evidence"]["production_data_artifact_dates"] == 364
    assert payload["data_artifact_evidence"]["production_evidence_dates_without_data_artifacts"] == [run_dates[0]]


def test_readiness_blocks_data_artifact_without_recorded_at(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    run_dates = _run_dates_ending_at(cfg.run_date)
    for run_date in run_dates:
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", _production_run_record(run_date, agent_status))
    _write_successful_invocations(cfg, run_dates)
    _write_production_data_artifacts(cfg, run_dates)
    _write_complete_knowledge_saves(cfg, run_dates)
    _write_production_source_snapshots(cfg, run_dates)
    _write_failure_memory(cfg)
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    _write_minimal_manifest(cfg)
    data_health_path = cfg.knowledge_root / "data_health.jsonl"
    rows = [json.loads(line) for line in data_health_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    rows[0].pop("recorded_at", None)
    data_health_path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows) + "\n",
        encoding="utf-8",
    )
    artifact_manifest.run(cfg)

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert payload["checks"]["has_365_successful_runs"]
    assert not payload["checks"]["has_365_data_artifact_dates"]
    assert payload["data_artifact_evidence"]["production_data_artifact_dates"] == 364
    assert payload["data_artifact_evidence"]["production_evidence_dates_without_data_artifacts"] == [run_dates[0]]


def test_readiness_blocks_source_snapshot_mismatch(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    run_dates = _run_dates_ending_at(cfg.run_date)
    for run_date in run_dates:
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", _production_run_record(run_date, agent_status))
    _write_successful_invocations(cfg, run_dates)
    _write_production_data_artifacts(cfg, run_dates)
    _write_complete_knowledge_saves(cfg, run_dates)
    _write_production_source_snapshots(cfg, run_dates)
    _write_failure_memory(cfg)
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    _write_minimal_manifest(cfg)
    stale_snapshot = read_json(cfg.run_dir / "source_snapshots" / "research_agent.json", {})
    stale_snapshot["item_count"] = 999
    write_json(cfg.run_dir / "source_snapshots" / "research_agent.json", stale_snapshot)
    artifact_manifest.run(cfg)

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert not payload["checks"]["latest_source_snapshots_match_current_outputs"]
    assert payload["source_snapshot_evidence"]["matches_current_outputs"] is False
    assert payload["source_snapshot_evidence"]["current_run_snapshot_files"]["research_agent"] is True
    assert "latest source snapshot files/jsonl do not match current market/research source outputs" in "\n".join(payload["blockers"])


def test_readiness_blocks_source_snapshot_items_mismatch(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    run_dates = _run_dates_ending_at(cfg.run_date)
    for run_date in run_dates:
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", _production_run_record(run_date, agent_status))
    _write_successful_invocations(cfg, run_dates)
    _write_production_data_artifacts(cfg, run_dates)
    _write_complete_knowledge_saves(cfg, run_dates)
    _write_production_source_snapshots(cfg, run_dates)
    _write_failure_memory(cfg)
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    _write_minimal_manifest(cfg)
    stale_snapshot = read_json(cfg.run_dir / "source_snapshots" / "market_intelligence.json", {})
    stale_snapshot["items"][0]["title"] = "stale event with same count"
    write_json(cfg.run_dir / "source_snapshots" / "market_intelligence.json", stale_snapshot)
    artifact_manifest.run(cfg)

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert not payload["checks"]["latest_source_snapshots_match_current_outputs"]
    assert payload["source_snapshot_evidence"]["matches_current_outputs"] is False
    assert "latest source snapshot files/jsonl do not match current market/research source outputs" in "\n".join(payload["blockers"])


def test_readiness_blocks_source_snapshot_without_replay_metadata(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    run_dates = _run_dates_ending_at(cfg.run_date)
    for run_date in run_dates:
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", _production_run_record(run_date, agent_status))
    _write_successful_invocations(cfg, run_dates)
    _write_production_data_artifacts(cfg, run_dates)
    _write_complete_knowledge_saves(cfg, run_dates)
    _write_production_source_snapshots(cfg, run_dates)
    _write_failure_memory(cfg)
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    _write_minimal_manifest(cfg)
    snapshot_path = cfg.knowledge_root / "source_snapshots.jsonl"
    rows = [json.loads(line) for line in snapshot_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    for row in rows:
        if row["run_date"] == run_dates[0] and row["agent"] == "market_intelligence":
            row["source_status"][0].pop("content_sha256", None)
            break
    snapshot_path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows) + "\n",
        encoding="utf-8",
    )
    artifact_manifest.run(cfg)

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert payload["checks"]["has_365_successful_runs"]
    assert not payload["checks"]["has_365_source_snapshot_dates"]
    assert payload["source_snapshot_evidence"]["production_source_snapshot_dates"] == 364
    assert "365 production-grade source snapshot dates missing" in "\n".join(payload["blockers"])


def test_readiness_blocks_source_snapshot_item_count_mismatch(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    run_dates = _run_dates_ending_at(cfg.run_date)
    for run_date in run_dates:
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", _production_run_record(run_date, agent_status))
    _write_successful_invocations(cfg, run_dates)
    _write_production_data_artifacts(cfg, run_dates)
    _write_complete_knowledge_saves(cfg, run_dates)
    _write_production_source_snapshots(cfg, run_dates)
    _write_failure_memory(cfg)
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    _write_minimal_manifest(cfg)
    snapshot_path = cfg.knowledge_root / "source_snapshots.jsonl"
    rows = [json.loads(line) for line in snapshot_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    for row in rows:
        if row["run_date"] == run_dates[0] and row["agent"] == "market_intelligence":
            row["item_count"] = 2
            break
    snapshot_path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows) + "\n",
        encoding="utf-8",
    )
    artifact_manifest.run(cfg)

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert payload["checks"]["has_365_successful_runs"]
    assert not payload["checks"]["has_365_source_snapshot_dates"]
    assert payload["source_snapshot_evidence"]["production_source_snapshot_dates"] == 364
    assert payload["source_snapshot_evidence"]["production_evidence_dates_without_source_snapshots"] == [run_dates[0]]


def test_readiness_blocks_source_snapshot_without_cached_items(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    run_dates = _run_dates_ending_at(cfg.run_date)
    for run_date in run_dates:
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", _production_run_record(run_date, agent_status))
    _write_successful_invocations(cfg, run_dates)
    _write_production_data_artifacts(cfg, run_dates)
    _write_complete_knowledge_saves(cfg, run_dates)
    _write_production_source_snapshots(cfg, run_dates)
    _write_failure_memory(cfg)
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    _write_minimal_manifest(cfg)
    snapshot_path = cfg.knowledge_root / "source_snapshots.jsonl"
    rows = [json.loads(line) for line in snapshot_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    for row in rows:
        if row["run_date"] == run_dates[0] and row["agent"] == "market_intelligence":
            row["items"] = []
            break
    snapshot_path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows) + "\n",
        encoding="utf-8",
    )
    artifact_manifest.run(cfg)

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert payload["checks"]["has_365_successful_runs"]
    assert not payload["checks"]["has_365_source_snapshot_dates"]
    assert payload["source_snapshot_evidence"]["production_source_snapshot_dates"] == 364
    assert payload["source_snapshot_evidence"]["production_evidence_dates_without_source_snapshots"] == [run_dates[0]]


def test_readiness_blocks_source_snapshot_timestamp_date_mismatch(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    run_dates = _run_dates_ending_at(cfg.run_date)
    for run_date in run_dates:
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", _production_run_record(run_date, agent_status))
    _write_successful_invocations(cfg, run_dates)
    _write_production_data_artifacts(cfg, run_dates)
    _write_complete_knowledge_saves(cfg, run_dates)
    _write_production_source_snapshots(cfg, run_dates)
    _write_failure_memory(cfg)
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    _write_minimal_manifest(cfg)
    snapshot_path = cfg.knowledge_root / "source_snapshots.jsonl"
    rows = [json.loads(line) for line in snapshot_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    for row in rows:
        if row["run_date"] == run_dates[0] and row["agent"] == "market_intelligence":
            row["snapshot_written_at"] = f"{run_dates[1][:4]}-{run_dates[1][4:6]}-{run_dates[1][6:]}T00:00:01+00:00"
            break
    snapshot_path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows) + "\n",
        encoding="utf-8",
    )
    artifact_manifest.run(cfg)

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert payload["checks"]["has_365_successful_runs"]
    assert not payload["checks"]["has_365_source_snapshot_dates"]
    assert payload["source_snapshot_evidence"]["production_source_snapshot_dates"] == 364
    assert payload["source_snapshot_evidence"]["production_evidence_dates_without_source_snapshots"] == [run_dates[0]]


def test_readiness_blocks_365_empty_research_activity_runs(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    run_dates = _run_dates_ending_at(cfg.run_date)
    for run_date in run_dates:
        row = _production_run_record(run_date, agent_status)
        row["counts"] = {
            "events": 3,
            "ideas": 1,
            "candidate_factors": 0,
            "backtest_results": 0,
            "raw_candidates": 0,
            "promoted": 0,
            "killed": 0,
        }
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", row)
    _write_successful_invocations(cfg, run_dates)
    _write_production_data_artifacts(cfg, run_dates)
    _write_complete_knowledge_saves(cfg, run_dates)
    _write_production_source_snapshots(cfg, run_dates)
    write_json(cfg.knowledge_root / "factor_database" / "factors.json", {
        "factors": [{"factor_id": "F1", "decision": "kill"}]
    })
    (cfg.knowledge_root / "failure_memory.jsonl").write_text('{"factor_id":"F1"}\n', encoding="utf-8")
    write_json(cfg.run_dir / "self_audit.json", {"status": "pass", "score": 1.0})
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    _write_minimal_manifest(cfg)

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert payload["checks"]["has_365_successful_runs"]
    assert payload["checks"]["has_365_data_artifact_dates"]
    assert payload["checks"]["has_365_source_snapshot_dates"]
    assert payload["checks"]["has_365_knowledge_save_dates"]
    assert payload["checks"]["has_365_successful_run_daily_invocations"]
    assert not payload["checks"]["latest_run_has_research_activity"]
    assert not payload["checks"]["has_365_research_activity_runs"]
    assert not payload["checks"]["has_365_unique_research_activity_dates"]
    assert not payload["checks"]["has_365_consecutive_research_activity_dates"]
    assert not payload["checks"]["has_365_production_evidence_runs"]
    blockers = "\n".join(payload["blockers"])
    assert "latest run lacks active research/backtest evidence" in blockers
    assert "365 active research/backtest runs missing" in blockers


def test_readiness_blocks_365_successful_runs_with_missing_agent_roster(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    full_agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    incomplete_agent_status = {
        name: "ok"
        for name in readiness_report.REQUIRED_AGENT_NAMES
        if name != "artifact_manifest"
    }
    run_dates = _run_dates_ending_at(cfg.run_date)
    for run_date in run_dates:
        append_jsonl(
            cfg.knowledge_root / "run_history.jsonl",
            _production_run_record(run_date, incomplete_agent_status),
        )
    _write_successful_invocations(cfg, run_dates)
    _write_production_data_artifacts(cfg, run_dates)
    _write_complete_knowledge_saves(cfg, run_dates)
    _write_production_source_snapshots(cfg, run_dates)
    write_json(cfg.knowledge_root / "factor_database" / "factors.json", {
        "factors": [{"factor_id": "F1", "decision": "kill"}]
    })
    _write_failure_memory(cfg)
    write_json(cfg.run_dir / "self_audit.json", {"status": "pass", "score": 1.0})
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    _write_minimal_manifest(cfg)
    latest = _production_run_record(cfg.run_date, full_agent_status)
    append_jsonl(cfg.knowledge_root / "run_history.jsonl", latest)
    write_json(cfg.knowledge_root / "run_history_latest.json", latest)

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert payload["checks"]["all_required_agents_seen_latest"]
    assert not payload["checks"]["has_365_successful_runs"]
    assert not payload["checks"]["has_365_production_evidence_runs"]
    assert payload["history"]["successful_audited_runs"] == 1
    assert "365-day unattended proof missing" in "\n".join(payload["blockers"])


def test_readiness_blocks_365_successful_runs_without_recorded_at(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    run_dates = _run_dates_ending_at(cfg.run_date)
    for run_date in run_dates:
        row = _production_run_record(run_date, agent_status)
        row.pop("recorded_at")
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", row)
    _write_successful_invocations(cfg, run_dates)
    _write_production_data_artifacts(cfg, run_dates)
    _write_complete_knowledge_saves(cfg, run_dates)
    _write_production_source_snapshots(cfg, run_dates)
    write_json(cfg.knowledge_root / "factor_database" / "factors.json", {
        "factors": [{"factor_id": "F1", "decision": "kill"}]
    })
    _write_failure_memory(cfg)
    write_json(cfg.run_dir / "self_audit.json", {"status": "pass", "score": 1.0})
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    _write_minimal_manifest(cfg)
    latest = _production_run_record(cfg.run_date, agent_status)
    append_jsonl(cfg.knowledge_root / "run_history.jsonl", latest)
    write_json(cfg.knowledge_root / "run_history_latest.json", latest)

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert not payload["checks"]["has_365_successful_runs"]
    assert not payload["checks"]["has_365_production_evidence_runs"]
    assert payload["history"]["successful_audited_runs"] == 1
    assert "365-day unattended proof missing" in "\n".join(payload["blockers"])


def test_readiness_blocks_latest_killed_factor_without_failure_memory(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    run_dates = _run_dates_ending_at(cfg.run_date)
    for run_date in run_dates:
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", _production_run_record(run_date, agent_status))
    _write_successful_invocations(cfg, run_dates)
    _write_production_data_artifacts(cfg, run_dates)
    _write_complete_knowledge_saves(cfg, run_dates)
    _write_production_source_snapshots(cfg, run_dates)
    write_json(cfg.knowledge_root / "factor_database" / "factors.json", {
        "factors": [{"run_date": cfg.run_date, "factor_id": "F1", "decision": "kill"}]
    })
    (cfg.knowledge_root / "failure_memory.jsonl").write_text(
        '{"run_date":"20260603","factor_id":"F1"}\n',
        encoding="utf-8",
    )
    write_json(cfg.run_dir / "self_audit.json", {"status": "pass", "score": 1.0})
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    _write_minimal_manifest(cfg)

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert not payload["checks"]["latest_killed_factors_have_failure_memory"]
    assert payload["knowledge_base"]["latest_killed_factor_ids"] == ["F1"]
    assert payload["knowledge_base"]["same_day_failure_memory_factor_ids"] == []
    assert "latest killed factors are missing same-day failure memory records" in "\n".join(payload["blockers"])


def test_readiness_blocks_killed_factor_failure_memory_without_details(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    run_dates = _run_dates_ending_at(cfg.run_date)
    for run_date in run_dates:
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", _production_run_record(run_date, agent_status))
    _write_successful_invocations(cfg, run_dates)
    _write_production_data_artifacts(cfg, run_dates)
    _write_complete_knowledge_saves(cfg, run_dates)
    _write_production_source_snapshots(cfg, run_dates)
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    _write_minimal_manifest(cfg)
    (cfg.knowledge_root / "failure_memory.jsonl").write_text(
        f'{{"run_date":"{cfg.run_date}","factor_id":"F1","formula_key":"rank(ret_5)"}}\n',
        encoding="utf-8",
    )

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert payload["checks"]["latest_killed_factors_have_failure_memory"]
    assert not payload["checks"]["latest_killed_factor_failure_memory_details_match"]
    assert payload["knowledge_base"]["failure_memory_detail_match"] is False
    assert "latest killed factor failure memory records do not match critique issues" in "\n".join(payload["blockers"])


def test_readiness_blocks_extra_same_day_failure_memory_record(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    run_dates = _run_dates_ending_at(cfg.run_date)
    for run_date in run_dates:
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", _production_run_record(run_date, agent_status))
    _write_successful_invocations(cfg, run_dates)
    _write_production_data_artifacts(cfg, run_dates)
    _write_complete_knowledge_saves(cfg, run_dates)
    _write_production_source_snapshots(cfg, run_dates)
    _write_failure_memory(cfg)
    append_jsonl(cfg.knowledge_root / "failure_memory.jsonl", {
        "run_date": cfg.run_date,
        "factor_id": "STALE_FAILURE",
        "formula_key": "rank(stale)",
        "issues": ["stale_extra_record"],
        "checks": {"leakage": {"score": "pass"}},
        "parent_metrics": {"rankic_mean": 0.0},
        "next_actions": ["STALE_NEXT"],
    })
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    _write_minimal_manifest(cfg)

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert not payload["checks"]["latest_killed_factors_have_failure_memory"]
    assert payload["knowledge_base"]["latest_killed_factor_ids"] == ["F1"]
    assert payload["knowledge_base"]["same_day_failure_memory_factor_ids"] == ["F1", "STALE_FAILURE"]
    assert "failure memory has extra same-day records" in "\n".join(payload["blockers"])


def test_readiness_blocks_killed_factor_failure_memory_with_stale_next_actions(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    run_dates = _run_dates_ending_at(cfg.run_date)
    for run_date in run_dates:
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", _production_run_record(run_date, agent_status))
    _write_successful_invocations(cfg, run_dates)
    _write_production_data_artifacts(cfg, run_dates)
    _write_complete_knowledge_saves(cfg, run_dates)
    _write_production_source_snapshots(cfg, run_dates)
    _write_failure_memory(cfg, _failure_memory_payload(cfg) | {"next_actions": ["STALE_PIVOT"]})
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    _write_minimal_manifest(cfg)

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert payload["checks"]["latest_killed_factors_have_failure_memory"]
    assert not payload["checks"]["latest_killed_factor_failure_memory_details_match"]
    assert payload["knowledge_base"]["failure_memory_detail_match"] is False
    assert "latest killed factor failure memory records do not match critique issues" in "\n".join(payload["blockers"])


def test_readiness_blocks_current_invocation_with_stale_latest_run_history(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    stale_end = (date.fromisoformat(f"{cfg.run_date[:4]}-{cfg.run_date[4:6]}-{cfg.run_date[6:]}") - timedelta(days=1)).strftime("%Y%m%d")
    run_dates = _run_dates_ending_at(stale_end)
    for run_date in run_dates:
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", _production_run_record(run_date, agent_status))
    _write_successful_invocations(cfg, run_dates + [cfg.run_date])
    _write_production_data_artifacts(cfg, run_dates)
    _write_complete_knowledge_saves(cfg, run_dates)
    _write_production_source_snapshots(cfg, run_dates)
    write_json(cfg.knowledge_root / "factor_database" / "factors.json", {
        "factors": [{"factor_id": "F1", "decision": "kill"}]
    })
    (cfg.knowledge_root / "failure_memory.jsonl").write_text('{"factor_id":"F1"}\n', encoding="utf-8")
    write_json(cfg.run_dir / "self_audit.json", {"status": "pass", "score": 1.0})
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    _write_minimal_manifest(cfg)

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert payload["checks"]["has_365_successful_runs"]
    assert payload["checks"]["has_365_production_evidence_runs"]
    assert payload["checks"]["run_daily_invocation_matches_run_date"]
    assert not payload["checks"]["latest_run_history_matches_run_date"]
    assert "latest run_history record does not match current run_date" in "\n".join(payload["blockers"])


def test_readiness_blocks_run_history_that_does_not_match_current_outputs(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    run_dates = _run_dates_ending_at(cfg.run_date)
    for run_date in run_dates:
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", _production_run_record(run_date, agent_status))
    _write_successful_invocations(cfg, run_dates)
    _write_production_data_artifacts(cfg, run_dates)
    _write_complete_knowledge_saves(cfg, run_dates)
    _write_production_source_snapshots(cfg, run_dates)
    _write_failure_memory(cfg)
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    _write_minimal_manifest(cfg)
    stale_history = _production_run_record(cfg.run_date, agent_status)
    stale_history["counts"]["backtest_results"] = 999
    append_jsonl(cfg.knowledge_root / "run_history.jsonl", stale_history)
    write_json(cfg.knowledge_root / "run_history_latest.json", stale_history)
    artifact_manifest.run(cfg)

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert payload["checks"]["latest_run_history_matches_run_date"]
    assert not payload["checks"]["latest_run_history_matches_current_outputs"]
    assert payload["history"]["latest_matches_current_outputs"] is False
    assert payload["history"]["latest_counts"]["backtest_results"] == 999
    assert payload["history"]["current_counts"]["backtest_results"] == 1
    assert "latest run_history record does not match current daily outputs" in "\n".join(payload["blockers"])


def test_readiness_blocks_365_run_history_without_source_snapshots(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    run_dates = [_run_date(i) for i in range(365)]
    for run_date in run_dates:
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", _production_run_record(run_date, agent_status))
    _write_successful_invocations(cfg, run_dates)
    write_json(cfg.knowledge_root / "factor_database" / "factors.json", {
        "factors": [{"factor_id": "F1", "decision": "kill"}]
    })
    (cfg.knowledge_root / "failure_memory.jsonl").write_text('{"factor_id":"F1"}\n', encoding="utf-8")
    (cfg.knowledge_root / "research_log.jsonl").write_text('{"run_date":"20260604"}\n', encoding="utf-8")
    (cfg.knowledge_root / "source_snapshots.jsonl").write_text('{"run_date":"20260604","agent":"market_intelligence"}\n', encoding="utf-8")
    write_json(cfg.run_dir / "self_audit.json", {"status": "pass", "score": 1.0})
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    _write_minimal_manifest(cfg)

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert payload["checks"]["has_365_successful_runs"]
    assert payload["checks"]["has_365_production_evidence_runs"]
    assert payload["checks"]["has_365_successful_run_daily_invocations"]
    assert not payload["checks"]["has_365_source_snapshot_dates"]
    assert not payload["checks"]["has_365_consecutive_source_snapshot_dates"]
    assert not payload["checks"]["production_evidence_dates_have_source_snapshots"]


def test_readiness_blocks_source_snapshots_without_replayable_items(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    run_dates = _run_dates_ending_at(cfg.run_date)
    for run_date in run_dates:
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", _production_run_record(run_date, agent_status))
    _write_successful_invocations(cfg, run_dates)
    _write_production_data_artifacts(cfg, run_dates)
    _write_complete_knowledge_saves(cfg, run_dates)
    source_quality = {
        "mode": "live",
        "total_sources": 3,
        "ok_sources": 3,
        "error_sources": 0,
        "coverage_ratio": 1.0,
        "missing_kinds": [],
        "fallback_used": False,
    }
    for run_date in run_dates:
        for agent in ["market_intelligence", "research_agent"]:
            append_jsonl(cfg.knowledge_root / "source_snapshots.jsonl", {
                "run_date": run_date,
                "agent": agent,
                "source_quality": source_quality,
                "source_status": [{"name": "source", "kind": "news", "status": "ok", "items": 0}],
                "item_count": 0,
                "items": [],
            })
    write_json(cfg.knowledge_root / "factor_database" / "factors.json", {
        "factors": [{"factor_id": "F1", "decision": "kill"}]
    })
    (cfg.knowledge_root / "failure_memory.jsonl").write_text('{"factor_id":"F1"}\n', encoding="utf-8")
    write_json(cfg.run_dir / "self_audit.json", {"status": "pass", "score": 1.0})
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    _write_minimal_manifest(cfg)

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert payload["checks"]["has_365_production_evidence_runs"]
    assert not payload["checks"]["has_365_source_snapshot_dates"]
    assert not payload["checks"]["has_365_consecutive_source_snapshot_dates"]
    assert not payload["checks"]["production_evidence_dates_have_source_snapshots"]
    assert payload["source_snapshot_evidence"]["production_source_snapshot_dates"] == 0


def test_readiness_blocks_365_run_history_without_data_artifacts(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    run_dates = [_run_date(i) for i in range(365)]
    for run_date in run_dates:
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", _production_run_record(run_date, agent_status))
    _write_successful_invocations(cfg, run_dates)
    _write_production_source_snapshots(cfg, run_dates)
    write_json(cfg.knowledge_root / "factor_database" / "factors.json", {
        "factors": [{"factor_id": "F1", "decision": "kill"}]
    })
    (cfg.knowledge_root / "failure_memory.jsonl").write_text('{"factor_id":"F1"}\n', encoding="utf-8")
    (cfg.knowledge_root / "research_log.jsonl").write_text('{"run_date":"20260604"}\n', encoding="utf-8")
    write_json(cfg.run_dir / "self_audit.json", {"status": "pass", "score": 1.0})
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    _write_minimal_manifest(cfg)

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert payload["checks"]["has_365_successful_runs"]
    assert payload["checks"]["has_365_production_evidence_runs"]
    assert not payload["checks"]["data_health_log_present"]
    assert not payload["checks"]["has_365_data_artifact_dates"]
    assert not payload["checks"]["has_365_consecutive_data_artifact_dates"]
    assert not payload["checks"]["production_evidence_dates_have_data_artifacts"]


def test_readiness_blocks_365_run_history_without_knowledge_saves(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    run_dates = [_run_date(i) for i in range(365)]
    for run_date in run_dates:
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", _production_run_record(run_date, agent_status))
    _write_successful_invocations(cfg, run_dates)
    _write_production_source_snapshots(cfg, run_dates)
    _write_production_data_artifacts(cfg, run_dates)
    write_json(cfg.knowledge_root / "factor_database" / "factors.json", {
        "factors": [{"factor_id": "F1", "decision": "kill"}]
    })
    (cfg.knowledge_root / "failure_memory.jsonl").write_text('{"factor_id":"F1"}\n', encoding="utf-8")
    append_jsonl(cfg.knowledge_root / "research_log.jsonl", {
        "run_date": cfg.run_date,
        "pipeline": {"run_quality": "complete"},
        "factor_database_write": {"status": "skipped", "reason": "test_missing_save"},
    })
    write_json(cfg.run_dir / "self_audit.json", {"status": "pass", "score": 1.0})
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    _write_minimal_manifest(cfg)

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert payload["checks"]["has_365_successful_runs"]
    assert payload["checks"]["has_365_production_evidence_runs"]
    assert payload["checks"]["has_365_successful_run_daily_invocations"]
    assert payload["checks"]["has_365_source_snapshot_dates"]
    assert payload["checks"]["has_365_data_artifact_dates"]
    assert payload["checks"]["research_log_present"]
    assert not payload["checks"]["has_365_knowledge_save_dates"]
    assert not payload["checks"]["has_365_consecutive_knowledge_save_dates"]
    assert not payload["checks"]["production_evidence_dates_have_knowledge_saves"]
    assert payload["knowledge_save_evidence"]["knowledge_save_dates"] == 0


def test_readiness_blocks_knowledge_saves_without_recorded_at(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    run_dates = _run_dates_ending_at(cfg.run_date)
    for run_date in run_dates:
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", _production_run_record(run_date, agent_status))
    _write_successful_invocations(cfg, run_dates)
    _write_production_source_snapshots(cfg, run_dates)
    _write_production_data_artifacts(cfg, run_dates)
    _write_complete_knowledge_saves(cfg, run_dates)
    _write_failure_memory(cfg)
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    _write_minimal_manifest(cfg)
    research_log_path = cfg.knowledge_root / "research_log.jsonl"
    rows = [json.loads(line) for line in research_log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    rows[0].pop("recorded_at", None)
    research_log_path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows) + "\n",
        encoding="utf-8",
    )
    artifact_manifest.run(cfg)

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert payload["checks"]["has_365_successful_runs"]
    assert not payload["checks"]["has_365_knowledge_save_dates"]
    assert payload["knowledge_save_evidence"]["knowledge_save_dates"] == 364
    assert payload["knowledge_save_evidence"]["production_evidence_dates_without_knowledge_saves"] == [run_dates[0]]


def test_readiness_blocks_knowledge_save_without_saved_factor_ids(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    run_dates = _run_dates_ending_at(cfg.run_date)
    for run_date in run_dates:
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", _production_run_record(run_date, agent_status))
    _write_successful_invocations(cfg, run_dates)
    _write_production_source_snapshots(cfg, run_dates)
    _write_production_data_artifacts(cfg, run_dates)
    _write_complete_knowledge_saves(cfg, run_dates)
    write_json(cfg.knowledge_root / "factor_database" / "factors.json", {
        "factors": [{"factor_id": "F1", "decision": "kill"}]
    })
    (cfg.knowledge_root / "failure_memory.jsonl").write_text('{"factor_id":"F1"}\n', encoding="utf-8")
    write_json(cfg.run_dir / "self_audit.json", {"status": "pass", "score": 1.0})
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    _write_minimal_manifest(cfg)

    lines = []
    for line in (cfg.knowledge_root / "research_log.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row["run_date"] == run_dates[0]:
            row["factor_database_write"]["saved_factor_count"] = 1
            row["factor_database_write"]["saved_factor_ids"] = []
        lines.append(json.dumps(row, ensure_ascii=False, sort_keys=True))
    (cfg.knowledge_root / "research_log.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert payload["checks"]["has_365_successful_runs"]
    assert payload["checks"]["has_365_production_evidence_runs"]
    assert not payload["checks"]["has_365_knowledge_save_dates"]
    assert not payload["checks"]["has_365_consecutive_knowledge_save_dates"]
    assert not payload["checks"]["production_evidence_dates_have_knowledge_saves"]
    assert payload["knowledge_save_evidence"]["knowledge_save_dates"] == 364
    assert payload["knowledge_save_evidence"]["production_evidence_dates_without_knowledge_saves"] == [run_dates[0]]


def test_readiness_blocks_365_run_history_without_365_run_daily_invocations(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    run_dates = [_run_date(i) for i in range(365)]
    for run_date in run_dates:
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", _production_run_record(run_date, agent_status))
    _write_successful_invocations(cfg, [cfg.run_date])
    write_json(cfg.knowledge_root / "factor_database" / "factors.json", {
        "factors": [{"factor_id": "F1", "decision": "kill"}]
    })
    (cfg.knowledge_root / "failure_memory.jsonl").write_text('{"factor_id":"F1"}\n', encoding="utf-8")
    (cfg.knowledge_root / "research_log.jsonl").write_text('{"run_date":"20260604"}\n', encoding="utf-8")
    (cfg.knowledge_root / "source_snapshots.jsonl").write_text('{"run_date":"20260604"}\n', encoding="utf-8")
    write_json(cfg.run_dir / "self_audit.json", {"status": "pass", "score": 1.0})
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    _write_minimal_manifest(cfg)

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert payload["checks"]["has_365_successful_runs"]
    assert payload["checks"]["has_365_production_evidence_runs"]
    assert not payload["checks"]["has_365_successful_run_daily_invocations"]
    assert not payload["checks"]["has_365_unique_successful_run_daily_invocation_dates"]
    assert not payload["checks"]["has_365_consecutive_successful_run_daily_invocation_dates"]
    assert not payload["checks"]["production_evidence_dates_have_successful_run_daily_invocations"]


def test_readiness_blocks_missing_run_daily_invocation(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    for i in range(365):
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", _production_run_record(_run_date(i), agent_status))
    write_json(cfg.knowledge_root / "factor_database" / "factors.json", {
        "factors": [{"factor_id": "F1", "decision": "kill"}]
    })
    (cfg.knowledge_root / "failure_memory.jsonl").write_text('{"factor_id":"F1"}\n', encoding="utf-8")
    (cfg.knowledge_root / "research_log.jsonl").write_text('{"run_date":"20260604"}\n', encoding="utf-8")
    (cfg.knowledge_root / "source_snapshots.jsonl").write_text('{"run_date":"20260604"}\n', encoding="utf-8")
    write_json(cfg.run_dir / "self_audit.json", {"status": "pass", "score": 1.0})
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    _write_minimal_manifest(cfg, invocation=False)

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert not payload["checks"]["run_daily_invocation_present"]
    assert "run_daily shell invocation record is missing" in payload["blockers"]


def test_readiness_blocks_failed_run_daily_invocation(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    for i in range(365):
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", _production_run_record(_run_date(i), agent_status))
    write_json(cfg.knowledge_root / "factor_database" / "factors.json", {"factors": [{"factor_id": "F1"}]})
    (cfg.knowledge_root / "failure_memory.jsonl").write_text('{"factor_id":"F1"}\n', encoding="utf-8")
    (cfg.knowledge_root / "research_log.jsonl").write_text('{"run_date":"20260604"}\n', encoding="utf-8")
    (cfg.knowledge_root / "source_snapshots.jsonl").write_text('{"run_date":"20260604"}\n', encoding="utf-8")
    write_json(cfg.run_dir / "self_audit.json", {"status": "pass", "score": 1.0})
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    _write_minimal_manifest(cfg, invocation={"status": "error", "exit_code": 1})

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert payload["checks"]["run_daily_invocation_present"]
    assert not payload["checks"]["run_daily_invocation_success"]
    assert "run_daily shell invocation did not succeed" in "\n".join(payload["blockers"])


def test_readiness_blocks_successful_invocation_without_shell_provenance(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    for i in range(365):
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", _production_run_record(_run_date(i), agent_status))
    write_json(cfg.knowledge_root / "factor_database" / "factors.json", {"factors": [{"factor_id": "F1"}]})
    (cfg.knowledge_root / "failure_memory.jsonl").write_text('{"factor_id":"F1"}\n', encoding="utf-8")
    (cfg.knowledge_root / "research_log.jsonl").write_text('{"run_date":"20260604"}\n', encoding="utf-8")
    (cfg.knowledge_root / "source_snapshots.jsonl").write_text('{"run_date":"20260604"}\n', encoding="utf-8")
    write_json(cfg.run_dir / "self_audit.json", {"status": "pass", "score": 1.0})
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    _write_minimal_manifest(cfg, invocation={
        "status": "success",
        "exit_code": 0,
        "shell_entrypoint": False,
        "entrypoint_script": None,
        "entrypoint_script_exists": False,
        "entrypoint_command": None,
    })

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert payload["checks"]["run_daily_invocation_present"]
    assert not payload["checks"]["run_daily_invocation_success"]
    assert payload["run_daily_invocation"]["shell_entrypoint"] is False
    assert "run_daily shell invocation did not succeed" in "\n".join(payload["blockers"])


def test_readiness_blocks_invocation_from_different_run_daily_script(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    run_dates = _run_dates_ending_at(cfg.run_date)
    for run_date in run_dates:
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", _production_run_record(run_date, agent_status))
    other_repo = tmp_path / "other_repo"
    other_repo.mkdir()
    other_run_daily = other_repo / "run_daily.sh"
    other_run_daily.write_text("#!/usr/bin/env bash\npython -m agent.run_entrypoint\n", encoding="utf-8")
    other_run_daily.chmod(0o755)
    _write_successful_invocations(cfg, run_dates, entrypoint_script=other_run_daily)
    _write_production_data_artifacts(cfg, run_dates)
    _write_complete_knowledge_saves(cfg, run_dates)
    _write_production_source_snapshots(cfg, run_dates)
    _write_failure_memory(cfg)
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    _write_minimal_manifest(cfg, invocation={"entrypoint_script": str(other_run_daily)})

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert payload["checks"]["run_daily_invocation_present"]
    assert not payload["checks"]["run_daily_invocation_success"]
    assert not payload["checks"]["has_365_successful_run_daily_invocations"]
    assert payload["run_daily_invocation"]["entrypoint_script"] == str(other_run_daily)
    assert payload["run_daily_invocation"]["expected_entrypoint_script"] == str(Path.cwd() / "run_daily.sh")
    assert "run_daily shell invocation did not succeed" in "\n".join(payload["blockers"])


def test_readiness_blocks_successful_invocation_without_finished_at(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    run_dates = _run_dates_ending_at(cfg.run_date)
    for run_date in run_dates:
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", _production_run_record(run_date, agent_status))
    _write_successful_invocations(cfg, run_dates)
    _write_production_data_artifacts(cfg, run_dates)
    _write_complete_knowledge_saves(cfg, run_dates)
    _write_production_source_snapshots(cfg, run_dates)
    _write_failure_memory(cfg)
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    _write_minimal_manifest(cfg)
    invocation_path = cfg.output_root / "run_daily_invocations.jsonl"
    rows = [json.loads(line) for line in invocation_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    rows[0].pop("finished_at", None)
    invocation_path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows) + "\n",
        encoding="utf-8",
    )
    artifact_manifest.run(cfg)

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert payload["checks"]["has_365_successful_runs"]
    assert not payload["checks"]["has_365_successful_run_daily_invocations"]
    assert not payload["checks"]["has_365_consecutive_successful_run_daily_invocation_dates"]
    assert payload["run_daily_invocation"]["successful_invocations"] == 364
    assert "365 successful run_daily shell invocations missing" in "\n".join(payload["blockers"])


def test_readiness_blocks_successful_invocation_with_cross_date_timestamps(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    run_dates = _run_dates_ending_at(cfg.run_date)
    for run_date in run_dates:
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", _production_run_record(run_date, agent_status))
    _write_successful_invocations(cfg, run_dates)
    _write_production_data_artifacts(cfg, run_dates)
    _write_complete_knowledge_saves(cfg, run_dates)
    _write_production_source_snapshots(cfg, run_dates)
    _write_failure_memory(cfg)
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    _write_minimal_manifest(cfg)
    invocation_path = cfg.output_root / "run_daily_invocations.jsonl"
    rows = [json.loads(line) for line in invocation_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    rows[-1]["finished_at"] = "2026-06-05T00:00:01+00:00"
    invocation_path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows) + "\n",
        encoding="utf-8",
    )
    write_json(cfg.output_root / "run_daily_invocation_latest.json", rows[-1])
    artifact_manifest.run(cfg)

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert payload["checks"]["has_365_successful_runs"]
    assert payload["checks"]["run_daily_invocation_present"]
    assert not payload["checks"]["run_daily_invocation_success"]
    assert not payload["checks"]["run_daily_invocation_timestamps_match_run_date"]
    assert not payload["checks"]["has_365_successful_run_daily_invocations"]
    assert payload["run_daily_invocation"]["successful_invocations"] == 364
    assert payload["run_daily_invocation"]["timestamps_match_run_date"] is False
    assert "run_daily shell invocation timestamps do not match invocation run_date" in "\n".join(payload["blockers"])


def test_readiness_blocks_run_daily_invocation_date_mismatch(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    for i in range(365):
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", _production_run_record(_run_date(i), agent_status))
    write_json(cfg.knowledge_root / "factor_database" / "factors.json", {"factors": [{"factor_id": "F1"}]})
    (cfg.knowledge_root / "failure_memory.jsonl").write_text('{"factor_id":"F1"}\n', encoding="utf-8")
    (cfg.knowledge_root / "research_log.jsonl").write_text('{"run_date":"20260604"}\n', encoding="utf-8")
    (cfg.knowledge_root / "source_snapshots.jsonl").write_text('{"run_date":"20260604"}\n', encoding="utf-8")
    write_json(cfg.run_dir / "self_audit.json", {"status": "pass", "score": 1.0})
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    _write_minimal_manifest(cfg, invocation={
        "run_date": "20260603",
        "started_at": "2026-06-03T00:00:00+00:00",
        "finished_at": "2026-06-03T00:00:01+00:00",
    })

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert payload["checks"]["run_daily_invocation_success"]
    assert not payload["checks"]["run_daily_invocation_matches_run_date"]
    assert payload["checks"]["run_daily_invocation_timestamps_match_run_date"]
    assert "run_daily shell invocation run_date mismatch" in "\n".join(payload["blockers"])


def test_readiness_blocks_run_history_recorded_at_date_mismatch(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    run_dates = _run_dates_ending_at(cfg.run_date)
    for run_date in run_dates:
        row = _production_run_record(run_date, agent_status)
        row["recorded_at"] = f"{run_date[:4]}-{run_date[4:6]}-{run_date[6:]}T00:00:02+00:00"
        if run_date == cfg.run_date:
            row["recorded_at"] = "2026-06-05T00:00:02+00:00"
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", row)
    _write_successful_invocations(cfg, run_dates)
    _write_production_data_artifacts(cfg, run_dates)
    _write_complete_knowledge_saves(cfg, run_dates)
    _write_production_source_snapshots(cfg, run_dates)
    _write_failure_memory(cfg)
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    _write_minimal_manifest(cfg)

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert not payload["checks"]["latest_run_history_recorded_at_matches_run_date"]
    assert not payload["checks"]["has_365_successful_runs"]
    assert payload["history"]["successful_audited_runs"] == 364
    assert payload["history"]["latest_recorded_at_matches_run_date"] is False
    assert "latest run_history recorded_at does not match its run_date" in "\n".join(payload["blockers"])


def test_readiness_quarantines_corrupt_jsonl_without_losing_latest_valid_run(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    for i in range(365):
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", _production_run_record(_run_date(i), agent_status))
    with (cfg.knowledge_root / "run_history.jsonl").open("a", encoding="utf-8") as f:
        f.write("{broken trailing json\n")
    write_json(cfg.knowledge_root / "factor_database" / "factors.json", {
        "factors": [{"factor_id": "F1", "decision": "kill"}]
    })
    (cfg.knowledge_root / "failure_memory.jsonl").write_text(
        '{"factor_id":"F1","formula_key":"rank(ret_5)"}\n',
        encoding="utf-8",
    )
    (cfg.knowledge_root / "research_log.jsonl").write_text(
        '{"run_date":"20260604","research":{"idea_count":1}}\n',
        encoding="utf-8",
    )
    (cfg.knowledge_root / "source_snapshots.jsonl").write_text(
        '{"run_date":"20260604","agent":"market_intelligence","item_count":1}\n',
        encoding="utf-8",
    )
    write_json(cfg.run_dir / "self_audit.json", {"status": "pass", "score": 1.0})
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    _write_minimal_manifest(cfg)

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert payload["checks"]["has_365_successful_runs"]
    assert not payload["checks"]["no_jsonl_parse_errors"]
    assert payload["jsonl_integrity"]["error_counts"]["run_history.jsonl"] == 1
    assert "latest run missing required agent records" not in "\n".join(payload["blockers"])
    quarantine = cfg.knowledge_root / "jsonl_quarantine" / "run_history.jsonl.corrupt.jsonl"
    assert quarantine.exists()


def test_readiness_blocks_when_artifact_manifest_missing_required_file(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    for i in range(365):
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", _production_run_record(_run_date(i), agent_status))
    write_json(cfg.knowledge_root / "factor_database" / "factors.json", {"factors": [{"factor_id": "F1"}]})
    (cfg.knowledge_root / "failure_memory.jsonl").write_text('{"factor_id":"F1"}\n', encoding="utf-8")
    (cfg.knowledge_root / "research_log.jsonl").write_text('{"run_date":"20260604"}\n', encoding="utf-8")
    (cfg.knowledge_root / "source_snapshots.jsonl").write_text('{"run_date":"20260604"}\n', encoding="utf-8")
    write_json(cfg.run_dir / "self_audit.json", {"status": "pass", "score": 1.0})
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    write_json(cfg.run_dir / "artifact_manifest.json", {
        "files": [
            {"relative_path": "daily_report.md", "sha256": "a"},
            {"relative_path": "pipeline_state.json", "sha256": "b"},
        ]
    })

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert not payload["checks"]["artifact_manifest_required_files_present"]
    assert "candidate_factors.json" in payload["artifact_manifest"]["missing_required_paths"]
    assert "backtest_results.json" in payload["artifact_manifest"]["missing_required_paths"]
    assert "READINESS_REPORT.md" in payload["artifact_manifest"]["missing_required_paths"]


def test_readiness_blocks_stale_artifact_manifest_run_date(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    run_dates = _run_dates_ending_at(cfg.run_date)
    for run_date in run_dates:
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", _production_run_record(run_date, agent_status))
    _write_successful_invocations(cfg, run_dates)
    _write_production_data_artifacts(cfg, run_dates)
    _write_complete_knowledge_saves(cfg, run_dates)
    _write_production_source_snapshots(cfg, run_dates)
    write_json(cfg.knowledge_root / "factor_database" / "factors.json", {"factors": [{"factor_id": "F1"}]})
    (cfg.knowledge_root / "failure_memory.jsonl").write_text('{"factor_id":"F1"}\n', encoding="utf-8")
    write_json(cfg.run_dir / "self_audit.json", {"status": "pass", "score": 1.0})
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    _write_minimal_manifest(cfg)
    manifest_path = cfg.run_dir / "artifact_manifest.json"
    manifest = read_json(manifest_path, {})
    manifest["run_date"] = "20260603"
    write_json(manifest_path, manifest)

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert payload["checks"]["artifact_manifest_present"]
    assert not payload["checks"]["artifact_manifest_matches_run_date"]
    assert payload["checks"]["artifact_manifest_required_files_present"]
    assert "artifact manifest run_date mismatch" in "\n".join(payload["blockers"])


def test_readiness_blocks_stale_artifact_manifest_latest(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    run_dates = _run_dates_ending_at(cfg.run_date)
    for run_date in run_dates:
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", _production_run_record(run_date, agent_status))
    _write_successful_invocations(cfg, run_dates)
    _write_production_data_artifacts(cfg, run_dates)
    _write_complete_knowledge_saves(cfg, run_dates)
    _write_production_source_snapshots(cfg, run_dates)
    write_json(cfg.knowledge_root / "factor_database" / "factors.json", {"factors": [{"factor_id": "F1"}]})
    _write_failure_memory(cfg)
    write_json(cfg.run_dir / "self_audit.json", {"status": "pass", "score": 1.0})
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    _write_minimal_manifest(cfg)
    latest = read_json(cfg.output_root / "artifact_manifest_latest.json", {})
    for item in latest["files"]:
        if item.get("relative_path") == "backtest_results.json":
            item["sha256"] = "stale"
            break
    write_json(cfg.output_root / "artifact_manifest_latest.json", latest)

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert not payload["checks"]["artifact_manifest_latest_matches_current_manifest"]
    assert payload["artifact_manifest"]["latest_matches_current_manifest"] is False
    assert "artifact_manifest_latest.json does not match current run artifact_manifest.json" in "\n".join(payload["blockers"])


def test_readiness_manifest_latest_ignores_mutable_readiness_outputs(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    run_dates = _run_dates_ending_at(cfg.run_date)
    for run_date in run_dates:
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", _production_run_record(run_date, agent_status))
    _write_successful_invocations(cfg, run_dates)
    _write_production_data_artifacts(cfg, run_dates)
    _write_complete_knowledge_saves(cfg, run_dates)
    _write_production_source_snapshots(cfg, run_dates)
    write_json(cfg.knowledge_root / "factor_database" / "factors.json", {"factors": [{"factor_id": "F1"}]})
    _write_failure_memory(cfg)
    write_json(cfg.run_dir / "self_audit.json", {"status": "pass", "score": 1.0})
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    _write_minimal_manifest(cfg)
    latest = read_json(cfg.output_root / "artifact_manifest_latest.json", {})
    for item in latest["files"]:
        if item.get("relative_path") == "READINESS_REPORT.json":
            item["sha256"] = "mutable"
            item["size_bytes"] = (item.get("size_bytes") or 0) + 999
            latest["total_size_bytes"] = (latest.get("total_size_bytes") or 0) + 999
            break
    write_json(cfg.output_root / "artifact_manifest_latest.json", latest)

    payload = readiness_report.run(cfg)

    assert payload["checks"]["artifact_manifest_latest_matches_current_manifest"]
    assert payload["artifact_manifest"]["latest_matches_current_manifest"] is True
    assert payload["artifact_manifest"]["stable_total_size_bytes"] == payload["artifact_manifest"]["latest_stable_total_size_bytes"]
    assert "READINESS_REPORT.json" in payload["artifact_manifest"]["mutable_readiness_paths"]


def test_readiness_blocks_stale_artifact_verification_latest(tmp_path: Path, monkeypatch) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    run_dates = _run_dates_ending_at(cfg.run_date)
    for run_date in run_dates:
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", _production_run_record(run_date, agent_status))
    _write_successful_invocations(cfg, run_dates)
    _write_production_data_artifacts(cfg, run_dates)
    _write_complete_knowledge_saves(cfg, run_dates)
    _write_production_source_snapshots(cfg, run_dates)
    write_json(cfg.knowledge_root / "factor_database" / "factors.json", {"factors": [{"factor_id": "F1"}]})
    _write_failure_memory(cfg)
    write_json(cfg.run_dir / "self_audit.json", {"status": "pass", "score": 1.0})
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    _write_minimal_manifest(cfg)
    current_verification = readiness_report.verify_manifest(cfg)
    stale_latest = dict(current_verification)
    stale_latest["manifest_generated_at"] = "2026-06-03T00:00:00+00:00"
    write_json(cfg.output_root / "artifact_verification_latest.json", stale_latest)

    def fake_verify_manifest(config):
        return current_verification

    monkeypatch.setattr(readiness_report, "verify_manifest", fake_verify_manifest)

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert payload["checks"]["artifact_manifest_verification_passed"]
    assert not payload["checks"]["artifact_verification_latest_matches_current_verification"]
    assert payload["artifact_manifest"]["verification"]["latest_matches_current_verification"] is False
    assert "artifact_verification_latest.json does not match current run artifact_verification.json" in "\n".join(
        payload["blockers"]
    )


def test_readiness_blocks_stale_artifact_verification_current_manifest(tmp_path: Path, monkeypatch) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    run_dates = _run_dates_ending_at(cfg.run_date)
    for run_date in run_dates:
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", _production_run_record(run_date, agent_status))
    _write_successful_invocations(cfg, run_dates)
    _write_production_data_artifacts(cfg, run_dates)
    _write_complete_knowledge_saves(cfg, run_dates)
    _write_production_source_snapshots(cfg, run_dates)
    write_json(cfg.knowledge_root / "factor_database" / "factors.json", {"factors": [{"factor_id": "F1"}]})
    _write_failure_memory(cfg)
    write_json(cfg.run_dir / "self_audit.json", {"status": "pass", "score": 1.0})
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    _write_minimal_manifest(cfg)
    stale_verification = readiness_report.verify_manifest(cfg)
    stale_verification["manifest_generated_at"] = "2026-06-03T00:00:00+00:00"
    write_json(cfg.output_root / "artifact_verification_latest.json", stale_verification)

    def fake_verify_manifest(config):
        return stale_verification

    monkeypatch.setattr(readiness_report, "verify_manifest", fake_verify_manifest)

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert payload["checks"]["artifact_manifest_verification_passed"]
    assert not payload["checks"]["artifact_manifest_verification_matches_current_manifest"]
    assert payload["artifact_manifest"]["verification"]["matches_current_manifest"] is False
    assert "artifact manifest verification did not check the current artifact_manifest.json" in "\n".join(
        payload["blockers"]
    )


def test_readiness_blocks_stale_knowledge_latest_pointers(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    run_dates = _run_dates_ending_at(cfg.run_date)
    for run_date in run_dates:
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", _production_run_record(run_date, agent_status))
    _write_successful_invocations(cfg, run_dates)
    _write_production_data_artifacts(cfg, run_dates)
    _write_complete_knowledge_saves(cfg, run_dates)
    _write_production_source_snapshots(cfg, run_dates)
    write_json(cfg.knowledge_root / "run_history_latest.json", _production_run_record("20260603", agent_status))
    write_json(cfg.knowledge_root / "factor_database" / "factors.json", {"factors": [{"factor_id": "F1"}]})
    (cfg.knowledge_root / "failure_memory.jsonl").write_text(
        f'{{"run_date":"{cfg.run_date}","factor_id":"F1"}}\n',
        encoding="utf-8",
    )
    write_json(cfg.run_dir / "self_audit.json", {"status": "pass", "score": 1.0})
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    _write_minimal_manifest(cfg)

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert not payload["checks"]["latest_knowledge_pointers_match_run_date"]
    assert not payload["knowledge_base"]["latest_pointer_alignment"]["run_history_latest"]
    assert "latest knowledge pointer files do not match current run_date" in "\n".join(payload["blockers"])


def test_readiness_blocks_stale_run_audit_config(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    run_dates = _run_dates_ending_at(cfg.run_date)
    for run_date in run_dates:
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", _production_run_record(run_date, agent_status))
    _write_successful_invocations(cfg, run_dates)
    _write_production_data_artifacts(cfg, run_dates)
    _write_complete_knowledge_saves(cfg, run_dates)
    _write_production_source_snapshots(cfg, run_dates)
    write_json(cfg.knowledge_root / "factor_database" / "factors.json", {"factors": [{"factor_id": "F1"}]})
    (cfg.knowledge_root / "failure_memory.jsonl").write_text('{"factor_id":"F1"}\n', encoding="utf-8")
    write_json(cfg.run_dir / "self_audit.json", {"status": "pass", "score": 1.0})
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    _write_minimal_manifest(cfg)
    run_audit_path = cfg.run_dir / "run_audit.json"
    run_audit = read_json(run_audit_path, {})
    run_audit["run_date"] = "20260603"
    run_audit["config"]["retention_days"] = cfg.retention_days + 1
    write_json(run_audit_path, run_audit)
    artifact_manifest.run(cfg)

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert not payload["checks"]["latest_run_audit_is_current_evidence"]
    assert payload["run_audit_evidence"]["present"]
    assert payload["run_audit_evidence"]["run_date"] == "20260603"
    assert "latest run_audit does not prove current config/lock/retention evidence" in "\n".join(payload["blockers"])


def test_readiness_blocks_run_audit_state_that_does_not_match_pipeline_state(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    run_dates = _run_dates_ending_at(cfg.run_date)
    for run_date in run_dates:
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", _production_run_record(run_date, agent_status))
    _write_successful_invocations(cfg, run_dates)
    _write_production_data_artifacts(cfg, run_dates)
    _write_complete_knowledge_saves(cfg, run_dates)
    _write_production_source_snapshots(cfg, run_dates)
    write_json(cfg.knowledge_root / "factor_database" / "factors.json", {"factors": [{"factor_id": "F1"}]})
    (cfg.knowledge_root / "failure_memory.jsonl").write_text('{"factor_id":"F1"}\n', encoding="utf-8")
    _write_minimal_manifest(cfg)
    run_audit_path = cfg.run_dir / "run_audit.json"
    run_audit = read_json(run_audit_path, {})
    write_json(cfg.run_dir / "pipeline_state.json", run_audit["state"])
    run_audit["state"]["agents"] = run_audit["state"]["agents"][:-1]
    run_audit["state"]["completed_agents"] = [
        item.get("agent") for item in run_audit["state"]["agents"]
    ]
    write_json(run_audit_path, run_audit)
    artifact_manifest.run(cfg)

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert not payload["checks"]["latest_run_audit_is_current_evidence"]
    assert not payload["run_audit_evidence"]["state_matches_pipeline_state"]
    assert payload["run_audit_evidence"]["audit_agent_count"] < payload["run_audit_evidence"]["pipeline_agent_count"]
    assert "latest run_audit does not prove current config/lock/retention evidence" in "\n".join(payload["blockers"])


def test_readiness_blocks_stale_self_audit_evidence(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    run_dates = _run_dates_ending_at(cfg.run_date)
    for run_date in run_dates:
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", _production_run_record(run_date, agent_status))
    _write_successful_invocations(cfg, run_dates)
    _write_production_data_artifacts(cfg, run_dates)
    _write_complete_knowledge_saves(cfg, run_dates)
    _write_production_source_snapshots(cfg, run_dates)
    write_json(cfg.knowledge_root / "factor_database" / "factors.json", {"factors": [{"factor_id": "F1"}]})
    (cfg.knowledge_root / "failure_memory.jsonl").write_text(
        f'{{"run_date":"{cfg.run_date}","factor_id":"F1"}}\n',
        encoding="utf-8",
    )
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    _write_minimal_manifest(cfg)
    stale_audit = _current_self_audit_payload(cfg)
    stale_audit["run_date"] = "20260603"
    write_json(cfg.run_dir / "self_audit.json", stale_audit)
    artifact_manifest.run(cfg)

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert payload["checks"]["latest_self_audit_pass"]
    assert not payload["checks"]["latest_self_audit_is_current_evidence"]
    assert payload["latest_self_audit"]["run_date"] == "20260603"
    assert payload["latest_self_audit"]["current_complete_evidence"] is False
    assert "latest self_audit.json does not prove current complete self-audit evidence" in "\n".join(payload["blockers"])


def test_readiness_blocks_stale_self_audit_markdown(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    daily_pipeline.run(cfg)
    (cfg.run_dir / "self_audit.md").write_text(
        "# Self Audit\n\nRun date: 20260603\nStatus: pass\nScore: 1.00\n",
        encoding="utf-8",
    )
    artifact_manifest.run(cfg)

    payload = readiness_report.run(cfg)

    assert payload["checks"]["latest_self_audit_is_current_evidence"]
    assert not payload["checks"]["latest_self_audit_markdown_matches_json"]
    assert payload["latest_self_audit"]["markdown_matches_json"] is False
    assert "latest self_audit.md does not match current self_audit.json" in "\n".join(payload["blockers"])


def test_readiness_blocks_self_audit_that_does_not_match_current_outputs(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    run_dates = _run_dates_ending_at(cfg.run_date)
    for run_date in run_dates:
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", _production_run_record(run_date, agent_status))
    _write_successful_invocations(cfg, run_dates)
    _write_production_data_artifacts(cfg, run_dates)
    _write_complete_knowledge_saves(cfg, run_dates)
    _write_production_source_snapshots(cfg, run_dates)
    _write_failure_memory(cfg)
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    _write_minimal_manifest(cfg)
    stale_audit = _current_self_audit_payload(cfg)
    stale_audit["counts"]["backtest_results"] = 999
    write_json(cfg.run_dir / "self_audit.json", stale_audit)
    artifact_manifest.run(cfg)

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert payload["checks"]["latest_self_audit_is_current_evidence"]
    assert not payload["checks"]["latest_self_audit_matches_current_outputs"]
    assert payload["latest_self_audit"]["matches_current_outputs"] is False
    assert payload["latest_self_audit"]["counts"]["backtest_results"] == 999
    assert payload["latest_self_audit"]["current_counts"]["backtest_results"] == 1
    assert "latest self_audit.json does not match current daily outputs" in "\n".join(payload["blockers"])


def test_readiness_blocks_when_artifact_manifest_hash_mismatch(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    for i in range(365):
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", _production_run_record(_run_date(i), agent_status))
    write_json(cfg.knowledge_root / "factor_database" / "factors.json", {"factors": [{"factor_id": "F1"}]})
    (cfg.knowledge_root / "failure_memory.jsonl").write_text('{"factor_id":"F1"}\n', encoding="utf-8")
    (cfg.knowledge_root / "research_log.jsonl").write_text('{"run_date":"20260604"}\n', encoding="utf-8")
    (cfg.knowledge_root / "source_snapshots.jsonl").write_text('{"run_date":"20260604"}\n', encoding="utf-8")
    write_json(cfg.run_dir / "self_audit.json", {"status": "pass", "score": 1.0})
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    _write_minimal_manifest(cfg)
    (cfg.run_dir / "daily_report.md").write_text("# Tampered Daily Report\n", encoding="utf-8")

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert not payload["checks"]["artifact_manifest_verification_passed"]
    assert payload["artifact_manifest"]["verification"]["hash_mismatch_count"] == 1
    assert payload["artifact_manifest"]["verification"]["hash_mismatches"][0]["relative_path"] == "daily_report.md"


def test_readiness_blocks_365_offline_synthetic_runs(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    offline_quality = {
        "mode": "offline",
        "ok_sources": 0,
        "fallback_used": True,
    }
    for i in range(365):
        run_date = _run_date(i)
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", {
            "run_date": run_date,
            "recorded_at": f"{run_date[:4]}-{run_date[4:6]}-{run_date[6:]}T00:00:02+00:00",
            "pipeline_status": "complete",
            "self_audit_status": "pass",
            "self_audit_score": 1.0,
            "agent_status": agent_status,
            "market_source_quality": offline_quality,
            "research_source_quality": offline_quality,
            "data_source_mode": "synthetic_fallback",
            "data_freshness": {"status": "not_applicable_synthetic"},
        })
    write_json(cfg.knowledge_root / "factor_database" / "factors.json", {"factors": [{"factor_id": "F1"}]})
    (cfg.knowledge_root / "failure_memory.jsonl").write_text('{"factor_id":"F1"}\n', encoding="utf-8")
    (cfg.knowledge_root / "research_log.jsonl").write_text('{"run_date":"20260604"}\n', encoding="utf-8")
    (cfg.knowledge_root / "source_snapshots.jsonl").write_text('{"run_date":"20260604"}\n', encoding="utf-8")
    write_json(cfg.run_dir / "self_audit.json", {"status": "pass", "score": 1.0})
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    _write_minimal_manifest(cfg)

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert payload["checks"]["has_365_successful_runs"]
    assert not payload["checks"]["has_365_production_evidence_runs"]
    assert not payload["checks"]["latest_data_is_production_evidence"]
    assert not payload["checks"]["latest_market_sources_are_production_evidence"]
    assert not payload["checks"]["latest_research_sources_are_production_evidence"]


def test_readiness_blocks_partial_live_sources_as_production_evidence(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    partial_quality = {
        "mode": "live",
        "total_sources": 3,
        "ok_sources": 2,
        "error_sources": 1,
        "coverage_ratio": 0.6667,
        "missing_kinds": ["policy"],
        "fallback_used": False,
    }
    for i in range(365):
        row = _production_run_record(_run_date(i), agent_status)
        row["market_source_quality"] = partial_quality
        row["research_source_quality"] = partial_quality
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", row)
    write_json(cfg.knowledge_root / "factor_database" / "factors.json", {"factors": [{"factor_id": "F1"}]})
    (cfg.knowledge_root / "failure_memory.jsonl").write_text('{"factor_id":"F1"}\n', encoding="utf-8")
    (cfg.knowledge_root / "research_log.jsonl").write_text('{"run_date":"20260604"}\n', encoding="utf-8")
    (cfg.knowledge_root / "source_snapshots.jsonl").write_text('{"run_date":"20260604"}\n', encoding="utf-8")
    write_json(cfg.run_dir / "self_audit.json", {"status": "pass", "score": 1.0})
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    _write_minimal_manifest(cfg)

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert payload["checks"]["has_365_successful_runs"]
    assert not payload["checks"]["latest_market_sources_are_production_evidence"]
    assert not payload["checks"]["latest_research_sources_are_production_evidence"]
    assert not payload["checks"]["has_365_production_evidence_runs"]


def test_readiness_blocks_live_sources_without_required_kind_coverage(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    market_quality = {
        "mode": "live",
        "total_sources": 1,
        "ok_sources": 1,
        "error_sources": 0,
        "coverage_ratio": 1.0,
        "covered_kinds": ["news"],
        "missing_kinds": [],
        "fallback_used": False,
    }
    research_quality = {
        **market_quality,
        "covered_kinds": ["paper"],
    }
    for i in range(365):
        row = _production_run_record(_run_date(i), agent_status)
        row["market_source_quality"] = market_quality
        row["research_source_quality"] = research_quality
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", row)
    write_json(cfg.knowledge_root / "factor_database" / "factors.json", {"factors": [{"factor_id": "F1"}]})
    (cfg.knowledge_root / "failure_memory.jsonl").write_text('{"factor_id":"F1"}\n', encoding="utf-8")
    (cfg.knowledge_root / "research_log.jsonl").write_text('{"run_date":"20260604"}\n', encoding="utf-8")
    (cfg.knowledge_root / "source_snapshots.jsonl").write_text('{"run_date":"20260604"}\n', encoding="utf-8")
    write_json(cfg.run_dir / "self_audit.json", {"status": "pass", "score": 1.0})
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    _write_minimal_manifest(cfg)

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert payload["checks"]["has_365_successful_runs"]
    assert not payload["checks"]["latest_market_sources_are_production_evidence"]
    assert not payload["checks"]["latest_research_sources_are_production_evidence"]
    assert not payload["checks"]["has_365_production_evidence_runs"]
    assert payload["latest_production_evidence"]["required_market_source_kinds"] == sorted(
        readiness_report.REQUIRED_MARKET_SOURCE_KINDS
    )
    assert payload["latest_production_evidence"]["required_research_source_kinds"] == sorted(
        readiness_report.REQUIRED_RESEARCH_SOURCE_KINDS
    )


def test_readiness_blocks_duplicate_dates_as_365_day_proof(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    for _ in range(365):
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", _production_run_record("20260604", agent_status))
    write_json(cfg.knowledge_root / "factor_database" / "factors.json", {"factors": [{"factor_id": "F1"}]})
    (cfg.knowledge_root / "failure_memory.jsonl").write_text('{"factor_id":"F1"}\n', encoding="utf-8")
    (cfg.knowledge_root / "research_log.jsonl").write_text('{"run_date":"20260604"}\n', encoding="utf-8")
    (cfg.knowledge_root / "source_snapshots.jsonl").write_text('{"run_date":"20260604"}\n', encoding="utf-8")
    write_json(cfg.run_dir / "self_audit.json", {"status": "pass", "score": 1.0})
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    _write_minimal_manifest(cfg)

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert payload["checks"]["has_365_successful_runs"]
    assert payload["checks"]["has_365_production_evidence_runs"]
    assert not payload["checks"]["has_365_unique_successful_run_dates"]
    assert not payload["checks"]["has_365_unique_production_evidence_dates"]
    assert payload["history"]["unique_successful_run_dates"] == 1
    assert payload["history"]["unique_production_evidence_dates"] == 1


def test_readiness_blocks_non_consecutive_365_day_proof(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.run_dir.mkdir(parents=True)
    agent_status = {name: "ok" for name in readiness_report.REQUIRED_AGENT_NAMES}
    for i in range(365):
        append_jsonl(cfg.knowledge_root / "run_history.jsonl", _production_run_record(_run_date(i * 2), agent_status))
    write_json(cfg.knowledge_root / "factor_database" / "factors.json", {"factors": [{"factor_id": "F1"}]})
    (cfg.knowledge_root / "failure_memory.jsonl").write_text('{"factor_id":"F1"}\n', encoding="utf-8")
    (cfg.knowledge_root / "research_log.jsonl").write_text('{"run_date":"20260604"}\n', encoding="utf-8")
    (cfg.knowledge_root / "source_snapshots.jsonl").write_text('{"run_date":"20260604"}\n', encoding="utf-8")
    write_json(cfg.run_dir / "self_audit.json", {"status": "pass", "score": 1.0})
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": name, "status": "ok"} for name in readiness_report.REQUIRED_AGENT_NAMES],
    })
    _write_minimal_manifest(cfg)

    payload = readiness_report.run(cfg)

    assert payload["status"] == "not_production_ready"
    assert payload["checks"]["has_365_successful_runs"]
    assert payload["checks"]["has_365_unique_successful_run_dates"]
    assert payload["checks"]["has_365_production_evidence_runs"]
    assert payload["checks"]["has_365_unique_production_evidence_dates"]
    assert not payload["checks"]["has_365_consecutive_successful_run_dates"]
    assert not payload["checks"]["has_365_consecutive_production_evidence_dates"]
    assert payload["history"]["longest_successful_date_streak_days"] == 1
    assert payload["history"]["longest_production_evidence_date_streak_days"] == 1
