"""Fast short-term A-share model search with LightGBM and WQ-style alphas.

This script is intentionally independent from the neural training pipeline. It
targets the urgent 2026-06-01 deployment workflow:

* use causal feature rows only;
* add shifted WorldQuant-style short-horizon alphas;
* select factors by pre-May daily/monthly IC stability;
* train fast tabular/ranking candidates;
* stop once the standard n=10,k=2 May backtest turns positive.
"""

from __future__ import annotations

import argparse
import json
import math
import pickle
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

try:
    import lightgbm as lgb
except ImportError:  # pragma: no cover - exercised only when dependency absent
    lgb = None

from sklearn.ensemble import HistGradientBoostingRegressor

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.short_term_competition_train import (  # noqa: E402
    MONEYFLOW_FEATURES,
    _add_moneyflow_features,
    _configure_data_dir,
    _merge_moneyflow,
    _read_moneyflow,
    _run_backtest,
)
from src import data_loader as dl  # noqa: E402
from src.eval import summarize, topk_spread  # noqa: E402
from src.features import compute_features, list_feature_cols  # noqa: E402
from src.labels import attach_labels, clip_outliers  # noqa: E402

CHECKPOINTS = PROJECT_ROOT / "checkpoints"
REPORTS = PROJECT_ROOT / "reports"
DAILY_LOGS = REPORTS / "daily_logs"
WQ_WINDOWS = (2, 3, 5, 10, 20)
EPS = 1e-8


@dataclass
class Candidate:
    name: str
    kind: str
    objective: str
    feature_set: str
    direction: str
    half_life_days: float
    num_leaves: int = 31
    learning_rate: float = 0.05
    n_estimators: int = 600
    max_iter: int = 400


def _rolling_last_rank(values: np.ndarray) -> float:
    vals = values[np.isfinite(values)]
    if len(vals) == 0:
        return np.nan
    return float(np.mean(vals <= vals[-1]))


def _rolling_decay(values: np.ndarray) -> float:
    vals = values[np.isfinite(values)]
    if len(vals) == 0:
        return np.nan
    weights = np.arange(1, len(vals) + 1, dtype=np.float64)
    return float(np.dot(vals, weights) / weights.sum())


def _per_stock_wq(g: pd.DataFrame) -> pd.DataFrame:
    g = g.sort_values("trade_date")
    out = g[["ts_code", "trade_date"]].copy()
    close = g["close"].astype(float)
    open_ = g["open"].astype(float)
    high = g["high"].astype(float)
    low = g["low"].astype(float)
    vwap = g["vwap"].astype(float)
    vol = g["vol"].astype(float)
    amount = g["amount"].astype(float)
    ret1 = np.log(close / close.shift(1))
    intraday = (close - open_) / (open_.abs() + EPS)
    vwap_gap = (close - vwap) / (close.abs() + EPS)
    money = pd.to_numeric(g.get("net_mf_amount", 0.0), errors="coerce")
    lg_buy = pd.to_numeric(g.get("buy_lg_amount", 0.0), errors="coerce") + pd.to_numeric(
        g.get("buy_elg_amount", 0.0), errors="coerce"
    )
    lg_sell = pd.to_numeric(g.get("sell_lg_amount", 0.0), errors="coerce") + pd.to_numeric(
        g.get("sell_elg_amount", 0.0), errors="coerce"
    )
    mf_ratio = money * 10.0 / (amount.abs() + EPS)
    mf_pressure = np.log1p(lg_buy.clip(lower=0.0)) - np.log1p(lg_sell.clip(lower=0.0))

    for w in WQ_WINDOWS:
        adv = vol.rolling(w).mean()
        ada = amount.rolling(w).mean()
        ret_w = np.log(close / close.shift(w))
        out[f"wq_ret_{w}"] = ret_w
        out[f"wq_rev_{w}"] = -ret_w
        out[f"wq_vol_ratio_{w}"] = vol / (adv + EPS) - 1.0
        out[f"wq_amt_ratio_{w}"] = amount / (ada + EPS) - 1.0
        out[f"wq_price_pos_{w}"] = (close - low.rolling(w).min()) / (
            (high.rolling(w).max() - low.rolling(w).min()).abs() + EPS
        )
        out[f"wq_intraday_sum_{w}"] = intraday.rolling(w).sum()
        out[f"wq_vwap_gap_{w}"] = close / (vwap.rolling(w).mean() + EPS) - 1.0
        out[f"wq_ts_rank_ret_{w}"] = (ret1 - ret1.rolling(w).min()) / (
            (ret1.rolling(w).max() - ret1.rolling(w).min()).abs() + EPS
        )
        out[f"wq_mf_ratio_ma_{w}"] = mf_ratio.rolling(w).mean()
        out[f"wq_mf_pressure_ma_{w}"] = mf_pressure.rolling(w).mean()
        if w >= 5:
            out[f"wq_corr_ret_vol_{w}"] = ret1.rolling(w).corr(vol / (adv + EPS))
    return out


