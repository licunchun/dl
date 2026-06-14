"""Generate daily targets for forward or inverse checkpoint-ranking strategies."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import torch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src import data_loader as dl  # noqa: E402
from src.dataset import WindowDataset  # noqa: E402
from src.features import compute_features  # noqa: E402
from src.labels import attach_labels  # noqa: E402
from src.train import build_model_from_checkpoint  # noqa: E402

DAILY_LOGS = PROJECT_ROOT / "reports" / "daily_logs"


def _configure_data_dir(data_dir: Path) -> None:
    dl.DATA_DIR = data_dir
    dl.PANEL_CACHE = data_dir / "panel.parquet"
    dl.load_basic.cache_clear()
    dl.load_trade_cal.cache_clear()


def _next_trading_date(asof_date: pd.Timestamp) -> pd.Timestamp:
    cal = dl.load_trade_cal()
    future = cal[cal > asof_date]
    if len(future) == 0:
        raise ValueError(f"No trading date after {asof_date.date()}")
    return pd.Timestamp(future[0])


def _load_panel(args) -> pd.DataFrame:
    cache_dir = args.cache_dir
    cache_dir.mkdir(parents=True, exist_ok=True)
    p = cache_dir / f"strategy_panel_{args.start}_{args.asof_date}.parquet"
    if p.exists() and not args.rebuild_cache:
        return pd.read_parquet(p)
    panel = dl.build_panel(dl.PanelBuildConfig(
        start=args.start,
        end=args.asof_date,
        cache_path=p,
        include_metric=True,
    ))
    return panel


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", type=Path, required=True)
    ap.add_argument("--cache-dir", type=Path, default=Path("/home/lcc17/pan_sync_20260528/strategy_cache"))
    ap.add_argument("--start", default="2026-01-01",
                    help="Feature warmup start. 2026-01-01 is enough for rolling windows used here.")
    ap.add_argument("--asof-date", required=True)
    ap.add_argument("--target-date", default=None)
    ap.add_argument("--model", default="lstm", choices=["mlp", "lstm", "transformer"])
    ap.add_argument("--tag", required=True)
    ap.add_argument("--direction", choices=["forward", "inverse"], default="forward")
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--rebuild-cache", action="store_true")
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    args = ap.parse_args()

    _configure_data_dir(args.data_dir)
    asof = pd.Timestamp(args.asof_date)
    target = pd.Timestamp(args.target_date) if args.target_date else _next_trading_date(asof)
    panel = _load_panel(args)
    panel = panel[panel["trade_date"] <= asof].copy()
    last_day = panel[panel["trade_date"] == asof].copy()
    if last_day.empty:
        raise ValueError(f"No panel rows for as-of date {asof.date()}")

    synth = last_day.copy()
    synth["trade_date"] = target
    synth["pct_chg"] = 0.0
    target_panel = pd.concat([panel, synth], ignore_index=True)

    ckpt_path = PROJECT_ROOT / "checkpoints" / f"{args.tag}.pt"
    ckpt = torch.load(ckpt_path, map_location=args.device, weights_only=False)
    feature_cols = ckpt["feature_cols"]
    feats = compute_features(target_panel)
    missing = [c for c in feature_cols if c not in feats.columns]
    if missing:
        raise ValueError(f"Checkpoint feature columns missing from current data: {missing}")

    labels = attach_labels(target_panel)
    window = int(ckpt.get("cfg", {}).get("window", 20))
    ds = WindowDataset(
        feats,
        labels,
        feature_cols,
        window=window,
        date_range=(str(asof - pd.Timedelta(days=180)), str(target)),
        drop_missing_label=False,
    )

    model = build_model_from_checkpoint(
        ckpt,
        model_name=ckpt.get("cfg", {}).get("model", args.model),
        n_features=len(feature_cols),
        window=window,
    )
    model.load_state_dict(ckpt["model_state"])
    model.to(args.device).eval()

    rows: list[dict] = []
    target_day = np.datetime64(target.to_datetime64(), "D")
    with torch.no_grad():
        for i, s in enumerate(ds.samples):
            end_date = np.datetime64(ds.blocks_dates[s.stock_idx][s.end_row], "D")
            if end_date != target_day:
                continue
            x, _, si, _ = ds[i]
            raw = float(model(x.unsqueeze(0).to(args.device)).cpu().item())
            score = -raw if args.direction == "inverse" else raw
            rows.append({"ts_code": ds.ts_codes[int(si)], "raw_pred": raw, "strategy_score": score})

    targets = pd.DataFrame(rows).sort_values("strategy_score", ascending=False).head(args.n)
    targets.insert(0, "rank", np.arange(1, len(targets) + 1))
    targets.insert(1, "asof_date", asof.strftime("%Y-%m-%d"))
    targets.insert(2, "target_trade_date", target.strftime("%Y-%m-%d"))
    targets.insert(3, "tag", args.tag)
    targets.insert(4, "direction", args.direction)
    basic = dl.load_basic()[["ts_code", "name", "industry"]]
    targets = targets.merge(basic, on="ts_code", how="left")
    ref = last_day.set_index("ts_code")
    targets["ref_vwap"] = targets["ts_code"].map(ref["vwap"]) if "vwap" in ref.columns else np.nan
    targets["ref_close"] = targets["ts_code"].map(ref["close"])

    DAILY_LOGS.mkdir(parents=True, exist_ok=True)
    out = DAILY_LOGS / f"{target.strftime('%Y%m%d')}_{args.tag}_{args.direction}_n{args.n}_targets.csv"
    targets.to_csv(out, index=False, encoding="utf-8-sig")
    print(f"[predict-strategy] wrote {out}")
    print(targets.to_string(index=False))


if __name__ == "__main__":
    main()
