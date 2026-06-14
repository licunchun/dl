from __future__ import annotations

from pathlib import Path
from typing import Any
import hashlib
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from .config import RunConfig, load_config
from .io_utils import append_jsonl, write_json


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _normalize_date(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s.astype(str), format="%Y%m%d", errors="coerce")


def _read_csv_dir(path: Path, start: str | None = None, end: str | None = None, usecols: list[str] | None = None) -> pd.DataFrame:
    frames = []
    for p in sorted(path.glob("*.csv")):
        stem = p.stem.split("_")[0]
        if stem.isdigit():
            if start and stem < start:
                continue
            if end and stem > end:
                continue
        try:
            frames.append(pd.read_csv(p, usecols=usecols))
        except ValueError:
            frames.append(pd.read_csv(p))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _csv_dir_summary(path: Path, start: str | None = None, end: str | None = None) -> dict[str, Any]:
    files = sorted(path.glob("*.csv")) if path.exists() else []
    selected = []
    for p in files:
        stem = p.stem.split("_")[0]
        if stem.isdigit():
            if start and stem < start:
                continue
            if end and stem > end:
                continue
        selected.append(p)
    return {
        "path": str(path),
        "exists": path.exists(),
        "csv_file_count": len(files),
        "selected_csv_file_count": len(selected),
        "selected_sample": [str(p) for p in selected[:5]],
    }


def _synthetic_dataset() -> pd.DataFrame:
    dates = pd.bdate_range("2025-01-01", periods=90)
    rows = []
    for j, code in enumerate(["AAA.SH", "BBB.SZ", "CCC.SH", "DDD.SZ"]):
        base = 10 + j
        for i, dt in enumerate(dates):
            close = base * (1 + 0.001 * i + 0.01 * np.sin(i / 5 + j))
            rows.append({
                "ts_code": code,
                "trade_date": dt,
                "open": close * 0.999,
                "high": close * 1.01,
                "low": close * 0.99,
                "close": close,
                "pre_close": close / 1.001,
                "pct_chg": 0.1,
                "vol": 100000 + i * 100,
                "amount": 50000 + i * 10,
                "vwap": close,
                "turnover_rate": 1.0 + j * 0.1,
                "pb": 1.0 + j * 0.2,
                "total_mv": 1000000 + j * 100000,
                "buy_lg_amount": 1000 + i,
                "sell_lg_amount": 900 + i,
                "buy_elg_amount": 500 + i,
                "sell_elg_amount": 450 + i,
                "is_st": False,
                "industry": "synthetic",
                "area": "synthetic",
                "market": "synthetic",
                "list_date": 20200101,
            })
    return pd.DataFrame(rows)


def _domain_coverage(df: pd.DataFrame) -> dict[str, Any]:
    domains = {
        "ohlcv": ["open", "high", "low", "close", "pre_close", "vol", "amount", "vwap"],
        "financial_metric": ["turnover_rate", "pb", "total_mv"],
        "industry": ["industry"],
        "moneyflow": ["buy_lg_amount", "sell_lg_amount", "buy_elg_amount", "sell_elg_amount", "mf_buy_pressure"],
        "risk_flags": ["is_st"],
        "derived_features": ["ret_5", "amount_ratio_20", "forward_ret_5d"],
    }
    out: dict[str, Any] = {}
    for name, cols in domains.items():
        present = [c for c in cols if c in df.columns]
        missing = [c for c in cols if c not in df.columns]
        null_rates = {
            c: round(float(df[c].isna().mean()), 6)
            for c in present
        }
        usable = bool(cols) and not missing and all(rate < 0.95 for rate in null_rates.values())
        out[name] = {
            "required_columns": cols,
            "present_columns": present,
            "missing_columns": missing,
            "null_rates": null_rates,
            "usable": usable,
        }
    return out


