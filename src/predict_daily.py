"""Pre-market CLI: given an as-of date D, produce the target 10-stock list.

Usage:
    python -m src.predict_daily --date 2026-05-29 --model transformer

Writes `reports/daily_logs/YYYYMMDD_targets.csv` with columns
(rank, asof_date, target_trade_date, ts_code, name, y_pred, close_ref_vwap).
`--date` is the data cutoff date: only rows up to D are used, and the output is
for the next open trading day after D.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import torch

from . import data_loader as dl
from .data_loader import PROJECT_ROOT, load_panel, load_basic, load_trade_cal
from .features import compute_features, list_feature_cols
from .labels import attach_labels
from .dataset import WindowDataset
from .train import build_model_from_checkpoint

CHECKPOINTS = PROJECT_ROOT / "checkpoints"
DAILY_LOGS = PROJECT_ROOT / "reports" / "daily_logs"


def _configure_data_dir(data_dir: Path) -> None:
    dl.DATA_DIR = Path(data_dir)
    dl.PANEL_CACHE = dl.DATA_DIR / "panel.parquet"
    dl.load_basic.cache_clear()
    dl.load_trade_cal.cache_clear()


def _load_panel_for_asof(asof_date: pd.Timestamp, data_dir: Path | None = None,
                         cache_dir: Path | None = None,
                         rebuild_cache: bool = False) -> pd.DataFrame:
    if data_dir is None:
        return load_panel()

    _configure_data_dir(data_dir)
    cache_dir = cache_dir or (Path(data_dir) / "daily_predict_cache")
    cache_dir.mkdir(parents=True, exist_ok=True)
    panel_cache = cache_dir / f"panel_2019-01-01_{asof_date.strftime('%Y-%m-%d')}.parquet"
    if panel_cache.exists() and not rebuild_cache:
        return pd.read_parquet(panel_cache)
    return dl.build_panel(dl.PanelBuildConfig(
        start="2019-01-01",
        end=asof_date.strftime("%Y-%m-%d"),
        cache_path=panel_cache,
        include_metric=True,
    ))


def _next_trading_date(asof_date: pd.Timestamp) -> pd.Timestamp:
    cal = load_trade_cal()
    future = cal[cal > pd.Timestamp(asof_date)]
    if len(future) == 0:
        raise ValueError(f"No trading date after {asof_date.date()} in trade calendar")
    return pd.Timestamp(future[0])


def _checkpoint_path(model_name: str, tag: str | None = None) -> Path:
    if tag:
        p = CHECKPOINTS / f"{tag}.pt"
        if not p.exists():
            raise FileNotFoundError(f"No checkpoint tag {tag}: {p}")
        return p
    ckpt_path = CHECKPOINTS / f"{model_name}_ic.pt"
    if ckpt_path.exists():
        return ckpt_path
    alt = CHECKPOINTS / f"{model_name}_mse.pt"
    if alt.exists():
        return alt
    raise FileNotFoundError(f"No checkpoint for {model_name}")


def predict_for_date(model_name: str, date: pd.Timestamp, n: int = 10,
                     window: int = 20, device: str = None,
                     tag: str | None = None,
                     data_dir: Path | None = None,
                     cache_dir: Path | None = None,
                     rebuild_cache: bool = False,
                     direction: str = "forward") -> pd.DataFrame:
    device = device or ("cuda" if torch.cuda.is_available() else "cpu")
    asof_date = pd.Timestamp(date)
    if data_dir is not None:
        _configure_data_dir(data_dir)
    target_trade_date = _next_trading_date(asof_date)
    ckpt_path = _checkpoint_path(model_name, tag)
    ckpt = torch.load(ckpt_path, map_location=device, weights_only=False)
    feature_cols = ckpt["feature_cols"]
    window = int(ckpt.get("cfg", {}).get("window", window))

    panel = _load_panel_for_asof(asof_date, data_dir, cache_dir, rebuild_cache)
    panel = panel[panel["trade_date"] <= asof_date].copy()
    last_day = panel[panel["trade_date"] == asof_date].copy()
    if last_day.empty:
        raise ValueError(f"No panel rows for as-of date {asof_date.date()}")

    # Feature rows are shifted by one day.  For a pre-market decision on the
    # next trading day, append a synthetic target-day row so the sample ending
    # on target_trade_date uses information through asof_date, not asof_date-1.
    synth = last_day.copy()
    synth["trade_date"] = target_trade_date
    synth["pct_chg"] = 0.0
    target_panel = pd.concat([panel, synth], ignore_index=True)

    feats = compute_features(target_panel)
    labels = attach_labels(target_panel)
    # Keep enough history for the sliding window, then select target-day samples.
    ds = WindowDataset(feats, labels, feature_cols, window=window,
                       date_range=(str(asof_date - pd.Timedelta(days=160)), str(target_trade_date)),
                       drop_missing_label=False)

    model = build_model_from_checkpoint(
        ckpt, model_name=model_name, n_features=len(feature_cols), window=window
    )
    model.load_state_dict(ckpt["model_state"])
    model.to(device).eval()

    # Build predictions just for samples whose end date is the target session.
    target_day = np.datetime64(target_trade_date.to_datetime64(), "D")
    rows: list[dict] = []
    for i, s in enumerate(ds.samples):
        end_date = np.datetime64(ds.blocks_dates[s.stock_idx][s.end_row], "D")
        if end_date != target_day:
            continue
        x, _, si, _ = ds[i]
        with torch.no_grad():
            raw = float(model(x.unsqueeze(0).to(device)).cpu().item())
        score = -raw if direction == "inverse" else raw
        rows.append({"ts_code": ds.ts_codes[int(si)], "y_pred": raw, "strategy_score": score})

    if not rows:
        return pd.DataFrame(columns=[
            "rank", "asof_date", "target_trade_date", "ts_code", "y_pred",
            "name", "industry", "ref_vwap", "ref_close",
        ])

    df = pd.DataFrame(rows).sort_values("strategy_score", ascending=False).head(n)
    df.insert(0, "rank", np.arange(1, len(df) + 1))
    df.insert(1, "asof_date", asof_date.strftime("%Y-%m-%d"))
    df.insert(2, "target_trade_date", target_trade_date.strftime("%Y-%m-%d"))
    df.insert(3, "direction", direction)

    basic = load_basic()[["ts_code", "name", "industry"]]
    df = df.merge(basic, on="ts_code", how="left")

    # Reference price = last known vwap, for limit-order anchoring
    last = last_day.set_index("ts_code")
    df["ref_vwap"] = df["ts_code"].map(last["vwap"]) if "vwap" in last.columns else np.nan
    df["ref_close"] = df["ts_code"].map(last["close"])
    return df


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True,
                    help="YYYY-MM-DD data cutoff date; output targets next trading day")
    ap.add_argument("--model", default="transformer")
    ap.add_argument("--tag", default=None,
                    help="Checkpoint tag, e.g. transformer_ic_large. Defaults to <model>_ic/<model>_mse.")
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--direction", choices=["forward", "inverse"], default="forward",
                    help="Rank high raw predictions (forward) or low raw predictions (inverse).")
    ap.add_argument("--data-dir", type=Path, default=None,
                    help="Optional current raw data directory, e.g. synced competition data.")
    ap.add_argument("--cache-dir", type=Path, default=None,
                    help="Panel cache directory used with --data-dir.")
    ap.add_argument("--rebuild-cache", action="store_true")
    args = ap.parse_args()

    d = pd.Timestamp(args.date)
    DAILY_LOGS.mkdir(parents=True, exist_ok=True)
    targets = predict_for_date(
        args.model, d, n=args.n, tag=args.tag,
        data_dir=args.data_dir, cache_dir=args.cache_dir,
        rebuild_cache=args.rebuild_cache,
        direction=args.direction,
    )
    target = pd.Timestamp(targets["target_trade_date"].iloc[0]) if len(targets) else _next_trading_date(d)
    out = DAILY_LOGS / f"{target.strftime('%Y%m%d')}_targets.csv"
    targets.to_csv(out, index=False, encoding="utf-8-sig")
    print(f"[predict] wrote {out}")
    print(targets.to_string(index=False))


if __name__ == "__main__":
    main()
