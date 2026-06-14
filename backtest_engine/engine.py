from __future__ import annotations

from typing import Any

import pandas as pd

from agent.backtest_agent import evaluate_factor as _evaluate_factor
from agent.backtest_agent import score_factor as _score_factor


def score_factor(df: pd.DataFrame, expression: str) -> pd.Series:
    """Score a factor expression on a standard daily dataset."""
    return _score_factor(df, expression)


def evaluate_factor(df: pd.DataFrame, factor: dict[str, Any], cost_bps: float = 10.0) -> dict[str, Any]:
    """Evaluate one factor using the MVP long-only backtest."""
    return _evaluate_factor(df, factor, cost_bps=cost_bps)

