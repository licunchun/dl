"""Predict competition targets from the saved short-term moneyflow checkpoint."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
import torch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.short_term_competition_train import (  # noqa: E402
    DAILY_LOGS,
    _build_frames,
    _configure_data_dir,
    _predict_target,
)
from src import data_loader as dl  # noqa: E402
from src.train import build_model_from_checkpoint  # noqa: E402


def _next_trading_date(asof_date: str) -> str:
    cal = dl.load_trade_cal()
    future = cal[cal > pd.Timestamp(asof_date)]
    if len(future) == 0:
        raise ValueError(f"No trading date after {asof_date}")
    return pd.Timestamp(future[0]).strftime("%Y-%m-%d")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", type=Path, required=True)
    ap.add_argument("--cache-dir", type=Path, default=Path("/home/lcc17/pan_sync_20260528/shortterm_cache"))
    ap.add_argument("--start", default="2019-01-01")
    ap.add_argument("--asof-date", required=True)
    ap.add_argument("--target-date", default=None)
    ap.add_argument("--tag", default="lstm_ic_short_mf_decay_h256_l2_w10")
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--window", type=int, default=10)
    ap.add_argument("--rebuild-cache", action="store_true")
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    args = ap.parse_args()

    _configure_data_dir(args.data_dir)
    if args.target_date is None:
        args.target_date = _next_trading_date(args.asof_date)

    _, _, available_feature_cols, panel = _build_frames(args)
    ckpt_path = PROJECT_ROOT / "checkpoints" / f"{args.tag}.pt"
    ckpt = torch.load(ckpt_path, map_location=args.device, weights_only=False)
    feature_cols = ckpt["feature_cols"]
    missing = [c for c in feature_cols if c not in available_feature_cols]
    if missing:
        raise ValueError(f"Checkpoint feature columns missing from current data: {missing}")
    model_name = ckpt.get("cfg", {}).get("model", "lstm")
    window = int(ckpt.get("cfg", {}).get("window", args.window))
    model = build_model_from_checkpoint(
        ckpt,
        model_name=model_name,
        n_features=len(feature_cols),
        window=window,
    )
    model.load_state_dict(ckpt["model_state"])
    model.to(args.device).eval()
    args.window = window

    targets = _predict_target(args, model, feature_cols, panel)
    DAILY_LOGS.mkdir(parents=True, exist_ok=True)
    out = DAILY_LOGS / f"{args.target_date.replace('-', '')}_{args.tag}_targets.csv"
    targets.to_csv(out, index=False, encoding="utf-8-sig")
    print(f"[predict-short] wrote {out}")
    print(targets.to_string(index=False))


if __name__ == "__main__":
    main()