def add_wq_alpha_features(feats: pd.DataFrame, panel: pd.DataFrame) -> pd.DataFrame:
    """Append shifted daily-rank WQ-style alphas to an existing feature frame.

    The alpha layer intentionally uses the already-causal base features for most
    formulas. This is much faster than computing many rolling formulas stock by
    stock, and still gives the tree model WorldQuant-like rank/reversal/momentum
    signals in the three-hour rescue window.
    """
    raw = _fast_wq_raw(feats, panel)
    raw_cols = [c for c in raw.columns if c.startswith("wq_")]
    basic = dl.load_basic()[["ts_code", "industry"]]
    industry = raw["ts_code"].map(basic.set_index("ts_code")["industry"])
    ranked_parts: dict[str, pd.Series] = {}
    for col in raw_cols:
        rank_col = f"{col}_rk"
        ranked_parts[rank_col] = raw.groupby(raw["trade_date"])[col].rank(pct=True, method="average")
        if _needs_industry_neutral_rank(col):
            neutral_col = f"{col}_indrk"
            neutral = raw[col] - raw[col].groupby([raw["trade_date"], industry], sort=False).transform("mean")
            ranked_parts[neutral_col] = neutral.groupby(raw["trade_date"]).rank(pct=True, method="average")

    ranked = pd.concat([raw[["ts_code", "trade_date"]], pd.DataFrame(ranked_parts)], axis=1)
    add_cols = list(ranked_parts)
    return feats.merge(ranked[["ts_code", "trade_date"] + add_cols], on=["ts_code", "trade_date"], how="left")


