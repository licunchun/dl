from __future__ import annotations

from typing import Any
from pathlib import Path
import hashlib

import math
import numpy as np
import pandas as pd

from .config import RunConfig, load_config
from .io_utils import ensure_dir, read_json, write_json


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _rank_by_date(df: pd.DataFrame, col: str) -> pd.Series:
    return df.groupby("trade_date")[col].rank(pct=True)


def score_factor(df: pd.DataFrame, expression: str) -> pd.Series:
    if expression == "shock_reversal_5":
        return (1 - _rank_by_date(df, "ret_5")) * _rank_by_date(df, "amount_ratio_20")
    if expression == "vwap_shock_reversal":
        return (1 - _rank_by_date(df, "vwap_dev")) * _rank_by_date(df, "amount_ratio_20")
    if expression == "moneyflow_exhaustion_reversal":
        return (1 - _rank_by_date(df, "ret_5")) * _rank_by_date(df, "mf_buy_pressure")
    if expression == "moneyflow_confirmed_momentum":
        return _rank_by_date(df, "ret_5") * _rank_by_date(df, "mf_buy_pressure")
    if expression == "value_liquidity_defensive":
        return (_rank_by_date(df, "pb_inv") + _rank_by_date(df, "liq_inv") + _rank_by_date(df, "low_vol")) / 3.0
    raise ValueError(f"unknown factor expression: {expression}")


def _rankic_by_date(df: pd.DataFrame, score_col: str, ret_col: str) -> pd.Series:
    vals = []
    for dt, g in df.groupby("trade_date", sort=True):
        sub = g[[score_col, ret_col]].replace([np.inf, -np.inf], np.nan).dropna()
        if len(sub) < 3 or sub[score_col].nunique() < 2:
            continue
        vals.append((dt, sub[score_col].rank().corr(sub[ret_col].rank())))
    return pd.Series(dict(vals), dtype=float)


def _long_only_metrics(df: pd.DataFrame, score_col: str, ret_col: str, cost_bps: float) -> dict[str, Any]:
    daily = []
    prev = set()
    for dt, g in df.groupby("trade_date", sort=True):
        sub = g[[score_col, ret_col, "ts_code"]].replace([np.inf, -np.inf], np.nan).dropna()
        if len(sub) < 3:
            continue
        cutoff = sub[score_col].quantile(0.8)
        long = sub[sub[score_col] >= cutoff]
        current = set(long["ts_code"])
        turnover = 1.0 if not prev else 1 - len(current & prev) / max(len(current), 1)
        prev = current
        net = float(long[ret_col].mean() - turnover * cost_bps / 10000.0)
        daily.append((dt, net, turnover, len(long)))
    if not daily:
        return {}
    out = pd.DataFrame(daily, columns=["date", "net", "turnover", "n_long"]).set_index("date")
    horizon = int(ret_col.split("_")[-1].removesuffix("d"))
    periods = 252 / max(horizon, 1)
    mean = out["net"].mean()
    std = out["net"].std()
    equity = (1 + out["net"].fillna(0)).cumprod()
    dd = equity / equity.cummax() - 1
    return {
        "portfolio_type": "long_only_top_quantile",
        "cost_bps": cost_bps,
        "periods_per_year": periods,
        "ann_return_net": float(mean * periods),
        "sharpe_net": float(mean / std * math.sqrt(periods)) if std and not np.isnan(std) else None,
        "max_drawdown": float(dd.min()),
        "turnover_mean": float(out["turnover"].mean()),
        "n_long_mean": float(out["n_long"].mean()),
        "days": int(len(out)),
    }


def _long_short_diagnostic(df: pd.DataFrame, score_col: str, ret_col: str, cost_bps: float) -> dict[str, Any]:
    daily = []
    prev_long: set[str] = set()
    prev_short: set[str] = set()
    for dt, g in df.groupby("trade_date", sort=True):
        sub = g[[score_col, ret_col, "ts_code"]].replace([np.inf, -np.inf], np.nan).dropna()
        if len(sub) < 4:
            continue
        low_cutoff = sub[score_col].quantile(0.2)
        high_cutoff = sub[score_col].quantile(0.8)
        long = sub[sub[score_col] >= high_cutoff]
        short = sub[sub[score_col] <= low_cutoff]
        if long.empty or short.empty:
            continue
        cur_long = set(long["ts_code"])
        cur_short = set(short["ts_code"])
        long_turnover = 1.0 if not prev_long else 1 - len(cur_long & prev_long) / max(len(cur_long), 1)
        short_turnover = 1.0 if not prev_short else 1 - len(cur_short & prev_short) / max(len(cur_short), 1)
        prev_long = cur_long
        prev_short = cur_short
        gross = float(long[ret_col].mean() - short[ret_col].mean())
        net = gross - (long_turnover + short_turnover) * cost_bps / 10000.0
        daily.append((dt, gross, net, (long_turnover + short_turnover) / 2.0, len(long), len(short)))
    if not daily:
        return {}
    out = pd.DataFrame(daily, columns=["date", "gross", "net", "turnover", "n_long", "n_short"]).set_index("date")
    horizon = int(ret_col.split("_")[-1].removesuffix("d"))
    periods = 252 / max(horizon, 1)
    mean = out["net"].mean()
    std = out["net"].std()
    equity = (1 + out["net"].fillna(0)).cumprod()
    dd = equity / equity.cummax() - 1
    return {
        "portfolio_type": "long_short_diagnostic_not_directly_tradable",
        "cost_bps": cost_bps,
        "periods_per_year": periods,
        "ann_return_net": float(mean * periods),
        "ann_return_gross": float(out["gross"].mean() * periods),
        "sharpe_net": float(mean / std * math.sqrt(periods)) if std and not np.isnan(std) else None,
        "max_drawdown": float(dd.min()),
        "turnover_mean": float(out["turnover"].mean()),
        "n_long_mean": float(out["n_long"].mean()),
        "n_short_mean": float(out["n_short"].mean()),
        "days": int(len(out)),
    }


