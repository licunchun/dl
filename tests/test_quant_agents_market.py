from __future__ import annotations

from pathlib import Path

from agent.config import RunConfig
from agent import market_intelligence
from agent.io_utils import read_json


def _cfg(tmp_path: Path, offline: bool = True) -> RunConfig:
    return RunConfig(
        run_date="20260604",
        data_root=tmp_path / "data",
        output_root=tmp_path / "reports",
        knowledge_root=tmp_path / "knowledge_base",
        factor_library=tmp_path / "factor_library",
        offline=offline,
    )


def test_market_intelligence_outputs_fallback_events(tmp_path: Path) -> None:
    payload = market_intelligence.run(_cfg(tmp_path, offline=True))
    out = tmp_path / "reports" / "daily_logs" / "20260604" / "daily_events.json"

    assert out.exists()
    assert payload["events"]
    assert payload["events"][0]["source"] == "offline_fallback"
    assert payload["source_quality"]["mode"] == "offline"
    assert payload["source_quality"]["fallback_used"]
    assert payload["source_quality"]["skipped_sources"] == payload["source_quality"]["total_sources"]
    assert all("kind" in item for item in payload["source_status"])
    assert all("url" in item for item in payload["source_status"])
    snapshot = read_json(tmp_path / "reports" / "daily_logs" / "20260604" / "source_snapshots" / "market_intelligence.json", {})
    assert snapshot["agent"] == "market_intelligence"
    assert snapshot["snapshot_written_at"]
    assert snapshot["source_quality"]["mode"] == "offline"
    assert (tmp_path / "knowledge_base" / "source_snapshots.jsonl").exists()


def test_market_intelligence_parses_titles_when_fetch_succeeds(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(market_intelligence, "_fetch_url", lambda url: "<rss><title>公告一</title><title>公告二</title></rss>")
    payload = market_intelligence.run(_cfg(tmp_path, offline=False))

    assert any(event["title"] == "公告一" for event in payload["events"])
    assert payload["source_status"][0]["status"] == "ok"
    assert payload["source_status"][0]["url"]
    assert payload["source_status"][0]["response_bytes"] > 0
    assert len(payload["source_status"][0]["content_sha256"]) == 64
    assert payload["source_status"][0]["fetched_at"]
    assert payload["source_quality"]["ok_sources"] == payload["source_quality"]["total_sources"]
    assert not payload["source_quality"]["fallback_used"]
    assert payload["source_snapshot"]["item_count"] == len(payload["events"])


def test_market_intelligence_records_partial_live_source_quality(tmp_path: Path, monkeypatch) -> None:
    def fake_fetch(url: str) -> str:
        if "csrc" in url:
            raise RuntimeError("blocked")
        return "<rss><title>市场新闻</title></rss>"

    monkeypatch.setattr(market_intelligence, "_fetch_url", fake_fetch)

    payload = market_intelligence.run(_cfg(tmp_path, offline=False))

    assert payload["source_quality"]["ok_sources"] > 0
    assert payload["source_quality"]["error_sources"] == 1
    assert payload["source_quality"]["coverage_ratio"] < 1
    assert "policy" in payload["source_quality"]["missing_kinds"]
    failed = next(item for item in payload["source_status"] if item["status"] == "error")
    assert failed["url"]
    assert failed["error_type"] == "RuntimeError"
    assert failed["fetched_at"]
