"""Feature engineering.

All features are causal: for every row (ts_code, t) every feature only uses
information strictly before and including t-1.  The output is the *feature
block as of the close of day t-1*; the next module (`labels.py`) then attaches
``y_{t}`` computed from closes at t and t+1.

Naming:
    ret_1, ret_5, ret_20             log returns over last 1/5/20 days
    ma_5, ma_20                      close / MA - 1
    std_5, std_20                    realised vol over last N days
    vol_ratio_5                      today vol / mean vol last 5 days  (t-1 based)
    amihud_20                        |ret| / amount rolling-20
    rsi_14 / macd / macd_sig         standard TA
    turn_z, mv_log, pe_inv, pb_inv   cross-sectional fundamentals (rank within day)
    rk_ret_1, rk_turn                cross-sectional ranks in [0, 1]

Everything lives in one function so the no-leakage test can sanity-check
numerical values directly.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

EPS = 1e-8


# ---- technical indicators (vectorised, pandas only) ------------------------

def _rsi(close: pd.Series, n: int = 14) -> pd.Series:
    delta = close.diff()
    up = delta.clip(lower=0.0)
    dn = (-delta).clip(lower=0.0)
    # Wilder's EMA
    alpha = 1.0 / n
    rs_up = up.ewm(alpha=alpha, adjust=False).mean()
    rs_dn = dn.ewm(alpha=alpha, adjust=False).mean()
    rs = rs_up / (rs_dn + EPS)
    return 100.0 - 100.0 / (1.0 + rs)


def _macd(close: pd.Series, fast: int = 12, slow: int = 26, sig: int = 9):
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd = ema_fast - ema_slow
    signal = macd.ewm(span=sig, adjust=False).mean()
    return macd, signal, (macd - signal)


# ---- per-stock feature block -----------------------------------------------

def _per_stock(df: pd.DataFrame) -> pd.DataFrame:
    """df is one stock's rows sorted by trade_date. Returns same length frame
    with engineered features; every feature is shifted by 1 so row t carries
    only information up to t-1."""
    g = df.copy()
    c = g["close"].astype(float)
    v = g["vol"].astype(float)
    a = g["amount"].astype(float)
    pct = g["pct_chg"].astype(float) / 100.0   # source is percent

    g["ret_1"] = np.log1p(pct)
    g["ret_5"] = g["ret_1"].rolling(5).sum()
    g["ret_20"] = g["ret_1"].rolling(20).sum()

    g["ma_5"] = c / c.rolling(5).mean() - 1.0
    g["ma_20"] = c / c.rolling(20).mean() - 1.0

    g["std_5"] = g["ret_1"].rolling(5).std()
    g["std_20"] = g["ret_1"].rolling(20).std()

    g["vol_ratio_5"] = v / (v.rolling(5).mean() + EPS)
    g["amihud_20"] = (g["ret_1"].abs() / (a + EPS)).rolling(20).mean()
    g["vwap_dev"] = (c - g["vwap"].astype(float)) / (g["vwap"].astype(float) + EPS)

    g["rsi_14"] = _rsi(c, 14)
    macd, macd_sig, macd_hist = _macd(c)
    g["macd"] = macd / (c + EPS)
    g["macd_sig"] = macd_sig / (c + EPS)
    g["macd_hist"] = macd_hist / (c + EPS)

    # Fundamentals may be NaN for some rows; fill forward within stock (still causal).
    for col in ("turnover_rate", "pe_ttm", "pb", "circ_mv"):
        if col in g.columns:
            g[col] = g[col].ffill()
    if "circ_mv" in g.columns:
        g["mv_log"] = np.log(g["circ_mv"].clip(lower=1.0))
    if "pe_ttm" in g.columns:
        g["pe_inv"] = 1.0 / g["pe_ttm"].replace(0, np.nan)
    if "pb" in g.columns:
        g["pb_inv"] = 1.0 / g["pb"].replace(0, np.nan)
    if "turnover_rate" in g.columns:
        g["turn"] = g["turnover_rate"]

    feat_cols = [
        "ret_1", "ret_5", "ret_20",
        "ma_5", "ma_20",
        "std_5", "std_20",
        "vol_ratio_5", "amihud_20", "vwap_dev",
        "rsi_14", "macd", "macd_sig", "macd_hist",
    ]
    for opt in ("turn", "mv_log", "pe_inv", "pb_inv"):
        if opt in g.columns:
            feat_cols.append(opt)

    # Shift by 1: features available at the open of day t use data ≤ t-1.
    g[feat_cols] = g[feat_cols].shift(1)
    return g[["ts_code", "trade_date"] + feat_cols]


# ---- cross-sectional ranks -------------------------------------------------

def _cross_section_ranks(feat: pd.DataFrame) -> pd.DataFrame:
    """Add day-wise rank features. Ranks are computed from the *already shifted*
    per-stock features, so they remain causal."""
    def _rank(col: pd.Series) -> pd.Series:
        return col.rank(pct=True, method="average")

    out = feat.copy()
    for src, dst in [("ret_1", "rk_ret_1"),
                     ("ret_5", "rk_ret_5"),
                     ("turn", "rk_turn"),
                     ("mv_log", "rk_mv")]:
        if src in out.columns:
            out[dst] = out.groupby("trade_date")[src].transform(_rank)
    return out


def compute_features(panel: pd.DataFrame) -> pd.DataFrame:
    """Main entry point. Takes the cached panel (from data_loader.build_panel)
    and returns a causal feature frame (same length, extra columns)."""
    panel = panel.sort_values(["ts_code", "trade_date"]).reset_index(drop=True)
    parts: list[pd.DataFrame] = []
    for code, g in panel.groupby("ts_code", sort=False):
        parts.append(_per_stock(g))
    feats = pd.concat(parts, ignore_index=True)
    feats = _cross_section_ranks(feats)
    return feats


FEATURE_COLS_BASE = [
    "ret_1", "ret_5", "ret_20",
    "ma_5", "ma_20",
    "std_5", "std_20",
    "vol_ratio_5", "amihud_20", "vwap_dev",
    "rsi_14", "macd", "macd_sig", "macd_hist",
    "turn", "mv_log", "pe_inv", "pb_inv",
    "rk_ret_1", "rk_ret_5", "rk_turn", "rk_mv",
]


def list_feature_cols(feats: pd.DataFrame) -> list[str]:
    return [c for c in FEATURE_COLS_BASE if c in feats.columns]
