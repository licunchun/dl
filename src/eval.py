"""Evaluation utilities.

Given a dataframe of ``(ts_code, trade_date, y_pred, y_true)`` rows, compute:

    IC        day-level Pearson(y_pred, y_true), mean over days
    RankIC    day-level Spearman
    ICIR      IC mean / IC std  (annualisation omitted; already daily)
    DirAcc    sign-agreement rate (ignoring zeros)
    Long-only top-k spread (optional)

Everything is cross-section aware: metrics are computed per trading day, then
summarised across days.  This mirrors how the backtest actually uses scores.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _daywise_metrics(df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, float]] = []
    for d, g in df.groupby("trade_date"):
        if len(g) < 30:
            continue
        p = g["y_pred"].to_numpy()
        y = g["y_true"].to_numpy()
        if np.std(p) < 1e-9 or np.std(y) < 1e-9:
            continue
        ic = np.corrcoef(p, y)[0, 1]
        rp = pd.Series(p).rank().to_numpy()
        ry = pd.Series(y).rank().to_numpy()
        rank_ic = np.corrcoef(rp, ry)[0, 1]
        nz = (y != 0)
        diracc = float(np.mean(np.sign(p[nz]) == np.sign(y[nz]))) if nz.any() else float("nan")
        rows.append({"trade_date": d, "ic": ic, "rank_ic": rank_ic, "diracc": diracc})
    return pd.DataFrame(rows)


def summarize(preds: pd.DataFrame) -> dict[str, float]:
    daily = _daywise_metrics(preds)
    if daily.empty:
        return {"ic": float("nan"), "rank_ic": float("nan"), "icir": float("nan"),
                "diracc": float("nan"), "n_days": 0}
    ic_std = daily["ic"].std(ddof=1)
    icir = float(daily["ic"].mean() / ic_std * np.sqrt(252)) if ic_std > 0 else float("nan")
    return {
        "ic": float(daily["ic"].mean()),
        "rank_ic": float(daily["rank_ic"].mean()),
        "icir": icir,
        "diracc": float(daily["diracc"].mean()),
        "n_days": int(len(daily)),
    }


def topk_spread(preds: pd.DataFrame, k: int = 10) -> pd.DataFrame:
    """For each day, average of top-k minus bottom-k realised returns."""
    out = []
    for d, g in preds.groupby("trade_date"):
        if len(g) < 2 * k:
            continue
        sorted_g = g.sort_values("y_pred", ascending=False)
        top = sorted_g.head(k)["y_true"].mean()
        bot = sorted_g.tail(k)["y_true"].mean()
        out.append({"trade_date": d, "top_k": top, "bot_k": bot, "spread": top - bot})
    return pd.DataFrame(out)
