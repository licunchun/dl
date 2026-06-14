from __future__ import annotations

import numpy as np
import pandas as pd
import torch

from src import backtest
from src.features import compute_features
from src.labels import attach_labels
from src.train import build_model, build_model_from_checkpoint, date_recency_weight


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


def test_inference_uses_checkpoint_window_by_default():
    model = build_model(
        "lstm",
        n_features=22,
        window=40,
        hidden=256,
        layers=3,
        dropout=0.2,
    )
    ckpt = {
        "feature_cols": [f"f{i}" for i in range(22)],
        "cfg": {
            "model": "lstm",
            "window": 40,
            "hidden": 256,
            "layers": 3,
            "dropout": 0.2,
        },
    }
    restored = build_model_from_checkpoint(ckpt)
    assert _param_count(model) == _param_count(restored)


def test_recency_weight_defaults_to_one_and_decays_by_age():
    old = torch.tensor([pd.Timestamp("2024-01-02").to_datetime64().astype("datetime64[D]").astype("int64")])
    recent = torch.tensor([pd.Timestamp("2024-12-31").to_datetime64().astype("datetime64[D]").astype("int64")])

    disabled = date_recency_weight(old, train_end="2024-12-31", half_life_days=0, min_weight=0.25)
    old_weight = date_recency_weight(old, train_end="2024-12-31", half_life_days=180, min_weight=0.25)
    recent_weight = date_recency_weight(recent, train_end="2024-12-31", half_life_days=180, min_weight=0.25)

    assert disabled.item() == 1.0
    assert 0.25 <= old_weight.item() < recent_weight.item()
    assert recent_weight.item() == 1.0


def test_sklearn_baseline_emits_compare_compatible_predictions():
    from scripts.train_sklearn_baseline import collect_sklearn_preds, train_sgd_baseline
    from src.dataset import WindowDataset

    dates = pd.bdate_range("2024-01-01", periods=6)
    feats = pd.DataFrame({
        "ts_code": ["AAA.SH"] * 6 + ["BBB.SZ"] * 6,
        "trade_date": list(dates) * 2,
        "ret_1": [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.5, 0.4, 0.3, 0.2, 0.1, 0.0],
        "rk_ret_1": [0.5] * 12,
    })
    labels = pd.DataFrame({
        "ts_code": ["AAA.SH"] * 6 + ["BBB.SZ"] * 6,
        "trade_date": list(dates) * 2,
        "y": [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.5, 0.4, 0.3, 0.2, 0.1, 0.0],
        "drop_reason": [""] * 12,
    })
    train_ds = WindowDataset(
        feats, labels, ["ret_1", "rk_ret_1"], window=2,
        date_range=("2024-01-01", "2024-01-05"),
    )
    val_ds = WindowDataset(
        feats, labels, ["ret_1", "rk_ret_1"], window=2,
        date_range=("2024-01-05", "2024-01-08"),
    )

    model = train_sgd_baseline(
        train_ds,
        train_end="2024-01-05",
        epochs=1,
        lr=1e-3,
        alpha=1e-5,
        batch_cap=None,
        min_stocks=1,
        half_life_days=0,
        min_date_weight=0.25,
        seed=42,
    )
    preds = collect_sklearn_preds(model, val_ds, batch_cap=None, min_stocks=1)

    assert set(preds.columns) == {"ts_code", "trade_date", "y_pred", "y_true"}
    assert len(preds) == 2
    assert preds["y_pred"].notna().all()


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


