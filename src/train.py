"""Training loop.

Two loss options:

    --loss mse      vanilla regression
    --loss ic       per-batch IC loss: 1 - pearson(pred, y) where each batch
                    is one trading day (cross-section). Optimises the metric
                    that actually drives the top-N selection strategy.

Cycling is one pass per epoch over trading days (thanks to DayBatchSampler).
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, asdict
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from torch.utils.data import DataLoader
from tqdm import tqdm

from .data_loader import PROJECT_ROOT, load_panel
from .features import compute_features, list_feature_cols
from .labels import attach_labels, clip_outliers
from .dataset import WindowDataset, DayBatchSampler
from .models import MLP, LSTMModel, TransformerModel
from .eval import summarize, topk_spread

CHECKPOINTS = PROJECT_ROOT / "checkpoints"
CHECKPOINTS.mkdir(exist_ok=True)
FEATURE_CACHE = PROJECT_ROOT / "data" / "features.parquet"
LABEL_CACHE = PROJECT_ROOT / "data" / "labels.parquet"


def _load_or_build_features_labels(rebuild: bool = False):
    if not rebuild and FEATURE_CACHE.exists() and LABEL_CACHE.exists():
        feats = pd.read_parquet(FEATURE_CACHE)
        labels = pd.read_parquet(LABEL_CACHE)
        return feats, labels
    panel = load_panel()
    print(f"[cache] building features from panel {panel.shape}")
    feats = compute_features(panel)
    labels = clip_outliers(attach_labels(panel), "y", 0.005)
    feats.to_parquet(FEATURE_CACHE, index=False)
    labels.to_parquet(LABEL_CACHE, index=False)
    print(f"[cache] wrote {FEATURE_CACHE} and {LABEL_CACHE}")
    return feats, labels


@dataclass
class TrainConfig:
    model: str = "transformer"
    loss: str = "ic"
    window: int = 20
    train_range: tuple[str, str] = ("2019-01-01", "2024-12-31")
    val_range: tuple[str, str] = ("2025-01-01", "2026-04-30")
    epochs: int = 8
    lr: float = 1e-3
    weight_decay: float = 1e-5
    device: str = "cuda" if torch.cuda.is_available() else "cpu"
    seed: int = 42
    min_stocks_per_day: int = 100
    hidden: int = 0
    layers: int = 0
    dropout: float = 0.1
    d_model: int = 0
    heads: int = 0
    amp: bool = False
    half_life_days: float = 0.0
    min_date_weight: float = 0.25


def _collate(batch):
    Xs, ys, sidx, dates = zip(*batch)
    X = torch.stack(Xs)
    y = torch.stack(ys)
    s = torch.tensor(sidx, dtype=torch.int64)
    d = torch.tensor(dates, dtype=torch.int64)
    return X, y, s, d


def build_model(
    name: str,
    n_features: int,
    window: int,
    *,
    hidden: int | None = None,
    layers: int | None = None,
    dropout: float | None = None,
    d_model: int | None = None,
    heads: int | None = None,
) -> torch.nn.Module:
    dropout = 0.1 if dropout is None else dropout
    if name == "mlp":
        kwargs = {"dropout": dropout}
        if hidden:
            kwargs["hidden"] = hidden
        if layers:
            kwargs["n_layers"] = layers
        return MLP(window=window, n_features=n_features, **kwargs)
    if name == "lstm":
        kwargs = {"dropout": dropout}
        if hidden:
            kwargs["hidden"] = hidden
        if layers:
            kwargs["n_layers"] = layers
        return LSTMModel(n_features=n_features, **kwargs)
    if name == "transformer":
        kwargs = {"dropout": dropout}
        if d_model:
            kwargs["d_model"] = d_model
        if heads:
            kwargs["n_heads"] = heads
        if layers:
            kwargs["n_layers"] = layers
        return TransformerModel(n_features=n_features, window=window, **kwargs)
    raise ValueError(name)


def build_model_from_checkpoint(
    ckpt: dict,
    model_name: str | None = None,
    *,
    n_features: int | None = None,
    window: int | None = None,
) -> torch.nn.Module:
    """Restore model capacity from new checkpoints, with old-checkpoint fallback."""
    cfg = ckpt.get("cfg", {})
    name = model_name or cfg.get("model")
    if not name:
        raise ValueError("model name is required for checkpoints without cfg['model']")
    feature_cols = ckpt.get("feature_cols", [])
    n_features = n_features or len(feature_cols)
    window = window or int(cfg.get("window", 20))
    return build_model(
        name,
        n_features=n_features,
        window=window,
        hidden=cfg.get("hidden") or None,
        layers=cfg.get("layers") or None,
        dropout=cfg.get("dropout", 0.1),
        d_model=cfg.get("d_model") or None,
        heads=cfg.get("heads") or None,
    )


def ic_loss(pred: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
    """1 - Pearson(pred, target).  Nothing to do on a singleton batch."""
    if pred.numel() < 2:
        return pred.new_tensor(0.0)
    pm = pred - pred.mean()
    tm = target - target.mean()
    num = (pm * tm).sum()
    den = torch.sqrt((pm * pm).sum() * (tm * tm).sum() + 1e-12)
    return 1.0 - num / den


def _normalise_batch_cap(batch_cap: int | None) -> int | None:
    return None if batch_cap is None or batch_cap <= 0 else batch_cap


def date_recency_weight(
    dates: torch.Tensor,
    *,
    train_end: str | pd.Timestamp,
    half_life_days: float,
    min_weight: float,
    device: str | torch.device | None = None,
) -> torch.Tensor:
    """Return one scalar recency weight for a day-batch.

    ``dates`` are epoch-day integers emitted by ``WindowDataset``.  A disabled
    half-life returns 1.0 so existing training commands are unchanged.
    """
    if half_life_days <= 0:
        return torch.tensor(1.0, dtype=torch.float32, device=device)
    if not 0.0 <= min_weight <= 1.0:
        raise ValueError("min_weight must be in [0, 1]")
    end_day = pd.Timestamp(train_end).to_datetime64().astype("datetime64[D]").astype("int64")
    mean_day = dates.float().mean()
    age = torch.clamp(torch.as_tensor(float(end_day), device=dates.device) - mean_day, min=0.0)
    decay = torch.pow(torch.tensor(0.5, dtype=torch.float32, device=dates.device), age / float(half_life_days))
    weight = torch.clamp(decay, min=float(min_weight), max=1.0)
    if device is not None:
        weight = weight.to(device)
    return weight


def _run_epoch(model, sampler, ds, optim, device, loss_name: str, train: bool,
               batch_cap: int | None = None, scaler=None, amp: bool = False,
               train_end: str | None = None, half_life_days: float = 0.0,
               min_date_weight: float = 0.25):
    model.train(train)
    losses: list[float] = []
    weighted_losses: list[float] = []
    weights: list[float] = []
    batch_cap = _normalise_batch_cap(batch_cap)
    for idxs in tqdm(sampler, desc=("train" if train else "val"), leave=False):
        if batch_cap and len(idxs) > batch_cap:
            idxs = np.random.choice(idxs, size=batch_cap, replace=False).tolist()
        xs, ys, _, dates = _collate([ds[i] for i in idxs])
        xs = xs.to(device, non_blocking=True)
        ys = ys.to(device, non_blocking=True)
        dates = dates.to(device, non_blocking=True)
        with torch.set_grad_enabled(train):
            with torch.autocast(device_type="cuda", enabled=amp):
                pred = model(xs)
                if loss_name == "ic":
                    loss = ic_loss(pred, ys)
                else:
                    loss = torch.nn.functional.mse_loss(pred, ys)
                weight = date_recency_weight(
                    dates,
                    train_end=train_end or pd.Timestamp.max,
                    half_life_days=half_life_days if train else 0.0,
                    min_weight=min_date_weight,
                    device=device,
                )
                opt_loss = loss * weight
        if train:
            optim.zero_grad()
            if scaler is not None and amp:
                scaler.scale(opt_loss).backward()
                scaler.unscale_(optim)
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                scaler.step(optim)
                scaler.update()
            else:
                opt_loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                optim.step()
        losses.append(float(loss.item()))
        weighted_losses.append(float(opt_loss.item()))
        weights.append(float(weight.item()))
    if not losses:
        return {"loss": float("nan"), "weighted_loss": float("nan"), "mean_weight": float("nan")}
    return {
        "loss": float(np.mean(losses)),
        "weighted_loss": float(np.mean(weighted_losses)),
        "mean_weight": float(np.mean(weights)),
    }


def _collect_preds(model, sampler, ds, device, batch_cap: int | None = None) -> pd.DataFrame:
    model.eval()
    rows: list[dict] = []
    batch_cap = _normalise_batch_cap(batch_cap)
    with torch.no_grad():
        for idxs in sampler:
            if batch_cap and len(idxs) > batch_cap:
                idxs = np.random.choice(idxs, size=batch_cap, replace=False).tolist()
            xs, ys, sidx, dates = _collate([ds[i] for i in idxs])
            xs = xs.to(device, non_blocking=True)
            pred = model(xs).detach().cpu().numpy()
            for p, yv, si, dt in zip(pred, ys.numpy(), sidx, dates.numpy()):
                rows.append({
                    "ts_code": ds.ts_codes[int(si)],
                    "trade_date": pd.Timestamp(int(dt), unit="D"),
                    "y_pred": float(p),
                    "y_true": float(yv),
                })
    return pd.DataFrame(rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", choices=["mlp", "lstm", "transformer"], default="transformer")
    ap.add_argument("--loss", choices=["mse", "ic"], default="ic")
    ap.add_argument("--epochs", type=int, default=8)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--window", type=int, default=20)
    ap.add_argument("--train-start", default="2019-01-01")
    ap.add_argument("--train-end", default="2024-12-31")
    ap.add_argument("--val-start", default="2025-01-01")
    ap.add_argument("--val-end", default="2026-04-30")
    ap.add_argument("--tag", default="")
    ap.add_argument("--rebuild-cache", action="store_true",
                    help="Rebuild data/features.parquet and data/labels.parquet")
    ap.add_argument("--batch-cap", type=int, default=8192,
                    help="Max samples per day-batch; <=0 means full cross-section.")
    ap.add_argument("--hidden", type=int, default=0,
                    help="MLP/LSTM hidden size override.")
    ap.add_argument("--layers", type=int, default=0,
                    help="MLP/LSTM/Transformer layer count override.")
    ap.add_argument("--dropout", type=float, default=0.1)
    ap.add_argument("--d-model", type=int, default=0,
                    help="Transformer d_model override.")
    ap.add_argument("--heads", type=int, default=0,
                    help="Transformer attention head count override.")
    ap.add_argument("--amp", action="store_true",
                    help="Use CUDA automatic mixed precision.")
    ap.add_argument("--half-life-days", type=float, default=0.0,
                    help="Exponential recency half-life for training day loss; <=0 disables weighting.")
    ap.add_argument("--min-date-weight", type=float, default=0.25,
                    help="Floor for old training-day weights when recency weighting is enabled.")
    args = ap.parse_args()
    if not 0.0 <= args.min_date_weight <= 1.0:
        raise ValueError("--min-date-weight must be in [0, 1]")

    cfg = TrainConfig(
        model=args.model, loss=args.loss,
        window=args.window, epochs=args.epochs, lr=args.lr,
        train_range=(args.train_start, args.train_end),
        val_range=(args.val_start, args.val_end),
        hidden=args.hidden,
        layers=args.layers,
        dropout=args.dropout,
        d_model=args.d_model,
        heads=args.heads,
        amp=args.amp,
        half_life_days=args.half_life_days,
        min_date_weight=args.min_date_weight,
    )
    cfg.amp = bool(cfg.amp and cfg.device.startswith("cuda"))

    torch.manual_seed(cfg.seed)
    np.random.seed(cfg.seed)

    print("[train] loading features / labels (cache if available)...")
    feats, labels = _load_or_build_features_labels(rebuild=args.rebuild_cache)
    if args.epochs == 0:
        print("[train] epochs=0; cache rebuild/load complete, skipping training.")
        return
    feature_cols = list_feature_cols(feats)
    print(f"[train] features ({len(feature_cols)}): {feature_cols}")

    train_ds = WindowDataset(feats, labels, feature_cols, cfg.window,
                             date_range=cfg.train_range)
    val_ds = WindowDataset(feats, labels, feature_cols, cfg.window,
                           date_range=cfg.val_range)
    print(f"[train] train samples: {len(train_ds)}  val samples: {len(val_ds)}")

    train_sampler = DayBatchSampler(train_ds, shuffle=True,
                                    min_stocks=cfg.min_stocks_per_day)
    val_sampler = DayBatchSampler(val_ds, shuffle=False,
                                  min_stocks=cfg.min_stocks_per_day)

    model = build_model(
        cfg.model,
        n_features=len(feature_cols),
        window=cfg.window,
        hidden=cfg.hidden or None,
        layers=cfg.layers or None,
        dropout=cfg.dropout,
        d_model=cfg.d_model or None,
        heads=cfg.heads or None,
    )
    model = model.to(cfg.device)
    optim = torch.optim.AdamW(model.parameters(), lr=cfg.lr, weight_decay=cfg.weight_decay)
    scaler = torch.cuda.amp.GradScaler(enabled=cfg.amp)
    n_params = sum(p.numel() for p in model.parameters())
    print(f"[train] model params: {n_params:,}  device={cfg.device} amp={cfg.amp}")

    tag = args.tag or f"{cfg.model}_{cfg.loss}"
    best_ic = -float("inf")
    best_path = CHECKPOINTS / f"{tag}.pt"
    log: list[dict] = []
    for epoch in range(cfg.epochs):
        tr = _run_epoch(model, train_sampler, train_ds, optim, cfg.device, cfg.loss,
                        train=True, batch_cap=args.batch_cap, scaler=scaler, amp=cfg.amp,
                        train_end=cfg.train_range[1], half_life_days=cfg.half_life_days,
                        min_date_weight=cfg.min_date_weight)
        vl = _run_epoch(model, val_sampler, val_ds, optim, cfg.device, cfg.loss,
                        train=False, batch_cap=args.batch_cap, amp=cfg.amp)
        preds = _collect_preds(model, val_sampler, val_ds, cfg.device,
                               batch_cap=args.batch_cap)
        m = summarize(preds)
        print(f"[ep {epoch}] train_loss={tr['loss']:.4f} weighted={tr['weighted_loss']:.4f} "
              f"mean_w={tr['mean_weight']:.3f} val_loss={vl['loss']:.4f} "
              f"IC={m['ic']:.4f} RankIC={m['rank_ic']:.4f} "
              f"ICIR={m['icir']:.3f} DirAcc={m['diracc']:.3f}")
        log.append({
            "epoch": epoch,
            "train_loss": tr["loss"],
            "train_weighted_loss": tr["weighted_loss"],
            "train_mean_weight": tr["mean_weight"],
            "val_loss": vl["loss"],
            **m,
        })
        if m["ic"] > best_ic:
            best_ic = m["ic"]
            torch.save({
                "model_state": model.state_dict(),
                "cfg": asdict(cfg),
                "feature_cols": feature_cols,
            }, best_path)

    preds_path = CHECKPOINTS / f"{tag}_val_preds.parquet"
    preds = _collect_preds(model, val_sampler, val_ds, cfg.device,
                           batch_cap=args.batch_cap)
    preds.to_parquet(preds_path, index=False)
    (CHECKPOINTS / f"{tag}_train_log.json").write_text(json.dumps(log, indent=2))
    print(f"[train] saved best to {best_path}, preds to {preds_path}")


if __name__ == "__main__":
    main()
