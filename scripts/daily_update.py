"""Daily data update + prediction pipeline.

Usage:
    python scripts/daily_update.py --date 2026-05-29

Workflow:
    1. Rebuilds panel cache (picks up new daily CSVs)
    2. Rebuilds WQ features + labels cache
    3. Predicts with best model(s) for the next trading day
    4. Outputs top-10 target list to reports/daily_logs/
"""

from __future__ import annotations

import argparse
import json
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.short_term_competition_train import (  # noqa: E402
    _add_moneyflow_features,
    _configure_data_dir,
    _merge_moneyflow,
    _read_moneyflow,
    _run_backtest,
)
from scripts.train_lgbm_wq_short import add_wq_alpha_features  # noqa: E402
from src import data_loader as dl  # noqa: E402
from src.eval import summarize, topk_spread  # noqa: E402
from src.features import compute_features, list_feature_cols  # noqa: E402
from src.labels import attach_labels, clip_outliers  # noqa: E402

DAILY_LOGS = PROJECT_ROOT / "reports" / "daily_logs"
CHECKPOINTS = PROJECT_ROOT / "checkpoints"

# Best models from exploration — ordered by priority for ensemble
BEST_MODELS = [
    {
        "tag": "explore_002_lgbm_lambdarank_selected_forward_hl30_train2025",
        "direction": "forward",
        "weight": 0.5,
    },
    {
        "tag": "lgbm_wq_06_selected_huber_forward_hl30",
        "direction": "forward",
        "weight": 0.3,
    },
]

# Additional diverse model (if checkpoint available)
EXTRA_MODEL = {
    "tag": "explore_004_lgbm_lambdarank_alpha_only_forward_hl30_train2024",
    "direction": "forward",
    "weight": 0.2,
}


def _next_trading_date(asof: pd.Timestamp) -> pd.Timestamp:
    cal = dl.load_trade_cal()
    future = sorted([d for d in cal if pd.Timestamp(d) > asof])
    if not future:
        raise ValueError(f"No trading date after {asof.date()}")
    return pd.Timestamp(future[0])