def evaluate_factor(df: pd.DataFrame, factor: dict[str, Any], cost_bps: float = 10.0) -> dict[str, Any]:
    horizon = int(factor.get("horizon_days", 5))
    ret_col = f"forward_ret_{horizon}d"
    score_col = "score"
    x = df.copy()
    x[score_col] = score_factor(x, factor["expression"])
    x = x[~x.get("is_st", False).astype(bool)]
    x = x.replace([np.inf, -np.inf], np.nan).dropna(subset=[score_col, ret_col])
    ic = _rankic_by_date(x, score_col, ret_col)
    portfolio = _long_only_metrics(x, score_col, ret_col, cost_bps)
    long_short = _long_short_diagnostic(x, score_col, ret_col, cost_bps)
    cost_sensitivity = {
        str(int(c)): _long_only_metrics(x, score_col, ret_col, float(c))
        for c in (5.0, 10.0, 20.0)
    }
    sample_days = int(len(ic))
    long_only_ann = portfolio.get("ann_return_net") if portfolio else None
    long_only_sharpe = portfolio.get("sharpe_net") if portfolio else None
    high_cost_ann = (cost_sensitivity.get("20") or {}).get("ann_return_net")
    positive_rankic = (float(ic.mean()) if len(ic) else -1) > 0
    decision = "raw_candidate" if (
        sample_days >= 20
        and positive_rankic
        and (long_only_ann or -1) > 0
        and (long_only_sharpe or -1) > 0
        and (high_cost_ann or -1) > 0
    ) else "kill"
    return {
        "factor_id": factor["factor_id"],
        "name": factor["name"],
        "formula": factor["formula"],
        "formula_key": factor.get("formula_key"),
        "expression": factor["expression"],
        "horizon_days": horizon,
        "rankic_mean": float(ic.mean()) if len(ic) else None,
        "rankic_ir": float(ic.mean() / ic.std() * math.sqrt(252)) if len(ic) > 2 and ic.std() else None,
        "rankic_positive_frac": float((ic > 0).mean()) if len(ic) else None,
        "rankic_by_date": [
            {"trade_date": str(idx.date() if hasattr(idx, "date") else idx), "rankic": float(val)}
            for idx, val in ic.items()
        ],
        "portfolio": portfolio,
        "long_short": long_short,
        "cost_sensitivity": cost_sensitivity,
        "rows": int(len(x)),
        "dates": int(x["trade_date"].nunique()) if "trade_date" in x else 0,
        "decision": decision,
        "decision_note": (
            "raw backtest candidate; requires critic approval before promotion"
            if decision == "raw_candidate"
            else "failed raw backtest gate"
        ),
    }


def run(config: RunConfig | None = None) -> dict[str, Any]:
    cfg = config or load_config()
    manifest = read_json(cfg.run_dir / "dataset_manifest.json", {})
    factors = read_json(cfg.run_dir / "candidate_factors.json", {"factors": []})
    dataset_path = Path(manifest["dataset_path"])
    expected_sha = manifest.get("dataset_sha256")
    if not expected_sha:
        raise RuntimeError("dataset manifest is missing dataset_sha256")
    actual_sha = _sha256(dataset_path)
    if actual_sha != expected_sha:
        raise RuntimeError(
            "dataset hash mismatch before backtest: "
            f"expected={expected_sha} actual={actual_sha} path={dataset_path}"
        )
    dataset_provenance = {
        "dataset_path": str(dataset_path),
        "dataset_sha256": actual_sha,
        "dataset_size_bytes": manifest.get("dataset_size_bytes"),
        "rows": manifest.get("rows"),
        "stocks": manifest.get("stocks"),
        "dates": manifest.get("dates"),
        "source_mode": manifest.get("source_mode"),
        "health_status": manifest.get("health_status"),
        "hash_verified": True,
    }
    df = pd.read_parquet(dataset_path)
    out_dir = ensure_dir(cfg.run_dir / "backtest_results")
    results = []
    for factor in factors.get("factors", []):
        result = evaluate_factor(df, factor)
        results.append(result)
        write_json(out_dir / f"{factor['factor_id']}.json", result)
    payload = {
        "agent": "backtest_agent",
        "run_date": cfg.run_date,
        "dataset_provenance": dataset_provenance,
        "results": results,
    }
    write_json(cfg.run_dir / "backtest_results.json", payload)
    return payload


if __name__ == "__main__":
    run()