def _health_report(df: pd.DataFrame, source_mode: str, cfg: RunConfig) -> dict[str, Any]:
    required = [
        "ts_code", "trade_date", "open", "close", "amount", "ret_5", "amount_ratio_20",
        "mf_buy_pressure", "forward_ret_5d",
    ]
    missing_cols = [c for c in required if c not in df.columns]
    date_min = str(df["trade_date"].min().date()) if "trade_date" in df and len(df) else None
    date_max = str(df["trade_date"].max().date()) if "trade_date" in df and len(df) else None
    run_ts = pd.to_datetime(cfg.run_date, format="%Y%m%d", errors="coerce")
    max_ts = pd.to_datetime(date_max, errors="coerce") if date_max else pd.NaT
    staleness_days = int((run_ts.normalize() - max_ts.normalize()).days) if pd.notna(run_ts) and pd.notna(max_ts) else None
    if source_mode == "synthetic_fallback":
        freshness_status = "not_applicable_synthetic"
        freshness_ok = True
    else:
        freshness_ok = staleness_days is not None and staleness_days >= 0 and staleness_days <= cfg.max_data_staleness_days
        freshness_status = "ok" if freshness_ok else "stale_or_future_dated"
    duplicate_keys = int(df.duplicated(["ts_code", "trade_date"]).sum()) if {"ts_code", "trade_date"}.issubset(df.columns) else 0
    domain_coverage = _domain_coverage(df)
    null_rates = {
        c: round(float(df[c].isna().mean()), 6)
        for c in required
        if c in df.columns
    }
    checks = {
        "has_rows": len(df) > 0,
        "has_required_columns": not missing_cols,
        "no_duplicate_keys": duplicate_keys == 0,
        "has_multiple_dates": int(df["trade_date"].nunique()) > 5 if "trade_date" in df else False,
        "has_multiple_stocks": int(df["ts_code"].nunique()) > 1 if "ts_code" in df else False,
        "data_freshness_ok": freshness_ok,
        "required_data_domains_usable": all(item["usable"] for item in domain_coverage.values()),
    }
    return {
        "agent": "data_agent",
        "run_date": cfg.run_date,
        "source_mode": source_mode,
        "rows": int(len(df)),
        "stocks": int(df["ts_code"].nunique()) if "ts_code" in df else 0,
        "dates": int(df["trade_date"].nunique()) if "trade_date" in df else 0,
        "date_min": date_min,
        "date_max": date_max,
        "freshness": {
            "status": freshness_status,
            "staleness_days": staleness_days,
            "max_allowed_staleness_days": cfg.max_data_staleness_days,
            "note": "synthetic fallback keeps offline tests runnable but is not production evidence" if source_mode == "synthetic_fallback" else "",
        },
        "missing_required_columns": missing_cols,
        "domain_coverage": domain_coverage,
        "duplicate_keys": duplicate_keys,
        "null_rates": null_rates,
        "checks": checks,
        "status": "ok" if all(checks.values()) else "warning",
    }


def build_dataset(cfg: RunConfig, lookback_days: int = 420) -> pd.DataFrame:
    end = cfg.run_date
    # Keep MVP runtime bounded. Users can increase via QUANT_DATA_START.
    start = pd.Timestamp(end).strftime("%Y%m%d") if "-" in end else end
    start_ts = pd.to_datetime(start, format="%Y%m%d", errors="coerce") - pd.Timedelta(days=lookback_days)
    start_str = start_ts.strftime("%Y%m%d") if pd.notna(start_ts) else None
    daily_root = cfg.data_root / "A股数据" / "daily"
    metric_root = cfg.data_root / "A股数据" / "metric"
    moneyflow_root = cfg.data_root / "A股数据" / "moneyflow"
    st_root = cfg.data_root / "A股数据" / "stock_st"
    basic_path = cfg.data_root / "A股数据" / "basic.csv"
    if not daily_root.exists():
        daily_root = cfg.data_root / "daily"
        metric_root = cfg.data_root / "metric"
        moneyflow_root = cfg.data_root / "moneyflow"
        st_root = cfg.data_root / "stock_st"
        basic_path = cfg.data_root / "basic.csv"

    source_detail = {
        "data_root": str(cfg.data_root),
        "start": start_str,
        "end": end,
        "daily": _csv_dir_summary(daily_root, start=start_str, end=end),
        "metric": _csv_dir_summary(metric_root, start=start_str, end=end),
        "moneyflow": _csv_dir_summary(moneyflow_root, start=start_str, end=end),
        "stock_st": _csv_dir_summary(st_root, start=start_str, end=end),
        "basic": {
            "path": str(basic_path),
            "exists": basic_path.exists(),
        },
    }
    daily = _read_csv_dir(daily_root, start=start_str, end=end, usecols=["ts_code", "trade_date", "open", "high", "low", "close", "pre_close", "pct_chg", "vol", "amount", "vwap"])
    if daily.empty:
        df = _add_features(_synthetic_dataset())
        df.attrs["source_mode"] = "synthetic_fallback"
        source_detail["fallback_reason"] = "daily_csv_missing_or_empty"
        df.attrs["data_source_detail"] = source_detail
        return df

    metric = _read_csv_dir(metric_root, start=start_str, end=end, usecols=["ts_code", "trade_date", "turnover_rate", "pb", "total_mv"])
    mf = _read_csv_dir(moneyflow_root, start=start_str, end=end, usecols=["ts_code", "trade_date", "buy_lg_amount", "sell_lg_amount", "buy_elg_amount", "sell_elg_amount"])
    st = _read_csv_dir(st_root, start=start_str, end=end, usecols=["ts_code", "trade_date"])
    for frame in [daily, metric, mf, st]:
        if not frame.empty and "trade_date" in frame:
            frame["trade_date"] = _normalize_date(frame["trade_date"])
    df = daily.copy()
    if not metric.empty:
        df = df.merge(metric, on=["ts_code", "trade_date"], how="left")
    else:
        for col in ["turnover_rate", "pb", "total_mv"]:
            df[col] = np.nan
    if not mf.empty:
        df = df.merge(mf, on=["ts_code", "trade_date"], how="left")
    else:
        for col in ["buy_lg_amount", "sell_lg_amount", "buy_elg_amount", "sell_elg_amount"]:
            df[col] = np.nan
    if not st.empty:
        st["is_st"] = True
        df = df.merge(st[["ts_code", "trade_date", "is_st"]].drop_duplicates(), on=["ts_code", "trade_date"], how="left")
    if basic_path.exists():
        try:
            basic = pd.read_csv(basic_path, usecols=["ts_code", "industry", "area", "market", "list_date"])
            df = df.merge(basic.drop_duplicates("ts_code"), on="ts_code", how="left")
        except ValueError:
            basic = pd.read_csv(basic_path)
            keep = [c for c in ["ts_code", "industry", "area", "market", "list_date"] if c in basic.columns]
            if "ts_code" in keep:
                df = df.merge(basic[keep].drop_duplicates("ts_code"), on="ts_code", how="left")
    if "industry" not in df.columns:
        df["industry"] = pd.NA
    df["is_st"] = df.get("is_st", False)
    df["is_st"] = df["is_st"].fillna(False).astype(bool)
    df = _add_features(df)
    df.attrs["source_mode"] = "local_csv"
    source_detail["fallback_reason"] = None
    df.attrs["data_source_detail"] = source_detail
    return df


