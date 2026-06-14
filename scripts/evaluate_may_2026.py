"""Evaluate saved checkpoints on the synced May 2026 data.

The May data currently ends at 2026-05-28.  Labels are next-trading-day
returns, so the latest verifiable prediction date is 2026-05-27.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import torch

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
from src import data_loader as dl  # noqa: E402
from src.dataset import DayBatchSampler, WindowDataset  # noqa: E402
from src.eval import summarize, topk_spread  # noqa: E402
from src.features import compute_features, list_feature_cols  # noqa: E402
from src.labels import attach_labels, clip_outliers  # noqa: E402
from src.train import _collect_preds, build_model_from_checkpoint  # noqa: E402


def _load_or_build(args) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    _configure_data_dir(args.data_dir)
    args.cache_dir.mkdir(parents=True, exist_ok=True)
    panel_cache = args.cache_dir / f"may_panel_{args.build_start}_{args.data_end}.parquet"
    feats_cache = args.cache_dir / f"may_features_{args.build_start}_{args.data_end}.parquet"
    label_suffix = "nofuturelimit" if args.no_future_limit_censor else "default"
    labels_cache = args.cache_dir / f"may_labels_{label_suffix}_{args.build_start}_{args.data_end}.parquet"

    if panel_cache.exists() and feats_cache.exists() and labels_cache.exists() and not args.rebuild_cache:
        return (
            pd.read_parquet(panel_cache),
            pd.read_parquet(feats_cache),
            pd.read_parquet(labels_cache),
        )

    panel = dl.build_panel(dl.PanelBuildConfig(
        start=args.build_start,
        end=args.data_end,
        cache_path=panel_cache,
        include_metric=True,
    ))
    moneyflow = _read_moneyflow(args.data_dir, args.build_start, args.data_end)
    panel = _merge_moneyflow(panel, moneyflow)
    feats = _add_moneyflow_features(compute_features(panel), panel)
    labels = clip_outliers(
        attach_labels(panel, drop_limit_tomorrow=not args.no_future_limit_censor),
        "y",
        0.005,
    )

    panel.to_parquet(panel_cache, index=False)
    feats.to_parquet(feats_cache, index=False)
    labels.to_parquet(labels_cache, index=False)
    return panel, feats, labels


def _evaluate_tag(args, tag: str, panel: pd.DataFrame, feats: pd.DataFrame, labels: pd.DataFrame) -> dict:
    ckpt_path = PROJECT_ROOT / "checkpoints" / f"{tag}.pt"
    ckpt = torch.load(ckpt_path, map_location="cpu", weights_only=False)
    feature_cols = ckpt["feature_cols"]
    missing = [c for c in feature_cols if c not in feats.columns]
    if missing:
        raise ValueError(f"{tag}: missing feature columns: {missing}")

    window = int(ckpt.get("cfg", {}).get("window", args.window))
    ds = WindowDataset(
        feats,
        labels,
        feature_cols,
        window=window,
        date_range=(args.warmup_start, args.val_end),
    )
    sampler = DayBatchSampler(ds, shuffle=False, min_stocks=100)
    model_name = ckpt.get("cfg", {}).get("model") or args.model
    model = build_model_from_checkpoint(ckpt, model_name=model_name, n_features=len(feature_cols), window=window)
    model.load_state_dict(ckpt["model_state"])
    model = model.to(args.device)

    preds = _collect_preds(model, sampler, ds, args.device, batch_cap=args.batch_cap)
    if preds.empty:
        raise ValueError(
            f"{tag}: no predictions were produced. "
            f"Try an earlier --build-start/--warmup-start for window={window}."
        )
    preds = preds[
        (preds["trade_date"] >= pd.Timestamp(args.val_start))
        & (preds["trade_date"] <= pd.Timestamp(args.val_end))
    ].reset_index(drop=True)

    out_dir = PROJECT_ROOT / "reports" / "may_2026_validation"
    out_dir.mkdir(parents=True, exist_ok=True)
    preds_path = out_dir / f"{tag}_may_preds.parquet"
    preds.to_parquet(preds_path, index=False)

    metrics = summarize(preds)
    spread = topk_spread(preds, k=args.topk)
    metrics[f"top{args.topk}_spread_bp"] = float(spread["spread"].mean() * 1e4) if len(spread) else float("nan")
    bt_stats = _run_backtest(preds, panel, out_dir / f"backtest_{tag}")
    row = {
        "tag": tag,
        "model": model_name,
        "window": window,
        "samples": int(len(preds)),
        "preds": str(preds_path.relative_to(PROJECT_ROOT)),
        **metrics,
        **{f"bt_{k}": v for k, v in bt_stats.items()},
    }
    return row


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", type=Path, default=Path("/home/lcc17/pan_sync_20260528/A股数据"))
    ap.add_argument("--cache-dir", type=Path, default=Path("/home/lcc17/pan_sync_20260528/may_eval_cache"))
    ap.add_argument("--build-start", default="2026-01-01")
    ap.add_argument("--warmup-start", default="2026-01-02")
    ap.add_argument("--val-start", default="2026-05-06")
    ap.add_argument("--val-end", default="2026-05-27")
    ap.add_argument("--data-end", default="2026-05-28")
    ap.add_argument("--tags", nargs="+", default=[
        "lstm_ic_large",
        "lstm_ic_h384_l2_w20",
        "lstm_ic_h384_l3_w20",
        "lstm_ic_h256_l3_w40",
        "lstm_ic_final_h384_l2_w20",
    ])
    ap.add_argument("--model", default="lstm")
    ap.add_argument("--window", type=int, default=20)
    ap.add_argument("--batch-cap", type=int, default=8192)
    ap.add_argument("--topk", type=int, default=10)
    ap.add_argument("--rebuild-cache", action="store_true")
    ap.add_argument("--no-future-limit-censor", action="store_true",
                    help="Do not drop rows using next-day limit-move information; use for leakage-free evaluation.")
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    args = ap.parse_args()

    panel, feats, labels = _load_or_build(args)
    rows = []
    for tag in args.tags:
        print(f"[may] evaluating {tag}", flush=True)
        row = _evaluate_tag(args, tag, panel, feats, labels)
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)

    out_dir = PROJECT_ROOT / "reports" / "may_2026_validation"
    df = pd.DataFrame(rows)
    df.to_csv(out_dir / "summary.csv", index=False)
    (out_dir / "summary.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    print(df.to_string(index=False))


if __name__ == "__main__":
    main()
