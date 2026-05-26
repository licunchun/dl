"""Compare model validation predictions and strategy NAV against baselines."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from .data_loader import PROJECT_ROOT
from .eval import summarize, topk_spread

CHECKPOINTS = PROJECT_ROOT / "checkpoints"


def compare_models(tags: list[str]) -> pd.DataFrame:
    rows = []
    for tag in tags:
        p = CHECKPOINTS / f"{tag}_val_preds.parquet"
        if not p.exists():
            print(f"[compare] skip missing {p}")
            continue
        preds = pd.read_parquet(p)
        s = summarize(preds)
        spread = topk_spread(preds, k=10)
        s["topk10_bp"] = float(spread["spread"].mean() * 1e4) if len(spread) else float("nan")
        rows.append({"tag": tag, **s})
    return pd.DataFrame(rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tags", nargs="+",
                    default=["mlp_mse", "lstm_ic", "transformer_mse", "transformer_ic"])
    args = ap.parse_args()
    tab = compare_models(args.tags)
    out = PROJECT_ROOT / "reports" / "compare_metrics.csv"
    tab.to_csv(out, index=False)
    print(tab.to_string(index=False))
    print(f"[compare] wrote {out}")


if __name__ == "__main__":
    main()