def _fast_wq_raw(feats: pd.DataFrame, panel: pd.DataFrame) -> pd.DataFrame:
    cols = [c for c in feats.columns if c not in {"ts_code", "trade_date"}]
    df = feats[["ts_code", "trade_date"] + cols].copy()
    ohlc_cols = ["open", "high", "low", "close", "vwap", "vol", "amount"]
    ohlc = panel[["ts_code", "trade_date"] + [c for c in ohlc_cols if c in panel.columns]].copy()
    ohlc = ohlc.sort_values(["ts_code", "trade_date"]).reset_index(drop=True)
    if {"open", "high", "low", "close", "vwap"}.issubset(ohlc.columns):
        ohlc["wq_intraday_raw"] = (ohlc["close"] - ohlc["open"]) / (ohlc["open"].abs() + EPS)
        ohlc["wq_range_raw"] = (ohlc["high"] - ohlc["low"]) / (ohlc["close"].abs() + EPS)
        ohlc["wq_vwap_gap_raw"] = (ohlc["close"] - ohlc["vwap"]) / (ohlc["close"].abs() + EPS)
    if {"vol", "amount"}.issubset(ohlc.columns):
        ohlc["wq_amt_per_vol_raw"] = ohlc["amount"] / (ohlc["vol"].abs() + EPS)
    raw_ohlc = [c for c in ohlc.columns if c.startswith("wq_")]
    if raw_ohlc:
        ohlc[raw_ohlc] = ohlc.groupby("ts_code", sort=False)[raw_ohlc].shift(1)
        df = df.merge(ohlc[["ts_code", "trade_date"] + raw_ohlc], on=["ts_code", "trade_date"], how="left")

    def s(name: str) -> pd.Series:
        if name in df.columns:
            return pd.to_numeric(df[name], errors="coerce")
        return pd.Series(np.nan, index=df.index)

    raw = df[["ts_code", "trade_date"]].copy()
    raw["wq_rev_1"] = -s("ret_1")
    raw["wq_rev_5"] = -s("ret_5")
    raw["wq_rev_20"] = -s("ret_20")
    raw["wq_mom_1"] = s("ret_1")
    raw["wq_mom_5"] = s("ret_5")
    raw["wq_mom_20"] = s("ret_20")
    raw["wq_mom_5_20"] = s("ret_5") - s("ret_20")
    raw["wq_rev_accel"] = -(s("ret_1") - s("ret_5"))
    raw["wq_ma_revert_5"] = -s("ma_5")
    raw["wq_ma_revert_20"] = -s("ma_20")
    raw["wq_trend_ma"] = s("ma_5") - s("ma_20")
    raw["wq_vwap_revert"] = -s("vwap_dev")
    raw["wq_low_vol_5"] = -s("std_5")
    raw["wq_low_vol_20"] = -s("std_20")
    raw["wq_vol_breakout"] = s("vol_ratio_5")
    raw["wq_vol_reversal"] = -s("vol_ratio_5") * s("ret_1")
    raw["wq_amihud_liq"] = -s("amihud_20")
    raw["wq_rsi_center"] = -(s("rsi_14") - 50.0).abs()
    raw["wq_rsi_mom"] = s("rsi_14")
    raw["wq_macd"] = s("macd")
    raw["wq_macd_hist"] = s("macd_hist")
    raw["wq_small_size"] = -s("mv_log")
    raw["wq_value_pe"] = s("pe_inv")
    raw["wq_value_pb"] = s("pb_inv")
    raw["wq_turnover"] = s("turn")
    raw["wq_turn_reversal"] = -s("turn") * s("ret_1")
    raw["wq_rank_rev_1"] = 1.0 - s("rk_ret_1")
    raw["wq_rank_rev_5"] = 1.0 - s("rk_ret_5")
    raw["wq_rank_mom_1"] = s("rk_ret_1")
    raw["wq_rank_mom_5"] = s("rk_ret_5")
    raw["wq_rank_turn"] = s("rk_turn")
    raw["wq_rank_small"] = 1.0 - s("rk_mv")
    raw["wq_mf_net"] = s("mf_net_amt_ratio")
    raw["wq_mf_vol"] = s("mf_net_vol_ratio")
    raw["wq_mf_lg"] = s("mf_lg_amt_ratio")
    raw["wq_mf_elg"] = s("mf_elg_amt_ratio")
    raw["wq_mf_pressure"] = s("mf_buy_pressure")
    raw["wq_mf_reversal"] = -s("mf_net_amt_ratio") * s("ret_1")
    raw["wq_mf_vwap"] = s("mf_net_amt_ratio") - s("vwap_dev")
    raw["wq_rank_mf_net"] = s("rk_mf_net_amt")
    raw["wq_rank_mf_lg"] = s("rk_mf_lg_amt")
    raw["wq_rank_mf_pressure"] = s("rk_mf_buy_pressure")
    raw["wq_intraday_reversal"] = -s("wq_intraday_raw")
    raw["wq_range_breakout"] = s("wq_range_raw")
    raw["wq_raw_vwap_revert"] = -s("wq_vwap_gap_raw")
    raw["wq_amt_per_vol"] = s("wq_amt_per_vol_raw")
    raw["wq_price_mf_combo"] = -s("ret_1") + s("mf_net_amt_ratio")
    raw["wq_safe_mom"] = s("ret_5") - s("std_5")
    return raw


def _needs_industry_neutral_rank(col: str) -> bool:
    core = (
        "wq_rev_1", "wq_rev_5", "wq_mom_5", "wq_mom_20",
        "wq_vwap_revert", "wq_vol_breakout", "wq_mf_net",
        "wq_mf_lg", "wq_mf_pressure", "wq_raw_vwap_revert",
        "wq_price_mf_combo", "wq_safe_mom",
    )
    return col in core


