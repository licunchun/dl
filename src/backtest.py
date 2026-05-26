"""Daily rebalancing backtest: n=10 initial, swap k=2 per day.

Given a scored panel (ts_code, trade_date, y_pred), we simulate:

    * day 0 : equal-weight buy top-n
    * day t : sell the k names with lowest score in the current book,
              replace with the k highest-scored names that aren't already held
              and that are tradable on t (not ST, not limit-up, not suspended).
    * Tradability is decided only from information available on day t.  Returns
      are realised on next-day close.  Commission 0.0003 is deducted
      on each round-trip.

This deliberately avoids vectorbt to keep the A-share constraints (T+1, limit
filter, trade-calendar alignment) straightforward and auditable.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .data_loader import PROJECT_ROOT, load_panel, load_index


@dataclass
class BTConfig:
    n_hold: int = 10
    k_swap: int = 2
    init_cash: float = 1_000_000.0
    fee_rate: float = 0.0003
    exclude_limit_up: bool = True
    preds_path: Path = PROJECT_ROOT / "checkpoints" / "transformer_ic_val_preds.parquet"


def _build_score_table(preds: pd.DataFrame, panel: pd.DataFrame) -> pd.DataFrame:
    """Merge predictions with the panel so we know close / pct_chg per row."""
    preds = preds.copy()
    preds["trade_date"] = pd.to_datetime(preds["trade_date"])
    m = preds.merge(
        panel[["ts_code", "trade_date", "close", "pct_chg"]],
        on=["ts_code", "trade_date"], how="inner",
    )
    # Next-day return realised between close_t → close_{t+1}
    m = m.sort_values(["ts_code", "trade_date"])
    m["next_close"] = m.groupby("ts_code")["close"].shift(-1)
    m["ret_next"] = m["next_close"] / m["close"] - 1.0
    return m


def _tradable_on_day(day: pd.DataFrame, exclude_limit_up: bool = True) -> pd.DataFrame:
    """Rows eligible for a decision made on day t, using no t+1 fields."""
    tradable = day[day["close"].notna()].copy()
    if exclude_limit_up:
        tradable = tradable[tradable["pct_chg"].abs() < 9.5]
    return tradable


def run_backtest(cfg: BTConfig) -> dict[str, pd.DataFrame | pd.Series]:
    preds = pd.read_parquet(cfg.preds_path)
    panel = load_panel()
    scores = _build_score_table(preds, panel)

    dates = np.sort(scores["trade_date"].unique())
    equity = cfg.init_cash
    book: dict[str, float] = {}   # ts_code -> weight (equal among holdings)
    equity_curve: list[dict] = []
    trades: list[dict] = []

    for i, d in enumerate(dates[:-1]):   # last day has no next-close
        day = scores[scores["trade_date"] == d].set_index("ts_code")
        tradable = _tradable_on_day(day, cfg.exclude_limit_up)

        # --- rebalance: decide which to hold EOD of d, realise return t→t+1 ---
        if not book:
            picks = tradable.sort_values("y_pred", ascending=False).head(cfg.n_hold).index.tolist()
            book = {c: 1.0 / cfg.n_hold for c in picks}
            turnover = 1.0
            trades.append({"trade_date": d, "action": "init", "codes": picks})
        else:
            # sell k lowest-score of current book
            cur_scores = tradable.loc[tradable.index.intersection(book)]["y_pred"]
            # if a holding was untradable today, drop it anyway (prefer forced exit)
            lost = [c for c in book if c not in cur_scores.index]
            sell = list(cur_scores.sort_values().head(cfg.k_swap).index) + lost
            sell = list(dict.fromkeys(sell))[: cfg.k_swap + len(lost)]
            remain = [c for c in book if c not in sell]

            need = cfg.n_hold - len(remain)
            candidates = tradable.drop(index=remain, errors="ignore")
            buy = candidates.sort_values("y_pred", ascending=False).head(need).index.tolist()

            new_book = remain + buy
            book = {c: 1.0 / cfg.n_hold for c in new_book}
            turnover = len(buy) / cfg.n_hold
            trades.append({"trade_date": d, "action": "rebal",
                           "sell": sell, "buy": buy})

        # compute next-day return of this book
        held_rets = day.loc[[c for c in book if c in day.index], "ret_next"].fillna(0.0)
        port_ret = float(held_rets.mean()) if len(held_rets) else 0.0
        fee = cfg.fee_rate * turnover * 2   # round trip
        equity *= (1.0 + port_ret - fee)
        equity_curve.append({"trade_date": d, "equity": equity,
                             "ret": port_ret - fee, "turnover": turnover})

    eq = pd.DataFrame(equity_curve).set_index("trade_date")
    return {"equity": eq, "trades": pd.DataFrame(trades)}


def perf_stats(equity: pd.DataFrame, freq: int = 252) -> dict[str, float]:
    r = equity["ret"].dropna()
    ann = (1 + r).prod() ** (freq / max(len(r), 1)) - 1
    sharpe = r.mean() / r.std() * np.sqrt(freq) if r.std() > 0 else float("nan")
    nav = equity["equity"] / equity["equity"].iloc[0]
    dd = (nav / nav.cummax() - 1).min()
    return {"annualised": float(ann), "sharpe": float(sharpe),
            "max_drawdown": float(dd), "n_days": int(len(r))}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--preds", default=None)
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--k", type=int, default=2)
    ap.add_argument("--out", default=str(PROJECT_ROOT / "reports" / "backtest"))
    ap.add_argument("--no-plot", action="store_true")
    args = ap.parse_args()

    cfg = BTConfig(n_hold=args.n, k_swap=args.k)
    if args.preds:
        cfg.preds_path = Path(args.preds)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    res = run_backtest(cfg)
    eq = res["equity"]
    eq.to_parquet(out / "equity.parquet")
    stats = perf_stats(eq)
    print("[bt] stats:", stats)

    # Index benchmark comparison
    bench = load_index("000300.SH")
    bench = bench[bench["trade_date"].isin(eq.index)]
    bench = bench.set_index("trade_date").sort_index()
    bench["nav"] = bench["close"] / bench["close"].iloc[0]
    strat_nav = eq["equity"] / eq["equity"].iloc[0]
    cmp = pd.concat([strat_nav.rename("strategy"), bench["nav"].rename("hs300")], axis=1)
    cmp.to_parquet(out / "nav_compare.parquet")
    print(cmp.tail())

    if not args.no_plot:
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            fig, ax = plt.subplots(figsize=(10, 5))
            cmp.plot(ax=ax)
            ax.set_title(f"Strategy vs HS300 (n={cfg.n_hold}, k={cfg.k_swap}, fee={cfg.fee_rate}) "
                         f"ann={stats['annualised']:.2%} sharpe={stats['sharpe']:.2f}")
            ax.set_xlabel("date")
            ax.set_ylabel("NAV")
            ax.grid(True, alpha=0.3)
            fig_path = PROJECT_ROOT / "reports" / "figures" / f"nav_compare_{Path(cfg.preds_path).stem}.png"
            fig_path.parent.mkdir(parents=True, exist_ok=True)
            fig.tight_layout(); fig.savefig(fig_path, dpi=120)
            print(f"[bt] saved {fig_path}")
        except ImportError:
            print("[bt] matplotlib not available, skipping plot")


if __name__ == "__main__":
    main()
