"""Fast LightGBM tests for literature-backed factor combinations."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.quick_lgbm_factor_groups import (  # noqa: E402
    Candidate,
    _evaluate,
    _fit_lgbm,
    _group_columns,
    _merge_xy,
    _read_frame,
    _schema_columns,
)
from scripts.train_lgbm_wq_short import select_features  # noqa: E402


LITERATURE_NOTES = {
    "carhart_ff_plus_momentum": {
        "source": "Fama-French/Carhart",
        "mapped_idea": "size + value + momentum; profitability/investment unavailable in local schema",
    },
    "aqr_style_value_momentum_defensive": {
        "source": "AQR style premia",
        "mapped_idea": "value + momentum + defensive/low-risk proxies",
    },
    "msci_barra_core_style": {
        "source": "MSCI/Barra style risk model",
        "mapped_idea": "size + value + momentum + volatility + liquidity",
    },
    "qlib_alpha158_like": {
        "source": "Microsoft Qlib Alpha158 + LightGBM benchmark",
        "mapped_idea": "rolling price/volume, return rank, technical, volatility and liquidity features",
    },
    "worldquant_101_price_volume": {
        "source": "WorldQuant 101 Formulaic Alphas",
        "mapped_idea": "ranked price/volume/reversal/momentum and VWAP/range style alphas",
    },
}


def _combo_specs(groups: dict[str, list[str]]) -> dict[str, list[str]]:
    def cols(*names: str) -> list[str]:
        merged: list[str] = []
        for name in names:
            merged.extend(groups.get(name, []))
        return list(dict.fromkeys(merged))

    return {
        "carhart_ff_plus_momentum": cols("value_size", "wq_momentum"),
        "aqr_style_value_momentum_defensive": cols("value_size", "wq_momentum", "vol_liquidity"),
        "msci_barra_core_style": cols("value_size", "wq_momentum", "vol_liquidity"),
        "qlib_alpha158_like": cols(
            "return_rank",
            "technical_trend",
            "vol_liquidity",
            "wq_price_volume",
            "wq_reversal",
            "wq_momentum",
        ),
        "worldquant_101_price_volume": cols("wq_momentum", "wq_reversal", "wq_price_volume"),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache-dir", type=Path, default=Path("/home/lcc17/pan_sync_20260528/shortterm_cache"))
    ap.add_argument("--build-start", default="2025-01-01")
    ap.add_argument("--data-end", default="2026-05-28")
    ap.add_argument("--train-start", default="2026-01-01")
    ap.add_argument("--train-end", default="2026-04-30")
    ap.add_argument("--val-start", default="2026-05-06")
    ap.add_argument("--val-end", default="2026-05-27")
    ap.add_argument("--max-features", type=int, default=55)
    ap.add_argument("--n-estimators", type=int, default=240)
    ap.add_argument("--learning-rate", type=float, default=0.055)
    ap.add_argument("--num-leaves", type=int, default=31)
    ap.add_argument("--early-stopping-rounds", type=int, default=20)
    ap.add_argument("--half-life-days", type=float, default=30.0)
    ap.add_argument("--min-date-weight", type=float, default=0.15)
    ap.add_argument("--num-threads", type=int, default=8)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out-suffix", default=None)
    args = ap.parse_args()

    started = time.monotonic()
    feat_path = args.cache_dir / f"features_wq_{args.build_start}_{args.data_end}.parquet"
    label_path = args.cache_dir / f"labels_nofuturelimit_{args.build_start}_{args.data_end}.parquet"
    panel_path = args.cache_dir / f"panel_{args.build_start}_{args.data_end}.parquet"

    groups = _group_columns(_schema_columns(feat_path))
    combos = {k: v for k, v in _combo_specs(groups).items() if v}
    all_cols = sorted({c for cols in combos.values() for c in cols})
    feats = _read_frame(feat_path, ["ts_code", "trade_date"] + all_cols)
    labels = _read_frame(label_path, ["ts_code", "trade_date", "y", "drop_reason"])
    panel = _read_frame(panel_path, ["ts_code", "trade_date", "open", "high", "low", "close", "vwap", "pct_chg"])

    rows: list[dict] = []
    for combo_name, raw_cols in combos.items():
        train_all = _merge_xy(feats, labels, raw_cols, args.train_start, args.train_end)
        selected, _ = select_features(
            train_all,
            raw_cols,
            max_features=min(args.max_features, len(raw_cols)),
            min_abs_ic=0.003,
            min_pos_rate=0.50,
        )
        cols = selected or raw_cols[: args.max_features]
        train_df = train_all[["ts_code", "trade_date", "y", "drop_reason"] + cols].copy()
        val_df = _merge_xy(feats, labels, cols, args.val_start, args.val_end)
        for direction in ("forward", "inverse"):
            tag = f"lit_{combo_name}_huber_{direction}"
            cand = Candidate(tag, combo_name, "huber", direction, cols)
            note = LITERATURE_NOTES[combo_name]
            print(
                f"[lit-combo-lgbm] fitting {tag} source={note['source']} "
                f"raw_features={len(raw_cols)} selected={len(cols)}"
            )
            model = _fit_lgbm(cand, train_df, val_df, args)
            row = _evaluate(cand, model, val_df, panel)
            row.update({
                "source": note["source"],
                "mapped_idea": note["mapped_idea"],
                "selected_features": ",".join(cols),
            })
            rows.append(row)
            print(json.dumps({
                "tag": row["tag"],
                "source": row["source"],
                "ic": row["ic"],
                "rank_ic": row["rank_ic"],
                "bt_annualised_pct": row["bt_annualised"] * 100.0,
                "bt_sharpe": row["bt_sharpe"],
            }, ensure_ascii=False), flush=True)

    out_dir = PROJECT_ROOT / "reports" / "may_2026_validation"
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = pd.DataFrame(rows).sort_values(["bt_annualised", "bt_sharpe"], ascending=False)
    suffix = args.out_suffix
    if suffix is None:
        suffix = f"train{args.train_start.replace('-', '')}_{args.train_end.replace('-', '')}"
    summary_path = out_dir / f"summary_factor_lgbm_literature_combos_{suffix}.csv"
    summary.to_csv(summary_path, index=False)
    (out_dir / f"summary_factor_lgbm_literature_combos_{suffix}.json").write_text(
        json.dumps(rows, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"[lit-combo-lgbm] wrote {summary_path}")
    print(summary[[
        "source", "factor_group", "direction", "features", "ic", "rank_ic",
        "top10_spread_bp", "bt_annualised", "bt_sharpe",
        "bt_max_drawdown", "bt_n_days",
    ]].to_string(index=False))
    print(f"[lit-combo-lgbm] done in {(time.monotonic() - started) / 60.0:.1f} min")


if __name__ == "__main__":
    main()