def _load_or_build_frames(args) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, list[str]]:
    _configure_data_dir(args.data_dir)
    args.cache_dir.mkdir(parents=True, exist_ok=True)
    panel_cache = args.cache_dir / f"panel_{args.build_start}_{args.data_end}.parquet"
    base_feats_cache = args.cache_dir / f"features_moneyflow_{args.build_start}_{args.data_end}.parquet"
    labels_cache = args.cache_dir / f"labels_nofuturelimit_{args.build_start}_{args.data_end}.parquet"
    wq_feats_cache = args.cache_dir / f"features_wq_{args.build_start}_{args.data_end}.parquet"

    if panel_cache.exists() and base_feats_cache.exists() and labels_cache.exists() and wq_feats_cache.exists() and not args.rebuild_cache:
        panel = pd.read_parquet(panel_cache)
        feats = pd.read_parquet(wq_feats_cache)
        labels = pd.read_parquet(labels_cache)
    else:
        if panel_cache.exists() and not args.rebuild_cache:
            panel = pd.read_parquet(panel_cache)
        else:
            panel = dl.build_panel(dl.PanelBuildConfig(
                start=args.build_start,
                end=args.data_end,
                cache_path=panel_cache,
                include_metric=True,
            ))
            moneyflow = _read_moneyflow(args.data_dir, args.build_start, args.data_end)
            panel = _merge_moneyflow(panel, moneyflow)
            panel.to_parquet(panel_cache, index=False)

        if base_feats_cache.exists() and not args.rebuild_cache:
            base_feats = pd.read_parquet(base_feats_cache)
        else:
            base_feats = _add_moneyflow_features(compute_features(panel), panel)
            base_feats.to_parquet(base_feats_cache, index=False)

        feats = add_wq_alpha_features(base_feats, panel)
        feats.to_parquet(wq_feats_cache, index=False)
        labels = clip_outliers(attach_labels(panel, drop_limit_tomorrow=False), "y", 0.005)
        labels.to_parquet(labels_cache, index=False)

    base_cols = list_feature_cols(feats) + [c for c in MONEYFLOW_FEATURES if c in feats.columns]
    wq_cols = [c for c in feats.columns if c.startswith("wq_")]
    feature_cols = list(dict.fromkeys(base_cols + wq_cols))
    return panel, feats, labels, feature_cols


def _merge_xy(
    feats: pd.DataFrame,
    labels: pd.DataFrame,
    feature_cols: list[str],
    start: str,
    end: str,
) -> pd.DataFrame:
    df = feats[["ts_code", "trade_date"] + feature_cols].merge(
        labels[["ts_code", "trade_date", "y", "drop_reason"]],
        on=["ts_code", "trade_date"],
        how="inner",
    )
    lo, hi = pd.Timestamp(start), pd.Timestamp(end)
    df = df[(df["trade_date"] >= lo) & (df["trade_date"] <= hi)]
    df = df[df["y"].notna() & (df["drop_reason"] == "")]
    return df.sort_values(["trade_date", "ts_code"]).reset_index(drop=True)


def _daily_group_indices(df: pd.DataFrame) -> list[tuple[pd.Timestamp, np.ndarray]]:
    return [(pd.Timestamp(d), g.index.to_numpy()) for d, g in df.groupby("trade_date", sort=True)]


def _safe_corr(x: np.ndarray, y: np.ndarray) -> float:
    mask = np.isfinite(x) & np.isfinite(y)
    if mask.sum() < 30:
        return float("nan")
    x = x[mask]
    y = y[mask]
    if np.std(x) < 1e-12 or np.std(y) < 1e-12:
        return float("nan")
    return float(np.corrcoef(x, y)[0, 1])


