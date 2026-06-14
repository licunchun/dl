from __future__ import annotations

from agent.config import RunConfig
from agent.data_agent import build_dataset
from backtest_engine import evaluate_factor


def test_backtest_engine_package_exports_evaluator(tmp_path) -> None:
    cfg = RunConfig(
        run_date="20260604",
        data_root=tmp_path / "missing",
        output_root=tmp_path / "reports",
        knowledge_root=tmp_path / "knowledge_base",
        factor_library=tmp_path / "factor_library",
        offline=True,
    )
    df = build_dataset(cfg)
    result = evaluate_factor(df, {
        "factor_id": "F_VOL_REV_5",
        "name": "放量5日反转",
        "formula": "(1 - rank(ret_5)) * rank(amount_ratio_20)",
        "expression": "shock_reversal_5",
        "horizon_days": 5,
    })

    assert result["factor_id"] == "F_VOL_REV_5"
    assert "portfolio" in result
