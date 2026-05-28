"""Standalone inference: load a saved checkpoint and write `{tag}_val_preds.parquet`.

Useful when training was interrupted and we only want to evaluate an existing
checkpoint on the validation window.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from tqdm import tqdm

from .data_loader import PROJECT_ROOT
from .features import list_feature_cols
from .dataset import WindowDataset, DayBatchSampler
from .train import _load_or_build_features_labels, build_model_from_checkpoint, _collect_preds


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    ap.add_argument("--model", required=True, choices=["mlp", "lstm", "transformer"])
    ap.add_argument("--val-start", default="2025-01-01")
    ap.add_argument("--val-end", default="2026-04-30")
    ap.add_argument("--batch-cap", type=int, default=2048)
    ap.add_argument("--window", type=int, default=20)
    ap.add_argument("--device", default=None,
                    help="Inference device. Defaults to cuda when available, else cpu.")
    args = ap.parse_args()
    device = args.device or ("cuda" if torch.cuda.is_available() else "cpu")

    ckpt_path = PROJECT_ROOT / "checkpoints" / f"{args.tag}.pt"
    ckpt = torch.load(ckpt_path, map_location="cpu", weights_only=False)
    feature_cols = ckpt["feature_cols"]

    feats, labels = _load_or_build_features_labels()
    val_ds = WindowDataset(feats, labels, feature_cols, args.window,
                           date_range=(args.val_start, args.val_end))
    val_sampler = DayBatchSampler(val_ds, shuffle=False, min_stocks=100)
    print(f"[infer] val days: {len(val_sampler)}  samples: {len(val_ds)}")

    model = build_model_from_checkpoint(
        ckpt, model_name=args.model, n_features=len(feature_cols), window=args.window
    )
    model.load_state_dict(ckpt["model_state"])
    model = model.to(device)
    model.eval()
    preds = _collect_preds(model, val_sampler, val_ds, device, batch_cap=args.batch_cap)
    out = PROJECT_ROOT / "checkpoints" / f"{args.tag}_val_preds.parquet"
    preds.to_parquet(out, index=False)
    print(f"[infer] wrote {out} shape={preds.shape}")

    from .eval import summarize
    print("[infer] summary:", summarize(preds))


if __name__ == "__main__":
    main()
