from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from . import backtest_agent
from .config import RunConfig, load_config
from .io_utils import read_json, write_json


FUTURE_FIELD_PATTERNS = ("forward_", "next_", "future_", "label", "target", "y_true")


def _factor_by_id(cfg: RunConfig) -> dict[str, dict[str, Any]]:
    factors = read_json(cfg.run_dir / "candidate_factors.json", {"factors": []})
    return {f.get("factor_id"): f for f in factors.get("factors", [])}


def _load_dataset(cfg: RunConfig) -> pd.DataFrame:
    manifest = read_json(cfg.run_dir / "dataset_manifest.json", {})
    path = manifest.get("dataset_path")
    if not path:
        return pd.DataFrame()
    try:
        return pd.read_parquet(path)
    except Exception:
        return pd.DataFrame()


def _leakage_checks(result: dict[str, Any], factor: dict[str, Any]) -> dict[str, Any]:
    text = " ".join(str(factor.get(k, "")) for k in ("factor_id", "formula", "expression", "name")).lower()
    uses_future_field = any(pattern in text for pattern in FUTURE_FIELD_PATTERNS)
    horizon = int(result.get("horizon_days") or factor.get("horizon_days") or 0)
    expected_ret = f"forward_ret_{horizon}d" if horizon else ""
    return {
        "uses_future_named_field": uses_future_field,
        "expected_label_column": expected_ret,
        "score": "fail" if uses_future_field else "pass",
    }


def _stability_checks(result: dict[str, Any]) -> dict[str, Any]:
    series = result.get("rankic_by_date") or []
    vals = pd.Series(
        [item.get("rankic") for item in series],
        index=pd.to_datetime([item.get("trade_date") for item in series], errors="coerce"),
        dtype=float,
    ).dropna()
    if vals.empty:
        return {
            "sample_days": 0,
            "positive_fraction": None,
            "monthly_positive_fraction": None,
            "score": "fail",
        }
    monthly = vals.groupby(vals.index.to_period("M")).mean()
    sample_days = int(len(vals))
    positive_fraction = float((vals > 0).mean())
    monthly_positive_fraction = float((monthly > 0).mean()) if len(monthly) else None
    score = "pass"
    if sample_days < 20 or positive_fraction < 0.45 or (monthly_positive_fraction is not None and monthly_positive_fraction < 0.45):
        score = "fail"
    elif sample_days < 60 or positive_fraction < 0.55:
        score = "warn"
    return {
        "sample_days": sample_days,
        "positive_fraction": positive_fraction,
        "monthly_positive_fraction": monthly_positive_fraction,
        "score": score,
    }


def _collinearity_checks(df: pd.DataFrame, factor: dict[str, Any]) -> dict[str, Any]:
    if df.empty or not factor.get("expression"):
        return {"max_abs_corr": None, "nearest_feature": None, "score": "unknown"}
    try:
        work = df.copy()
        work["score"] = backtest_agent.score_factor(work, factor["expression"])
    except Exception as exc:
        return {"max_abs_corr": None, "nearest_feature": None, "score": "unknown", "error": str(exc)[:200]}
    candidates = [
        "ret_1", "ret_5", "ret_20", "std_20", "amount_ratio_20", "vwap_dev",
        "pb_inv", "liq_inv", "low_vol", "mf_buy_pressure", "amihud_20",
    ]
    corrs: dict[str, float] = {}
    for col in candidates:
        if col not in work:
            continue
        sub = work[["score", col]].replace([np.inf, -np.inf], np.nan).dropna()
        if len(sub) < 10 or sub["score"].nunique() < 2 or sub[col].nunique() < 2:
            continue
        corr = sub["score"].rank().corr(sub[col].rank())
        if pd.notna(corr):
            corrs[col] = float(corr)
    if not corrs:
        return {"max_abs_corr": None, "nearest_feature": None, "score": "unknown"}
    nearest, corr = max(corrs.items(), key=lambda x: abs(x[1]))
    score = "fail" if abs(corr) >= 0.98 else ("warn" if abs(corr) >= 0.9 else "pass")
    return {"max_abs_corr": abs(corr), "nearest_feature": nearest, "score": score}


def critique_result(result: dict[str, Any], factor: dict[str, Any] | None = None, df: pd.DataFrame | None = None) -> dict[str, Any]:
    factor = factor or {}
    df = df if df is not None else pd.DataFrame()
    issues = []
    if result.get("rankic_mean") is None:
        issues.append("insufficient_rankic_sample")
    elif result["rankic_mean"] <= 0:
        issues.append("non_positive_rankic")
    portfolio = result.get("portfolio") or {}
    cost_sensitivity = result.get("cost_sensitivity") or {}
    high_cost = cost_sensitivity.get("20") or {}
    long_short = result.get("long_short") or {}
    if (portfolio.get("ann_return_net") or 0) <= 0:
        issues.append("non_positive_cost_adjusted_return")
    if (high_cost.get("ann_return_net") or 0) <= 0:
        issues.append("non_positive_high_cost_return")
    if (portfolio.get("turnover_mean") or 0) > 0.7:
        issues.append("high_turnover")
    if (portfolio.get("max_drawdown") or 0) < -0.4:
        issues.append("large_drawdown")
    if result.get("dates", 0) < 60:
        issues.append("insufficient_backtest_dates")
    if long_short and (long_short.get("ann_return_net") or 0) <= 0:
        issues.append("negative_long_short_diagnostic")
    leakage = _leakage_checks(result, factor)
    stability = _stability_checks(result)
    collinearity = _collinearity_checks(df, factor)
    if leakage["score"] != "pass":
        issues.append("potential_lookahead_field_reference")
    if stability["score"] == "fail":
        issues.append("unstable_rankic")
    elif stability["score"] == "warn":
        issues.append("weak_rankic_stability")
    if collinearity["score"] == "fail":
        issues.append("near_duplicate_existing_feature")
    elif collinearity["score"] == "warn":
        issues.append("high_collinearity_with_existing_feature")
    return {
        "factor_id": result.get("factor_id"),
        "decision": "promote" if not issues and result.get("decision") == "raw_candidate" else "kill",
        "issues": issues,
        "checks": {
            "leakage": leakage,
            "stability": stability,
            "collinearity": collinearity,
        },
        "leakage_check": "pass" if leakage["score"] == "pass" else "fail",
    }


def run(config: RunConfig | None = None) -> dict[str, Any]:
    cfg = config or load_config()
    results = read_json(cfg.run_dir / "backtest_results.json", {"results": []})
    factors = _factor_by_id(cfg)
    df = _load_dataset(cfg)
    critiques = [critique_result(r, factors.get(r.get("factor_id"), {}), df) for r in results.get("results", [])]
    lines = ["# Failure Analysis", "", f"Run date: {cfg.run_date}", ""]
    for item in critiques:
        lines += [
            f"## {item['factor_id']}",
            "",
            f"- decision: {item['decision']}",
            f"- issues: {', '.join(item['issues']) if item['issues'] else 'none'}",
            f"- leakage_check: {item['leakage_check']}",
            f"- stability: {item['checks']['stability']['score']}",
            f"- collinearity: {item['checks']['collinearity']['score']}",
            "",
        ]
    path = cfg.run_dir / "failure_analysis.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    payload = {"agent": "critic_agent", "run_date": cfg.run_date, "critiques": critiques}
    write_json(cfg.run_dir / "critique.json", payload)
    return payload


if __name__ == "__main__":
    run()