def select_features(
    train_df: pd.DataFrame,
    feature_cols: list[str],
    *,
    max_features: int,
    min_abs_ic: float,
    min_pos_rate: float,
) -> tuple[list[str], pd.DataFrame]:
    groups = _daily_group_indices(train_df)
    y = train_df["y"].to_numpy(dtype=np.float64)
    rows: list[dict[str, float | str]] = []
    for col in feature_cols:
        vals = train_df[col].to_numpy(dtype=np.float64)
        daily = []
        for d, idx in groups:
            ic = _safe_corr(vals[idx], y[idx])
            if math.isfinite(ic):
                daily.append((d, ic))
        if not daily:
            continue
        daily_df = pd.DataFrame(daily, columns=["trade_date", "ic"])
        daily_df["month"] = daily_df["trade_date"].dt.to_period("M").astype(str)
        monthly = daily_df.groupby("month")["ic"].mean()
        mean_ic = float(daily_df["ic"].mean())
        abs_mean_ic = abs(mean_ic)
        pos_rate = float((np.sign(monthly) == np.sign(mean_ic)).mean()) if mean_ic != 0 else 0.0
        recent = monthly.tail(3)
        recent_ok = bool((np.sign(recent) == np.sign(mean_ic)).mean() >= 2 / 3) if len(recent) else False
        rows.append({
            "feature": col,
            "mean_ic": mean_ic,
            "abs_mean_ic": abs_mean_ic,
            "pos_rate": pos_rate,
            "recent3_mean_ic": float(recent.mean()) if len(recent) else float("nan"),
            "recent_ok": recent_ok,
            "n_days": int(len(daily_df)),
        })
    report = pd.DataFrame(rows).sort_values("abs_mean_ic", ascending=False)
    strict = report[
        (report["abs_mean_ic"] >= min_abs_ic)
        & (report["pos_rate"] >= min_pos_rate)
        & (report["recent_ok"])
    ]
    chosen = strict["feature"].head(max_features).tolist()
    if len(chosen) < min(30, max_features):
        chosen = report["feature"].head(max_features).tolist()
    return chosen, report


def _make_rank_labels(df: pd.DataFrame) -> np.ndarray:
    ranks = df.groupby("trade_date")["y"].rank(pct=True, method="average")
    labels = np.floor(ranks.fillna(0.0).to_numpy() * 5.0).astype(np.int32)
    return np.clip(labels, 0, 4)


def _date_weights(dates: pd.Series, train_end: str, half_life_days: float, min_weight: float) -> np.ndarray:
    if half_life_days <= 0:
        return np.ones(len(dates), dtype=np.float32)
    end_day = pd.Timestamp(train_end).to_datetime64().astype("datetime64[D]").astype("int64")
    day = dates.to_numpy(dtype="datetime64[D]").astype("int64")
    age = np.maximum(0, end_day - day)
    decay = np.exp(-np.log(2.0) * age / half_life_days)
    return (min_weight + (1.0 - min_weight) * decay).astype(np.float32)


def _matrix(df: pd.DataFrame, feature_cols: list[str]) -> np.ndarray:
    x = df[feature_cols].to_numpy(dtype=np.float32, copy=True)
    x[~np.isfinite(x)] = np.nan
    return x


def _groups_for_ranker(df: pd.DataFrame) -> list[int]:
    return [len(g) for _, g in df.groupby("trade_date", sort=True)]


def _fit_candidate(
    cand: Candidate,
    train_df: pd.DataFrame,
    val_df: pd.DataFrame,
    feature_cols: list[str],
    args,
):
    x_train = _matrix(train_df, feature_cols)
    y_train = train_df["y"].to_numpy(dtype=np.float32)
    x_val = _matrix(val_df, feature_cols)
    y_val = val_df["y"].to_numpy(dtype=np.float32)

    if cand.kind == "lgbm" and lgb is not None:
        common = {
            "random_state": args.seed,
            "n_jobs": args.num_threads,
            "learning_rate": cand.learning_rate,
            "n_estimators": cand.n_estimators,
            "num_leaves": cand.num_leaves,
            "subsample": 0.85,
            "colsample_bytree": 0.85,
            "min_child_samples": 80,
            "reg_alpha": 0.05,
            "reg_lambda": 0.5,
            "verbosity": -1,
        }
        callbacks = [lgb.early_stopping(args.early_stopping_rounds, verbose=False), lgb.log_evaluation(100)]
        if cand.objective == "rank_xendcg":
            model = lgb.LGBMRanker(
                objective="rank_xendcg",
                label_gain=[0, 1, 3, 7, 15],
                **common,
            )
            model.fit(
                x_train,
                _make_rank_labels(train_df),
                group=_groups_for_ranker(train_df),
                eval_set=[(x_val, _make_rank_labels(val_df))],
                eval_group=[_groups_for_ranker(val_df)],
                eval_at=[10],
                callbacks=callbacks,
            )
        else:
            model = lgb.LGBMRegressor(objective=cand.objective, **common)
            model.fit(
                x_train,
                y_train,
                sample_weight=_date_weights(
                    train_df["trade_date"], args.train_end, cand.half_life_days, args.min_date_weight
                ),
                eval_set=[(x_val, y_val)],
                eval_sample_weight=[
                    np.ones(len(y_val), dtype=np.float32),
                ],
                callbacks=callbacks,
            )
        return model

    model = HistGradientBoostingRegressor(
        loss="absolute_error",
        learning_rate=cand.learning_rate,
        max_iter=cand.max_iter,
        max_leaf_nodes=cand.num_leaves,
        l2_regularization=0.05,
        random_state=args.seed,
        early_stopping=True,
        validation_fraction=0.12,
    )
    model.fit(x_train, y_train, sample_weight=_date_weights(
        train_df["trade_date"], args.train_end, cand.half_life_days, args.min_date_weight
    ))
    return model


