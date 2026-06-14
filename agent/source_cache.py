from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .config import RunConfig
from .io_utils import append_jsonl, write_json


def write_source_snapshot(
    cfg: RunConfig,
    agent_name: str,
    source_status: list[dict[str, Any]],
    source_quality: dict[str, Any],
    items: list[dict[str, Any]],
) -> dict[str, Any]:
    snapshot = {
        "run_date": cfg.run_date,
        "agent": agent_name,
        "snapshot_written_at": datetime.now(timezone.utc).isoformat(),
        "source_status": source_status,
        "source_quality": source_quality,
        "item_count": len(items),
        "items": items[:50],
    }
    write_json(cfg.run_dir / "source_snapshots" / f"{agent_name}.json", snapshot)
    append_jsonl(cfg.knowledge_root / "source_snapshots.jsonl", snapshot)
    write_json(cfg.knowledge_root / "source_snapshots_latest.json", snapshot)
    return snapshot
