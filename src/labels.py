"""Label construction.

Target: next-day log return computed from close-to-close,

    y_t = log(close_{t+1} / close_t)

This is the return realised between the *close of t* and the *close of t+1*.
Under the competition flow (pre-market decision on day t+1 with information up
to t-1's close), a positive y_t means the asset would have been profitable to
hold from t through t+1.

Rows are dropped if:
  * The next day is a non-trading day (no close_{t+1}) or the stock is missing
    on t+1 (suspension).
  * The current-day change hit the A-share limit (≈ ±10% / ±20% / ±5% depending
    on board).  On a limit-up day the order would not fill; keeping these rows
    biases the IC upwards.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# Conservative caps; strict board-specific caps are handled by pre_close ratio.
LIMIT_SOFT = 0.095     # drop |pct_chg| ≥ 9.5 % as "likely hit limit"


def _is_board_limit(row_pct: pd.Series) -> pd.Series:
    """Heuristic: |pct_chg| very close to ±10% is assumed to be a limit day."""
    return row_pct.abs() >= LIMIT_SOFT


def attach_labels(panel: pd.DataFrame) -> pd.DataFrame:
    """Expects the raw panel (with pct_chg / close) sorted by (ts_code, date).

    Returns a frame with columns [ts_code, trade_date, y, y_raw, drop_reason]
    where ``drop_reason`` is non-empty for rows that should be excluded.
    """
    p = panel.sort_values(["ts_code", "trade_date"]).reset_index(drop=True)
    g = p.groupby("ts_code", sort=False)
    next_close = g["close"].shift(-1)
    next_pct = g["pct_chg"].shift(-1) / 100.0

    y_raw = np.log(next_close / p["close"])
    # Drop limit days on t+1 (can't buy at limit-up open) and suspensions.
    hit_next_limit = _is_board_limit(next_pct.fillna(0))
    suspended = next_close.isna()
    # Also drop rows where today's pct_chg NaN (first listing day after filter).
    bad_today = p["pct_chg"].isna()

    reasons = pd.Series("", index=p.index, dtype=object)
    reasons = reasons.mask(suspended, "suspended")
    reasons = reasons.mask(hit_next_limit & (reasons == ""), "limit_tomorrow")
    reasons = reasons.mask(bad_today & (reasons == ""), "bad_today")

    out = p[["ts_code", "trade_date", "close", "pct_chg"]].copy()
    out["y_raw"] = y_raw
    out["y"] = y_raw.where(reasons == "", np.nan)
    out["drop_reason"] = reasons
    return out


def clip_outliers(df: pd.DataFrame, col: str = "y", q: float = 0.005) -> pd.DataFrame:
    """Cross-sectional winsorisation of the label, per trading day.  Helps
    against a few extreme outliers (e.g. post-suspension gap)."""
    out = df.copy()
    def _clip(s: pd.Series) -> pd.Series:
        lo, hi = s.quantile(q), s.quantile(1 - q)
        return s.clip(lo, hi)
    out[col] = out.groupby("trade_date")[col].transform(_clip)
    return out
