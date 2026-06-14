from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd


def _load_alpha_backtest():
    path = Path(__file__).resolve().parents[1] / "alpha-stage" / "scripts" / "alpha_backtest.py"
    spec = importlib.util.spec_from_file_location("alpha_backtest_cache_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_panel_cache_roundtrip_and_source_invalidation(tmp_path, monkeypatch) -> None:
    mod = _load_alpha_backtest()
    data_root = tmp_path / "data"
    daily = data_root / "daily"
    metric = data_root / "metric"
    moneyflow = data_root / "moneyflow"
    st = data_root / "stock_st"
    for path in [daily, metric, moneyflow, st]:
        path.mkdir(parents=True)
    source = daily / "20260101.csv"
    source.write_text("ts_code,trade_date\n000001.SZ,20260101\n", encoding="utf-8")

    monkeypatch.setattr(mod, "ARTIFACT_DIR", tmp_path / "artifacts")
    monkeypatch.setattr(mod, "DAILY_DIR", daily)
    monkeypatch.setattr(mod, "METRIC_DIR", metric)
    monkeypatch.setattr(mod, "MONEYFLOW_DIR", moneyflow)
    monkeypatch.setattr(mod, "ST_DIR", st)
    monkeypatch.setenv("ALPHA_PANEL_CACHE", "1")
    monkeypatch.setenv("ALPHA_REFRESH_CACHE", "0")

    panel = pd.DataFrame(
        {
            "ts_code": ["000001.SZ"],
            "trade_date": [pd.Timestamp("2026-01-01")],
            "score": [0.5],
        }
    )

    mod.write_panel_cache(panel, start="20260101", end="20260101")
    cached = mod.read_panel_cache(start="20260101", end="20260101")

    assert cached is not None
    assert cached["ts_code"].tolist() == ["000001.SZ"]
    selected = mod.read_panel_cache(start="20260101", end="20260101", columns=["ts_code"])
    assert selected is not None
    assert selected.columns.tolist() == ["ts_code"]

    source.write_text("ts_code,trade_date\n000001.SZ,20260101\n000002.SZ,20260101\n", encoding="utf-8")

    assert mod.read_panel_cache(start="20260101", end="20260101") is None


def test_delayed_exit_uses_next_fillable_open_instead_of_dropping() -> None:
    mod = _load_alpha_backtest()
    df = pd.DataFrame(
        {
            "ts_code": ["000001.SZ"] * 5,
            "trade_date": pd.date_range("2026-01-01", periods=5, freq="D"),
            "open": [10.0, 11.0, 9.0, 12.0, 13.0],
            "next_open": [11.0, 9.0, 12.0, 13.0, float("nan")],
            "sell_blocked_limit": [False, True, False, False, True],
        }
    )

    out = mod.add_delayed_exit_returns(df.copy(), [1], max_delay_days=2)

    assert out.loc[0, "exit_fillable_1d"]
    assert out.loc[0, "exit_delay_1d"] == 1
    assert out.loc[0, "ret_o2o_1d"] == (12.0 / 11.0) - 1


def test_delayed_exit_marks_unfillable_when_no_later_open_available() -> None:
    mod = _load_alpha_backtest()
    df = pd.DataFrame(
        {
            "ts_code": ["000001.SZ"] * 4,
            "trade_date": pd.date_range("2026-01-01", periods=4, freq="D"),
            "open": [10.0, 11.0, 9.0, 8.0],
            "next_open": [11.0, 9.0, 8.0, float("nan")],
            "sell_blocked_limit": [False, True, True, True],
        }
    )

    out = mod.add_delayed_exit_returns(df.copy(), [1], max_delay_days=1)

    assert not out.loc[0, "exit_fillable_1d"]
    assert pd.isna(out.loc[0, "exit_delay_1d"])
    assert pd.isna(out.loc[0, "ret_o2o_1d"])
