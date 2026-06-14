from __future__ import annotations

from pathlib import Path

import pandas as pd

from agent.config import RunConfig
from agent.io_utils import read_json, write_json
from agent import data_agent, factor_design, research_agent


def _cfg(tmp_path: Path) -> RunConfig:
    return RunConfig(
        run_date="20260604",
        data_root=tmp_path / "missing_data",
        output_root=tmp_path / "reports",
        knowledge_root=tmp_path / "knowledge_base",
        factor_library=tmp_path / "factor_library",
        offline=True,
    )


def test_research_agent_outputs_ideas(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    write_json(cfg.run_dir / "daily_events.json", {"events": [{"title": "测试事件"}]})

    payload = research_agent.run(cfg)

    assert (cfg.run_dir / "research_ideas.json").exists()
    assert len(payload["ideas"]) >= 3
    assert payload["source_quality"]["mode"] == "offline"
    assert payload["source_quality"]["fallback_used"]
    assert payload["source_quality"]["skipped_sources"] == payload["source_quality"]["total_sources"]
    assert all("url" in item for item in payload["source_status"])
    snapshot = read_json(cfg.run_dir / "source_snapshots" / "research_agent.json", {})
    assert snapshot["agent"] == "research_agent"
    assert snapshot["snapshot_written_at"]
    assert snapshot["source_quality"]["mode"] == "offline"
    assert (cfg.knowledge_root / "source_snapshots.jsonl").exists()


def test_research_agent_records_live_source_quality(tmp_path: Path, monkeypatch) -> None:
    cfg = RunConfig(
        run_date="20260604",
        data_root=tmp_path / "missing_data",
        output_root=tmp_path / "reports",
        knowledge_root=tmp_path / "knowledge_base",
        factor_library=tmp_path / "factor_library",
        offline=False,
    )
    write_json(cfg.run_dir / "daily_events.json", {"events": [{"title": "市场事件"}]})
    monkeypatch.setattr(research_agent, "_fetch_url", lambda url: "<html><title>Alpha paper context</title></html>")

    payload = research_agent.run(cfg)

    assert payload["source_quality"]["ok_sources"] == payload["source_quality"]["total_sources"]
    assert payload["source_status"][0]["url"]
    assert payload["source_status"][0]["response_bytes"] > 0
    assert len(payload["source_status"][0]["content_sha256"]) == 64
    assert payload["source_status"][0]["fetched_at"]
    assert payload["source_quality"]["context_items"] > 0
    assert not payload["source_quality"]["fallback_used"]
    assert any("Alpha paper context" in idea["evidence"] for idea in payload["ideas"])
    assert payload["source_snapshot"]["item_count"] == payload["source_quality"]["context_items"]


def test_research_agent_records_partial_source_failure(tmp_path: Path, monkeypatch) -> None:
    cfg = RunConfig(
        run_date="20260604",
        data_root=tmp_path / "missing_data",
        output_root=tmp_path / "reports",
        knowledge_root=tmp_path / "knowledge_base",
        factor_library=tmp_path / "factor_library",
        offline=False,
    )
    write_json(cfg.run_dir / "daily_events.json", {"events": []})

    def fake_fetch(url: str) -> str:
        if "quantconnect" in url:
            raise RuntimeError("blocked")
        return "<html><title>Research context</title></html>"

    monkeypatch.setattr(research_agent, "_fetch_url", fake_fetch)

    payload = research_agent.run(cfg)

    assert payload["source_quality"]["ok_sources"] > 0
    assert payload["source_quality"]["error_sources"] == 1
    assert payload["source_quality"]["coverage_ratio"] < 1
    assert "community" in payload["source_quality"]["missing_kinds"]
    failed = next(item for item in payload["source_status"] if item["status"] == "error")
    assert failed["url"]
    assert failed["error_type"] == "RuntimeError"
    assert failed["fetched_at"]


def test_factor_design_skips_failed_factor_ids(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    write_json(cfg.run_dir / "research_ideas.json", {"ideas": [{"idea_id": "R001", "theme": "volume_shock_reversal"}]})
    write_json(cfg.knowledge_root / "factor_database" / "factors.json", {"factors": [{"factor_id": "F_VOL_REV_5", "decision": "kill"}]})

    payload = factor_design.run(cfg)

    ids = {f["factor_id"] for f in payload["factors"]}
    assert "F_VOL_REV_5" not in ids
    assert "F_VWAP_REV_5" in ids
    assert payload["skipped_factors"][0]["factor_id"] == "F_VOL_REV_5"
    assert payload["skipped_factors"][0]["reason"] == "matched_failed_factor_memory"
    kept = next(f for f in payload["factors"] if f["factor_id"] == "F_VWAP_REV_5")
    assert kept["formula_key"]
    assert kept["provenance"]["source_idea_id"] == "R001"
    assert (cfg.run_dir / "candidate_factors" / "F_VWAP_REV_5.json").exists()


def test_factor_design_skips_failed_formula_even_with_new_id(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    write_json(cfg.run_dir / "research_ideas.json", {"ideas": [{"idea_id": "R001", "theme": "volume_shock_reversal"}]})
    write_json(cfg.knowledge_root / "factor_database" / "factors.json", {
        "factors": [{
            "factor_id": "OLD_ID",
            "formula": "(1 - rank(ret_5)) * rank(amount_ratio_20)",
            "decision": "kill",
        }]
    })

    payload = factor_design.run(cfg)

    ids = {f["factor_id"] for f in payload["factors"]}
    assert "F_VOL_REV_5" not in ids
    assert payload["failed_memory_audit"]["source_counts"]["factor_database"] == 1


def test_factor_design_skips_failed_formula_key_with_format_variation(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    write_json(cfg.run_dir / "research_ideas.json", {"ideas": [{"idea_id": "R001", "theme": "volume_shock_reversal"}]})
    write_json(cfg.knowledge_root / "factor_database" / "factors.json", {
        "factors": [{
            "factor_id": "OLD_ID",
            "formula": " ( 1 - RANK( ret_5 ) ) * RANK( amount_ratio_20 ) ",
            "decision": "kill",
        }]
    })

    payload = factor_design.run(cfg)

    ids = {f["factor_id"] for f in payload["factors"]}
    assert "F_VOL_REV_5" not in ids


def test_factor_design_normalizes_stored_failure_formula_key(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    write_json(cfg.run_dir / "research_ideas.json", {"ideas": [{"idea_id": "R001", "theme": "volume_shock_reversal"}]})
    write_json(cfg.knowledge_root / "factor_database" / "factors.json", {
        "factors": [{
            "factor_id": "OLD_ID",
            "formula_key": " ( 1 - RANK( ret_5 ) ) * RANK( amount_ratio_20 ) ",
            "decision": "kill",
        }]
    })

    payload = factor_design.run(cfg)

    ids = {f["factor_id"] for f in payload["factors"]}
    assert "F_VOL_REV_5" not in ids


def test_factor_design_skips_failed_formula_across_run_dates(tmp_path: Path) -> None:
    cfg1 = _cfg(tmp_path)
    write_json(cfg1.knowledge_root / "factor_database" / "factors.json", {
        "factors": [{
            "run_date": "20260604",
            "factor_id": "F_VOL_REV_5",
            "formula": "(1 - rank(ret_5)) * rank(amount_ratio_20)",
            "expression": "shock_reversal_5",
            "decision": "kill",
        }]
    })
    cfg2 = RunConfig(
        run_date="20260605",
        data_root=cfg1.data_root,
        output_root=cfg1.output_root,
        knowledge_root=cfg1.knowledge_root,
        factor_library=cfg1.factor_library,
        offline=True,
    )
    write_json(cfg2.run_dir / "research_ideas.json", {"ideas": [{"idea_id": "R001", "theme": "volume_shock_reversal"}]})

    payload = factor_design.run(cfg2)

    ids = {f["factor_id"] for f in payload["factors"]}
    assert "F_VOL_REV_5" not in ids
    assert "F_VWAP_REV_5" in ids


def test_factor_design_quarantines_corrupt_failure_memory_and_reports_audit(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    write_json(cfg.run_dir / "research_ideas.json", {"ideas": [{"idea_id": "R001", "theme": "volume_shock_reversal"}]})
    memory_path = cfg.knowledge_root / "failure_memory.jsonl"
    memory_path.parent.mkdir(parents=True, exist_ok=True)
    memory_path.write_text(
        '{"factor_id":"OLD","formula_key":"(1-rank(ret_5))*rank(amount_ratio_20)"}\n'
        '{broken json\n',
        encoding="utf-8",
    )

    payload = factor_design.run(cfg)

    ids = {f["factor_id"] for f in payload["factors"]}
    assert "F_VOL_REV_5" not in ids
    assert payload["failed_memory_audit"]["source_counts"]["failure_memory"] == 1
    assert payload["failed_memory_audit"]["failure_memory_parse_errors"] == 1
    quarantine = cfg.knowledge_root / "jsonl_quarantine" / "failure_memory.jsonl.corrupt.jsonl"
    assert quarantine.exists()


def test_data_agent_writes_standard_dataset_with_fallback(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)

    payload = data_agent.run(cfg)
    df = pd.read_parquet(payload["dataset_path"])
    health = data_agent._health_report(df, payload["source_mode"], cfg)
    written_health = read_json(cfg.run_dir / "data_health.json", {})

    assert payload["rows"] > 0
    assert (cfg.run_dir / "data_health.json").exists()
    assert payload["health_status"] == "ok"
    manifest = read_json(cfg.run_dir / "dataset_manifest.json", {})
    assert manifest["dataset_sha256"]
    assert manifest["dataset_size_bytes"] > 0
    assert manifest["data_source_detail"]["daily"]["exists"] is False
    assert manifest["data_source_detail"]["daily"]["selected_csv_file_count"] == 0
    assert manifest["data_source_detail"]["fallback_reason"] == "daily_csv_missing_or_empty"
    assert health["freshness"]["status"] == "not_applicable_synthetic"
    assert written_health["data_source_detail"]["fallback_reason"] == "daily_csv_missing_or_empty"
    assert health["checks"]["data_freshness_ok"]
    assert {"ret_5", "amount_ratio_20", "forward_ret_5d", "mf_buy_pressure"}.issubset(df.columns)


def test_data_health_warns_on_stale_local_data(tmp_path: Path) -> None:
    cfg = RunConfig(
        run_date="20260604",
        data_root=tmp_path / "missing_data",
        output_root=tmp_path / "reports",
        knowledge_root=tmp_path / "knowledge_base",
        factor_library=tmp_path / "factor_library",
        offline=True,
        max_data_staleness_days=7,
    )
    df = data_agent._add_features(data_agent._synthetic_dataset())

    health = data_agent._health_report(df, "local_csv", cfg)

    assert health["status"] == "warning"
    assert health["freshness"]["status"] == "stale_or_future_dated"
    assert not health["checks"]["data_freshness_ok"]


def test_data_agent_merges_basic_industry_and_reports_domains(tmp_path: Path) -> None:
    cfg = RunConfig(
        run_date="20260604",
        data_root=tmp_path / "data",
        output_root=tmp_path / "reports",
        knowledge_root=tmp_path / "knowledge_base",
        factor_library=tmp_path / "factor_library",
        offline=False,
        max_data_staleness_days=7,
    )
    root = cfg.data_root / "A股数据"
    for name in ["daily", "metric", "moneyflow", "stock_st"]:
        (root / name).mkdir(parents=True, exist_ok=True)
    dates = pd.bdate_range("2026-05-01", "2026-06-04")
    daily_rows = []
    metric_rows = []
    money_rows = []
    for code, base, industry in [("000001.SZ", 10.0, "银行"), ("000002.SZ", 20.0, "地产")]:
        for i, dt in enumerate(dates):
            day = int(dt.strftime("%Y%m%d"))
            close = base + i * 0.1
            daily_rows.append({
                "ts_code": code,
                "trade_date": day,
                "open": close,
                "high": close * 1.01,
                "low": close * 0.99,
                "close": close,
                "pre_close": close - 0.1,
                "pct_chg": 0.1,
                "vol": 100000 + i,
                "amount": 50000 + i,
                "vwap": close,
            })
            metric_rows.append({
                "ts_code": code,
                "trade_date": day,
                "turnover_rate": 1.0,
                "pb": 1.2,
                "total_mv": 1000000,
            })
            money_rows.append({
                "ts_code": code,
                "trade_date": day,
                "buy_lg_amount": 1000,
                "sell_lg_amount": 900,
                "buy_elg_amount": 500,
                "sell_elg_amount": 450,
            })
    pd.DataFrame(daily_rows).to_csv(root / "daily" / "20260604.csv", index=False)
    pd.DataFrame(metric_rows).to_csv(root / "metric" / "20260604.csv", index=False)
    pd.DataFrame(money_rows).to_csv(root / "moneyflow" / "20260604.csv", index=False)
    pd.DataFrame({
        "ts_code": ["000001.SZ", "000002.SZ"],
        "industry": ["银行", "地产"],
        "area": ["深圳", "深圳"],
        "market": ["主板", "主板"],
        "list_date": [19910403, 19910129],
    }).to_csv(root / "basic.csv", index=False)

    payload = data_agent.run(cfg)
    df = pd.read_parquet(payload["dataset_path"])
    health = read_json(cfg.run_dir / "data_health.json", {})
    manifest = read_json(cfg.run_dir / "dataset_manifest.json", {})

    assert payload["source_mode"] == "local_csv"
    assert {"银行", "地产"} == set(df["industry"].dropna().unique())
    assert health["checks"]["required_data_domains_usable"]
    assert health["domain_coverage"]["industry"]["usable"]
    assert health["domain_coverage"]["financial_metric"]["usable"]
    assert health["freshness"]["status"] == "ok"
    assert manifest["data_source_detail"]["daily"]["selected_csv_file_count"] == 1
    assert manifest["data_source_detail"]["metric"]["selected_csv_file_count"] == 1
    assert manifest["data_source_detail"]["moneyflow"]["selected_csv_file_count"] == 1
    assert manifest["data_source_detail"]["basic"]["exists"] is True
    latest = read_json(cfg.knowledge_root / "data_health_latest.json", {})
    assert latest["data_source_detail"]["daily"]["selected_csv_file_count"] == 1


def test_data_health_warns_when_financial_domain_missing(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    df = data_agent._add_features(data_agent._synthetic_dataset().drop(columns=["pb"]))

    health = data_agent._health_report(df, "local_csv", cfg)

    assert health["status"] == "warning"
    assert not health["checks"]["required_data_domains_usable"]
    assert not health["domain_coverage"]["financial_metric"]["usable"]
    assert health["domain_coverage"]["financial_metric"]["null_rates"]["pb"] == 1.0