def _predict(model, df: pd.DataFrame, feature_cols: list[str], direction: str) -> pd.DataFrame:
    raw = model.predict(_matrix(df, feature_cols))
    score = -raw if direction == "inverse" else raw
    return pd.DataFrame({
        "ts_code": df["ts_code"].to_numpy(),
        "trade_date": df["trade_date"].to_numpy(),
        "y_pred": score.astype(float),
        "raw_pred": raw.astype(float),
        "y_true": df["y"].to_numpy(dtype=float),
    })


def _evaluate_candidate(
    cand: Candidate,
    model,
    val_df: pd.DataFrame,
    feature_cols: list[str],
    panel: pd.DataFrame,
) -> tuple[dict, pd.DataFrame]:
    preds = _predict(model, val_df, feature_cols, cand.direction)
    metrics = summarize(preds)
    spread = topk_spread(preds, k=10)
    metrics["top10_spread_bp"] = float(spread["spread"].mean() * 1e4) if len(spread) else float("nan")
    out_dir = REPORTS / f"backtest_{cand.name}"
    bt_stats = _run_backtest(preds, panel, out_dir)
    row = {
        "tag": cand.name,
        "kind": cand.kind,
        "objective": cand.objective,
        "feature_set": cand.feature_set,
        "direction": cand.direction,
        "half_life_days": cand.half_life_days,
        "num_leaves": cand.num_leaves,
        "learning_rate": cand.learning_rate,
        "features": len(feature_cols),
        "samples": len(preds),
        **metrics,
        **{f"bt_{k}": v for k, v in bt_stats.items()},
    }
    return row, preds


def _candidate_grid(args, feature_sets: dict[str, list[str]]) -> list[tuple[Candidate, list[str]]]:
    kind = "lgbm" if lgb is not None else "sklearn_hgb"
    objectives = ["regression_l1", "huber"]
    if lgb is not None:
        objectives.append("rank_xendcg")
    candidates: list[tuple[Candidate, list[str]]] = []
    idx = 0
    for feature_set, cols in feature_sets.items():
        if not cols:
            continue
        for objective in objectives:
            for half_life in (30.0, 60.0, 90.0):
                for direction in ("forward", "inverse"):
                    leaves = 15 if feature_set != "selected" else 31
                    lr = 0.05 if objective != "rank_xendcg" else 0.03
                    name = f"lgbm_wq_{idx:02d}_{feature_set}_{objective}_{direction}_hl{int(half_life)}"
                    if kind != "lgbm":
                        name = name.replace("lgbm", "hgb")
                    candidates.append((Candidate(
                        name=name,
                        kind=kind,
                        objective=objective if kind == "lgbm" else "absolute_error",
                        feature_set=feature_set,
                        direction=direction,
                        half_life_days=half_life,
                        num_leaves=leaves,
                        learning_rate=lr,
                        n_estimators=args.n_estimators,
                        max_iter=args.n_estimators,
                    ), cols))
                    idx += 1
    return candidates[: args.max_candidates]


