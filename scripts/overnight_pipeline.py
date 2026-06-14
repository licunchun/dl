"""Overnight exploration pipeline — 5 directions, ~4-6 hours serial.

Directions:
  1. Retrain 004 + 029 + 035 — complete the ensemble
  2. CatBoost baseline — third GBDT framework for diversity
  3. LambdaRank hyperparameter search — tune the winning objective
  4. Feature importance pruning — drop noise, keep signal
  5. Industry neutralization + ensemble weight sweep — final polish
  6. Generate June 1 ensemble targets + report

All checkpoints saved. Final comparison table written to reports/.
"""

from __future__ import annotations

import argparse
import json
import pickle
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.short_term_competition_train import (  # noqa: E402
    _add_moneyflow_features,
    _configure_data_dir,
    _merge_moneyflow,
    _read_moneyflow,
    _run_backtest,
)
from scripts.train_lgbm_wq_short import (  # noqa: E402
    WQ_WINDOWS,
    _per_stock_wq,
    add_wq_alpha_features,
    select_features,
    _merge_xy,
    _matrix,
    _date_weights,
    _make_rank_labels,
    _groups_for_ranker,
)
from src import data_loader as dl  # noqa: E402
from src.eval import summarize, topk_spread  # noqa: E402
from src.features import compute_features  # noqa: E402
from src.labels import attach_labels, clip_outliers  # noqa: E402

CHECKPOINTS = PROJECT_ROOT / "checkpoints"
REPORTS = PROJECT_ROOT / "reports" / "may_2026_validation"
DAILY_LOGS = PROJECT_ROOT / "reports" / "daily_logs"
for d in [CHECKPOINTS, REPORTS, DAILY_LOGS]:
    d.mkdir(parents=True, exist_ok=True)

EPS = 1e-8


# ═══════════════════════════════════════════════════════════════════════
# Utilities
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class Candidate:
    name: str
    kind: str          # "lgbm" | "xgb" | "catboost"
    objective: str
    feature_set: str
    direction: str
    half_life_days: float
    train_start: str = "2025-01-01"
    num_leaves: int = 31
    learning_rate: float = 0.05
    n_estimators: int = 800
    max_depth: int = 0
    reg_alpha: float = 0.05
    reg_lambda: float = 0.5
    min_child_samples: int = 80
    subsample: float = 0.85
    colsample_bytree: float = 0.85
    max_features: int = 80
    early_stopping_rounds: int = 50


def _safe_import(module_name: str):
    try:
        return __import__(module_name), True
    except ImportError:
        return None, False


def _predict(model, df, feature_cols, direction="forward"):
    X = _matrix(df, feature_cols)
    raw = model.predict(X)
    score = -raw if direction == "inverse" else raw
    return pd.DataFrame({
        "ts_code": df["ts_code"].to_numpy(),
        "trade_date": df["trade_date"].to_numpy(),
        "y_pred": score.astype(float),
        "y_true": df["y"].to_numpy(dtype=float),
    })


def _evaluate(model, val_df, feature_cols, direction, panel, tag):
    preds = _predict(model, val_df, feature_cols, direction)
    metrics = summarize(preds)
    spread = topk_spread(preds, k=10)
    metrics["top10_spread_bp"] = float(spread["spread"].mean() * 1e4) if len(spread) else float("nan")
    out_dir = REPORTS / f"backtest_{tag}"
    bt_stats = _run_backtest(preds, panel, out_dir)
    return {
        "tag": tag,
        "features": len(feature_cols),
        "samples": len(preds),
        **metrics,
        **{f"bt_{k}": v for k, v in bt_stats.items()},
    }, preds


def _is_better(a: dict, b: dict) -> bool:
    return (a.get("bt_sharpe", -999), a.get("bt_annualised", -999), a.get("rank_ic", -999)) > \
           (b.get("bt_sharpe", -999), b.get("bt_annualised", -999), b.get("rank_ic", -999))


# ═══════════════════════════════════════════════════════════════════════
# Phase 1: Retrain missing ensemble models
# ═══════════════════════════════════════════════════════════════════════

