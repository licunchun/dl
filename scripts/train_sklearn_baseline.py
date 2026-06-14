"""Train a leakage-aligned sklearn linear baseline.

The baseline uses the same causal ``WindowDataset`` as neural models, flattens
each stock window, and writes ``checkpoints/<tag>_val_preds.parquet`` so
``src.compare`` and ``src.backtest`` can evaluate it without special casing.
"""

from __future__ import annotations

import argparse
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from sklearn.linear_model import SGDRegressor
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.data_loader import PROJECT_ROOT
from src.dataset import DayBatchSampler, WindowDataset
from src.features import list_feature_cols
from src.train import CHECKPOINTS, _collate, _load_or_build_features_labels, date_recency_weight


def _load_training_frames(args) -> tuple[pd.DataFrame, pd.DataFrame]:
    if args.data_dir is None:
        return _load_or_build_features_labels(rebuild=args.rebuild_cache)

    from scripts.evaluate_may_2026 import _load_or_build

    panel, feats, labels = _load_or_build(args)
    return feats, labels


def _flatten_batch(ds: WindowDataset, idxs: list[int]) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[str]]:
    xs, ys, sidx, dates = _collate([ds[i] for i in idxs])
    codes = [ds.ts_codes[int(si)] for si in sidx]
    return xs.numpy().reshape(len(idxs), -1), ys.numpy(), dates.numpy(), codes


def _iter_day_batches(
    ds: WindowDataset,
    *,
    shuffle: bool,
    min_stocks: int,
    batch_cap: int | None,
):
    sampler = DayBatchSampler(ds, shuffle=shuffle, min_stocks=min_stocks)
    for idxs in sampler:
        if batch_cap and batch_cap > 0 and len(idxs) > batch_cap:
            idxs = np.random.choice(idxs, size=batch_cap, replace=False).tolist()
        yield idxs


def train_sgd_baseline(
    train_ds: WindowDataset,
    *,
    train_end: str,
    epochs: int,
    lr: float,
    alpha: float,
    batch_cap: int | None,
    min_stocks: int,
    half_life_days: float,
    min_date_weight: float,
    seed: int,
):
    scaler = StandardScaler()
    reg = SGDRegressor(
        loss="squared_error",
        penalty="elasticnet",
        alpha=alpha,
        l1_ratio=0.15,
        learning_rate="constant",
        eta0=lr,
        random_state=seed,
        max_iter=1,
        tol=None,
        warm_start=True,
    )

    for idxs in _iter_day_batches(
        train_ds, shuffle=False, min_stocks=min_stocks, batch_cap=batch_cap
    ):
        x, _, dates, _ = _flatten_batch(train_ds, idxs)
        weight = float(date_recency_weight(
            dates=torch.tensor(dates),
            train_end=train_end,
            half_life_days=half_life_days,
            min_weight=min_date_weight,
        ))
        scaler.partial_fit(x, sample_weight=np.full(x.shape[0], weight, dtype=np.float32))

    fitted = False
    for epoch in range(epochs):
        losses: list[float] = []
        for idxs in _iter_day_batches(
            train_ds, shuffle=True, min_stocks=min_stocks, batch_cap=batch_cap
        ):
            x, y, dates, _ = _flatten_batch(train_ds, idxs)
            weight = float(date_recency_weight(
                dates=torch.tensor(dates),
                train_end=train_end,
                half_life_days=half_life_days,
                min_weight=min_date_weight,
            ))
            sample_weight = np.full(len(y), weight, dtype=np.float32)
            x_scaled = scaler.transform(x)
            if not fitted:
                reg.partial_fit(x_scaled, y, sample_weight=sample_weight)
                fitted = True
            else:
                reg.partial_fit(x_scaled, y, sample_weight=sample_weight)
            pred = reg.predict(x_scaled)
            losses.append(float(np.mean((pred - y) ** 2)))
        print(f"[sklearn ep {epoch}] train_mse={np.mean(losses):.6f}")
    return {"scaler": scaler, "regressor": reg}


def collect_sklearn_preds(
    model,
    val_ds: WindowDataset,
    *,
    batch_cap: int | None,
    min_stocks: int,
) -> pd.DataFrame:
    rows: list[dict] = []
    for idxs in _iter_day_batches(val_ds, shuffle=False, min_stocks=min_stocks, batch_cap=batch_cap):
        x, y, dates, codes = _flatten_batch(val_ds, idxs)
        pred = model["regressor"].predict(model["scaler"].transform(x))
        for code, dt, yv, pv in zip(codes, dates, y, pred):
            rows.append({
                "ts_code": code,
                "trade_date": pd.Timestamp(int(dt), unit="D"),
                "y_pred": float(pv),
                "y_true": float(yv),
            })
    return pd.DataFrame(rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="sklearn_sgd_linear")
    ap.add_argument("--data-dir", type=Path, default=None)
    ap.add_argument("--cache-dir", type=Path, default=Path("/home/lcc17/pan_sync_20260528/may_eval_cache"))
    ap.add_argument("--build-start", default="2024-01-01")
    ap.add_argument("--data-end", default="2026-05-28")
    ap.add_argument("--window", type=int, default=20)
    ap.add_argument("--train-start", default="2019-01-01")
    ap.add_argument("--train-end", default="2024-12-31")
    ap.add_argument("--val-start", default="2025-01-01")
    ap.add_argument("--val-end", default="2026-04-30")
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--lr", type=float, default=1e-4)
    ap.add_argument("--alpha", type=float, default=1e-5)
    ap.add_argument("--batch-cap", type=int, default=8192)
    ap.add_argument("--min-stocks-per-day", type=int, default=100)
    ap.add_argument("--half-life-days", type=float, default=0.0)
    ap.add_argument("--min-date-weight", type=float, default=0.25)
    ap.add_argument("--rebuild-cache", action="store_true")
    ap.add_argument("--no-future-limit-censor", action="store_true")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    if not 0.0 <= args.min_date_weight <= 1.0:
        raise ValueError("--min-date-weight must be in [0, 1]")

    np.random.seed(args.seed)
    feats, labels = _load_training_frames(args)
    feature_cols = list_feature_cols(feats)
    train_ds = WindowDataset(
        feats, labels, feature_cols, window=args.window,
        date_range=(args.train_start, args.train_end),
    )
    val_ds = WindowDataset(
        feats, labels, feature_cols, window=args.window,
        date_range=(args.val_start, args.val_end),
    )
    print(f"[sklearn] features={len(feature_cols)} train={len(train_ds)} val={len(val_ds)}")

    model = train_sgd_baseline(
        train_ds,
        train_end=args.train_end,
        epochs=args.epochs,
        lr=args.lr,
        alpha=args.alpha,
        batch_cap=args.batch_cap,
        min_stocks=args.min_stocks_per_day,
        half_life_days=args.half_life_days,
        min_date_weight=args.min_date_weight,
        seed=args.seed,
    )
    preds = collect_sklearn_preds(
        model, val_ds, batch_cap=args.batch_cap, min_stocks=args.min_stocks_per_day
    )

    CHECKPOINTS.mkdir(exist_ok=True)
    preds_path = CHECKPOINTS / f"{args.tag}_val_preds.parquet"
    model_path = CHECKPOINTS / f"{args.tag}.pkl"
    preds.to_parquet(preds_path, index=False)
    with model_path.open("wb") as fh:
        pickle.dump({
            "model": model,
            "feature_cols": feature_cols,
            "cfg": vars(args),
        }, fh)
    print(f"[sklearn] wrote {preds_path.relative_to(PROJECT_ROOT)}")
    print(f"[sklearn] wrote {model_path.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