def rebuild_cache(args) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Rebuild panel, features, and labels from scratch."""
    _configure_data_dir(args.data_dir)
    args.cache_dir.mkdir(parents=True, exist_ok=True)

    panel_cache = args.cache_dir / f"panel_daily_{args.date}.parquet"
    wq_feats_cache = args.cache_dir / f"features_wq_daily_{args.date}.parquet"
    labels_cache = args.cache_dir / f"labels_nofuturelimit_daily_{args.date}.parquet"

    # Build panel
    print(f"[daily] building panel from {args.build_start} to {args.date}...")
    panel = dl.build_panel(dl.PanelBuildConfig(
        start=args.build_start,
        end=args.date,
        cache_path=panel_cache,
        include_metric=True,
    ))
    moneyflow = _read_moneyflow(args.data_dir, args.build_start, args.date)
    panel = _merge_moneyflow(panel, moneyflow)

    # Build features
    print(f"[daily] building WQ features...")
    base_feats = _add_moneyflow_features(compute_features(panel), panel)
    feats = add_wq_alpha_features(base_feats, panel)

    # Build labels (no future limit censor for honest evaluation)
    labels = clip_outliers(
        attach_labels(panel, drop_limit_tomorrow=False), "y", 0.005
    )

    panel.to_parquet(panel_cache, index=False)
    feats.to_parquet(wq_feats_cache, index=False)
    labels.to_parquet(labels_cache, index=False)
    print(f"[daily] cache rebuilt: panel={panel.shape}, feats={feats.shape}, labels={labels.shape}")
    return panel, feats, labels


def predict_model(tag: str, direction: str, feats: pd.DataFrame,
                  last_date: pd.Timestamp) -> pd.DataFrame | None:
    """Predict with a single model. Returns None if checkpoint missing."""
    ckpt_path = CHECKPOINTS / f"{tag}.pkl"
    if not ckpt_path.exists():
        print(f"[daily] WARNING: checkpoint not found: {ckpt_path}")
        return None

    ckpt = pickle.load(open(ckpt_path, "rb"))
    model = ckpt["model"]
    cols = ckpt.get("feature_cols", ckpt.get("row", {}).get("feature_cols", []))
    if isinstance(cols, str):
        cols = [cols]
    cols = [c for c in cols if c in feats.columns]
    if not cols:
        print(f"[daily] WARNING: no valid feature columns for {tag}")
        return None

    target = feats[feats["trade_date"] == last_date].copy()
    target = target.dropna(subset=cols, how="all").reset_index(drop=True)
    if target.empty:
        print(f"[daily] WARNING: no target-day rows for {tag}")
        return None

    X = target[cols].to_numpy(dtype=np.float32)
    X[~np.isfinite(X)] = np.nan
    raw = model.predict(X)
    score = -raw if direction == "inverse" else raw

    return pd.DataFrame({
        "ts_code": target["ts_code"].to_numpy(),
        "score": score.astype(float),
    })


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True, help="As-of date YYYY-MM-DD (latest data cutoff)")
    ap.add_argument("--data-dir", type=Path, default=Path("/home/lcc17/pan_sync_20260528/A股数据"))
    ap.add_argument("--cache-dir", type=Path, default=Path("/home/lcc17/pan_sync_20260528/shortterm_cache"))
    ap.add_argument("--build-start", default="2025-01-01")
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--num-threads", type=int, default=8)
    args = ap.parse_args()

    asof_date = pd.Timestamp(args.date)
    next_trade = _next_trading_date(asof_date)
    print(f"[daily] as-of: {asof_date.date()}  target: {next_trade.date()}")

    # Step 1: Rebuild cache
    panel, feats, labels = rebuild_cache(args)
    last_date = pd.Timestamp(sorted(feats["trade_date"].unique())[-1])
    print(f"[daily] last feature date: {last_date.date()}")

    # Step 2: Predict with each model
    basic = dl.load_basic()[["ts_code", "name", "industry"]]
    all_scores: dict[str, pd.DataFrame] = {}

    for m in BEST_MODELS:
        preds = predict_model(m["tag"], m["direction"], feats, last_date)
        if preds is not None:
            all_scores[m["tag"]] = preds

    # Try extra model
    extra = predict_model(EXTRA_MODEL["tag"], EXTRA_MODEL["direction"], feats, last_date)
    if extra is not None:
        all_scores[EXTRA_MODEL["tag"]] = extra

    if not all_scores:
        print("[daily] FATAL: no models could predict")
        sys.exit(1)

    # Step 3: Ensemble (rank-average)
    merged = None
    weights = {m["tag"]: m["weight"] for m in BEST_MODELS}
    weights[EXTRA_MODEL["tag"]] = EXTRA_MODEL["weight"]
    total_w = sum(weights.get(t, 0) for t in all_scores)

    for tag, preds in all_scores.items():
        w = weights.get(tag, 1.0) / total_w
        preds = preds.copy()
        preds["rank_pct"] = preds["score"].rank(pct=True)
        if merged is None:
            merged = preds[["ts_code"]].copy()
            merged["ensemble"] = preds["rank_pct"] * w
        else:
            merged["ensemble"] += preds["rank_pct"] * w

    # Add stock info and sort
    out = merged.merge(basic, on="ts_code", how="left")
    out = out.sort_values("ensemble", ascending=False).head(args.n)

    # Save
    DAILY_LOGS.mkdir(parents=True, exist_ok=True)
    target_str = next_trade.strftime("%Y%m%d")
    out.insert(0, "rank", range(1, args.n + 1))
    out.insert(1, "asof_date", asof_date.strftime("%Y-%m-%d"))
    out.insert(2, "target_trade_date", next_trade.strftime("%Y-%m-%d"))
    out.insert(3, "models", "+".join(all_scores.keys()))

    out_path = DAILY_LOGS / f"{target_str}_targets.csv"
    out.to_csv(out_path, index=False, encoding="utf-8-sig")

    print(f"\n[daily] === Top {args.n} for {next_trade.date()} ===")
    print(out[["rank", "ts_code", "name", "industry"]].to_string(index=False))
    print(f"\n[daily] saved: {out_path}")
    print(f"[daily] models used: {list(all_scores.keys())}")


if __name__ == "__main__":
    main()