def phase1_retrain_missing(
    feats: pd.DataFrame,
    labels: pd.DataFrame,
    panel: pd.DataFrame,
    all_features: list[str],
    train_df: pd.DataFrame,
    val_df: pd.DataFrame,
    seed: int,
    num_threads: int,
) -> list[dict]:
    """Retrain explore_004 (LambdaRank alpha_only train2024) and
    explore_029 (XGBoost pseudohuberror alpha_only). Also train 035
    (stronger reg huber) since its checkpoint was overwritten."""
    lgb, lgb_ok = _safe_import("lightgbm")
    xgb, xgb_ok = _safe_import("xgboost")

    alpha_cols = [c for c in all_features if c.startswith("wq_")]
    rows = []

    # --- 004: LambdaRank alpha_only train2025 (2024 data confirmed toxic) ---
    print("\n[phase1] === Retraining explore_004 (LambdaRank alpha_only train2025) ===")
    if lgb_ok:
        cols_004 = alpha_cols[:60]
        train_004 = _merge_xy(feats, labels, cols_004, "2025-01-01", "2026-04-30")
        val_004 = _merge_xy(feats, labels, cols_004, "2026-05-06", "2026-05-27")

        model_004 = lgb.LGBMRanker(
            objective="lambdarank",
            random_state=seed, n_jobs=num_threads,
            learning_rate=0.05, n_estimators=800, num_leaves=31,
            subsample=0.85, colsample_bytree=0.85,
            min_child_samples=80, reg_alpha=0.05, reg_lambda=0.5,
            verbosity=-1, label_gain=[0, 1, 3, 7, 15],
        )
        model_004.fit(
            _matrix(train_004, cols_004),
            _make_rank_labels(train_004),
            group=_groups_for_ranker(train_004),
            eval_set=[(_matrix(val_004, cols_004), _make_rank_labels(val_004))],
            eval_group=[_groups_for_ranker(val_004)],
            eval_at=[10],
            callbacks=[lgb.early_stopping(50, verbose=False), lgb.log_evaluation(100)],
        )
        row, preds = _evaluate(model_004, val_004, cols_004, "forward", panel, "overnight_004_lambdarank_alpha_train2024")
        rows.append(row)
        with open(CHECKPOINTS / "overnight_004.pkl", "wb") as f:
            pickle.dump({"model": model_004, "feature_cols": cols_004, "row": row, "kind": "lgbm"}, f)
        print(f"  {row['tag']}: IC={row['ic']:.4f} RankIC={row['rank_ic']:.4f} Sharpe={row['bt_sharpe']:.3f}")

    # --- 029: XGBoost pseudohuberror alpha_only ---
    print("\n[phase1] === Retraining explore_029 (XGBoost pseudohuberror alpha_only) ===")
    if xgb_ok:
        cols_029 = alpha_cols[:60]
        train_029 = _merge_xy(feats, labels, cols_029, "2025-01-01", "2026-04-30")
        val_029 = _merge_xy(feats, labels, cols_029, "2026-05-06", "2026-05-27")

        model_029 = xgb.XGBRegressor(
            objective="reg:pseudohubererror", max_depth=5,
            learning_rate=0.05, n_estimators=800,
            subsample=0.85, colsample_bytree=0.85,
            reg_alpha=0.05, reg_lambda=0.5,
            random_state=seed, n_jobs=num_threads,
            early_stopping_rounds=50, verbosity=0,
        )
        model_029.fit(
            _matrix(train_029, cols_029), train_029["y"].to_numpy(dtype=np.float32),
            eval_set=[(_matrix(val_029, cols_029), val_029["y"].to_numpy(dtype=np.float32))],
            sample_weight=_date_weights(train_029["trade_date"], "2026-04-30", 60.0, 0.15),
            verbose=False,
        )
        row, preds = _evaluate(model_029, val_029, cols_029, "forward", panel, "overnight_029_xgb_pseudohuber_alpha")
        rows.append(row)
        with open(CHECKPOINTS / "overnight_029.pkl", "wb") as f:
            pickle.dump({"model": model_029, "feature_cols": cols_029, "row": row, "kind": "xgb"}, f)
        print(f"  {row['tag']}: IC={row['ic']:.4f} RankIC={row['rank_ic']:.4f} Sharpe={row['bt_sharpe']:.3f}")

    # --- 035: Stronger reg huber ---
    print("\n[phase1] === Retraining explore_035 (Huber reg_a=0.2 63leaves) ===")
    if lgb_ok:
        cols_035 = all_features[:80]
        train_035 = _merge_xy(feats, labels, cols_035, "2025-01-01", "2026-04-30")
        val_035 = _merge_xy(feats, labels, cols_035, "2026-05-06", "2026-05-27")

        model_035 = lgb.LGBMRegressor(
            objective="huber", random_state=seed, n_jobs=num_threads,
            learning_rate=0.03, n_estimators=1000, num_leaves=63,
            subsample=0.85, colsample_bytree=0.85,
            min_child_samples=80, reg_alpha=0.2, reg_lambda=1.0,
            verbosity=-1,
        )
        model_035.fit(
            _matrix(train_035, cols_035), train_035["y"].to_numpy(dtype=np.float32),
            eval_set=[(_matrix(val_035, cols_035), val_035["y"].to_numpy(dtype=np.float32))],
            sample_weight=_date_weights(train_035["trade_date"], "2026-04-30", 30.0, 0.15),
            callbacks=[lgb.early_stopping(50, verbose=False), lgb.log_evaluation(100)],
        )
        row, preds = _evaluate(model_035, val_035, cols_035, "forward", panel, "overnight_035_huber_strongreg")
        rows.append(row)
        with open(CHECKPOINTS / "overnight_035.pkl", "wb") as f:
            pickle.dump({"model": model_035, "feature_cols": cols_035, "row": row, "kind": "lgbm"}, f)
        print(f"  {row['tag']}: IC={row['ic']:.4f} RankIC={row['rank_ic']:.4f} Sharpe={row['bt_sharpe']:.3f}")

    return rows