def _build_target_frame(panel: pd.DataFrame, args) -> pd.DataFrame:
    asof = pd.Timestamp(args.asof_date)
    target = pd.Timestamp(args.target_date)
    base = panel[panel["trade_date"] <= asof].copy()
    last = base[base["trade_date"] == asof].copy()
    if last.empty:
        raise ValueError(f"No panel rows for as-of {args.asof_date}")
    synth = last.copy()
    synth["trade_date"] = target
    synth["pct_chg"] = 0.0
    return pd.concat([base, synth], ignore_index=True)


def _predict_target(
    model,
    feature_cols: list[str],
    panel: pd.DataFrame,
    best_row: dict,
    args,
) -> pd.DataFrame:
    target_panel = _build_target_frame(panel, args)
    target_feats = add_wq_alpha_features(_add_moneyflow_features(compute_features(target_panel), target_panel), target_panel)
    target_df = target_feats[target_feats["trade_date"] == pd.Timestamp(args.target_date)].copy()
    target_df = target_df.dropna(subset=feature_cols, how="all").reset_index(drop=True)
    if target_df.empty:
        raise ValueError(f"No target-day feature rows for {args.target_date}")
    raw = model.predict(_matrix(target_df, feature_cols))
    direction = str(best_row["direction"])
    score = -raw if direction == "inverse" else raw
    out = pd.DataFrame({
        "ts_code": target_df["ts_code"].to_numpy(),
        "raw_pred": raw.astype(float),
        "strategy_score": score.astype(float),
    }).sort_values("strategy_score", ascending=False).head(args.n)
    out.insert(0, "rank", np.arange(1, len(out) + 1))
    out.insert(1, "asof_date", args.asof_date)
    out.insert(2, "target_trade_date", args.target_date)
    out.insert(3, "tag", best_row["tag"])
    out.insert(4, "direction", direction)
    basic = dl.load_basic()[["ts_code", "name", "industry"]]
    out = out.merge(basic, on="ts_code", how="left")
    last = panel[panel["trade_date"] == pd.Timestamp(args.asof_date)].set_index("ts_code")
    out["ref_vwap"] = out["ts_code"].map(last["vwap"])
    out["ref_close"] = out["ts_code"].map(last["close"])
    return out


