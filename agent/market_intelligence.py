from __future__ import annotations

import re
import time
import urllib.request
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
from html import unescape
from typing import Any

from .config import RunConfig, load_config
from .io_utils import write_json
from .source_cache import write_source_snapshot


RSS_SOURCES = [
    {
        "name": "sse_disclosure",
        "url": "https://www.sse.com.cn/disclosure/listedinfo/announcement/rss.xml",
        "kind": "announcement",
    },
    {
        "name": "szse_disclosure",
        "url": "https://www.szse.cn/disclosure/listed/notice/index.html",
        "kind": "announcement",
    },
    {
        "name": "eastmoney_market_news",
        "url": "https://finance.eastmoney.com/",
        "kind": "news",
    },
    {
        "name": "csrc_policy",
        "url": "https://www.csrc.gov.cn/",
        "kind": "policy",
    },
    {
        "name": "sina_industry",
        "url": "https://finance.sina.com.cn/stock/",
        "kind": "industry",
    },
    {
        "name": "cninfo_research_context",
        "url": "https://www.cninfo.com.cn/",
        "kind": "research_context",
    },
]


def _fetch_url(url: str, timeout: int = 8) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "quant-research-agent/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def _extract_titles(raw: str, limit: int = 12) -> list[str]:
    titles = re.findall(r"<title[^>]*>(.*?)</title>", raw, flags=re.I | re.S)
    cleaned = []
    for title in titles:
        text = re.sub(r"<[^>]+>", "", title)
        text = unescape(re.sub(r"\s+", " ", text)).strip()
        if text and text.lower() not in {"rss", "上交所", "深交所"}:
            cleaned.append(text[:180])
    if not cleaned:
        snippets = re.findall(r">([^<>]{12,120})<", raw)
        cleaned = [unescape(re.sub(r"\s+", " ", s)).strip() for s in snippets if s.strip()]
    return cleaned[:limit]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _source_quality(source_status: list[dict[str, Any]], events: list[dict[str, Any]], offline: bool) -> dict[str, Any]:
    total = len(source_status)
    ok = sum(1 for s in source_status if s.get("status") == "ok")
    errors = sum(1 for s in source_status if s.get("status") == "error")
    skipped = sum(1 for s in source_status if s.get("status") == "skipped_offline")
    covered_kinds = sorted({e.get("kind") for e in events if e.get("source") != "offline_fallback" and e.get("kind")})
    required_kinds = sorted({s["kind"] for s in RSS_SOURCES})
    missing_kinds = sorted(set(required_kinds) - set(covered_kinds))
    fallback_used = any(e.get("source") == "offline_fallback" for e in events)
    return {
        "mode": "offline" if offline else ("live" if ok else "fallback"),
        "total_sources": total,
        "ok_sources": ok,
        "error_sources": errors,
        "skipped_sources": skipped,
        "coverage_ratio": round(ok / total, 4) if total else 0.0,
        "covered_kinds": covered_kinds,
        "missing_kinds": missing_kinds,
        "fallback_used": fallback_used,
        "live_events": sum(1 for e in events if e.get("source") != "offline_fallback"),
    }


def run(config: RunConfig | None = None) -> dict[str, Any]:
    cfg = config or load_config()
    events: list[dict[str, Any]] = []
    source_status: list[dict[str, Any]] = []

    for source in RSS_SOURCES:
        if cfg.offline:
            source_status.append({
                "name": source["name"],
                "kind": source["kind"],
                "url": source["url"],
                "status": "skipped_offline",
            })
            continue
        try:
            started = time.time()
            raw = _fetch_url(source["url"])
            raw_bytes = raw.encode("utf-8", errors="ignore")
            titles = _extract_titles(raw)
            for title in titles:
                events.append({
                    "date": cfg.run_date,
                    "source": source["name"],
                    "kind": source["kind"],
                    "title": title,
                    "url": source["url"],
                })
            source_status.append({
                "name": source["name"],
                "kind": source["kind"],
                "url": source["url"],
                "status": "ok",
                "items": len(titles),
                "response_bytes": len(raw_bytes),
                "content_sha256": hashlib.sha256(raw_bytes).hexdigest(),
                "fetched_at": _utc_now(),
                "latency_sec": round(time.time() - started, 3),
            })
            time.sleep(0.2)
        except Exception as exc:
            source_status.append({
                "name": source["name"],
                "kind": source["kind"],
                "url": source["url"],
                "status": "error",
                "error_type": type(exc).__name__,
                "error": str(exc)[:300],
                "fetched_at": _utc_now(),
            })

    if not events:
        events.append({
            "date": cfg.run_date,
            "source": "offline_fallback",
            "kind": "market_context",
            "title": "No live market events collected; continue with local data and historical factor memory.",
            "url": None,
        })

    source_quality = _source_quality(source_status, events, cfg.offline)
    snapshot = write_source_snapshot(cfg, "market_intelligence", source_status, source_quality, events)
    payload = {
        "agent": "market_intelligence",
        "run_date": cfg.run_date,
        "config": asdict(cfg) | {
            "data_root": str(cfg.data_root),
            "output_root": str(cfg.output_root),
            "knowledge_root": str(cfg.knowledge_root),
            "factor_library": str(cfg.factor_library),
        },
        "source_status": source_status,
        "source_quality": source_quality,
        "source_snapshot": {
            "item_count": snapshot["item_count"],
            "run_path": str(cfg.run_dir / "source_snapshots" / "market_intelligence.json"),
            "knowledge_path": str(cfg.knowledge_root / "source_snapshots.jsonl"),
        },
        "events": events,
    }
    write_json(cfg.run_dir / "daily_events.json", payload)
    return payload


if __name__ == "__main__":
    run()