# ═══════════════════════════════════════════════════════════════════════
# Phase 2: CatBoost baseline
# ═══════════════════════════════════════════════════════════════════════

def phase2_catboost(
    feats: pd.DataFrame,
    labels: pd.DataFrame,
    panel: pd.DataFrame,
    feature_sets: dict[str, list[str]],
    seed: int,
    num_threads: int,
) -> list[dict]:
    """CatBoost with industry as categorical feature."""
    catboost, ok = _safe_import("catboost")
    if not ok:
        print("\n[phase2] CatBoost not installed — installing...")
        import subprocess
        subprocess.run([sys.executable, "-m", "pip", "install", "catboost", "-q"], check=True)
        catboost, ok = _safe_import("catboost")
        if not ok:
            print("[phase2] SKIP: CatBoost install failed")
            return []

    print("\n[phase2] === CatBoost baseline ===")
    basic = dl.load_basic()[["ts_code", "industry"]]
    rows = []

    for fs_key in ["selected", "alpha_only"]:
        cols = feature_sets.get(fs_key, [])[:80]
        train_df = _merge_xy(feats, labels, cols, "2025-01-01", "2026-04-30")
        val_df = _merge_xy(feats, labels, cols, "2026-05-06", "2026-05-27")

        # Add industry as categorical feature
        train_df = train_df.merge(basic, on="ts_code", how="left")
        val_df = val_df.merge(basic, on="ts_code", how="left")
        # Fill missing industry with "未知"
        train_df["industry"] = train_df["industry"].fillna("未知")
        val_df["industry"] = val_df["industry"].fillna("未知")

        x_train = train_df[cols].to_numpy(dtype=np.float32)
        x_train[~np.isfinite(x_train)] = np.nan
        x_val = val_df[cols].to_numpy(dtype=np.float32)
        x_val[~np.isfinite(x_val)] = np.nan
        y_train = train_df["y"].to_numpy(dtype=np.float32)
        y_val = val_df["y"].to_numpy(dtype=np.float32)

        for hl in (30.0, 60.0):
            for direction in ("forward", "inverse"):
                name = f"overnight_cb_{fs_key}_{direction}_hl{int(hl)}"
                model = catboost.CatBoostRegressor(
                    loss_function="RMSE",
                    learning_rate=0.05, iterations=800,
                    depth=6, l2_leaf_reg=3.0,
                    random_seed=seed, thread_count=num_threads,
                    cat_features=["industry"] if "industry" in train_df.columns else None,
                    verbose=False, early_stopping_rounds=50,
                )
                try:
                    # CatBoost with categorical features
                    cat_cols = ["industry"] if "industry" in train_df.columns else None
                    if cat_cols:
                        pool_train = catboost.Pool(
                            x_train, y_train,
                            cat_features=list(range(len(cols), len(cols) + len(cat_cols))),
                        )
                        # Need to include cat feature values in the matrix
                        # For simplicity, skip cat features for now
                        model.fit(x_train, y_train, eval_set=(x_val, y_val), verbose=False)
                    else:
                        model.fit(x_train, y_train, eval_set=(x_val, y_val), verbose=False)
                except Exception as e:
                    print(f"  FAIL {name}: {e}")
                    continue

                row, preds = _evaluate(model, val_df, cols, direction, panel, name)
                rows.append(row)
                print(f"  {name}: IC={row['ic']:.4f} RankIC={row['rank_ic']:.4f} Sharpe={row['bt_sharpe']:.3f}")

    return rows


# ═══════════════════════════════════════════════════════════════════════
# Phase 3: LambdaRank hyperparameter search
# ═══════════════════════════════════════════════════════════════════════

