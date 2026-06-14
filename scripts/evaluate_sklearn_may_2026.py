"""Evaluate a saved sklearn baseline on the synced May 2026 data."""

from __future__ import annotations

import argparse
import json
import pickle
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.evaluate_may_2026 import _load_or_build  # noqa: E402
from scripts.short_term_competition_train import _run_backtest  # noqa: E402
from scripts.train_sklearn_baseline import collect_sklearn_preds  # noqa: E402
from src.dataset import DayBatchSampler, WindowDataset  # noqa: E402
from src.eval import summarize, topk_spread  # noqa: E402
from src.train import CHECKPOINTS  # noqa: E402


def evaluate_tag(args, tag: str) -> dict:
    model_path = CHECKPOINTS / f"{tag}.pkl"
    with model_path.open("rb") as fh:
        payload = pickle.load(fh)
    model = payload["model"]
    feature_cols = payload["feature_cols"]
    cfg = payload.get("cfg", {})
    window = int(cfg.get("window", args.window))

    panel, feats, labels = _load_or_build(args)
    missing = [c for c in feature_cols if c not in feats.columns]
    if missing:
        raise ValueError(f"{tag}: missing feature columns: {missing}")

    ds = WindowDataset(
        feats,
        labels,
        feature_cols,
        window=window,
        date_range=(args.warmup_start, args.val_end),
    )
    # Keep the same day eligibility convention as neural May evaluation.
    sampler = DayBatchSampler(ds, shuffle=False, min_stocks=args.min_stocks_per_day)
    if len(sampler) == 0:
        raise ValueError(f"{tag}: no May day-batches available")

    preds = collect_sklearn_preds(
        model,
        ds,
        batch_cap=args.batch_cap,
        min_stocks=args.min_stocks_per_day,
    )
    preds = preds[
        (preds["trade_date"] >= pd.Timestamp(args.val_start))
        & (preds["trade_date"] <= pd.Timestamp(args.val_end))
    ].reset_index(drop=True)

    out_dir = ROOT / "reports" / "may_2026_validation"
    out_dir.mkdir(parents=True, exist_ok=True)
    preds_path = out_dir / f"{tag}_may_preds.parquet"
    preds.to_parquet(preds_path, index=False)

    metrics = summarize(preds)
    spread = topk_spread(preds, k=args.topk)
    metrics[f"top{args.topk}_spread_bp"] = float(spread["spread"].mean() * 1e4) if len(spread) else float("nan")
    bt_stats = _run_backtest(preds, panel, out_dir / f"backtest_{tag}")
    return {
        "tag": tag,
        "model": "sklearn_sgd",
        "window": window,
        "samples": int(len(preds)),
        "preds": str(preds_path.relative_to(ROOT)),
        **metrics,
        **{f"bt_{k}": v for k, v in bt_stats.items()},
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", type=Path, default=Path("/home/lcc17/pan_sync_20260528/A股数据"))
    ap.add_argument("--cache-dir", type=Path, default=Path("/home/lcc17/pan_sync_20260528/may_eval_cache"))
    ap.add_argument("--build-start", default="2026-01-01")
    ap.add_argument("--warmup-start", default="2026-01-02")
    ap.add_argument("--val-start", default="2026-05-06")
    ap.add_argument("--val-end", default="2026-05-27")
    ap.add_argument("--data-end", default="2026-05-28")
    ap.add_argument("--tags", nargs="+", default=["sklearn_sgd_recency_w20"])
    ap.add_argument("--window", type=int, default=20)
    ap.add_argument("--batch-cap", type=int, default=8192)
    ap.add_argument("--min-stocks-per-day", type=int, default=100)
    ap.add_argument("--topk", type=int, default=10)
    ap.add_argument("--rebuild-cache", action="store_true")
    ap.add_argument("--no-future-limit-censor", action="store_true")
    args = ap.parse_args()

    rows = []
    for tag in args.tags:
        print(f"[may-sklearn] evaluating {tag}", flush=True)
        row = evaluate_tag(args, tag)
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)

    out_dir = ROOT / "reports" / "may_2026_validation"
    df = pd.DataFrame(rows)
    out = out_dir / "summary_sklearn.csv"
    df.to_csv(out, index=False)
    (out_dir / "summary_sklearn.json").write_text(
        json.dumps(rows, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(df.to_string(index=False))
    print(f"[may-sklearn] wrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
