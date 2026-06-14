from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path


@dataclass(frozen=True)
class RunConfig:
    run_date: str
    data_root: Path
    output_root: Path
    knowledge_root: Path
    factor_library: Path
    offline: bool = False
    agent_retries: int = 1
    retention_days: int = 370
    max_data_staleness_days: int = 7
    lock_stale_minutes: int = 180
    min_free_disk_mb: int = 512

    @property
    def run_dir(self) -> Path:
        return self.output_root / "daily_logs" / self.run_date


def load_config() -> RunConfig:
    run_date = _load_run_date()
    output_root = Path(os.environ.get("QUANT_OUTPUT_ROOT", "reports"))
    knowledge_root = Path(os.environ.get("QUANT_KNOWLEDGE_ROOT", "knowledge_base"))
    factor_library = Path(os.environ.get("QUANT_FACTOR_LIBRARY", "factor_library"))
    data_root = Path(os.environ.get("QUANT_DATA_ROOT", str(Path.home() / "pan_sync_20260528"))).expanduser()
    offline = os.environ.get("QUANT_OFFLINE", "0") == "1"
    agent_retries = int(os.environ.get("QUANT_AGENT_RETRIES", "1"))
    retention_days = int(os.environ.get("QUANT_RETENTION_DAYS", "370"))
    max_data_staleness_days = int(os.environ.get("QUANT_MAX_DATA_STALENESS_DAYS", "7"))
    lock_stale_minutes = int(os.environ.get("QUANT_LOCK_STALE_MINUTES", "180"))
    min_free_disk_mb = int(os.environ.get("QUANT_MIN_FREE_DISK_MB", "512"))
    return RunConfig(
        run_date=run_date,
        data_root=data_root,
        output_root=output_root,
        knowledge_root=knowledge_root,
        factor_library=factor_library,
        offline=offline,
        agent_retries=agent_retries,
        retention_days=retention_days,
        max_data_staleness_days=max_data_staleness_days,
        lock_stale_minutes=lock_stale_minutes,
        min_free_disk_mb=min_free_disk_mb,
    )


def _load_run_date() -> str:
    value = os.environ.get("QUANT_DATE") or os.environ.get("QUANT_RUN_DATE") or date.today().strftime("%Y%m%d")
    if len(value) != 8 or not value.isdigit():
        raise ValueError(f"run date must be a valid YYYYMMDD date, got {value!r}")
    try:
        datetime.strptime(value, "%Y%m%d")
    except ValueError as exc:
        raise ValueError(f"run date must be a valid YYYYMMDD date, got {value!r}") from exc
    return value