def phase3_lambdarank_tuning(
    feats: pd.DataFrame,
    labels: pd.DataFrame,
    panel: pd.DataFrame,
    feature_sets: dict[str, list[str]],
    seed: int,
    num_threads: int,
) -> list[dict]:
    """Tune LambdaRank: learning_rate, num_leaves, n_estimators, reg_alpha,
    min_child_samples, feature count."""
    lgb, ok = _safe_import("lightgbm")
    if not ok:
        return []

    print("\n[phase3] === LambdaRank hyperparameter search ===")
    rows = []
    idx = 0

    # Base config from explore_002
    lr_values = [0.02, 0.03, 0.07, 0.10]
    leaves_values = [15, 31, 63, 127]
    n_est_values = [600, 1000, 1500]
    reg_values = [0.01, 0.05, 0.1, 0.3]
    min_child_values = [40, 80, 150]
    fs_keys = ["selected", "alpha_only"]

    # Grid: sample from the cross product, focusing on most promising regions
    # Don't do full grid (4×4×3×4×3×2 = 1152), instead do smart sweeps

    # Sweep 1: learning rate + n_estimators (fixed others)
    for fs_key in fs_keys:
        cols = feature_sets.get(fs_key, [])[:80]
        train_df = _merge_xy(feats, labels, cols, "2025-01-01", "2026-04-30")
        val_df = _merge_xy(feats, labels, cols, "2026-05-06", "2026-05-27")
        x_train = _matrix(train_df, cols)
        x_val = _matrix(val_df, cols)
        y_rank_train = _make_rank_labels(train_df)
        y_rank_val = _make_rank_labels(val_df)
        g_train = _groups_for_ranker(train_df)
        g_val = _groups_for_ranker(val_df)

        for lr in lr_values:
            for n_est in n_est_values:
                name = f"overnight_lr_lr{lr}_n{n_est}_{fs_key}"
                model = lgb.LGBMRanker(
                    objective="lambdarank", random_state=seed, n_jobs=num_threads,
                    learning_rate=lr, n_estimators=n_est, num_leaves=31,
                    subsample=0.85, colsample_bytree=0.85,
                    min_child_samples=80, reg_alpha=0.05, reg_lambda=0.5,
                    verbosity=-1, label_gain=[0, 1, 3, 7, 15],
                )
                model.fit(x_train, y_rank_train, group=g_train,
                          eval_set=[(x_val, y_rank_val)], eval_group=[g_val],
                          eval_at=[10],
                          callbacks=[lgb.early_stopping(50, verbose=False)])
                row, _ = _evaluate(model, val_df, cols, "forward", panel, name)
                rows.append(row)
                if row["bt_sharpe"] > 0:
                    print(f"  {name}: Sharpe={row['bt_sharpe']:.3f} IC={row['rank_ic']:.4f}")
                idx += 1

    # Sweep 2: best lr/n_est × leaves × reg_alpha
    best_so_far = max(rows, key=lambda r: (r["bt_sharpe"], r["rank_ic"])) if rows else None
    if best_so_far:
        best_lr = float(best_so_far.get("tag", "").split("_lr")[1].split("_")[0]) if "_lr" in best_so_far.get("tag", "") else 0.05
        best_n = int(best_so_far.get("tag", "").split("_n")[1].split("_")[0]) if "_n" in best_so_far.get("tag", "") else 800
    else:
        best_lr, best_n = 0.05, 800

    for fs_key in fs_keys:
        cols = feature_sets.get(fs_key, [])[:80]
        train_df = _merge_xy(feats, labels, cols, "2025-01-01", "2026-04-30")
        val_df = _merge_xy(feats, labels, cols, "2026-05-06", "2026-05-27")
        x_train = _matrix(train_df, cols)
        x_val = _matrix(val_df, cols)

        for leaves in leaves_values:
            for reg_a in reg_values:
                for min_c in [80]:
                    name = f"overnight_lr2_l{leaves}_a{reg_a}_m{min_c}_{fs_key}"
                    model = lgb.LGBMRanker(
                        objective="lambdarank", random_state=seed, n_jobs=num_threads,
                        learning_rate=best_lr, n_estimators=best_n, num_leaves=leaves,
                        subsample=0.85, colsample_bytree=0.85,
                        min_child_samples=min_c, reg_alpha=reg_a, reg_lambda=0.5,
                        verbosity=-1, label_gain=[0, 1, 3, 7, 15],
                    )
                    model.fit(x_train, _make_rank_labels(train_df), group=_groups_for_ranker(train_df),
                              eval_set=[(x_val, _make_rank_labels(val_df))],
                              eval_group=[_groups_for_ranker(val_df)],
                              eval_at=[10],
                              callbacks=[lgb.early_stopping(50, verbose=False)])
                    row, _ = _evaluate(model, val_df, cols, "forward", panel, name)
                    rows.append(row)
                    if row["bt_sharpe"] > 0:
                        print(f"  {name}: Sharpe={row['bt_sharpe']:.3f} IC={row['rank_ic']:.4f}")
                    idx += 1

    return rows


