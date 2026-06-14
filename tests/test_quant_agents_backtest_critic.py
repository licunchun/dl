from __future__ import annotations

from pathlib import Path

import pytest

from agent.config import RunConfig
from agent import backtest_agent, critic_agent, data_agent, evolution_agent, factor_design, knowledge_base, research_agent
from agent.io_utils import read_json, write_json


def _cfg(tmp_path: Path) -> RunConfig:
    return RunConfig(
        run_date="20260604",
        data_root=tmp_path / "missing_data",
        output_root=tmp_path / "reports",
        knowledge_root=tmp_path / "knowledge_base",
        factor_library=tmp_path / "factor_library",
        offline=True,
    )


def _prepare(tmp_path: Path) -> RunConfig:
    cfg = _cfg(tmp_path)
    write_json(cfg.run_dir / "daily_events.json", {"events": [{"title": "测试事件"}]})
    research_agent.run(cfg)
    factor_design.run(cfg)
    data_agent.run(cfg)
    return cfg


def test_backtest_agent_writes_results(tmp_path: Path) -> None:
    cfg = _prepare(tmp_path)

    payload = backtest_agent.run(cfg)

    assert payload["results"]
    assert payload["dataset_provenance"]["hash_verified"]
    assert payload["dataset_provenance"]["dataset_sha256"]
    assert (cfg.run_dir / "backtest_results").exists()
    assert {"rankic_mean", "portfolio", "decision"}.issubset(payload["results"][0])
    assert "rankic_by_date" in payload["results"][0]
    assert payload["results"][0]["rankic_by_date"]
    assert payload["results"][0]["decision"] in {"raw_candidate", "kill"}
    assert payload["results"][0]["decision"] != "promote"
    assert "decision_note" in payload["results"][0]
    assert payload["results"][0]["long_short"]["portfolio_type"] == "long_short_diagnostic_not_directly_tradable"
    assert set(payload["results"][0]["cost_sensitivity"]) == {"5", "10", "20"}


def test_backtest_rejects_dataset_manifest_hash_mismatch(tmp_path: Path) -> None:
    cfg = _prepare(tmp_path)
    dataset_path = cfg.run_dir / "daily_dataset.parquet"
    with dataset_path.open("ab") as f:
        f.write(b"tamper")

    with pytest.raises(RuntimeError, match="dataset hash mismatch"):
        backtest_agent.run(cfg)


def test_critic_evolution_and_knowledge_base_update(tmp_path: Path) -> None:
    cfg = _prepare(tmp_path)
    backtest_agent.run(cfg)

    critique = critic_agent.run(cfg)
    evolved = evolution_agent.run(cfg)
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [
            {"agent": "market_intelligence", "status": "ok"},
            {"agent": "research_agent", "status": "ok"},
            {"agent": "factor_design", "status": "ok"},
            {"agent": "data_agent", "status": "ok"},
            {"agent": "backtest_agent", "status": "ok"},
            {"agent": "critic_agent", "status": "ok"},
            {"agent": "evolution_agent", "status": "ok"},
            {"agent": "knowledge_base", "status": "ok"},
        ],
    })
    db = knowledge_base.run(cfg)

    assert (cfg.run_dir / "failure_analysis.md").exists()
    assert critique["critiques"]
    first = critique["critiques"][0]
    assert {"leakage", "stability", "collinearity"}.issubset(first["checks"])
    assert first["checks"]["stability"]["sample_days"] > 0
    assert evolved["next_generation_factors"]
    assert db["factors"]
    db_factor = db["factors"][0]
    assert "formula_key" in db_factor
    for field in [
        "horizon_days",
        "rankic_ir",
        "rankic_positive_frac",
        "long_short",
        "cost_sensitivity",
        "rows",
        "dates",
        "decision_note",
    ]:
        assert field in db_factor
    assert db_factor["long_short"]["portfolio_type"] == "long_short_diagnostic_not_directly_tradable"
    assert set(db_factor["cost_sensitivity"]) == {"5", "10", "20"}
    assert (cfg.knowledge_root / "research_log.jsonl").exists()
    assert (cfg.knowledge_root / "research_log_latest.json").exists()
    latest_log = read_json(cfg.knowledge_root / "research_log_latest.json", {})
    assert latest_log["research"]["idea_count"] > 0
    assert latest_log["factor_design"]["candidate_count"] > 0
    assert "skipped_failed_count" in latest_log["factor_design"]
    assert "failed_memory_audit" in latest_log["factor_design"]
    assert latest_log["backtest"]["result_count"] > 0
    backtest_results = read_json(cfg.run_dir / "backtest_results.json", {})["results"]
    result_ids = [item["factor_id"] for item in backtest_results]
    assert latest_log["backtest"]["result_factor_ids"] == result_ids
    assert latest_log["factor_database_write"]["saved_factor_count"] == len(result_ids)
    assert latest_log["factor_database_write"]["saved_factor_ids"] == result_ids
    assert latest_log["backtest"]["dataset_provenance"]["hash_verified"]
    assert latest_log["critic"]["critique_count"] > 0
    assert "skipped_failed_count" in latest_log["evolution"]
    assert (cfg.knowledge_root / "failure_memory.jsonl").exists()
    for child in evolved["next_generation_factors"]:
        assert child["formula_key"]
        assert child["provenance"]["source"] == "evolution_agent"
        assert child["rationale"]


