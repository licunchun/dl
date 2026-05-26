"""Tests for causal integrity: no future information leaks into features.

Run with:
    pytest tests/test_no_leakage.py

These tests build a small synthetic panel (2 stocks, 60 days) where all
future rows are poisoned with a huge value.  If a feature referenced any
future row, its t-1 feature value would explode; we assert it doesn't.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.features import compute_features, list_feature_cols
from src.labels import attach_labels
from src.dataset import WindowDataset


def _make_panel(n_days: int = 60, spike_after: int = 40) -> pd.DataFrame:
    dates = pd.bdate_range("2023-01-02", periods=n_days, freq="B")
    rows = []
    for ts in ("AAAA.SH", "BBBB.SZ"):
        close = np.linspace(10, 20, n_days)
        # poison the future: huge jump after spike_after
        close[spike_after:] = 1e6
        for i, d in enumerate(dates):
            prev = close[i - 1] if i > 0 else close[i]
            rows.append({
                "ts_code": ts,
                "trade_date": d,
                "open": close[i] * 0.99,
                "high": close[i] * 1.02,
                "low": close[i] * 0.98,
                "close": close[i],
                "pre_close": prev,
                "pct_chg": (close[i] / prev - 1) * 100 if prev else 0.0,
                "vol": 1000.0 + i,
                "amount": 1e6 + i,
                "vwap": close[i],
                "turnover_rate": 1.5,
                "pe_ttm": 10.0,
                "pb": 1.2,
                "circ_mv": 5e8,
            })
    return pd.DataFrame(rows)


def test_features_are_strictly_causal():
    panel = _make_panel(n_days=60, spike_after=40)
    feats = compute_features(panel)
    cols = list_feature_cols(feats)

    # Row at day 40 (index 40) is the FIRST poisoned row. Features at day 40
    # were shifted by one so should reflect only pre-poison data → bounded.
    pre = feats[feats["trade_date"] == panel.loc[39, "trade_date"]]
    at_poison = feats[feats["trade_date"] == panel.loc[40, "trade_date"]]
    for c in cols:
        if c.startswith("rk_"):
            continue
        pre_max = np.nanmax(np.abs(pre[c].to_numpy())) if not pre[c].dropna().empty else 0
        val = at_poison[c].to_numpy()
        assert np.all(np.isfinite(val) | np.isnan(val)), f"{c} has inf/nan-explosion"
        # Allow generous tolerance for returns/ratios; the key property is
        # they are NOT astronomically large like 1e6.
        assert np.nanmax(np.abs(val)) < max(pre_max * 100 + 10, 100), (
            f"feature {c} at poison date looks like it peeked into future"
        )


def test_label_is_next_day_return():
    panel = _make_panel(n_days=20, spike_after=999)
    labels = attach_labels(panel)
    first_stock = labels[labels["ts_code"] == "AAAA.SH"].reset_index(drop=True)
    # y at row i should be log(close_{i+1}/close_i)
    closes = panel[panel["ts_code"] == "AAAA.SH"]["close"].to_numpy()
    for i in range(len(first_stock) - 1):
        if not pd.isna(first_stock.loc[i, "y"]):
            assert np.isclose(
                first_stock.loc[i, "y_raw"], np.log(closes[i + 1] / closes[i])
            )


def test_window_zscore_uses_window_only():
    panel = _make_panel(n_days=80, spike_after=999)
    feats = compute_features(panel)
    labels = attach_labels(panel)
    cols = list_feature_cols(feats)
    ds = WindowDataset(feats, labels, cols, window=20,
                       date_range=("2023-01-02", "2023-12-31"),
                       drop_missing_label=False)
    if len(ds) == 0:
        pytest.skip("synthetic dataset too small for window=20")
    x, _, _, _ = ds[0]
    arr = x.numpy()
    # Standardised columns should have near-zero mean per window.
    std_cols_idx = np.where(ds._zscore_mask)[0]
    mu = arr[:, std_cols_idx].mean(axis=0)
    assert np.max(np.abs(mu)) < 1e-5, f"per-window z-score mean not 0: {mu}"