def test_labels_can_keep_future_limit_rows_for_leakage_free_eval():
    dates = pd.to_datetime(["2025-01-02", "2025-01-03", "2025-01-06"])
    panel = pd.DataFrame({
        "ts_code": ["AAA.SH"] * 3,
        "trade_date": dates,
        "close": [10.0, 11.0, 11.2],
        "pct_chg": [0.0, 10.0, 1.8],
    })

    default = attach_labels(panel)
    no_censor = attach_labels(panel, drop_limit_tomorrow=False)

    assert default.loc[0, "drop_reason"] == "limit_tomorrow"
    assert pd.isna(default.loc[0, "y"])
    assert no_censor.loc[0, "drop_reason"] == ""
    assert np.isfinite(no_censor.loc[0, "y"])


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
        assert input_panel["trade_date"].max() == dates[-1]
        target_rows = input_panel[input_panel["trade_date"] == dates[-1]]
        assert set(target_rows["ts_code"]) == {"AAA.SH", "BBB.SZ"}
        asof_close = panel[panel["trade_date"] == asof].set_index("ts_code")["close"]
        assert target_rows.set_index("ts_code")["close"].equals(asof_close)
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


def test_predict_daily_inverse_selects_lowest_raw_score(monkeypatch, tmp_path):
    import src.predict_daily as predict_daily

    dates = pd.bdate_range("2025-01-01", periods=26)
    asof = dates[-2]
    rows = []
    for code, base in [("AAA.SH", 10.0), ("BBB.SZ", 20.0)]:
        closes = base + np.arange(len(dates), dtype=float) * 0.1
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

    class OrderedModel(torch.nn.Module):
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
    monkeypatch.setattr(predict_daily, "build_model_from_checkpoint", lambda *a, **k: OrderedModel())

    forward = predict_daily.predict_for_date("mlp", asof, n=1, tag="dummy", direction="forward")
    inverse = predict_daily.predict_for_date("mlp", asof, n=1, tag="dummy", direction="inverse")

    assert forward["ts_code"].iloc[0] != inverse["ts_code"].iloc[0]
    assert forward["strategy_score"].iloc[0] == forward["y_pred"].iloc[0]
    assert inverse["strategy_score"].iloc[0] == -inverse["y_pred"].iloc[0]


def test_wq_alpha_features_are_shifted_and_causal(monkeypatch):
    import scripts.train_lgbm_wq_short as wq

    dates = pd.bdate_range("2025-01-01", periods=32)
    rows = []
    for code, base in [("AAA.SH", 10.0), ("BBB.SZ", 20.0)]:
        for i, d in enumerate(dates):
            close = base + i * 0.1
            rows.append({
                "ts_code": code,
                "trade_date": d,
                "open": close - 0.03,
                "high": close + 0.08,
                "low": close - 0.08,
                "close": close,
                "pre_close": close - 0.1 if i else close,
                "pct_chg": 0.0 if i == 0 else close / (close - 0.1) * 100 - 100,
                "vol": 1000.0 + i * 10,
                "amount": 100000.0 + i * 1000,
                "vwap": close - 0.01,
                "turnover_rate": 1.0,
                "pe_ttm": 10.0,
                "pb": 1.0,
                "circ_mv": 1e8,
                "buy_lg_amount": 20.0 + i,
                "sell_lg_amount": 10.0,
                "buy_elg_amount": 5.0,
                "sell_elg_amount": 3.0,
                "net_mf_vol": 100.0 + i,
                "net_mf_amount": 30.0 + i,
            })
    panel = pd.DataFrame(rows)
    base_feats = panel[["ts_code", "trade_date"]].copy()
    monkeypatch.setattr(wq.dl, "load_basic", lambda: pd.DataFrame({
        "ts_code": ["AAA.SH", "BBB.SZ"],
        "industry": ["x", "y"],
    }))

    clean = wq.add_wq_alpha_features(base_feats, panel)
    poisoned_panel = panel.copy()
    poisoned_panel.loc[poisoned_panel["trade_date"] > dates[24], "close"] = 1e9
    poisoned = wq.add_wq_alpha_features(base_feats, poisoned_panel)

    cols = [c for c in clean.columns if c.startswith("wq_")]
    probe = dates[20]
    clean_row = clean[clean["trade_date"] == probe].sort_values("ts_code")[cols].reset_index(drop=True)
    poisoned_row = poisoned[poisoned["trade_date"] == probe].sort_values("ts_code")[cols].reset_index(drop=True)

    pd.testing.assert_frame_equal(clean_row, poisoned_row)
