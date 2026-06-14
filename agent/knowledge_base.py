from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .config import RunConfig, load_config
from .io_utils import append_jsonl, read_json, write_json


def _run_quality(cfg: RunConfig) -> dict[str, Any]:
    pipeline_state = read_json(cfg.run_dir / "pipeline_state.json", {})
    agents = pipeline_state.get("agents") or []
    agent_errors = [
        {
            "agent": item.get("agent"),
            "status": item.get("status"),
            "error": item.get("error"),
        }
        for item in agents
        if item.get("status") != "ok"
    ]
    status = pipeline_state.get("status") or "unknown"
    current_agent = pipeline_state.get("current_agent")
    standalone = not pipeline_state
    upstream_complete = status == "running" and current_agent == "knowledge_base" and not agent_errors
    complete = standalone or (status == "complete" and not agent_errors) or upstream_complete
    return {
        "pipeline_status": status,
        "current_agent": current_agent,
        "run_quality": "standalone" if standalone else ("complete" if complete else "incomplete"),
        "has_agent_errors": bool(agent_errors),
        "agent_errors": agent_errors,
    }


def _summarize_research_run(cfg: RunConfig, results: dict[str, Any], critiques: dict[str, Any], quality: dict[str, Any]) -> dict[str, Any]:
    events = read_json(cfg.run_dir / "daily_events.json", {"events": [], "source_quality": {}})
    ideas = read_json(cfg.run_dir / "research_ideas.json", {"ideas": [], "source_quality": {}, "research_context": []})
    factors = read_json(cfg.run_dir / "candidate_factors.json", {"factors": []})
    next_generation = read_json(cfg.run_dir / "next_generation_factors.json", {"next_generation_factors": []})
    data_health = read_json(cfg.run_dir / "data_health.json", {})
    critique_rows = critiques.get("critiques", [])
    result_rows = results.get("results", [])
    return {
        "run_date": cfg.run_date,
        "pipeline": quality,
        "events": {
            "count": len(events.get("events", [])),
            "source_quality": events.get("source_quality", {}),
            "top_titles": [item.get("title") for item in events.get("events", [])[:5]],
        },
        "research": {
            "idea_count": len(ideas.get("ideas", [])),
            "idea_ids": [item.get("idea_id") for item in ideas.get("ideas", [])],
            "themes": sorted({item.get("theme") for item in ideas.get("ideas", []) if item.get("theme")}),
            "source_quality": ideas.get("source_quality", {}),
            "context_items": len(ideas.get("research_context", [])),
        },
        "factor_design": {
            "candidate_count": len(factors.get("factors", [])),
            "skipped_failed_count": len(factors.get("skipped_factors", [])),
            "factor_ids": [item.get("factor_id") for item in factors.get("factors", [])],
            "formula_keys": [item.get("formula_key") for item in factors.get("factors", []) if item.get("formula_key")],
            "failed_memory_audit": factors.get("failed_memory_audit", {}),
        },
        "backtest": {
            "result_count": len(result_rows),
            "result_factor_ids": [item.get("factor_id") for item in result_rows if item.get("factor_id")],
            "dataset_provenance": results.get("dataset_provenance", {}),
            "promoted_raw": sum(1 for item in result_rows if item.get("decision") == "promote"),
            "killed_raw": sum(1 for item in result_rows if item.get("decision") == "kill"),
            "top_rankic": [
                {
                    "factor_id": item.get("factor_id"),
                    "rankic_mean": item.get("rankic_mean"),
                    "ann_return_net": (item.get("portfolio") or {}).get("ann_return_net"),
                }
                for item in sorted(result_rows, key=lambda x: x.get("rankic_mean") or -9, reverse=True)[:5]
            ],
        },
        "critic": {
            "critique_count": len(critique_rows),
            "promoted": sum(1 for item in critique_rows if item.get("decision") == "promote"),
            "killed": sum(1 for item in critique_rows if item.get("decision") == "kill"),
            "issue_counts": {
                issue: sum(1 for row in critique_rows for item in row.get("issues", []) if item == issue)
                for issue in sorted({item for row in critique_rows for item in row.get("issues", [])})
            },
        },
        "evolution": {
            "next_generation_count": len(next_generation.get("next_generation_factors", [])),
            "skipped_failed_count": len(next_generation.get("skipped_evolution_factors", [])),
            "next_factor_ids": [item.get("factor_id") for item in next_generation.get("next_generation_factors", [])],
            "skipped_factor_ids": [
                item.get("factor_id") for item in next_generation.get("skipped_evolution_factors", [])
            ],
        },
        "data": {
            "status": data_health.get("status"),
            "source_mode": data_health.get("source_mode"),
            "rows": data_health.get("rows"),
            "stocks": data_health.get("stocks"),
            "dates": data_health.get("dates"),
            "freshness": data_health.get("freshness", {}),
        },
    }


def run(config: RunConfig | None = None) -> dict[str, Any]:
    cfg = config or load_config()
    results = read_json(cfg.run_dir / "backtest_results.json", {"results": []})
    critiques = read_json(cfg.run_dir / "critique.json", {"critiques": []})
    quality = _run_quality(cfg)
    critique_by_id = {c["factor_id"]: c for c in critiques.get("critiques", [])}
    db_path = cfg.knowledge_root / "factor_database" / "factors.json"
    db = read_json(db_path, {"factors": []})
    saved_factor_ids: list[str] = []
    replaced_factor_count = 0
    if quality["run_quality"] in {"complete", "standalone"}:
        previous_factors = db.get("factors", [])
        db["factors"] = [
            factor
            for factor in previous_factors
            if str(factor.get("run_date")) != str(cfg.run_date)
        ]
        replaced_factor_count = len(previous_factors) - len(db["factors"])
        for result in results.get("results", []):
            critique = critique_by_id.get(result["factor_id"], {})
            db["factors"].append({
                "run_date": cfg.run_date,
                "factor_id": result["factor_id"],
                "name": result["name"],
                "formula": result["formula"],
                "formula_key": result.get("formula_key"),
                "expression": result.get("expression"),
                "horizon_days": result.get("horizon_days"),
                "rankic_mean": result.get("rankic_mean"),
                "rankic_ir": result.get("rankic_ir"),
                "rankic_positive_frac": result.get("rankic_positive_frac"),
                "portfolio": result.get("portfolio"),
                "long_short": result.get("long_short"),
                "cost_sensitivity": result.get("cost_sensitivity"),
                "rows": result.get("rows"),
                "dates": result.get("dates"),
                "decision_note": result.get("decision_note"),
                "decision": critique.get("decision", result.get("decision")),
                "issues": critique.get("issues", []),
                "run_quality": quality["run_quality"],
            })
            saved_factor_ids.append(str(result["factor_id"]))
    write_json(db_path, db)
    research_log_record = _summarize_research_run(cfg, results, critiques, quality)
    research_log_record["recorded_at"] = datetime.now(timezone.utc).isoformat()
    if quality["run_quality"] != "complete":
        research_log_record["factor_database_write"] = {
            "status": "skipped",
            "reason": "pipeline_not_complete",
        }
    else:
        research_log_record["factor_database_write"] = {
            "status": "updated",
            "reason": "pipeline_complete",
            "saved_factor_count": len(saved_factor_ids),
            "saved_factor_ids": saved_factor_ids,
            "replaced_same_day_factor_count": replaced_factor_count,
        }
    append_jsonl(cfg.knowledge_root / "research_log.jsonl", research_log_record)
    write_json(cfg.knowledge_root / "research_log_latest.json", research_log_record)
    db["research_log_record"] = research_log_record
    return db


if __name__ == "__main__":
    run()