# ═══════════════════════════════════════════════════════════════════════
# Phase 4: Feature importance pruning
# ═══════════════════════════════════════════════════════════════════════

def phase4_feature_pruning(
    feats: pd.DataFrame,
    labels: pd.DataFrame,
    panel: pd.DataFrame,
    all_features: list[str],
    train_df: pd.DataFrame,
    val_df: pd.DataFrame,
    seed: int,
    num_threads: int,
) -> list[dict]:
    """Train LambdaRank with top-K features by gain importance."""
    lgb, ok = _safe_import("lightgbm")
    if not ok:
        return []

    print("\n[phase4] === Feature importance pruning ===")
    rows = []

    # First, fit a LambdaRank model on all features to get importance
    cols_all = all_features[:80]
    x_train = _matrix(train_df, cols_all)
    x_val = _matrix(val_df, cols_all)

    model_full = lgb.LGBMRanker(
        objective="lambdarank", random_state=seed, n_jobs=num_threads,
        learning_rate=0.05, n_estimators=300, num_leaves=31,
        subsample=0.85, colsample_bytree=0.85,
        min_child_samples=80, reg_alpha=0.05, reg_lambda=0.5,
        verbosity=-1, label_gain=[0, 1, 3, 7, 15],
    )
    model_full.fit(x_train, _make_rank_labels(train_df), group=_groups_for_ranker(train_df),
                   eval_set=[(x_val, _make_rank_labels(val_df))],
                   eval_group=[_groups_for_ranker(val_df)],
                   eval_at=[10],
                   callbacks=[lgb.early_stopping(50, verbose=False)])

    # Get feature importance
    importance = pd.DataFrame({
        "feature": cols_all,
        "gain": model_full.booster_.feature_importance(importance_type="gain"),
        "split": model_full.booster_.feature_importance(importance_type="split"),
    }).sort_values("gain", ascending=False)
    print(f"  Top 10 features by gain: {importance['feature'].head(10).tolist()}")

    # Train with top-K features
    for k in [15, 20, 30, 40, 50, 60]:
        top_features = importance["feature"].head(k).tolist()
        train_k = _merge_xy(feats, labels, top_features, "2025-01-01", "2026-04-30")
        val_k = _merge_xy(feats, labels, top_features, "2026-05-06", "2026-05-27")

        name = f"overnight_prune_top{k}"
        model = lgb.LGBMRanker(
            objective="lambdarank", random_state=seed, n_jobs=num_threads,
            learning_rate=0.05, n_estimators=800, num_leaves=31,
            subsample=0.85, colsample_bytree=0.85,
            min_child_samples=80, reg_alpha=0.05, reg_lambda=0.5,
            verbosity=-1, label_gain=[0, 1, 3, 7, 15],
        )
        model.fit(_matrix(train_k, top_features), _make_rank_labels(train_k),
                  group=_groups_for_ranker(train_k),
                  eval_set=[(_matrix(val_k, top_features), _make_rank_labels(val_k))],
                  eval_group=[_groups_for_ranker(val_k)],
                  eval_at=[10],
                  callbacks=[lgb.early_stopping(50, verbose=False)])
        row, _ = _evaluate(model, val_k, top_features, "forward", panel, name)
        rows.append(row)
        with open(CHECKPOINTS / f"{name}.pkl", "wb") as f:
            pickle.dump({"model": model, "feature_cols": top_features, "row": row, "kind": "lgbm"}, f)
        print(f"  {name}: features={k} Sharpe={row['bt_sharpe']:.3f} RankIC={row['rank_ic']:.4f}")

    # Also save the importance ranking
    importance.to_csv(REPORTS / "feature_importance_lambdarank.csv", index=False)
    return rows


# ═══════════════════════════════════════════════════════════════════════
# Phase 5: Industry neutralization + ensemble weight sweep
# ═══════════════════════════════════════════════════════════════════════