def _add_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values(["ts_code", "trade_date"]).reset_index(drop=True)
    for col in ["vwap", "pb", "buy_lg_amount", "sell_lg_amount", "buy_elg_amount", "sell_elg_amount"]:
        if col not in df.columns:
            df[col] = np.nan
    g = df.groupby("ts_code", sort=False)
    df["ret_1"] = g["close"].pct_change(1)
    df["ret_5"] = g["close"].pct_change(5)
    df["ret_20"] = g["close"].pct_change(20)
    df["std_20"] = g["ret_1"].rolling(20, min_periods=8).std().reset_index(level=0, drop=True)
    df["amount_ma20"] = g["amount"].rolling(20, min_periods=8).mean().reset_index(level=0, drop=True)
    df["amount_ratio_20"] = df["amount"] / df["amount_ma20"].replace(0, np.nan)
    df["vwap_dev"] = df["close"] / df["vwap"].replace(0, np.nan) - 1
    df["pb_inv"] = 1.0 / df["pb"].replace(0, np.nan)
    amount_yuan = df["amount"].replace(0, np.nan) * 1000.0
    df["amihud_1"] = df["ret_1"].abs() / amount_yuan
    df["amihud_20"] = g["amihud_1"].rolling(20, min_periods=8).mean().reset_index(level=0, drop=True)
    df["liq_inv"] = 1 - df.groupby("trade_date")["amihud_20"].rank(pct=True)
    df["low_vol"] = 1 - df.groupby("trade_date")["std_20"].rank(pct=True)
    df["mf_buy_pressure"] = (
        (df["buy_lg_amount"].fillna(0) + df["buy_elg_amount"].fillna(0))
        - (df["sell_lg_amount"].fillna(0) + df["sell_elg_amount"].fillna(0))
    ) / df["amount"].replace(0, np.nan)
    for h in [1, 5, 10, 20]:
        df[f"forward_ret_{h}d"] = g["open"].shift(-(h + 1)) / g["open"].shift(-1) - 1
    return df


def run(config: RunConfig | None = None) -> dict[str, Any]:
    cfg = config or load_config()
    df = build_dataset(cfg)
    out_path = cfg.run_dir / "daily_dataset.parquet"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, index=False)
    stat = out_path.stat()
    source_mode = str(df.attrs.get("source_mode", "unknown"))
    data_source_detail = df.attrs.get("data_source_detail") or {}
    health = _health_report(df, source_mode, cfg)
    health["data_source_detail"] = data_source_detail
    write_json(cfg.run_dir / "data_health.json", health)
    payload = {
        "agent": "data_agent",
        "run_date": cfg.run_date,
        "dataset_path": str(out_path),
        "rows": int(len(df)),
        "stocks": int(df["ts_code"].nunique()) if "ts_code" in df else 0,
        "dates": int(df["trade_date"].nunique()) if "trade_date" in df else 0,
        "source_mode": source_mode,
        "health_status": health["status"],
        "dataset_sha256": _sha256(out_path),
        "dataset_size_bytes": stat.st_size,
        "data_source_detail": data_source_detail,
    }
    write_json(cfg.run_dir / "dataset_manifest.json", payload)
    data_artifact_record = {
        "run_date": cfg.run_date,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "agent": "data_agent",
        "dataset_manifest": payload,
        "data_health": health,
        "data_source_mode": source_mode,
        "data_freshness": health.get("freshness", {}),
        "data_checks": health.get("checks", {}),
        "data_domain_coverage": health.get("domain_coverage", {}),
        "data_source_detail": data_source_detail,
    }
    append_jsonl(cfg.knowledge_root / "data_health.jsonl", data_artifact_record)
    write_json(cfg.knowledge_root / "data_health_latest.json", data_artifact_record)
    return payload


if __name__ == "__main__":
    run()
