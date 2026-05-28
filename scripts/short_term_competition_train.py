"""Train one short-horizon competition model from the synced 2026-05-28 data.

This script is intentionally standalone so it does not change the main training
pipeline while the long A100 job is still running.  The model objective is still
cross-sectional IC, but the split and features are tuned for the 2026-06-01 to
2026-06-12 virtual trading window:

* train on broad history with exponential recency weights;
* validate on May 2026, the closest labelled period;
* add shifted moneyflow features;
* emit a 2026-06-01 target list using 2026-05-28 as the data cutoff.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd
import torch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src import data_loader as dl
from src.backtest import perf_stats
from src.dataset import DayBatchSampler, WindowDataset
from src.eval import summarize, topk_spread
from src.features import compute_features, list_feature_cols
from src.labels import attach_labels, clip_outliers
from src.train import TrainConfig, _collate, _collect_preds, build_model, ic_loss

CHECKPOINTS = PROJECT_ROOT / "checkpoints"
REPORTS = PROJECT_ROOT / "reports"
DAILY_LOGS = REPORTS / "daily_logs"

MONEYFLOW_COLS = [
    "ts_code", "trade_date",
    "buy_lg_amount", "sell_lg_amount",
    "buy_elg_amount", "sell_elg_amount",
    "net_mf_vol", "net_mf_amount",
]
MONEYFLOW_FEATURES = [
    "mf_net_amt_ratio",
    "mf_net_vol_ratio",
    "mf_lg_amt_ratio",
    "mf_elg_amt_ratio",
    "mf_buy_pressure",
    "rk_mf_net_amt",
    "rk_mf_lg_amt",
    "rk_mf_buy_pressure",
]


def _normalise_batch_cap(batch_cap: int | None) -> int | None:
    return None if batch_cap is None or batch_cap <= 0 else batch_cap


def _date_weight(date_days: int, train_end_days: int, half_life_days: float, min_weight: float) -> float:
    if half_life_days <= 0:
        return 1.0
    age = max(0, train_end_days - date_days)
    decay = math.exp(-math.log(2.0) * age / half_life_days)
    return float(min_weight + (1.0 - min_weight) * decay)


def _run_epoch_weighted(
    model,
    sampler,
    ds,
    optim,
    device,
    *,
    train: bool,
    train_end: str,
    half_life_days: float,
    min_date_weight: float,
    batch_cap: int | None = None,
    scaler=None,
    amp: bool = False,
) -> dict[str, float]:
    """Run one IC epoch, optionally weighting older day-batches less."""
    model.train(train)
    losses: list[float] = []
    weighted_losses: list[float] = []
    weights: list[float] = []
    batch_cap = _normalise_batch_cap(batch_cap)
    train_end_days = int(pd.Timestamp(train_end).to_datetime64().astype("datetime64[D]").astype("int64"))

    for idxs in sampler:
        if batch_cap and len(idxs) > batch_cap:
            idxs = np.random.choice(idxs, size=batch_cap, replace=False).tolist()
        xs, ys, _, dates = _collate([ds[i] for i in idxs])
        xs = xs.to(device, non_blocking=True)
        ys = ys.to(device, non_blocking=True)
        weight = _date_weight(int(dates[0]), train_end_days, half_life_days, min_date_weight) if train else 1.0

        with torch.set_grad_enabled(train):
            with torch.autocast(device_type="cuda", enabled=amp):
                raw_loss = ic_loss(model(xs), ys)
                loss = raw_loss * weight
        if train:
            optim.zero_grad()
            if scaler is not None and amp:
                scaler.scale(loss).backward()
                scaler.unscale_(optim)
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                scaler.step(optim)
                scaler.update()
            else:
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                optim.step()

        losses.append(float(raw_loss.item()))
        weighted_losses.append(float(loss.item()))
        weights.append(weight)

    return {
        "loss": float(np.mean(losses)) if losses else float("nan"),
        "weighted_loss": float(np.mean(weighted_losses)) if weighted_losses else float("nan"),
        "mean_weight": float(np.mean(weights)) if weights else float("nan"),
    }


def _configure_data_dir(data_dir: Path) -> None:
    dl.DATA_DIR = data_dir
    dl.PANEL_CACHE = data_dir / "panel.parquet"
    dl.load_basic.cache_clear()
    dl.load_trade_cal.cache_clear()


def _read_moneyflow(data_dir: Path, start: str, end: str) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for d in dl.trading_dates(start, end):
        p = data_dir / "moneyflow" / f"{d.strftime('%Y%m%d')}.csv"
        if not p.exists():
            continue
        df = pd.read_csv(p, dtype={"ts_code": str})
        keep = [c for c in MONEYFLOW_COLS if c in df.columns]
        df = df[keep].copy()
        df["trade_date"] = pd.to_datetime(df["trade_date"].astype(str), format="%Y%m%d")
        frames.append(df)
    if not frames:
        return pd.DataFrame(columns=MONEYFLOW_COLS)
    return pd.concat(frames, ignore_index=True)


def _merge_moneyflow(panel: pd.DataFrame, moneyflow: pd.DataFrame) -> pd.DataFrame:
    if moneyflow.empty:
        return panel
    return panel.merge(moneyflow, on=["ts_code", "trade_date"], how="left")


def _add_moneyflow_features(feats: pd.DataFrame, panel: pd.DataFrame) -> pd.DataFrame:
    cols = [c for c in MONEYFLOW_COLS if c in panel.columns]
    if len(cols) <= 2:
        return feats

    mf = panel[["ts_code", "trade_date", "amount", "vol"] + cols[2:]].copy()
    for c in cols[2:] + ["amount", "vol"]:
        mf[c] = pd.to_numeric(mf[c], errors="coerce")

    # daily.amount is thousand yuan; moneyflow amounts are ten-thousand yuan.
    amt = mf["amount"].abs() + 1e-8
    vol = mf["vol"].abs() + 1e-8
    lg_net = mf.get("buy_lg_amount", 0.0) - mf.get("sell_lg_amount", 0.0)
    elg_net = mf.get("buy_elg_amount", 0.0) - mf.get("sell_elg_amount", 0.0)
    lg_buy = mf.get("buy_lg_amount", 0.0) + mf.get("buy_elg_amount", 0.0)
    lg_sell = mf.get("sell_lg_amount", 0.0) + mf.get("sell_elg_amount", 0.0)

    mf["mf_net_amt_ratio"] = mf.get("net_mf_amount", 0.0) * 10.0 / amt
    mf["mf_net_vol_ratio"] = mf.get("net_mf_vol", 0.0) / vol
    mf["mf_lg_amt_ratio"] = lg_net * 10.0 / amt
    mf["mf_elg_amt_ratio"] = elg_net * 10.0 / amt
    mf["mf_buy_pressure"] = np.log1p(lg_buy.clip(lower=0.0)) - np.log1p(lg_sell.clip(lower=0.0))

    raw = MONEYFLOW_FEATURES[:5]
    mf = mf.sort_values(["ts_code", "trade_date"])
    mf[raw] = mf.groupby("ts_code", sort=False)[raw].shift(1)

    def _rank(col: pd.Series) -> pd.Series:
        return col.rank(pct=True, method="average")

    mf["rk_mf_net_amt"] = mf.groupby("trade_date")["mf_net_amt_ratio"].transform(_rank)
    mf["rk_mf_lg_amt"] = mf.groupby("trade_date")["mf_lg_amt_ratio"].transform(_rank)
    mf["rk_mf_buy_pressure"] = mf.groupby("trade_date")["mf_buy_pressure"].transform(_rank)
    return feats.merge(mf[["ts_code", "trade_date"] + MONEYFLOW_FEATURES],
                       on=["ts_code", "trade_date"], how="left")


def _build_frames(args) -> tuple[pd.DataFrame, pd.DataFrame, list[str], pd.DataFrame]:
    _configure_data_dir(args.data_dir)
    cache_dir = args.cache_dir
    cache_dir.mkdir(parents=True, exist_ok=True)
    panel_cache = cache_dir / f"panel_{args.start}_{args.asof_date}.parquet"
    feats_cache = cache_dir / f"features_moneyflow_{args.start}_{args.asof_date}.parquet"
    labels_cache = cache_dir / f"labels_{args.start}_{args.asof_date}.parquet"

    if panel_cache.exists() and feats_cache.exists() and labels_cache.exists() and not args.rebuild_cache:
        panel = pd.read_parquet(panel_cache)
        feats = pd.read_parquet(feats_cache)
        labels = pd.read_parquet(labels_cache)
    else:
        cfg = dl.PanelBuildConfig(
            start=args.start,
            end=args.asof_date,
            cache_path=panel_cache,
            include_metric=True,
        )
        panel = dl.build_panel(cfg)
        moneyflow = _read_moneyflow(args.data_dir, args.start, args.asof_date)
        panel = _merge_moneyflow(panel, moneyflow)
        panel.to_parquet(panel_cache, index=False)
        feats = _add_moneyflow_features(compute_features(panel), panel)
        labels = clip_outliers(attach_labels(panel), "y", 0.005)
        feats.to_parquet(feats_cache, index=False)
        labels.to_parquet(labels_cache, index=False)

    feature_cols = list_feature_cols(feats) + [c for c in MONEYFLOW_FEATURES if c in feats.columns]
    return feats, labels, feature_cols, panel


def _save_best(tag: str, model: torch.nn.Module, cfg: TrainConfig, feature_cols: list[str]) -> None:
    CHECKPOINTS.mkdir(exist_ok=True)
    torch.save({
        "model_state": model.state_dict(),
        "cfg": asdict(cfg),
        "feature_cols": feature_cols,
    }, CHECKPOINTS / f"{tag}.pt")


def _run_backtest(preds: pd.DataFrame, panel: pd.DataFrame, out_dir: Path) -> dict[str, float]:
    from src.backtest import BTConfig, _build_score_table, _tradable_on_day

    cfg = BTConfig()
    scores = _build_score_table(preds, panel)
    dates = np.sort(scores["trade_date"].unique())
    equity = cfg.init_cash
    book: dict[str, float] = {}
    rows: list[dict] = []
    for d in dates[:-1]:
        day = scores[scores["trade_date"] == d].set_index("ts_code")
        tradable = _tradable_on_day(day, cfg.exclude_limit_up)
        if not book:
            picks = tradable.sort_values("y_pred", ascending=False).head(cfg.n_hold).index.tolist()
            book = {c: 1.0 / cfg.n_hold for c in picks}
            turnover = 1.0
        else:
            cur_scores = tradable.loc[tradable.index.intersection(book)]["y_pred"]
            lost = [c for c in book if c not in cur_scores.index]
            sell = list(cur_scores.sort_values().head(cfg.k_swap).index) + lost
            remain = [c for c in book if c not in sell]
            need = cfg.n_hold - len(remain)
            buy = tradable.drop(index=remain, errors="ignore").sort_values("y_pred", ascending=False).head(need).index.tolist()
            book = {c: 1.0 / cfg.n_hold for c in remain + buy}
            turnover = len(buy) / cfg.n_hold
        held_rets = day.loc[[c for c in book if c in day.index], "ret_next"].fillna(0.0)
        port_ret = float(held_rets.mean()) if len(held_rets) else 0.0
        equity *= (1.0 + port_ret - cfg.fee_rate * turnover * 2)
        rows.append({"trade_date": d, "equity": equity, "ret": port_ret - cfg.fee_rate * turnover * 2,
                     "turnover": turnover})

    out_dir.mkdir(parents=True, exist_ok=True)
    eq = pd.DataFrame(rows).set_index("trade_date")
    eq.to_parquet(out_dir / "equity.parquet")
    stats = perf_stats(eq)
    (out_dir / "stats.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")
    return stats


def _predict_target(args, model: torch.nn.Module, feature_cols: list[str], panel: pd.DataFrame) -> pd.DataFrame:
    asof = pd.Timestamp(args.asof_date)
    target = pd.Timestamp(args.target_date)
    base = panel[panel["trade_date"] <= asof].copy()
    last_day = base[base["trade_date"] == asof].copy()
    synth = last_day.copy()
    synth["trade_date"] = target
    synth["pct_chg"] = 0.0
    target_panel = pd.concat([base, synth], ignore_index=True)
    feats = _add_moneyflow_features(compute_features(target_panel), target_panel)
    labels = attach_labels(target_panel)
    ds = WindowDataset(
        feats, labels, feature_cols, window=args.window,
        date_range=(str(asof - pd.Timedelta(days=160)), str(target)),
        drop_missing_label=False,
    )

    device = args.device
    model.eval()
    rows: list[dict] = []
    target_day = np.datetime64(target.to_datetime64(), "D")
    with torch.no_grad():
        for i, s in enumerate(ds.samples):
            end_date = np.datetime64(ds.blocks_dates[s.stock_idx][s.end_row], "D")
            if end_date != target_day:
                continue
            x, _, si, _ = ds[i]
            pred = float(model(x.unsqueeze(0).to(device)).cpu().item())
            rows.append({"ts_code": ds.ts_codes[int(si)], "y_pred": pred})

    out = pd.DataFrame(rows).sort_values("y_pred", ascending=False).head(args.n)
    out.insert(0, "rank", np.arange(1, len(out) + 1))
    out.insert(1, "asof_date", asof.strftime("%Y-%m-%d"))
    out.insert(2, "target_trade_date", target.strftime("%Y-%m-%d"))
    basic = dl.load_basic()[["ts_code", "name", "industry"]]
    out = out.merge(basic, on="ts_code", how="left")
    ref = last_day.set_index("ts_code")
    out["ref_vwap"] = out["ts_code"].map(ref["vwap"])
    out["ref_close"] = out["ts_code"].map(ref["close"])
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", type=Path, default=Path("/home/lcc17/pan_sync_20260528/A股数据"))
    ap.add_argument("--cache-dir", type=Path, default=Path("/home/lcc17/pan_sync_20260528/shortterm_cache"))
    ap.add_argument("--start", default="2019-01-01")
    ap.add_argument("--train-end", default="2026-04-30")
    ap.add_argument("--val-start", default="2026-05-06")
    ap.add_argument("--val-end", default="2026-05-27")
    ap.add_argument("--asof-date", default="2026-05-28")
    ap.add_argument("--target-date", default="2026-06-01")
    ap.add_argument("--tag", default="lstm_ic_short_mf_decay_h256_l2_w10")
    ap.add_argument("--window", type=int, default=10)
    ap.add_argument("--hidden", type=int, default=256)
    ap.add_argument("--layers", type=int, default=2)
    ap.add_argument("--dropout", type=float, default=0.25)
    ap.add_argument("--epochs", type=int, default=12)
    ap.add_argument("--batch-cap", type=int, default=8192)
    ap.add_argument("--half-life-days", type=float, default=180.0,
                    help="Exponential recency half-life for training day IC loss; <=0 disables weighting.")
    ap.add_argument("--min-date-weight", type=float, default=0.25,
                    help="Floor weight for old training dates when recency weighting is enabled.")
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--rebuild-cache", action="store_true")
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    args = ap.parse_args()
    if not 0.0 <= args.min_date_weight <= 1.0:
        raise ValueError("--min-date-weight must be in [0, 1]")

    torch.manual_seed(42)
    np.random.seed(42)
    feats, labels, feature_cols, panel = _build_frames(args)

    cfg = TrainConfig(
        model="lstm", loss="ic", window=args.window,
        train_range=(args.start, args.train_end),
        val_range=(args.val_start, args.val_end),
        epochs=args.epochs, hidden=args.hidden, layers=args.layers,
        dropout=args.dropout, amp=args.device.startswith("cuda"),
        device=args.device,
    )
    train_ds = WindowDataset(feats, labels, feature_cols, args.window, date_range=cfg.train_range)
    val_ds = WindowDataset(feats, labels, feature_cols, args.window, date_range=cfg.val_range)
    train_sampler = DayBatchSampler(train_ds, shuffle=True, min_stocks=100)
    val_sampler = DayBatchSampler(val_ds, shuffle=False, min_stocks=100)
    print(f"[short] features={len(feature_cols)} train_samples={len(train_ds)} val_samples={len(val_ds)}")

    model = build_model("lstm", len(feature_cols), args.window,
                        hidden=args.hidden, layers=args.layers, dropout=args.dropout).to(args.device)
    optim = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-5)
    scaler = torch.cuda.amp.GradScaler(enabled=cfg.amp)
    best_ic = -float("inf")
    log: list[dict] = []
    best_state = None
    for epoch in range(args.epochs):
        tr = _run_epoch_weighted(
            model, train_sampler, train_ds, optim, args.device,
            train=True, train_end=args.train_end,
            half_life_days=args.half_life_days,
            min_date_weight=args.min_date_weight,
            batch_cap=args.batch_cap, scaler=scaler, amp=cfg.amp,
        )
        vl = _run_epoch_weighted(
            model, val_sampler, val_ds, optim, args.device,
            train=False, train_end=args.train_end,
            half_life_days=args.half_life_days,
            min_date_weight=args.min_date_weight,
            batch_cap=args.batch_cap, amp=cfg.amp,
        )
        preds = _collect_preds(model, val_sampler, val_ds, args.device, batch_cap=args.batch_cap)
        m = summarize(preds)
        spread = topk_spread(preds, k=10)
        m["topk10_bp"] = float(spread["spread"].mean() * 1e4) if len(spread) else float("nan")
        print(f"[ep {epoch}] train_loss={tr['loss']:.4f} weighted={tr['weighted_loss']:.4f} "
              f"mean_w={tr['mean_weight']:.3f} val_loss={vl['loss']:.4f} "
              f"IC={m['ic']:.4f} RankIC={m['rank_ic']:.4f} Top10bp={m['topk10_bp']:.1f}")
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
            best_state = {k: v.detach().cpu() for k, v in model.state_dict().items()}
            _save_best(args.tag, model, cfg, feature_cols)

    if best_state is not None:
        model.load_state_dict(best_state)
    preds = _collect_preds(model, val_sampler, val_ds, args.device, batch_cap=args.batch_cap)
    preds_path = CHECKPOINTS / f"{args.tag}_val_preds.parquet"
    preds.to_parquet(preds_path, index=False)
    (CHECKPOINTS / f"{args.tag}_train_log.json").write_text(json.dumps(log, indent=2), encoding="utf-8")
    stats = _run_backtest(preds, panel, REPORTS / f"backtest_{args.tag}")
    targets = _predict_target(args, model, feature_cols, panel)
    DAILY_LOGS.mkdir(parents=True, exist_ok=True)
    target_path = DAILY_LOGS / f"{args.target_date.replace('-', '')}_short_term_targets.csv"
    targets.to_csv(target_path, index=False, encoding="utf-8-sig")
    print("[short] best_val", summarize(preds))
    print("[short] backtest", stats)
    print(f"[short] wrote {preds_path}")
    print(f"[short] wrote {target_path}")
    print(targets.to_string(index=False))


if __name__ == "__main__":
    main()