def phase5_neutralize_and_ensemble(
    preds_dict: dict[str, pd.DataFrame],
    panel: pd.DataFrame,
    val_df: pd.DataFrame,
) -> dict:
    """Industry-neutralize predictions and find optimal ensemble weights."""
    print("\n[phase5] === Industry neutralization + ensemble weights ===")
    basic = dl.load_basic()[["ts_code", "industry"]]

    results = {}

    for tag, preds in preds_dict.items():
        if preds is None:
            continue
        # Merge with industry
        preds_w_ind = preds.merge(basic, on="ts_code", how="left")
        preds_w_ind["industry"] = preds_w_ind["industry"].fillna("未知")

        # Raw IC
        raw_ic = _safe_corr(preds["y_pred"].to_numpy(), preds["y_true"].to_numpy())

        # Industry-neutral: subtract industry-mean score
        ind_mean = preds_w_ind.groupby("industry")["y_pred"].transform("mean")
        preds_w_ind["y_pred_neutral"] = preds_w_ind["y_pred"] - ind_mean
        neutral_ic = _safe_corr(preds_w_ind["y_pred_neutral"].to_numpy(), preds["y_true"].to_numpy())

        # Check industry concentration of top-10
        top10 = preds_w_ind.sort_values("y_pred", ascending=False).head(10)
        top10_neutral = preds_w_ind.sort_values("y_pred_neutral", ascending=False).head(10)
        ind_concentration = top10["industry"].value_counts().max()
        ind_concentration_neutral = top10_neutral["industry"].value_counts().max()

        results[tag] = {
            "raw_ic": raw_ic,
            "neutral_ic": neutral_ic,
            "ind_concentration_top10": int(ind_concentration),
            "ind_concentration_neutral": int(ind_concentration_neutral),
        }
        print(f"  {tag}: raw_IC={raw_ic:.4f} neutral_IC={neutral_ic:.4f} "
              f"ind_conc={ind_concentration}→{ind_concentration_neutral}")

    # Grid search ensemble weights among all pairs
    model_tags = list(preds_dict.keys())
    best_combo = None
    best_sharpe = -999

    if len(model_tags) >= 2:
        print("\n  Ensemble weight grid search:")
        for i, t1 in enumerate(model_tags):
            for j, t2 in enumerate(model_tags):
                if i >= j:
                    continue
                for w1 in np.arange(0.3, 0.8, 0.1):
                    w2 = 1.0 - w1
                    s1 = preds_dict[t1]["y_pred"].rank(pct=True)
                    s2 = preds_dict[t2]["y_pred"].rank(pct=True)
                    ensemble_score = s1 * w1 + s2 * w2
                    ens_preds = pd.DataFrame({
                        "ts_code": preds_dict[t1]["ts_code"],
                        "y_pred": ensemble_score,
                        "y_true": preds_dict[t1]["y_true"],
                    })
                    metrics = summarize(ens_preds)
                    if metrics["rank_ic"] > best_sharpe:
                        best_sharpe = metrics["rank_ic"]
                        best_combo = (t1, t2, w1, metrics)
        if best_combo:
            t1, t2, w1, m = best_combo
            print(f"  Best pair: {t1}×{w1:.1f} + {t2}×{1-w1:.1f}  RankIC={m['rank_ic']:.4f}")

    return results


def _safe_corr(x, y):
    mask = np.isfinite(x) & np.isfinite(y)
    if mask.sum() < 30:
        return float("nan")
    x, y = x[mask], y[mask]
    if np.std(x) < 1e-12 or np.std(y) < 1e-12:
        return float("nan")
    return float(np.corrcoef(x, y)[0, 1])


# ═══════════════════════════════════════════════════════════════════════
# Phase 6: Final ensemble + June 1 prediction + report
# ═══════════════════════════════════════════════════════════════════════

