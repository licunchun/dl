"""Quick LightGBM factor-group comparison for the May 2026 validation slice."""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.short_term_competition_train import _run_backtest  # noqa: E402
from scripts.train_lgbm_wq_short import _date_weights, _matrix, select_features  # noqa: E402
from src.eval import summarize, topk_spread  # noqa: E402


@dataclass(frozen=True)
class Candidate:
    tag: str
    factor_group: str
    objective: str
    direction: str
    features: list[str]


def _schema_columns(path: Path) -> list[str]:
    return pq.read_schema(path).names


def _group_columns(columns: list[str]) -> dict[str, list[str]]:
    skip = {"ts_code", "trade_date"}
    cols = [c for c in columns if c not in skip]

    def has_any(c: str, parts: tuple[str, ...]) -> bool:
        return any(p in c for p in parts)

    groups = {
        "return_rank": [
            c for c in cols
            if c in {"ret_1", "ret_5", "ret_20", "rk_ret_1", "rk_ret_5"}
        ],
        "technical_trend": [
            c for c in cols
            if has_any(c, ("ma_", "rsi", "macd", "vwap_dev"))
        ],
        "vol_liquidity": [
            c for c in cols
            if has_any(c, ("std_", "vol", "amihud", "turn"))
        ],
        "value_size": [
            c for c in cols
            if has_any(c, ("mv", "pe", "pb", "small_size", "value_"))
        ],
        "moneyflow": [
            c for c in cols
            if c.startswith("mf_") or c.startswith("rk_mf_") or c.startswith("wq_mf_") or "_mf_" in c
        ],
        "wq_momentum": [
            c for c in cols
            if c.startswith("wq_") and has_any(c, ("mom", "safe_mom", "trend"))
        ],
        "wq_reversal": [
            c for c in cols
            if c.startswith("wq_") and has_any(c, ("rev", "revert"))
        ],
        "wq_price_volume": [
            c for c in cols
            if c.startswith("wq_") and has_any(c, ("vol", "vwap", "range", "amt", "price"))
        ],
    }
    return {k: list(dict.fromkeys(v)) for k, v in groups.items() if v}


def _read_frame(path: Path, columns: list[str]) -> pd.DataFrame:
    return pd.read_parquet(path, columns=list(dict.fromkeys(columns)))


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


def _fit_lgbm(cand: Candidate, train_df: pd.DataFrame, val_df: pd.DataFrame, args):
    import lightgbm as lgb

    model = lgb.LGBMRegressor(
        objective=cand.objective,
        random_state=args.seed,
        n_jobs=args.num_threads,
        learning_rate=args.learning_rate,
        n_estimators=args.n_estimators,
        num_leaves=args.num_leaves,
        subsample=0.85,
        colsample_bytree=0.85,
        min_child_samples=80,
        reg_alpha=0.05,
        reg_lambda=0.5,
        verbosity=-1,
    )
    model.fit(
        _matrix(train_df, cand.features),
        train_df["y"].to_numpy(dtype=np.float32),
        sample_weight=_date_weights(
            train_df["trade_date"], args.train_end, args.half_life_days, args.min_date_weight
        ),
        eval_set=[(_matrix(val_df, cand.features), val_df["y"].to_numpy(dtype=np.float32))],
        callbacks=[
            lgb.early_stopping(args.early_stopping_rounds, verbose=False),
            lgb.log_evaluation(0),
        ],
    )
    return model


def _predict(model, df: pd.DataFrame, cand: Candidate) -> pd.DataFrame:
    raw = model.predict(_matrix(df, cand.features))
    score = -raw if cand.direction == "inverse" else raw
    return pd.DataFrame({
        "ts_code": df["ts_code"].to_numpy(),
        "trade_date": df["trade_date"].to_numpy(),
        "y_pred": score.astype(float),
        "raw_pred": raw.astype(float),
        "y_true": df["y"].to_numpy(dtype=float),
    })


def _evaluate(cand: Candidate, model, val_df: pd.DataFrame, panel: pd.DataFrame) -> dict:
    preds = _predict(model, val_df, cand)
    metrics = summarize(preds)
    spread = topk_spread(preds, k=10)
    metrics["top10_spread_bp"] = float(spread["spread"].mean() * 1e4) if len(spread) else float("nan")
    out_dir = PROJECT_ROOT / "reports" / f"backtest_factor_lgbm_{cand.tag}"
    bt_stats = _run_backtest(preds, panel, out_dir)
    return {
        "tag": cand.tag,
        "factor_group": cand.factor_group,
        "objective": cand.objective,
        "direction": cand.direction,
        "features": len(cand.features),
        "samples": len(preds),
        **metrics,
        **{f"bt_{k}": v for k, v in bt_stats.items()},
    }


