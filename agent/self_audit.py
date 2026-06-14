from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import RunConfig, load_config
from .io_utils import read_json, write_json


REQUIRED_RUN_FILES = [
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
]


def _exists_nonempty(path: Path) -> bool:
    return path.exists() and path.stat().st_size > 0


def _pipeline_reached_audit_phase(pipeline_state: dict[str, Any]) -> bool:
    if pipeline_state.get("status") in {"complete", "complete_with_errors"}:
        return True
    if pipeline_state.get("status") != "running":
        return False
    current = pipeline_state.get("current_agent")
    completed = set(pipeline_state.get("completed_agents") or [])
    required_core = {
        "market_intelligence",
        "preflight",
        "research_agent",
        "factor_design",
        "data_agent",
        "backtest_agent",
        "critic_agent",
        "evolution_agent",
        "knowledge_base",
        "schedule",
    }
    return current in {"self_audit", "readiness_report"} and required_core.issubset(completed)


def run(config: RunConfig | None = None) -> dict[str, Any]:
    cfg = config or load_config()
    run_dir = cfg.run_dir
    pipeline_state = read_json(run_dir / "pipeline_state.json", {"status": "missing", "agents": []})
    events = read_json(run_dir / "daily_events.json", {"events": [], "source_status": []})
    ideas = read_json(run_dir / "research_ideas.json", {"ideas": []})
    factors = read_json(run_dir / "candidate_factors.json", {"factors": []})
    backtests = read_json(run_dir / "backtest_results.json", {"results": []})
    data_health = read_json(run_dir / "data_health.json", {"status": "missing", "checks": {}})
    preflight = read_json(run_dir / "preflight.json", {"status": "missing", "checks": {}})
    factor_db = read_json(cfg.knowledge_root / "factor_database" / "factors.json", {"factors": []})

    file_checks = {name: _exists_nonempty(run_dir / name) for name in REQUIRED_RUN_FILES}
    agent_errors = [a for a in pipeline_state.get("agents", []) if a.get("status") != "ok"]
    source_status = events.get("source_status", [])
    source_quality = events.get("source_quality", {})
    live_sources_ok = sum(1 for s in source_status if s.get("status") == "ok")
    source_mode = source_quality.get("mode") or ("offline" if cfg.offline else ("live_partial" if live_sources_ok else "fallback"))

    checks = {
        "required_files_present": all(file_checks.values()),
        "pipeline_completed": _pipeline_reached_audit_phase(pipeline_state),
        "preflight_ok": preflight.get("status") == "ok",
        "no_agent_errors": not agent_errors,
        "events_available": len(events.get("events", [])) > 0,
        "market_source_quality_recorded": bool(source_quality),
        "ideas_available": len(ideas.get("ideas", [])) > 0,
        "research_source_quality_recorded": bool(ideas.get("source_quality")),
        "factors_available": len(factors.get("factors", [])) > 0,
        "backtests_available": len(backtests.get("results", [])) > 0,
        "data_health_ok": data_health.get("status") == "ok",
        "data_freshness_ok": data_health.get("checks", {}).get("data_freshness_ok") is True,
        "knowledge_base_updated": len(factor_db.get("factors", [])) > 0,
    }
    score = round(sum(1 for ok in checks.values() if ok) / len(checks), 4)
    status = "pass" if score >= 0.9 and checks["pipeline_completed"] and checks["preflight_ok"] else "warning"
    payload = {
        "agent": "self_audit",
        "run_date": cfg.run_date,
        "status": status,
        "score": score,
        "source_mode": source_mode,
        "checks": checks,
        "file_checks": file_checks,
        "agent_errors": agent_errors,
        "counts": {
            "events": len(events.get("events", [])),
            "ideas": len(ideas.get("ideas", [])),
            "candidate_factors": len(factors.get("factors", [])),
            "backtest_results": len(backtests.get("results", [])),
            "knowledge_factors": len(factor_db.get("factors", [])),
        },
        "data_freshness": data_health.get("freshness", {}),
        "preflight": preflight,
        "market_source_quality": source_quality,
        "research_source_quality": ideas.get("source_quality", {}),
    }
    write_json(run_dir / "self_audit.json", payload)

    lines = [
        "# Self Audit",
        "",
        f"Run date: {cfg.run_date}",
        f"Status: {status}",
        f"Score: {score:.2f}",
        f"Source mode: {source_mode}",
        "",
        "## Checks",
        "",
    ]
    for name, ok in checks.items():
        lines.append(f"- {name}: {'ok' if ok else 'fail'}")
    lines += [
        "",
        "## Preflight",
        "",
        f"- status: {preflight.get('status')}",
        f"- min_free_disk_ok: {preflight.get('checks', {}).get('min_free_disk_ok')}",
        f"- required_dirs_writable: {preflight.get('checks', {}).get('required_dirs_writable')}",
    ]
    freshness = data_health.get("freshness", {})
    if freshness:
        lines += [
            "",
            "## Data Freshness",
            "",
            f"- status: {freshness.get('status')}",
            f"- staleness_days: {freshness.get('staleness_days')}",
            f"- max_allowed_staleness_days: {freshness.get('max_allowed_staleness_days')}",
        ]
    (run_dir / "self_audit.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return payload


if __name__ == "__main__":
    run()
