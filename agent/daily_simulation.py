from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any

from . import daily_pipeline
from .config import RunConfig, load_config
from .io_utils import read_json, write_json


def _date_range(start_yyyymmdd: str, days: int) -> list[str]:
    start = datetime.strptime(start_yyyymmdd, "%Y%m%d").date()
    return [(start + timedelta(days=i)).strftime("%Y%m%d") for i in range(days)]


def run_simulation(base_config: RunConfig | None = None, days: int | None = None) -> dict[str, Any]:
    cfg = base_config or load_config()
    sim_days = days if days is not None else int(os.environ.get("QUANT_SIM_DAYS", "7"))
    run_dates = _date_range(cfg.run_date, sim_days)
    summaries: list[dict[str, Any]] = []
    for run_date in run_dates:
        day_cfg = RunConfig(
            run_date=run_date,
            data_root=cfg.data_root,
            output_root=cfg.output_root,
            knowledge_root=cfg.knowledge_root,
            factor_library=cfg.factor_library,
            offline=cfg.offline,
            agent_retries=cfg.agent_retries,
            retention_days=cfg.retention_days,
            max_data_staleness_days=cfg.max_data_staleness_days,
            lock_stale_minutes=cfg.lock_stale_minutes,
            min_free_disk_mb=cfg.min_free_disk_mb,
        )
        outputs = daily_pipeline.run(day_cfg)
        state = read_json(day_cfg.run_dir / "pipeline_state.json", {})
        audit = read_json(day_cfg.run_dir / "self_audit.json", {})
        summaries.append({
            "run_date": run_date,
            "pipeline_status": state.get("status"),
            "self_audit_status": audit.get("status"),
            "self_audit_score": audit.get("score"),
            "candidate_factors": len(outputs.get("factor_design", {}).get("factors", [])),
            "backtest_results": len(outputs.get("backtest_agent", {}).get("results", [])),
            "knowledge_factors": len(outputs.get("knowledge_base", {}).get("factors", [])),
        })
    history_path = cfg.knowledge_root / "run_history.jsonl"
    history_lines = history_path.read_text(encoding="utf-8").strip().splitlines() if history_path.exists() else []
    simulation_passed = len(history_lines) >= sim_days and all(r["pipeline_status"] == "complete" for r in summaries)
    payload = {
        "agent": "daily_simulation",
        "start_date": cfg.run_date,
        "days": sim_days,
        "uses_shell_entrypoint": False,
        "production_ready_evidence": False,
        "evidence_scope": "local_simulation_only",
        "note": "Runs daily_pipeline directly for local smoke testing; does not count as shell-level run_daily production evidence.",
        "run_dates": run_dates,
        "runs": summaries,
        "history_lines": len(history_lines),
        "latest_run_date": read_json(cfg.knowledge_root / "run_history_latest.json", {}).get("run_date"),
        "status": "simulation_pass" if simulation_passed else "simulation_warning",
    }
    write_json(cfg.output_root / "multi_day_simulation.json", payload)
    return payload


if __name__ == "__main__":
    run_simulation()
