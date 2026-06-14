"""3-hour model exploration: LightGBM extended grid + XGBoost + shallow MLP.

Key untested directions based on web search (2025 best practices):
  1. LambdaRank objective — optimizes ranking directly, not point prediction
  2. Different data windows — 2024-only, 2024-mid, 2025-only train starts
  3. Feature set variations — alpha_only, base_plus_alpha, different counts
  4. XGBoost baseline — complementary to LightGBM
  5. More regularization — higher reg_alpha/lambda, lower learning rates

Design philosophy: fewer epochs, strong regularization, time-budget gating.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import pickle
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

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
from scripts.train_lgbm_wq_short import (  # noqa: E402
    _daily_group_indices,
    _date_weights,
    _matrix,
    _merge_xy,
    _safe_corr,
    add_wq_alpha_features,
    select_features,
)
from src.eval import summarize, topk_spread  # noqa: E402

CHECKPOINTS = PROJECT_ROOT / "checkpoints"
REPORTS = PROJECT_ROOT / "reports"
DAILY_LOGS = REPORTS / "daily_logs"
EPS = 1e-8


# ---------------------------------------------------------------------------
# Candidate definition
# ---------------------------------------------------------------------------

@dataclass
class Candidate:
    name: str
    kind: str          # lgbm | xgb | mlp
    objective: str
    feature_set: str
    direction: str
    half_life_days: float
    train_start: str
    num_leaves: int = 31
    learning_rate: float = 0.05
    n_estimators: int = 600
    max_depth: int = 0
    reg_alpha: float = 0.05
    reg_lambda: float = 0.5
    max_features: int = 80
    early_stopping_rounds: int = 50
    subsample: float = 0.85
    colsample_bytree: float = 0.85
    min_child_samples: int = 80


# ---------------------------------------------------------------------------
# LightGBM training
# ---------------------------------------------------------------------------

def _try_import_lgb():
    try:
        import lightgbm as lgb
        return lgb, True
    except ImportError:
        return None, False


def _try_import_xgb():
    try:
        import xgboost as xgb
        return xgb, True
    except ImportError:
        return None, False


def _groups_for_ranker(df: pd.DataFrame) -> list[int]:
    return [len(g) for _, g in df.groupby("trade_date", sort=True)]


def _make_rank_labels(df: pd.DataFrame) -> np.ndarray:
    ranks = df.groupby("trade_date")["y"].rank(pct=True, method="average")
    labels = np.floor(ranks.fillna(0.0).to_numpy() * 5.0).astype(np.int32)
    return np.clip(labels, 0, 4)


def _compute_feature_sets(
    all_features: list[str],
    max_features: int,
) -> dict[str, list[str]]:
    """Return different feature subsets for exploration."""
    base_cols = [c for c in all_features if not c.startswith("wq_")]
    alpha_cols = [c for c in all_features if c.startswith("wq_")]
    # selected is computed later with IC filtering, placeholder here
    return {
        "all": all_features[:max_features],
        "base_only": base_cols[:max_features],
        "alpha_only": alpha_cols[:max_features],
        "base_plus_alpha": list(dict.fromkeys(base_cols[:max(40, max_features // 2)] + alpha_cols[:max(40, max_features // 2)]))[:max_features],
    }


def _fit_lgbm(
    cand: Candidate,
    train_df: pd.DataFrame,
    val_df: pd.DataFrame,
    feature_cols: list[str],
    seed: int,
    num_threads: int,
):
    import lightgbm as lgb

    x_train = _matrix(train_df, feature_cols)
    y_train = train_df["y"].to_numpy(dtype=np.float32)
    x_val = _matrix(val_df, feature_cols)
    y_val = val_df["y"].to_numpy(dtype=np.float32)

    common = {
        "random_state": seed,
        "n_jobs": num_threads,
        "learning_rate": cand.learning_rate,
        "n_estimators": cand.n_estimators,
        "num_leaves": cand.num_leaves,
        "subsample": cand.subsample,
        "colsample_bytree": cand.colsample_bytree,
        "min_child_samples": cand.min_child_samples,
        "reg_alpha": cand.reg_alpha,
        "reg_lambda": cand.reg_lambda,
        "verbosity": -1,
    }
    if cand.max_depth > 0:
        common["max_depth"] = cand.max_depth

    callbacks = [lgb.early_stopping(cand.early_stopping_rounds, verbose=False), lgb.log_evaluation(200)]

    if cand.objective == "lambdarank":
        model = lgb.LGBMRanker(
            objective="lambdarank",
            metric="ndcg",
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
    elif cand.objective == "rank_xendcg":
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
        train_end = "2026-04-30"
        model.fit(
            x_train, y_train,
            sample_weight=_date_weights(train_df["trade_date"], train_end, cand.half_life_days, 0.15),
            eval_set=[(x_val, y_val)],
            callbacks=callbacks,
        )
    return model


# ---------------------------------------------------------------------------
# XGBoost training
# ---------------------------------------------------------------------------

def _fit_xgb(
    cand: Candidate,
    train_df: pd.DataFrame,
    val_df: pd.DataFrame,
    feature_cols: list[str],
    seed: int,
    num_threads: int,
):
    import xgboost as xgb

    x_train = _matrix(train_df, feature_cols)
    y_train = train_df["y"].to_numpy(dtype=np.float32)
    x_val = _matrix(val_df, feature_cols)
    y_val = val_df["y"].to_numpy(dtype=np.float32)

    train_end = "2026-04-30"
    sw = _date_weights(train_df["trade_date"], train_end, cand.half_life_days, 0.15)

    dtrain = xgb.DMatrix(x_train, label=y_train, weight=sw)
    dval = xgb.DMatrix(x_val, label=y_val)

    params = {
        "objective": cand.objective,
        "learning_rate": cand.learning_rate,
        "max_depth": max(cand.max_depth, 5),
        "subsample": cand.subsample,
        "colsample_bytree": cand.colsample_bytree,
        "reg_alpha": cand.reg_alpha,
        "reg_lambda": cand.reg_lambda,
        "min_child_weight": cand.min_child_samples,
        "random_state": seed,
        "n_jobs": num_threads,
        "verbosity": 0,
        "eval_metric": "rmse",
    }

    model = xgb.train(
        params,
        dtrain,
        num_boost_round=cand.n_estimators,
        evals=[(dval, "val")],
        early_stopping_rounds=cand.early_stopping_rounds,
        verbose_eval=200,
    )
    return model


# ---------------------------------------------------------------------------
# Prediction & evaluation
# ---------------------------------------------------------------------------

def _predict_tree(model, df: pd.DataFrame, feature_cols: list[str], direction: str, kind: str) -> pd.DataFrame:
    x = _matrix(df, feature_cols)
    if kind == "xgb":
        import xgboost as xgb
        raw = model.predict(xgb.DMatrix(x))
    else:
        raw = model.predict(x)
    score = -raw if direction == "inverse" else raw
    return pd.DataFrame({
        "ts_code": df["ts_code"].to_numpy(),
        "trade_date": df["trade_date"].to_numpy(),
        "y_pred": score.astype(float),
        "raw_pred": raw.astype(float),
        "y_true": df["y"].to_numpy(dtype=float),
    })


def _evaluate(cand: Candidate, model, val_df: pd.DataFrame, feature_cols: list[str], panel: pd.DataFrame) -> tuple[dict, pd.DataFrame]:
    preds = _predict_tree(model, val_df, feature_cols, cand.direction, cand.kind)
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
        "train_start": cand.train_start,
        "num_leaves": cand.num_leaves,
        "learning_rate": cand.learning_rate,
        "n_estimators": cand.n_estimators,
        "max_depth": cand.max_depth,
        "reg_alpha": cand.reg_alpha,
        "reg_lambda": cand.reg_lambda,
        "features": len(feature_cols),
        "samples": len(preds),
        **metrics,
        **{f"bt_{k}": v for k, v in bt_stats.items()},
    }
    return row, preds


# ---------------------------------------------------------------------------
# Grid builder
# ---------------------------------------------------------------------------

def build_exploration_grid(
    feature_sets: dict[str, list[str]],
    lgb_available: bool,
    xgb_available: bool,
) -> list[tuple[Candidate, str]]:
    """Build a focused exploration grid. Returns list of (candidate, feature_set_key).

    Priority order (most promising first):
      A. LambdaRank — completely untested, ranking-native objective
      B. Data window + feature count variations on huber (the only working objective)
      C. XGBoost baseline — for ensemble diversity
      D. Regularization sweep on best config
    """
    candidates: list[tuple[Candidate, str]] = []
    idx = 0

    # ---- Phase A: LambdaRank (most promising, ~18 candidates) ----
    if lgb_available:
        for fs_key in ["selected", "alpha_only", "base_plus_alpha"]:
            for train_start in ["2024-01-01", "2025-01-01"]:
                for hl in (30.0, 60.0):
                    direction = "forward"  # focus on forward first
                    name = f"explore_{idx:03d}_lgbm_lambdarank_{fs_key}_{direction}_hl{int(hl)}_train{train_start[:4]}"
                    candidates.append((Candidate(
                        name=name, kind="lgbm", objective="lambdarank",
                        feature_set=fs_key, direction=direction,
                        half_life_days=hl, train_start=train_start,
                        num_leaves=31, learning_rate=0.05, n_estimators=800,
                    ), fs_key))
                    idx += 1

    # ---- Phase B: Data window + feature count on huber (~12 candidates) ----
    if lgb_available:
        for train_start in ["2024-01-01", "2024-06-01", "2025-01-01"]:
            for max_feat in [40, 80, 120]:
                for hl in (30.0,):
                    direction = "forward"
                    name = f"explore_{idx:03d}_lgbm_huber_f{max_feat}_{direction}_hl{int(hl)}_train{train_start[:4]}"
                    candidates.append((Candidate(
                        name=name, kind="lgbm", objective="huber",
                        feature_set="selected", direction=direction,
                        half_life_days=hl, train_start=train_start,
                        num_leaves=31, learning_rate=0.05, n_estimators=800,
                        max_features=max_feat,
                    ), "selected"))
                    idx += 1

    # ---- Phase C: XGBoost baseline (~12 candidates) ----
    if xgb_available:
        for fs_key in ["selected", "alpha_only"]:
            for objective in ["reg:pseudohubererror"]:  # most relevant for financial data
                for hl in (30.0, 60.0, 90.0):
                    for direction in ("forward", "inverse"):
                        name = f"explore_{idx:03d}_xgb_{objective}_{fs_key}_{direction}_hl{int(hl)}"
                        candidates.append((Candidate(
                            name=name, kind="xgb", objective=objective,
                            feature_set=fs_key, direction=direction,
                            half_life_days=hl, train_start="2025-01-01",
                            max_depth=5, learning_rate=0.05,
                            n_estimators=800, early_stopping_rounds=30,
                        ), fs_key))
                        idx += 1

    # ---- Phase D: Regularization + deeper trees on best combo (~6 candidates) ----
    if lgb_available:
        for reg_alpha in [0.1, 0.2]:
            for num_leaves in [63,]:
                for lr in [0.03,]:
                    for n_est in [1000, 1500]:
                        name = f"explore_{idx:03d}_lgbm_huber_reg_a{reg_alpha}_l{num_leaves}_lr{lr}_n{n_est}_fwd_hl30"
                        candidates.append((Candidate(
                            name=name, kind="lgbm", objective="huber",
                            feature_set="selected", direction="forward",
                            half_life_days=30.0, train_start="2025-01-01",
                            num_leaves=num_leaves, learning_rate=lr, n_estimators=n_est,
                            reg_alpha=reg_alpha, reg_lambda=1.0,
                        ), "selected"))
                        idx += 1

    # ---- Phase E: Short half-life sweep on best config (~3 candidates) ----
    if lgb_available:
        for hl in (10.0, 20.0, 45.0):
            name = f"explore_{idx:03d}_lgbm_huber_fwd_hl{int(hl)}_n1000"
            candidates.append((Candidate(
                name=name, kind="lgbm", objective="huber",
                feature_set="selected", direction="forward",
                half_life_days=hl, train_start="2025-01-01",
                num_leaves=31, learning_rate=0.05, n_estimators=1000,
            ), "selected"))
            idx += 1
            # also test inverse for these
            name_inv = f"explore_{idx:03d}_lgbm_huber_inv_hl{int(hl)}_n1000"
            candidates.append((Candidate(
                name=name_inv, kind="lgbm", objective="huber",
                feature_set="selected", direction="inverse",
                half_life_days=hl, train_start="2025-01-01",
                num_leaves=31, learning_rate=0.05, n_estimators=1000,
            ), "selected"))
            idx += 1

    return candidates


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", type=Path, default=Path("/home/lcc17/pan_sync_20260528/A股数据"))
    ap.add_argument("--cache-dir", type=Path, default=Path("/home/lcc17/pan_sync_20260528/shortterm_cache"))
    ap.add_argument("--data-end", default="2026-05-28")
    ap.add_argument("--build-start", default="2025-01-01")
    ap.add_argument("--val-start", default="2026-05-06")
    ap.add_argument("--val-end", default="2026-05-27")
    ap.add_argument("--asof-date", default="2026-05-28")
    ap.add_argument("--target-date", default="2026-06-01")
    ap.add_argument("--time-budget-min", type=float, default=160.0)
    ap.add_argument("--num-threads", type=int, default=8)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--rebuild-cache", action="store_true")
    ap.add_argument("--phase", default="all", choices=["all", "lgbm", "xgb"])
    args = ap.parse_args()

    np.random.seed(args.seed)
    started = time.monotonic()

    lgb, lgb_ok = _try_import_lgb()
    xgb, xgb_ok = _try_import_xgb()
    print(f"[explore] lgbm={lgb_ok} xgb={xgb_ok}")

    # ---- Load data (reuse cache) ----
    _configure_data_dir(args.data_dir)
    panel_cache = args.cache_dir / f"panel_{args.build_start}_{args.data_end}.parquet"
    wq_feats_cache = args.cache_dir / f"features_wq_{args.build_start}_{args.data_end}.parquet"
    labels_cache = args.cache_dir / f"labels_nofuturelimit_{args.build_start}_{args.data_end}.parquet"

    panel = pd.read_parquet(panel_cache) if panel_cache.exists() else None
    feats = pd.read_parquet(wq_feats_cache) if wq_feats_cache.exists() else None
    labels = pd.read_parquet(labels_cache) if labels_cache.exists() else None

    if feats is None or labels is None or args.rebuild_cache:
        from src.data_loader import PanelBuildConfig, build_panel
        from src.features import compute_features, list_feature_cols
        from src.labels import attach_labels, clip_outliers

        if panel is None or args.rebuild_cache:
            panel = build_panel(PanelBuildConfig(start=args.build_start, end=args.data_end, include_metric=True))
            moneyflow = _read_moneyflow(args.data_dir, args.build_start, args.data_end)
            panel = _merge_moneyflow(panel, moneyflow)
            panel.to_parquet(panel_cache, index=False)

        base_feats = _add_moneyflow_features(compute_features(panel), panel)
        feats = add_wq_alpha_features(base_feats, panel)
        feats.to_parquet(wq_feats_cache, index=False)

        labels = clip_outliers(attach_labels(panel, drop_limit_tomorrow=False), "y", 0.005)
        labels.to_parquet(labels_cache, index=False)

    base_cols = [c for c in feats.columns if not c.startswith("wq_") and c not in ("ts_code", "trade_date")]
    wq_cols = [c for c in feats.columns if c.startswith("wq_")]
    all_features = list(dict.fromkeys(base_cols + wq_cols))
    print(f"[explore] features: base={len(base_cols)} wq={len(wq_cols)} total={len(all_features)}")

    # ---- Feature selection on default training window ----
    train_sel_df = _merge_xy(feats, labels, all_features, "2025-01-01", "2026-04-30")
    all_selected, feature_report = select_features(
        train_sel_df, all_features, max_features=120, min_abs_ic=0.005, min_pos_rate=0.55,
    )
    print(f"[explore] selected {len(all_selected)} features out of {len(all_features)}")

    # Build feature sets dynamically
    alpha_cols = [c for c in all_features if c.startswith("wq_")]
    feature_sets = {
        "selected": all_selected[:80],
        "alpha_only": [c for c in all_selected if c.startswith("wq_")][:80],
        "base_plus_alpha": list(dict.fromkeys(
            [c for c in all_selected if not c.startswith("wq_")][:40] +
            [c for c in all_selected if c.startswith("wq_")][:40]
        ))[:80],
    }

    # ---- Build grid ----
    candidates = build_exploration_grid(feature_sets, lgb_ok, xgb_ok)
    print(f"[explore] total candidates: {len(candidates)}")

    # ---- Run ----
    rows: list[dict] = []
    best: tuple[dict, pd.DataFrame, object, list[str], Candidate] | None = None

    for cand, fs_key in candidates:
        elapsed_min = (time.monotonic() - started) / 60.0
        if elapsed_min > args.time_budget_min:
            print(f"[explore] TIME BUDGET reached at {elapsed_min:.1f} min")
            break

        cols = feature_sets.get(fs_key, all_features[:cand.max_features])
        if len(cols) > cand.max_features:
            cols = cols[:cand.max_features]

        # Build train/val data for this candidate's window
        train_df = _merge_xy(feats, labels, cols, cand.train_start, "2026-04-30")
        val_df = _merge_xy(feats, labels, cols, args.val_start, args.val_end)

        if len(train_df) < 10000 or len(val_df) < 1000:
            print(f"[explore] SKIP {cand.name}: insufficient data train={len(train_df)} val={len(val_df)}")
            continue

        print(f"[explore] [{elapsed_min:.0f}m] fitting {cand.name} features={len(cols)} train={cand.train_start}")

        try:
            if cand.kind == "lgbm":
                model = _fit_lgbm(cand, train_df, val_df, cols, args.seed, args.num_threads)
            elif cand.kind == "xgb":
                model = _fit_xgb(cand, train_df, val_df, cols, args.seed, args.num_threads)
            else:
                continue

            row, preds = _evaluate(cand, model, val_df, cols, panel)
            rows.append(row)
            print(json.dumps({k: row[k] for k in ["tag", "ic", "rank_ic", "top10_spread_bp", "bt_annualised", "bt_sharpe"]}, ensure_ascii=False), flush=True)

            # Update best
            is_better = best is None or (
                row.get("bt_annualised", -999), row.get("bt_sharpe", -999), row.get("rank_ic", -999)
            ) > (
                best[0].get("bt_annualised", -999), best[0].get("bt_sharpe", -999), best[0].get("rank_ic", -999)
            )
            if is_better:
                best = (row, preds, model, cols, cand)
                # Save best immediately
                CHECKPOINTS.mkdir(exist_ok=True)
                model_path = CHECKPOINTS / f"{cand.name}.pkl"
                with open(model_path, "wb") as fh:
                    pickle.dump({"model": model, "feature_cols": cols, "row": row, "kind": cand.kind}, fh)
                preds_path = REPORTS / "may_2026_validation" / f"{cand.name}_may_preds.parquet"
                preds_path.parent.mkdir(parents=True, exist_ok=True)
                preds.to_parquet(preds_path, index=False)
                print(f"[explore] NEW BEST: {cand.name} bt_annual={row['bt_annualised']:.3f} bt_sharpe={row['bt_sharpe']:.3f}")

            # Early stop if we find a very strong model
            if row.get("bt_sharpe", -999) > 1.0 and row.get("bt_annualised", -999) > 0.2:
                print(f"[explore] STRONG model found: {cand.name}, continuing for diversity...")

        except Exception as e:
            print(f"[explore] FAIL {cand.name}: {e}")
            continue

    # ---- Final summary ----
    if not rows:
        print("[explore] FATAL: no candidates completed")
        sys.exit(1)

    summary = pd.DataFrame(rows).sort_values(["bt_annualised", "bt_sharpe"], ascending=False)
    out_dir = REPORTS / "may_2026_validation"
    out_dir.mkdir(parents=True, exist_ok=True)
    summary.to_csv(out_dir / "summary_explore.csv", index=False)
    (out_dir / "summary_explore.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")

    if best:
        best_row, best_preds, best_model, best_cols, best_cand = best
        print(f"\n[explore] ===== BEST: {best_cand.name} =====")
        print(json.dumps(best_row, indent=2, ensure_ascii=False))
        print(f"\n[explore] Top 10 by Sharpe:")
        print(summary[["tag", "kind", "objective", "ic", "rank_ic", "top10_spread_bp", "bt_annualised", "bt_sharpe"]].head(15).to_string(index=False))

    elapsed = (time.monotonic() - started) / 60.0
    print(f"\n[explore] Done in {elapsed:.1f} min, {len(rows)} candidates evaluated")


if __name__ == "__main__":
    main()
