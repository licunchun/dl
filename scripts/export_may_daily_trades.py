"""Export May 2026 daily buy/sell lists for the selected LightGBM strategy."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.quick_lgbm_factor_groups import Candidate, _fit_lgbm, _merge_xy, _read_frame  # noqa: E402
from src.backtest import BTConfig, _build_score_table, _tradable_on_day, perf_stats  # noqa: E402
from src import data_loader as dl  # noqa: E402
from scripts.short_term_competition_train import _configure_data_dir  # noqa: E402
from scripts.train_lgbm_wq_short import _matrix  # noqa: E402


def _names(codes: list[str], basic: pd.DataFrame) -> str:
    name_map = basic.set_index("ts_code")["name"].to_dict()
    return ";".join(f"{c}:{name_map.get(c, '')}" for c in codes)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", type=Path, default=Path("/home/lcc17/pan_sync_20260528/A股数据"))
    ap.add_argument("--cache-dir", type=Path, default=Path("/home/lcc17/pan_sync_20260528/shortterm_cache"))
    ap.add_argument("--summary", type=Path, default=PROJECT_ROOT / "reports/may_2026_validation/summary_factor_lgbm_literature_combos_train2026q1q4.csv")
    ap.add_argument("--build-start", default="2025-01-01")
    ap.add_argument("--data-end", default="2026-05-31")
    ap.add_argument("--train-start", default="2026-01-01")
    ap.add_argument("--train-end", default="2026-04-30")
    ap.add_argument("--trade-start", default="2026-05-06")
    ap.add_argument("--trade-end", default="2026-05-29")
    ap.add_argument("--strategy", default="lit_carhart_ff_plus_momentum_huber_forward")
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--k", type=int, default=2)
    ap.add_argument("--num-threads", type=int, default=8)
    ap.add_argument("--n-estimators", type=int, default=240)
    ap.add_argument("--learning-rate", type=float, default=0.055)
    ap.add_argument("--num-leaves", type=int, default=31)
    ap.add_argument("--early-stopping-rounds", type=int, default=20)
    ap.add_argument("--half-life-days", type=float, default=30.0)
    ap.add_argument("--min-date-weight", type=float, default=0.15)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    _configure_data_dir(args.data_dir)
    summary = pd.read_csv(args.summary)
    row = summary[summary["tag"] == args.strategy].iloc[0]
    cols = [c for c in str(row["selected_features"]).split(",") if c]

    feat_path = args.cache_dir / f"features_wq_daily_{args.data_end}.parquet"
    label_path = args.cache_dir / f"labels_nofuturelimit_daily_{args.data_end}.parquet"
    panel_path = args.cache_dir / f"panel_daily_{args.data_end}.parquet"
    feats = _read_frame(feat_path, ["ts_code", "trade_date"] + cols)
    labels = _read_frame(label_path, ["ts_code", "trade_date", "y", "drop_reason"])
    panel = _read_frame(panel_path, ["ts_code", "trade_date", "close", "pct_chg"])

    train_all = _merge_xy(feats, labels, cols, args.train_start, args.train_end)
    val_df = _merge_xy(feats, labels, cols, "2026-05-06", "2026-05-27")
    cand = Candidate(args.strategy, "carhart_ff_plus_momentum", "huber", "forward", cols)
    model = _fit_lgbm(cand, train_all[["ts_code", "trade_date", "y", "drop_reason"] + cols], val_df, args)

    lo, hi = pd.Timestamp(args.trade_start), pd.Timestamp(args.trade_end)
    pred_df = feats[(feats["trade_date"] >= lo) & (feats["trade_date"] <= hi)].copy()
    pred_df = pred_df.dropna(subset=cols, how="all").reset_index(drop=True)
    pred_df["y_pred"] = model.predict(_matrix(pred_df, cols)).astype(float)
    scores = _build_score_table(pred_df[["ts_code", "trade_date", "y_pred"]], panel)
    dates = np.sort(scores["trade_date"].unique())

    cfg = BTConfig(n_hold=args.n, k_swap=args.k)
    basic = dl.load_basic()[["ts_code", "name", "industry"]]
    book: dict[str, float] = {}
    equity = cfg.init_cash
    trade_rows: list[dict] = []
    holding_rows: list[dict] = []
    equity_rows: list[dict] = []

    for d in dates:
        day = scores[scores["trade_date"] == d].set_index("ts_code")
        tradable = _tradable_on_day(day, cfg.exclude_limit_up)
        if tradable.empty:
            continue

        if not book:
            sell: list[str] = []
            buy = tradable.sort_values("y_pred", ascending=False).head(cfg.n_hold).index.tolist()
            book = {c: 1.0 / cfg.n_hold for c in buy}
            action = "init"
        else:
            cur_scores = tradable.loc[tradable.index.intersection(book)]["y_pred"]
            lost = [c for c in book if c not in cur_scores.index]
            sell = list(cur_scores.sort_values().head(cfg.k_swap).index) + lost
            sell = list(dict.fromkeys(sell))[: cfg.k_swap + len(lost)]
            remain = [c for c in book if c not in sell]
            need = cfg.n_hold - len(remain)
            buy = tradable.drop(index=remain, errors="ignore").sort_values("y_pred", ascending=False).head(need).index.tolist()
            book = {c: 1.0 / cfg.n_hold for c in remain + buy}
            action = "rebal"

        held = list(book)
        trade_rows.append({
            "trade_date": pd.Timestamp(d).strftime("%Y-%m-%d"),
            "action": action,
            "buy_count": len(buy),
            "sell_count": len(sell),
            "buy": _names(buy, basic),
            "sell": _names(sell, basic),
            "holdings": _names(held, basic),
        })
        for rank, code in enumerate(held, 1):
            rec = basic[basic["ts_code"] == code].head(1)
            holding_rows.append({
                "trade_date": pd.Timestamp(d).strftime("%Y-%m-%d"),
                "rank_in_book": rank,
                "ts_code": code,
                "name": rec["name"].iloc[0] if len(rec) else "",
                "industry": rec["industry"].iloc[0] if len(rec) else "",
                "score": float(day.loc[code, "y_pred"]) if code in day.index else np.nan,
            })

        if "ret_next" in day.columns and day.loc[[c for c in held if c in day.index], "ret_next"].notna().any():
            held_rets = day.loc[[c for c in held if c in day.index], "ret_next"].fillna(0.0)
            turnover = len(buy) / cfg.n_hold
            ret = float(held_rets.mean()) - cfg.fee_rate * turnover * 2
            equity *= 1.0 + ret
            equity_rows.append({"trade_date": pd.Timestamp(d).strftime("%Y-%m-%d"), "equity": equity, "ret": ret})

    out_dir = PROJECT_ROOT / "reports" / "may_2026_validation"
    trades = pd.DataFrame(trade_rows)
    holdings = pd.DataFrame(holding_rows)
    equity_df = pd.DataFrame(equity_rows)
    trades.to_csv(out_dir / "may_daily_trades_carhart_lgbm.csv", index=False, encoding="utf-8-sig")
    holdings.to_csv(out_dir / "may_daily_holdings_carhart_lgbm.csv", index=False, encoding="utf-8-sig")
    equity_df.to_csv(out_dir / "may_daily_equity_carhart_lgbm.csv", index=False, encoding="utf-8-sig")
    if len(equity_df):
        stats = perf_stats(equity_df.set_index("trade_date"))
        total = equity_df["equity"].iloc[-1] / cfg.init_cash - 1.0
        print({"total_return": total, **stats})
    print(trades[["trade_date", "buy", "sell"]].to_string(index=False))


if __name__ == "__main__":
    main()
