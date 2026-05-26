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

from .data_loader import PROJECT_ROOT, load_panel, load_basic, load_trade_cal
from .features import compute_features, list_feature_cols
from .labels import attach_labels
from .dataset import WindowDataset
from .train import build_model_from_checkpoint

CHECKPOINTS = PROJECT_ROOT / "checkpoints"
DAILY_LOGS = PROJECT_ROOT / "reports" / "daily_logs"


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
                     tag: str | None = None) -> pd.DataFrame:
    device = device or ("cuda" if torch.cuda.is_available() else "cpu")
    asof_date = pd.Timestamp(date)
    target_trade_date = _next_trading_date(asof_date)
    ckpt_path = _checkpoint_path(model_name, tag)
    ckpt = torch.load(ckpt_path, map_location=device, weights_only=False)
    feature_cols = ckpt["feature_cols"]
    window = int(ckpt.get("cfg", {}).get("window", window))

    panel = load_panel()
    panel = panel[panel["trade_date"] <= asof_date]
    feats = compute_features(panel)
    labels = attach_labels(panel)
    # Keep enough history for the sliding window, then select samples ending at asof_date.
    ds = WindowDataset(feats, labels, feature_cols, window=window,
                       date_range=(str(asof_date - pd.Timedelta(days=120)), str(asof_date)),
                       drop_missing_label=False)

    model = build_model_from_checkpoint(
        ckpt, model_name=model_name, n_features=len(feature_cols), window=window
    )
    model.load_state_dict(ckpt["model_state"])
    model.to(device).eval()

    # Build predictions just for samples whose end date == the requested date
    target_day = np.datetime64(asof_date.to_datetime64(), "D")
    rows: list[dict] = []
    for i, s in enumerate(ds.samples):
        end_date = np.datetime64(ds.blocks_dates[s.stock_idx][s.end_row], "D")
        if end_date != target_day:
            continue
        x, _, si, _ = ds[i]
        with torch.no_grad():
            p = float(model(x.unsqueeze(0).to(device)).cpu().item())
        rows.append({"ts_code": ds.ts_codes[int(si)], "y_pred": p})

    if not rows:
        return pd.DataFrame(columns=[
            "rank", "asof_date", "target_trade_date", "ts_code", "y_pred",
            "name", "industry", "ref_vwap", "ref_close",
        ])

    df = pd.DataFrame(rows).sort_values("y_pred", ascending=False).head(n)
    df.insert(0, "rank", np.arange(1, len(df) + 1))
    df.insert(1, "asof_date", asof_date.strftime("%Y-%m-%d"))
    df.insert(2, "target_trade_date", target_trade_date.strftime("%Y-%m-%d"))

    basic = load_basic()[["ts_code", "name", "industry"]]
    df = df.merge(basic, on="ts_code", how="left")

    # Reference price = last known vwap, for limit-order anchoring
    last = panel[panel["trade_date"] == asof_date].set_index("ts_code")
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
    args = ap.parse_args()

    d = pd.Timestamp(args.date)
    DAILY_LOGS.mkdir(parents=True, exist_ok=True)
    targets = predict_for_date(args.model, d, n=args.n, tag=args.tag)
    target = pd.Timestamp(targets["target_trade_date"].iloc[0]) if len(targets) else _next_trading_date(d)
    out = DAILY_LOGS / f"{target.strftime('%Y%m%d')}_targets.csv"
    targets.to_csv(out, index=False, encoding="utf-8-sig")
    print(f"[predict] wrote {out}")
    print(targets.to_string(index=False))


if __name__ == "__main__":
    main()
