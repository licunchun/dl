from __future__ import annotations

import re
import time
import urllib.request
from datetime import datetime, timezone
import hashlib
from html import unescape
from typing import Any

from .config import RunConfig, load_config
from .io_utils import read_json, write_json
from .source_cache import write_source_snapshot


DEFAULT_IDEAS = [
    {
        "idea_id": "R001",
        "theme": "volume_shock_reversal",
        "hypothesis": "A股短期过度放量下跌后存在流动性恢复反弹，但需要控制ST、涨跌停和换手成本。",
        "preferred_horizon_days": [1, 5],
        "required_fields": ["ret_1", "ret_5", "amount_ratio_20", "turnover_rate"],
    },
    {
        "idea_id": "R002",
        "theme": "moneyflow_exhaustion",
        "hypothesis": "大单/超大单买入压力与价格延伸叠加后可能出现短期耗尽或确认效应。",
        "preferred_horizon_days": [5, 10],
        "required_fields": ["mf_buy_pressure", "ret_5", "amount"],
    },
    {
        "idea_id": "R003",
        "theme": "defensive_liquidity_value",
        "hypothesis": "低波动、高流动性、低PB组合可能在A股中低频长仓中提供更稳定风险调整收益。",
        "preferred_horizon_days": [5, 20],
        "required_fields": ["std_20", "amihud_20", "pb"],
    },
]


RESEARCH_SOURCES = [
    {
        "name": "arxiv_quant_finance",
        "url": "https://arxiv.org/list/q-fin/recent",
        "kind": "paper",
    },
    {
        "name": "worldquant_101_formulaic_alphas",
        "url": "https://arxiv.org/abs/1601.00991",
        "kind": "factor_library",
    },
    {
        "name": "quantconnect_research",
        "url": "https://www.quantconnect.com/research",
        "kind": "community",
    },
]


def _fetch_url(url: str, timeout: int = 8) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "quant-research-agent/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def _extract_context(raw: str, limit: int = 5) -> list[str]:
    titles = re.findall(r"<title[^>]*>(.*?)</title>", raw, flags=re.I | re.S)
    snippets = titles or re.findall(r">([^<>]{24,180})<", raw)
    cleaned = []
    for item in snippets:
        text = re.sub(r"<[^>]+>", "", item)
        text = unescape(re.sub(r"\s+", " ", text)).strip()
        if text:
            cleaned.append(text[:220])
    return cleaned[:limit]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _collect_research_context(cfg: RunConfig) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    contexts: list[dict[str, Any]] = []
    statuses: list[dict[str, Any]] = []
    for source in RESEARCH_SOURCES:
        if cfg.offline:
            statuses.append({
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
            items = _extract_context(raw)
            statuses.append({
                "name": source["name"],
                "kind": source["kind"],
                "url": source["url"],
                "status": "ok",
                "items": len(items),
                "response_bytes": len(raw_bytes),
                "content_sha256": hashlib.sha256(raw_bytes).hexdigest(),
                "fetched_at": _utc_now(),
                "latency_sec": round(time.time() - started, 3),
            })
            for item in items:
                contexts.append({
                    "source": source["name"],
                    "kind": source["kind"],
                    "text": item,
                    "url": source["url"],
                })
        except Exception as exc:
            statuses.append({
                "name": source["name"],
                "kind": source["kind"],
                "url": source["url"],
                "status": "error",
                "error_type": type(exc).__name__,
                "error": str(exc)[:300],
                "fetched_at": _utc_now(),
            })
    return contexts, statuses


def _source_quality(statuses: list[dict[str, Any]], contexts: list[dict[str, Any]], offline: bool) -> dict[str, Any]:
    total = len(statuses)
    ok = sum(1 for s in statuses if s.get("status") == "ok")
    skipped = sum(1 for s in statuses if s.get("status") == "skipped_offline")
    errors = sum(1 for s in statuses if s.get("status") == "error")
    covered_kinds = sorted({c.get("kind") for c in contexts if c.get("kind")})
    required_kinds = sorted({s["kind"] for s in RESEARCH_SOURCES})
    return {
        "mode": "offline" if offline else ("live" if ok else "fallback"),
        "total_sources": total,
        "ok_sources": ok,
        "error_sources": errors,
        "skipped_sources": skipped,
        "coverage_ratio": round(ok / total, 4) if total else 0.0,
        "covered_kinds": covered_kinds,
        "missing_kinds": sorted(set(required_kinds) - set(covered_kinds)),
        "fallback_used": not contexts,
        "context_items": len(contexts),
    }


def run(config: RunConfig | None = None) -> dict[str, Any]:
    cfg = config or load_config()
    events = read_json(cfg.run_dir / "daily_events.json", {"events": []})
    event_titles = [e.get("title", "") for e in events.get("events", [])]
    research_context, source_status = _collect_research_context(cfg)
    context_texts = [item["text"] for item in research_context]
    ideas = []
    for idea in DEFAULT_IDEAS:
        item = dict(idea)
        item["evidence"] = (event_titles + context_texts)[:5]
        item["status"] = "candidate"
        ideas.append(item)
    source_quality = _source_quality(source_status, research_context, cfg.offline)
    snapshot = write_source_snapshot(cfg, "research_agent", source_status, source_quality, research_context)
    payload = {
        "agent": "research_agent",
        "run_date": cfg.run_date,
        "ideas": ideas,
        "research_context": research_context,
        "source_status": source_status,
        "source_quality": source_quality,
        "source_snapshot": {
            "item_count": snapshot["item_count"],
            "run_path": str(cfg.run_dir / "source_snapshots" / "research_agent.json"),
            "knowledge_path": str(cfg.knowledge_root / "source_snapshots.jsonl"),
        },
        "notes": "MVP uses durable local priors plus daily event titles; live research sources are best-effort and auditable.",
    }
    write_json(cfg.run_dir / "research_ideas.json", payload)
    return payload


if __name__ == "__main__":
    run()
