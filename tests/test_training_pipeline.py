from __future__ import annotations

import numpy as np
import pandas as pd
import torch

from src import backtest
from src.features import compute_features
from src.train import build_model, build_model_from_checkpoint


def _param_count(model: torch.nn.Module) -> int:
    return sum(p.numel() for p in model.parameters())


def test_large_model_capacity_is_restored_from_checkpoint_cfg():
    model = build_model(
        "transformer",
        n_features=22,
        window=20,
        d_model=256,
        heads=8,
        layers=4,
        dropout=0.2,
    )
    ckpt = {
        "feature_cols": [f"f{i}" for i in range(22)],
        "cfg": {
            "model": "transformer",
            "window": 20,
            "d_model": 256,
            "heads": 8,
            "layers": 4,
            "dropout": 0.2,
        },
    }
    restored = build_model_from_checkpoint(ckpt)
    assert _param_count(model) == _param_count(restored)
    assert 3_000_000 <= _param_count(restored) <= 3_300_000


def test_backtest_tradable_filter_ignores_next_day_limit_move():
    dates = pd.to_datetime(["2025-01-02", "2025-01-03"])
    panel = pd.DataFrame({
        "ts_code": ["AAA.SH", "BBB.SZ", "AAA.SH", "BBB.SZ"],
        "trade_date": [dates[0], dates[0], dates[1], dates[1]],
        "close": [10.0, 10.0, 11.0, 10.2],
        "pct_chg": [0.0, 0.0, 10.0, 2.0],
    })
    preds = pd.DataFrame({
        "ts_code": ["AAA.SH", "BBB.SZ"],
        "trade_date": [dates[0], dates[0]],
        "y_pred": [1.0, 0.5],
    })

    scores = backtest._build_score_table(preds, panel)
    day = scores[scores["trade_date"] == dates[0]].set_index("ts_code")
    tradable = backtest._tradable_on_day(day, exclude_limit_up=True)

    assert "next_pct" not in scores.columns
    assert set(tradable.index) == {"AAA.SH", "BBB.SZ"}


def test_predict_daily_uses_asof_cutoff_and_next_trading_day(monkeypatch, tmp_path):
    import src.predict_daily as predict_daily

    dates = pd.bdate_range("2025-01-01", periods=26)
    asof = dates[-2]
    rows = []
    for code, base in [("AAA.SH", 10.0), ("BBB.SZ", 20.0)]:
        closes = base + np.arange(len(dates), dtype=float) * 0.1
        closes[-1] = 1e9
        for i, d in enumerate(dates):
            prev = closes[i - 1] if i else closes[i]
            rows.append({
                "ts_code": code,
                "trade_date": d,
                "open": closes[i],
                "high": closes[i],
                "low": closes[i],
                "close": closes[i],
                "pre_close": prev,
                "pct_chg": (closes[i] / prev - 1.0) * 100 if prev else 0.0,
                "vol": 1000.0,
                "amount": 100000.0,
                "vwap": closes[i],
                "turnover_rate": 1.0,
                "pe_ttm": 10.0,
                "pb": 1.0,
                "circ_mv": 1e8,
            })
    panel = pd.DataFrame(rows)

    def checked_compute_features(input_panel: pd.DataFrame) -> pd.DataFrame:
        assert input_panel["trade_date"].max() <= asof
        return compute_features(input_panel)

    class DummyModel(torch.nn.Module):
        def forward(self, x: torch.Tensor) -> torch.Tensor:
            return x[:, -1, 0]

    ckpt_dir = tmp_path / "checkpoints"
    ckpt_dir.mkdir()
    torch.save({
        "feature_cols": ["ret_1"],
        "model_state": {},
        "cfg": {"model": "mlp", "window": 20},
    }, ckpt_dir / "dummy.pt")

    monkeypatch.setattr(predict_daily, "CHECKPOINTS", ckpt_dir)
    monkeypatch.setattr(predict_daily, "load_panel", lambda: panel)
    monkeypatch.setattr(predict_daily, "load_trade_cal", lambda: pd.DatetimeIndex(dates))
    monkeypatch.setattr(predict_daily, "load_basic", lambda: pd.DataFrame({
        "ts_code": ["AAA.SH", "BBB.SZ"],
        "name": ["AAA", "BBB"],
        "industry": ["x", "y"],
    }))
    monkeypatch.setattr(predict_daily, "compute_features", checked_compute_features)
    monkeypatch.setattr(predict_daily, "build_model_from_checkpoint", lambda *a, **k: DummyModel())

    out = predict_daily.predict_for_date("mlp", asof, n=2, tag="dummy")

    assert set(out["asof_date"]) == {asof.strftime("%Y-%m-%d")}
    assert set(out["target_trade_date"]) == {dates[-1].strftime("%Y-%m-%d")}
    assert len(out) == 2