def _pct(x: float) -> float:
    return float(x) * 100.0 if math.isfinite(float(x)) else float("nan")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache-dir", type=Path, default=Path("/home/lcc17/pan_sync_20260528/shortterm_cache"))
    ap.add_argument("--build-start", default="2025-01-01")
    ap.add_argument("--data-end", default="2026-05-28")
    ap.add_argument("--train-start", default="2025-01-01")
    ap.add_argument("--train-end", default="2026-04-30")
    ap.add_argument("--val-start", default="2026-05-06")
    ap.add_argument("--val-end", default="2026-05-27")
    ap.add_argument("--max-features", type=int, default=30)
    ap.add_argument("--n-estimators", type=int, default=220)
    ap.add_argument("--learning-rate", type=float, default=0.06)
    ap.add_argument("--num-leaves", type=int, default=31)
    ap.add_argument("--early-stopping-rounds", type=int, default=25)
    ap.add_argument("--half-life-days", type=float, default=30.0)
    ap.add_argument("--min-date-weight", type=float, default=0.15)
    ap.add_argument("--num-threads", type=int, default=8)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    started = time.monotonic()
    feat_path = args.cache_dir / f"features_wq_{args.build_start}_{args.data_end}.parquet"
    label_path = args.cache_dir / f"labels_nofuturelimit_{args.build_start}_{args.data_end}.parquet"
    panel_path = args.cache_dir / f"panel_{args.build_start}_{args.data_end}.parquet"

    groups = _group_columns(_schema_columns(feat_path))
    all_group_cols = sorted({c for cols in groups.values() for c in cols})
    feats = _read_frame(feat_path, ["ts_code", "trade_date"] + all_group_cols)
    labels = _read_frame(label_path, ["ts_code", "trade_date", "y", "drop_reason"])
    panel = _read_frame(panel_path, ["ts_code", "trade_date", "open", "high", "low", "close", "vwap", "pct_chg"])

    rows: list[dict] = []
    for group_name, raw_cols in groups.items():
        train_all = _merge_xy(feats, labels, raw_cols, args.train_start, args.train_end)
        selected, _ = select_features(
            train_all,
            raw_cols,
            max_features=min(args.max_features, len(raw_cols)),
            min_abs_ic=0.003,
            min_pos_rate=0.50,
        )
        cols = selected or raw_cols[: args.max_features]
        val_df = _merge_xy(feats, labels, cols, args.val_start, args.val_end)
        train_df = train_all[["ts_code", "trade_date", "y", "drop_reason"] + cols].copy()
        for direction in ("forward", "inverse"):
            tag = f"fast_{group_name}_huber_{direction}"
            cand = Candidate(tag, group_name, "huber", direction, cols)
            print(f"[factor-lgbm] fitting {tag} raw_features={len(raw_cols)} selected={len(cols)}")
            model = _fit_lgbm(cand, train_df, val_df, args)
            row = _evaluate(cand, model, val_df, panel)
            rows.append(row)
            print(json.dumps({
                "tag": row["tag"],
                "ic": row["ic"],
                "rank_ic": row["rank_ic"],
                "bt_annualised_pct": _pct(row["bt_annualised"]),
                "bt_sharpe": row["bt_sharpe"],
            }, ensure_ascii=False), flush=True)

    out_dir = PROJECT_ROOT / "reports" / "may_2026_validation"
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = pd.DataFrame(rows).sort_values(["bt_annualised", "bt_sharpe"], ascending=False)
    summary_path = out_dir / "summary_factor_lgbm_fast.csv"
    summary.to_csv(summary_path, index=False)
    (out_dir / "summary_factor_lgbm_fast.json").write_text(
        json.dumps(rows, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"[factor-lgbm] wrote {summary_path}")
    print(summary[[
        "tag", "factor_group", "direction", "features", "ic", "rank_ic",
        "top10_spread_bp", "bt_annualised", "bt_sharpe", "bt_max_drawdown", "bt_n_days",
    ]].head(20).to_string(index=False))
    print(f"[factor-lgbm] done in {(time.monotonic() - started) / 60.0:.1f} min")


if __name__ == "__main__":
    main()