def test_knowledge_base_replaces_same_day_factor_records(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    write_json(cfg.run_dir / "pipeline_state.json", {
        "status": "complete",
        "agents": [{"agent": "knowledge_base", "status": "ok"}],
    })
    base_result = {
        "factor_id": "F_STABLE",
        "name": "stable",
        "formula": "rank(ret_5)",
        "formula_key": "rank(ret_5)",
        "expression": "stable_expr",
        "horizon_days": 5,
        "rankic_ir": 1.0,
        "rankic_positive_frac": 0.6,
        "portfolio": {"ann_return_net": 0.01},
        "long_short": {"ann_return_net": 0.02},
        "cost_sensitivity": {"10": {"ann_return_net": 0.01}},
        "rows": 100,
        "dates": 10,
        "decision": "raw_candidate",
    }
    write_json(cfg.run_dir / "backtest_results.json", {"results": [{**base_result, "rankic_mean": 0.01}]})
    write_json(cfg.run_dir / "critique.json", {
        "critiques": [{"factor_id": "F_STABLE", "decision": "kill", "issues": ["old_issue"]}]
    })
    knowledge_base.run(cfg)

    write_json(cfg.run_dir / "backtest_results.json", {"results": [{**base_result, "rankic_mean": 0.25}]})
    write_json(cfg.run_dir / "critique.json", {
        "critiques": [{"factor_id": "F_STABLE", "decision": "promote", "issues": []}]
    })
    payload = knowledge_base.run(cfg)

    same_day = [
        factor
        for factor in payload["factors"]
        if factor.get("run_date") == cfg.run_date and factor.get("factor_id") == "F_STABLE"
    ]
    assert len(same_day) == 1
    assert same_day[0]["rankic_mean"] == 0.25
    assert same_day[0]["decision"] == "promote"
    latest_log = read_json(cfg.knowledge_root / "research_log_latest.json", {})
    assert latest_log["factor_database_write"]["saved_factor_ids"] == ["F_STABLE"]
    assert latest_log["factor_database_write"]["replaced_same_day_factor_count"] == 1


def test_evolution_generates_issue_specific_repair_variants(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    write_json(cfg.run_dir / "backtest_results.json", {
        "results": [{
            "factor_id": "BAD_VOL",
            "name": "bad volume",
            "formula": "rank(ret_5)",
            "formula_key": "rank(ret_5)",
            "expression": "shock_reversal_5",
            "horizon_days": 5,
            "rankic_mean": -0.02,
            "rankic_ir": -1.0,
            "rankic_positive_frac": 0.3,
            "portfolio": {
                "ann_return_net": -0.1,
                "turnover_mean": 0.8,
                "max_drawdown": -0.5,
            },
            "decision": "kill",
        }]
    })
    write_json(cfg.run_dir / "critique.json", {
        "critiques": [{
            "factor_id": "BAD_VOL",
            "decision": "kill",
            "issues": [
                "non_positive_rankic",
                "non_positive_cost_adjusted_return",
                "high_turnover",
                "large_drawdown",
            ],
            "checks": {"leakage": {"score": "pass"}},
        }]
    })

    payload = evolution_agent.run(cfg)

    child_ids = {child["factor_id"] for child in payload["next_generation_factors"]}
    assert {
        "BAD_VOL_PIVOT_REV",
        "BAD_VOL_PIVOT_COST",
        "BAD_VOL_PIVOT_DEF",
    }.issubset(child_ids)
    memory = (cfg.knowledge_root / "failure_memory.jsonl").read_text(encoding="utf-8")
    assert "BAD_VOL" in memory
    assert "BAD_VOL_PIVOT_REV" in memory


def test_evolution_skips_variants_that_match_failure_memory(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    write_json(cfg.run_dir / "backtest_results.json", {
        "results": [{
            "factor_id": "BAD_VOL",
            "name": "bad volume",
            "formula": "rank(ret_5)",
            "formula_key": "rank(ret_5)",
            "expression": "shock_reversal_5",
            "horizon_days": 5,
            "rankic_mean": -0.02,
            "rankic_ir": -1.0,
            "rankic_positive_frac": 0.3,
            "portfolio": {
                "ann_return_net": -0.1,
                "turnover_mean": 0.8,
                "max_drawdown": -0.5,
            },
            "decision": "kill",
        }]
    })
    write_json(cfg.run_dir / "critique.json", {
        "critiques": [{
            "factor_id": "BAD_VOL",
            "decision": "kill",
            "issues": ["non_positive_cost_adjusted_return", "high_turnover"],
            "checks": {"leakage": {"score": "pass"}},
        }]
    })
    memory_path = cfg.knowledge_root / "failure_memory.jsonl"
    memory_path.parent.mkdir(parents=True, exist_ok=True)
    memory_path.write_text(
        '{"factor_id":"OLD_COST_REPAIR","formula_key":"(rank(ret_5))*(1-rank(turnover_20))"}\n',
        encoding="utf-8",
    )

    payload = evolution_agent.run(cfg)

    child_ids = {child["factor_id"] for child in payload["next_generation_factors"]}
    skipped_ids = {child["factor_id"] for child in payload["skipped_evolution_factors"]}
    assert "BAD_VOL_PIVOT_COST" not in child_ids
    assert "BAD_VOL_PIVOT_COST" in skipped_ids
    assert not (cfg.run_dir / "next_generation_factors" / "BAD_VOL_PIVOT_COST.json").exists()
    assert payload["failed_memory_audit"]["source_counts"]["failure_memory"] == 1


def test_evolution_normalizes_stored_failure_formula_key(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    write_json(cfg.run_dir / "backtest_results.json", {
        "results": [{
            "factor_id": "BAD_VOL",
            "name": "bad volume",
            "formula": "rank(ret_5)",
            "formula_key": "rank(ret_5)",
            "expression": "shock_reversal_5",
            "horizon_days": 5,
            "rankic_mean": -0.02,
            "rankic_ir": -1.0,
            "rankic_positive_frac": 0.3,
            "portfolio": {
                "ann_return_net": -0.1,
                "turnover_mean": 0.8,
                "max_drawdown": -0.5,
            },
            "decision": "kill",
        }]
    })
    write_json(cfg.run_dir / "critique.json", {
        "critiques": [{
            "factor_id": "BAD_VOL",
            "decision": "kill",
            "issues": ["non_positive_cost_adjusted_return", "high_turnover"],
            "checks": {"leakage": {"score": "pass"}},
        }]
    })
    memory_path = cfg.knowledge_root / "failure_memory.jsonl"
    memory_path.parent.mkdir(parents=True, exist_ok=True)
    memory_path.write_text(
        '{"factor_id":"OLD_COST_REPAIR","formula_key":" ( RANK( ret_5 ) ) * ( 1 - RANK( turnover_20 ) ) "}\n',
        encoding="utf-8",
    )

    payload = evolution_agent.run(cfg)

    child_ids = {child["factor_id"] for child in payload["next_generation_factors"]}
    skipped_ids = {child["factor_id"] for child in payload["skipped_evolution_factors"]}
    assert "BAD_VOL_PIVOT_COST" not in child_ids
    assert "BAD_VOL_PIVOT_COST" in skipped_ids


def test_factor_design_uses_failure_memory_to_skip_repeated_formulas(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    write_json(cfg.run_dir / "research_ideas.json", {
        "ideas": [{
            "idea_id": "I1",
            "theme": "volume_shock_reversal",
            "hypothesis": "test",
            "evidence": [],
        }],
        "source_quality": {"mode": "offline"},
    })
    memory_path = cfg.knowledge_root / "failure_memory.jsonl"
    memory_path.parent.mkdir(parents=True, exist_ok=True)
    memory_path.write_text(
        '{"factor_id":"OLD","formula":"(1 - rank(ret_5)) * rank(amount_ratio_20)",'
        '"formula_key":"(1-rank(ret_5))*rank(amount_ratio_20)",'
        '"expression":"shock_reversal_5"}\n',
        encoding="utf-8",
    )

    payload = factor_design.run(cfg)

    factor_ids = {factor["factor_id"] for factor in payload["factors"]}
    assert "F_VOL_REV_5" not in factor_ids
    assert "F_VWAP_REV_5" in factor_ids
    assert read_json(cfg.run_dir / "candidate_factors.json", {})["factors"]


def test_critic_flags_future_named_factor_fields() -> None:
    result = {
        "factor_id": "BAD",
        "horizon_days": 5,
        "rankic_mean": 0.1,
        "rankic_by_date": [{"trade_date": "2026-01-01", "rankic": 0.2}] * 25,
        "portfolio": {"ann_return_net": 0.1, "turnover_mean": 0.1, "max_drawdown": -0.1},
        "decision": "promote",
    }
    factor = {
        "factor_id": "BAD",
        "formula": "rank(forward_ret_5d)",
        "expression": "future_label",
    }

    critique = critic_agent.critique_result(result, factor)

    assert critique["decision"] == "kill"
    assert "potential_lookahead_field_reference" in critique["issues"]
    assert critique["checks"]["leakage"]["score"] == "fail"


def test_critic_requires_cost_and_long_short_support_for_promotion() -> None:
    result = {
        "factor_id": "WEAK",
        "horizon_days": 5,
        "rankic_mean": 0.03,
        "dates": 120,
        "rankic_by_date": [
            {"trade_date": f"2026-01-{(i % 28) + 1:02d}", "rankic": 0.1}
            for i in range(80)
        ],
        "portfolio": {
            "ann_return_net": 0.12,
            "turnover_mean": 0.2,
            "max_drawdown": -0.1,
        },
        "long_short": {
            "ann_return_net": -0.02,
        },
        "cost_sensitivity": {
            "20": {"ann_return_net": -0.01},
        },
        "decision": "raw_candidate",
    }
    factor = {
        "factor_id": "WEAK",
        "formula": "rank(ret_5)",
        "expression": "moneyflow_confirmed_momentum",
    }

    critique = critic_agent.critique_result(result, factor)

    assert critique["decision"] == "kill"
    assert "non_positive_high_cost_return" in critique["issues"]
    assert "negative_long_short_diagnostic" in critique["issues"]