def _write_artifacts(
    row: dict,
    preds: pd.DataFrame,
    model,
    feature_cols: list[str],
    args,
) -> tuple[Path, Path, Path]:
    CHECKPOINTS.mkdir(exist_ok=True)
    out_dir = REPORTS / "may_2026_validation"
    out_dir.mkdir(parents=True, exist_ok=True)
    preds_path = out_dir / f"{row['tag']}_may_preds.parquet"
    model_path = CHECKPOINTS / f"{row['tag']}.pkl"
    preds.to_parquet(preds_path, index=False)
    with model_path.open("wb") as fh:
        pickle.dump({
            "model": model,
            "feature_cols": feature_cols,
            "row": row,
            "cfg": vars(args),
        }, fh)
    return preds_path, model_path, out_dir


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", type=Path, default=Path("/home/lcc17/pan_sync_20260528/A股数据"))
    ap.add_argument("--cache-dir", type=Path, default=Path("/home/lcc17/pan_sync_20260528/shortterm_cache"))
    ap.add_argument("--build-start", default="2025-01-01")
    ap.add_argument("--train-start", default="2025-01-01")
    ap.add_argument("--train-end", default="2026-04-30")
    ap.add_argument("--val-start", default="2026-05-06")
    ap.add_argument("--val-end", default="2026-05-27")
    ap.add_argument("--data-end", default="2026-05-28")
    ap.add_argument("--asof-date", default="2026-05-28")
    ap.add_argument("--target-date", default="2026-06-01")
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--max-features", type=int, default=80)
    ap.add_argument("--max-candidates", type=int, default=18)
    ap.add_argument("--n-estimators", type=int, default=600)
    ap.add_argument("--early-stopping-rounds", type=int, default=50)
    ap.add_argument("--time-budget-min", type=float, default=170.0)
    ap.add_argument("--min-abs-ic", type=float, default=0.005)
    ap.add_argument("--min-pos-rate", type=float, default=0.55)
    ap.add_argument("--min-date-weight", type=float, default=0.15)
    ap.add_argument("--num-threads", type=int, default=8)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--rebuild-cache", action="store_true")
    ap.add_argument("--stop-on-positive", action="store_true", default=True)
    args = ap.parse_args()

    np.random.seed(args.seed)
    started = time.monotonic()
    panel, feats, labels, all_features = _load_or_build_frames(args)
    train_df = _merge_xy(feats, labels, all_features, args.train_start, args.train_end)
    val_df = _merge_xy(feats, labels, all_features, args.val_start, args.val_end)
    print(f"[lgbm-wq] backend={'lightgbm' if lgb is not None else 'sklearn_hgb'}")
    print(f"[lgbm-wq] train={len(train_df)} val={len(val_df)} raw_features={len(all_features)}")

    selected, feature_report = select_features(
        train_df,
        all_features,
        max_features=args.max_features,
        min_abs_ic=args.min_abs_ic,
        min_pos_rate=args.min_pos_rate,
    )
    out_dir = REPORTS / "may_2026_validation"
    out_dir.mkdir(parents=True, exist_ok=True)
    feature_report.to_csv(out_dir / "lgbm_wq_feature_ic.csv", index=False)
    base_cols = [c for c in all_features if not c.startswith("wq_")]
    alpha_cols = [c for c in selected if c.startswith("wq_")]
    feature_sets = {
        "selected": selected,
        "alpha": alpha_cols[: args.max_features],
        "base_plus_alpha": list(dict.fromkeys(base_cols + alpha_cols[:40]))[: args.max_features],
    }
    print(f"[lgbm-wq] selected={len(selected)} alpha_selected={len(alpha_cols)}")

    rows: list[dict] = []
    best: tuple[dict, pd.DataFrame, object, list[str]] | None = None
    for cand, cols in _candidate_grid(args, feature_sets):
        elapsed_min = (time.monotonic() - started) / 60.0
        if elapsed_min > args.time_budget_min:
            print(f"[lgbm-wq] time budget reached at {elapsed_min:.1f} min")
            break
        print(f"[lgbm-wq] fitting {cand.name} features={len(cols)}")
        model = _fit_candidate(cand, train_df, val_df, cols, args)
        row, preds = _evaluate_candidate(cand, model, val_df, cols, panel)
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
        is_better = best is None or (
            row["bt_annualised"],
            row["bt_sharpe"],
            row["rank_ic"],
        ) > (
            best[0]["bt_annualised"],
            best[0]["bt_sharpe"],
            best[0]["rank_ic"],
        )
        if is_better:
            best = (row, preds, model, cols)
            _write_artifacts(row, preds, model, cols, args)
        if args.stop_on_positive and row["bt_annualised"] > 0 and row["bt_sharpe"] > 0:
            print(f"[lgbm-wq] positive May backtest found: {cand.name}")
            best = (row, preds, model, cols)
            break

    if not rows or best is None:
        raise RuntimeError("No candidate completed")

    summary = pd.DataFrame(rows).sort_values(["bt_annualised", "bt_sharpe"], ascending=False)
    summary_path = out_dir / "summary_lgbm_wq.csv"
    summary.to_csv(summary_path, index=False)
    (out_dir / "summary_lgbm_wq.json").write_text(
        json.dumps(rows, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    best_row, best_preds, best_model, best_cols = best
    preds_path, model_path, _ = _write_artifacts(best_row, best_preds, best_model, best_cols, args)
    targets = _predict_target(best_model, best_cols, panel, best_row, args)
    DAILY_LOGS.mkdir(parents=True, exist_ok=True)
    target_path = DAILY_LOGS / f"{args.target_date.replace('-', '')}_{best_row['tag']}_targets.csv"
    targets.to_csv(target_path, index=False, encoding="utf-8-sig")

    print(f"[lgbm-wq] wrote {summary_path}")
    print(f"[lgbm-wq] best {json.dumps(best_row, ensure_ascii=False)}")
    print(f"[lgbm-wq] wrote {preds_path}")
    print(f"[lgbm-wq] wrote {model_path}")
    print(f"[lgbm-wq] wrote {target_path}")
    print(targets.to_string(index=False))


if __name__ == "__main__":
    main()