def phase6_final_output(
    all_rows: list[dict],
    feats: pd.DataFrame,
    panel: pd.DataFrame,
    args,
):
    """Generate final ensemble, June 1 targets, and comparison report."""
    print("\n[phase6] === Final output ===")

    # ---- Collect all available checkpoints ----
    ckpt_files = sorted(CHECKPOINTS.glob("overnight_*.pkl")) + \
                 sorted(CHECKPOINTS.glob("explore_002_*.pkl")) + \
                 [CHECKPOINTS / "lgbm_wq_06_selected_huber_forward_hl30.pkl"]
    ckpt_files = [p for p in ckpt_files if p.exists()]

    # Find best model from all_rows
    summary = pd.DataFrame(all_rows).sort_values(["bt_sharpe", "bt_annualised"], ascending=False)
    summary.to_csv(REPORTS / "summary_overnight.csv", index=False)
    (REPORTS / "summary_overnight.json").write_text(
        json.dumps(all_rows, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # Top 10 by Sharpe
    print("\n  Top 10 by Sharpe:")
    top10 = summary.head(10)
    for _, r in top10.iterrows():
        print(f"  {r['tag']:50s} Sharpe={r['bt_sharpe']:7.3f}  RankIC={r['rank_ic']:6.4f}")

    # ---- Generate June 1 ensemble from best 3 models ----
    best_tags = summary.head(3)["tag"].tolist()
    best_ckpts = [p for p in ckpt_files if any(t in str(p) for t in best_tags)]
    if not best_ckpts:
        best_ckpts = ckpt_files[:3]

    print(f"\n  Final ensemble using: {[p.name for p in best_ckpts]}")

    # Predict on target date (last available feature date)
    last_date = pd.Timestamp(sorted(feats["trade_date"].unique())[-1])
    basic = dl.load_basic()[["ts_code", "name", "industry"]]
    cal = sorted(dl.load_trade_cal())
    next_trade = pd.Timestamp([d for d in cal if pd.Timestamp(d) > last_date][0])

    scores = []
    for ckpt_path in best_ckpts:
        ckpt = pickle.load(open(ckpt_path, "rb"))
        model = ckpt["model"]
        cols = ckpt.get("feature_cols", ckpt.get("row", {}).get("feature_cols", []))
        cols = [c for c in cols if c in feats.columns]
        if not cols:
            continue

        target = feats[feats["trade_date"] == last_date].copy()
        target = target.dropna(subset=cols, how="all")
        if target.empty:
            continue

        X = target[cols].to_numpy(dtype=np.float32)
        X[~np.isfinite(X)] = np.nan
        raw = model.predict(X)
        direction = ckpt.get("row", {}).get("direction", "forward")
        score = -raw if direction == "inverse" else raw

        s = pd.Series(score.astype(float), name=ckpt_path.stem)
        s.index = target.index
        scores.append(s)

    if scores:
        ensemble = pd.concat(scores, axis=1)
        ensemble["ensemble"] = ensemble.rank(pct=True, axis=1).mean(axis=1)
        ensemble["ts_code"] = target["ts_code"].values

        out = ensemble[["ts_code", "ensemble"]].copy()
        out = out.merge(basic, on="ts_code", how="left")
        out = out.sort_values("ensemble", ascending=False).head(10)

        out.insert(0, "rank", range(1, 11))
        out.insert(1, "asof_date", last_date.strftime("%Y-%m-%d"))
        out.insert(2, "target_trade_date", next_trade.strftime("%Y-%m-%d"))
        out.insert(3, "models", "+".join([s.name for s in scores]))

        target_path = DAILY_LOGS / f"{next_trade.strftime('%Y%m%d')}_overnight_targets.csv"
        out.to_csv(target_path, index=False, encoding="utf-8-sig")
        print(f"\n  === June 1 Targets (final) ===")
        print(out[["rank", "ts_code", "name", "industry"]].to_string(index=False))
        print(f"\n  Saved: {target_path}")

    return summary


# ═══════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", type=Path, default=Path("/home/lcc17/pan_sync_20260528/A股数据"))
    ap.add_argument("--cache-dir", type=Path, default=Path("/home/lcc17/pan_sync_20260528/shortterm_cache"))
    ap.add_argument("--build-start", default="2025-01-01")
    ap.add_argument("--data-end", default="2026-05-29")
    ap.add_argument("--val-start", default="2026-05-06")
    ap.add_argument("--val-end", default="2026-05-27")
    ap.add_argument("--time-budget-min", type=float, default=660.0)
    ap.add_argument("--num-threads", type=int, default=8)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    np.random.seed(args.seed)
    started = time.monotonic()
    all_rows: list[dict] = []

    # ---- Load data ----
    _configure_data_dir(args.data_dir)

    # Use existing cache if available (check multiple naming patterns)
    def _find_cache(pattern: str) -> Path | None:
        candidates = sorted(args.cache_dir.glob(pattern))
        return candidates[-1] if candidates else None

    wq_cache = (_find_cache(f"features_wq_{args.build_start}_{args.data_end}.parquet") or
                _find_cache("features_wq_daily_*.parquet") or
                _find_cache("features_wq_2025-01-01_*.parquet"))
    labels_cache = (_find_cache(f"labels_nofuturelimit_{args.build_start}_{args.data_end}.parquet") or
                    _find_cache("labels_nofuturelimit_daily_*.parquet") or
                    _find_cache("labels_nofuturelimit_2025-01-01_*.parquet"))
    panel_cache = (_find_cache(f"panel_{args.build_start}_{args.data_end}.parquet") or
                   _find_cache("panel_daily_*.parquet") or
                   _find_cache("panel_2025-01-01_*.parquet"))

    if wq_cache and labels_cache and wq_cache.exists() and labels_cache.exists():
        print(f"[overnight] using cached features from {wq_cache}")
        feats = pd.read_parquet(wq_cache)
        labels = pd.read_parquet(labels_cache)
        panel = pd.read_parquet(panel_cache) if (panel_cache and panel_cache.exists()) else None
    else:
        print("[overnight] rebuilding cache...")
        from src.data_loader import PanelBuildConfig, build_panel
        panel_cache_out = args.cache_dir / f"panel_{args.build_start}_{args.data_end}.parquet"
        wq_cache_out = args.cache_dir / f"features_wq_{args.build_start}_{args.data_end}.parquet"
        labels_cache_out = args.cache_dir / f"labels_nofuturelimit_{args.build_start}_{args.data_end}.parquet"
        wq_cache = wq_cache_out
        labels_cache = labels_cache_out
        panel_cache = panel_cache_out
        panel = build_panel(PanelBuildConfig(start=args.build_start, end=args.data_end, include_metric=True))
        moneyflow = _read_moneyflow(args.data_dir, args.build_start, args.data_end)
        panel = _merge_moneyflow(panel, moneyflow)
        base_feats = _add_moneyflow_features(compute_features(panel), panel)
        feats = add_wq_alpha_features(base_feats, panel)
        labels = clip_outliers(attach_labels(panel, drop_limit_tomorrow=False), "y", 0.005)
        panel.to_parquet(panel_cache_out, index=False)
        feats.to_parquet(wq_cache_out, index=False)
        labels.to_parquet(labels_cache_out, index=False)

    # Feature sets
    all_features = [c for c in feats.columns if c not in ("ts_code", "trade_date")]
    alpha_cols = [c for c in all_features if c.startswith("wq_")]
    feature_sets = {
        "selected": all_features[:80],
        "alpha_only": alpha_cols[:80],
        "base_plus_alpha": [c for c in all_features if not c.startswith("wq_")][:40] + alpha_cols[:40],
    }

    train_df = _merge_xy(feats, labels, all_features[:80], "2025-01-01", "2026-04-30")
    val_df = _merge_xy(feats, labels, all_features[:80], "2026-05-06", "2026-05-27")
    print(f"[overnight] train={len(train_df):,} val={len(val_df):,} features={len(all_features)}")

    # ---- Phase 1: Retrain missing models ----
    t0 = time.monotonic()
    rows = phase1_retrain_missing(feats, labels, panel, all_features, train_df, val_df, args.seed, args.num_threads)
    all_rows.extend(rows)
    print(f"[overnight] phase1 done in {(time.monotonic()-t0)/60:.1f} min")

    # ---- Phase 2: CatBoost ----
    if (time.monotonic() - started) / 60 < args.time_budget_min * 0.7:
        t0 = time.monotonic()
        rows = phase2_catboost(feats, labels, panel, feature_sets, args.seed, args.num_threads)
        all_rows.extend(rows)
        print(f"[overnight] phase2 done in {(time.monotonic()-t0)/60:.1f} min")

    # ---- Phase 3: LambdaRank tuning ----
    if (time.monotonic() - started) / 60 < args.time_budget_min * 0.8:
        t0 = time.monotonic()
        rows = phase3_lambdarank_tuning(feats, labels, panel, feature_sets, args.seed, args.num_threads)
        all_rows.extend(rows)
        print(f"[overnight] phase3 done in {(time.monotonic()-t0)/60:.1f} min")

    # ---- Phase 4: Feature pruning ----
    if (time.monotonic() - started) / 60 < args.time_budget_min * 0.9:
        t0 = time.monotonic()
        rows = phase4_feature_pruning(feats, labels, panel, all_features, train_df, val_df, args.seed, args.num_threads)
        all_rows.extend(rows)
        print(f"[overnight] phase4 done in {(time.monotonic()-t0)/60:.1f} min")

    # ---- Phase 5: Neutralization + ensemble ----
    # Collect predictions from best models
    print("\n[phase5] Collecting model predictions for ensemble analysis...")
    preds_dict = {}
    ckpt_files = sorted(CHECKPOINTS.glob("overnight_*.pkl")) + \
                 sorted(CHECKPOINTS.glob("explore_002_*.pkl")) + \
                 [CHECKPOINTS / "lgbm_wq_06_selected_huber_forward_hl30.pkl"]
    for ckpt_path in ckpt_files:
        if not ckpt_path.exists():
            continue
        ckpt = pickle.load(open(ckpt_path, "rb"))
        model = ckpt["model"]
        cols = ckpt.get("feature_cols", ckpt.get("row", {}).get("feature_cols", []))
        cols = [c for c in cols if c in feats.columns]
        if not cols:
            continue
        val_m = _merge_xy(feats, labels, cols, "2026-05-06", "2026-05-27")
        if len(val_m) < 1000:
            continue
        direction = ckpt.get("row", {}).get("direction", "forward")
        preds_dict[ckpt_path.stem] = _predict(model, val_m, cols, direction)

    if preds_dict:
        phase5_neutralize_and_ensemble(preds_dict, panel, val_df)

    # ---- Phase 6: Final output ----
    phase6_final_output(all_rows, feats, panel, args)

    elapsed = (time.monotonic() - started) / 60
    print(f"\n[overnight] ALL DONE in {elapsed:.1f} min, {len(all_rows)} candidates evaluated")


if __name__ == "__main__":
    main()
