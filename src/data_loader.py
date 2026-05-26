"""Data loading utilities.

Raw data lives under ``data/`` with the following structure (extracted from the
course zip, see README.md of the data pack):

    data/
      basic.csv                # all stocks meta
      trade_cal.csv            # trading calendar (SSE)
      daily/YYYYMMDD.csv       # cross-section OHLCV per trade day (2016~)
      market/000001.SH.csv ... # index OHLCV
      metric/YYYYMMDD.csv      # per-stock fundamentals (PE/PB/turnover/mv)
      moneyflow/YYYYMMDD.csv
      stock_st/YYYYMMDD.csv    # daily ST names
      index_weight/, news/     # unused by baseline

This module provides:

    - ``load_basic()``        : filtered universe (excl. 北交所 by default)
    - ``load_trade_cal()``    : open trading dates
    - ``load_st_set(date)``   : set of ST ts_codes on a given date
    - ``iter_daily(start,end)``
    - ``build_panel(...)``    : assemble and cache a long-form parquet panel
                                (ts_code, trade_date, OHLCV + metric fields)
                                with the competition universe already applied

The heavy lifting is cached to ``data/panel.parquet`` so training / features
only pay the IO cost once.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Iterator

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
PANEL_CACHE = DATA_DIR / "panel.parquet"

# Competition universe: all A-shares except ST and 北交所.
# `basic.csv::market` values observed: 主板 / 创业板 / 科创板 / 北交所 / CDR.
DEFAULT_EXCLUDE_MARKETS = ("北交所",)

DAILY_COLS = [
    "ts_code", "trade_date",
    "open", "high", "low", "close", "pre_close",
    "change", "pct_chg", "vol", "amount", "vwap",
]

METRIC_COLS = [
    "ts_code", "trade_date",
    "turnover_rate", "turnover_rate_f", "volume_ratio",
    "pe", "pe_ttm", "pb", "ps", "ps_ttm",
    "total_share", "float_share", "free_share",
    "total_mv", "circ_mv",
]


def _parse_date(s: str | int | pd.Timestamp) -> pd.Timestamp:
    return pd.Timestamp(str(s))


@lru_cache(maxsize=1)
def load_basic(exclude_markets: tuple[str, ...] = DEFAULT_EXCLUDE_MARKETS) -> pd.DataFrame:
    """Stock meta; filtered by market."""
    df = pd.read_csv(DATA_DIR / "basic.csv", dtype={"symbol": str, "list_date": str})
    if exclude_markets:
        df = df[~df["market"].isin(exclude_markets)].copy()
    df["list_date"] = pd.to_datetime(df["list_date"], format="%Y%m%d", errors="coerce")
    return df.reset_index(drop=True)


@lru_cache(maxsize=1)
def load_trade_cal(exchange: str = "SSE") -> pd.DatetimeIndex:
    cal = pd.read_csv(DATA_DIR / "trade_cal.csv", dtype={"cal_date": str, "pretrade_date": str})
    cal = cal[(cal["exchange"] == exchange) & (cal["is_open"].astype(int) == 1)]
    return pd.DatetimeIndex(pd.to_datetime(cal["cal_date"], format="%Y%m%d")).sort_values()


def trading_dates(start: str, end: str) -> pd.DatetimeIndex:
    cal = load_trade_cal()
    s, e = _parse_date(start), _parse_date(end)
    return cal[(cal >= s) & (cal <= e)]


def _daily_path(date: pd.Timestamp, subdir: str = "daily") -> Path:
    return DATA_DIR / subdir / f"{date.strftime('%Y%m%d')}.csv"


def load_st_set(date: pd.Timestamp) -> set[str]:
    p = _daily_path(date, subdir="stock_st")
    if not p.exists():
        return set()
    df = pd.read_csv(p, usecols=["ts_code"])
    return set(df["ts_code"].tolist())


def iter_daily(start: str, end: str, subdir: str = "daily") -> Iterator[tuple[pd.Timestamp, Path]]:
    for d in trading_dates(start, end):
        p = _daily_path(d, subdir=subdir)
        if p.exists():
            yield d, p


def load_daily_slice(date: pd.Timestamp) -> pd.DataFrame:
    df = pd.read_csv(_daily_path(date), dtype={"ts_code": str})
    df["trade_date"] = pd.to_datetime(df["trade_date"].astype(str), format="%Y%m%d")
    return df[DAILY_COLS]


def load_metric_slice(date: pd.Timestamp) -> pd.DataFrame | None:
    p = _daily_path(date, subdir="metric")
    if not p.exists():
        return None
    df = pd.read_csv(p, dtype={"ts_code": str})
    df["trade_date"] = pd.to_datetime(df["trade_date"].astype(str), format="%Y%m%d")
    keep = [c for c in METRIC_COLS if c in df.columns]
    return df[keep]


@dataclass
class PanelBuildConfig:
    start: str = "2019-01-01"
    end: str = "2026-04-30"
    exclude_markets: tuple[str, ...] = DEFAULT_EXCLUDE_MARKETS
    min_list_days: int = 60            # drop stocks in first 60 days after listing (新股炒作)
    drop_st: bool = True
    include_metric: bool = True
    cache_path: Path = PANEL_CACHE


def build_panel(cfg: PanelBuildConfig | None = None, verbose: bool = True) -> pd.DataFrame:
    """Assemble long-form panel and cache it to parquet.

    Returned columns:
        ts_code, trade_date, open, high, low, close, pre_close, pct_chg,
        vol, amount, vwap, [metric fields ...]
    Only rows that pass: not ST on trade_date, market ≠ 北交所, list_date
    + min_list_days ≤ trade_date.
    """
    cfg = cfg or PanelBuildConfig()
    basic = load_basic(exclude_markets=cfg.exclude_markets)
    code2list = dict(zip(basic["ts_code"], basic["list_date"]))
    valid_codes = set(basic["ts_code"])

    daily_frames: list[pd.DataFrame] = []
    metric_frames: list[pd.DataFrame] = []
    dates = list(trading_dates(cfg.start, cfg.end))
    if verbose:
        print(f"[panel] scanning {len(dates)} trading dates {cfg.start} → {cfg.end}")
    for i, d in enumerate(dates):
        p = _daily_path(d)
        if not p.exists():
            continue
        df = load_daily_slice(d)
        df = df[df["ts_code"].isin(valid_codes)]
        if cfg.drop_st:
            st_today = load_st_set(d)
            if st_today:
                df = df[~df["ts_code"].isin(st_today)]
        # min-list-days filter
        if cfg.min_list_days > 0:
            lst = df["ts_code"].map(code2list)
            ok = (d - lst).dt.days >= cfg.min_list_days
            df = df[ok.fillna(False)]
        daily_frames.append(df)

        if cfg.include_metric:
            m = load_metric_slice(d)
            if m is not None:
                metric_frames.append(m)

        if verbose and (i % 100 == 0):
            print(f"[panel] {i}/{len(dates)} {d.date()} rows={len(df)}")

    panel = pd.concat(daily_frames, ignore_index=True)
    if metric_frames:
        metric = pd.concat(metric_frames, ignore_index=True)
        panel = panel.merge(metric.drop(columns=["close"], errors="ignore"),
                            on=["ts_code", "trade_date"], how="left")

    panel = panel.sort_values(["ts_code", "trade_date"]).reset_index(drop=True)
    for c in ("open", "high", "low", "close", "pre_close", "pct_chg",
              "vol", "amount", "vwap"):
        panel[c] = pd.to_numeric(panel[c], errors="coerce")

    cfg.cache_path.parent.mkdir(parents=True, exist_ok=True)
    panel.to_parquet(cfg.cache_path, index=False)
    if verbose:
        print(f"[panel] wrote {cfg.cache_path} shape={panel.shape}")
    return panel


def load_panel(cache_path: Path = PANEL_CACHE) -> pd.DataFrame:
    if not cache_path.exists():
        raise FileNotFoundError(
            f"{cache_path} not found. Run `python -m src.data_loader build-panel` first."
        )
    return pd.read_parquet(cache_path)


def load_index(ts_code: str = "000300.SH") -> pd.DataFrame:
    p = DATA_DIR / "market" / f"{ts_code}.csv"
    df = pd.read_csv(p, dtype={"ts_code": str})
    df["trade_date"] = pd.to_datetime(df["trade_date"].astype(str), format="%Y%m%d")
    return df.sort_values("trade_date").reset_index(drop=True)


def main() -> None:
    ap = argparse.ArgumentParser(description="A-share panel builder")
    sub = ap.add_subparsers(dest="cmd", required=True)

    bp = sub.add_parser("build-panel")
    bp.add_argument("--start", default="2019-01-01")
    bp.add_argument("--end", default="2026-04-30")
    bp.add_argument("--no-metric", action="store_true")
    bp.add_argument("--out", default=str(PANEL_CACHE))

    sub.add_parser("peek")

    args = ap.parse_args()
    if args.cmd == "build-panel":
        cfg = PanelBuildConfig(
            start=args.start, end=args.end,
            include_metric=not args.no_metric,
            cache_path=Path(args.out),
        )
        build_panel(cfg)
    elif args.cmd == "peek":
        p = load_panel()
        print(p.head(), "\n---")
        print("shape:", p.shape)
        print("date range:", p["trade_date"].min(), "→", p["trade_date"].max())
        print("stocks:", p["ts_code"].nunique())


if __name__ == "__main__":
    main()
