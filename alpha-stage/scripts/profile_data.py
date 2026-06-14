#!/usr/bin/env python3
"""Profile local A-share data for alpha discovery."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq


ROOT = Path.home() / "pan_sync_20260528"
OUT_DIR = Path("alpha-stage")
ARTIFACT_DIR = OUT_DIR / "artifacts"


def file_tree_summary(root: Path) -> dict:
    files = [p for p in root.rglob("*") if p.is_file()]
    by_ext = Counter(p.suffix.lower() or "<none>" for p in files)
    by_parent = Counter(str(p.parent.relative_to(root)) for p in files)
    return {
        "root": str(root),
        "total_files": len(files),
        "size_gb": round(sum(p.stat().st_size for p in files) / 1024**3, 3),
        "by_ext": dict(by_ext.most_common()),
        "by_parent_top": dict(by_parent.most_common(30)),
    }


def parquet_summary(path: Path) -> dict:
    pf = pq.ParquetFile(path)
    meta = pf.metadata
    cols = list(pf.schema_arrow.names)
    out = {
        "path": str(path),
        "rows": meta.num_rows,
        "columns": cols,
        "num_columns": len(cols),
        "size_mb": round(path.stat().st_size / 1024**2, 2),
    }
    sample_cols = [c for c in ["ts_code", "trade_date", "open", "close", "amount", "vol"] if c in cols]
    if sample_cols:
        try:
            df = pd.read_parquet(path, columns=sample_cols)
        except Exception as exc:
            out["sample_read_error"] = str(exc)
            return out
        if "trade_date" in df:
            out["date_min"] = str(df["trade_date"].min())
            out["date_max"] = str(df["trade_date"].max())
            out["n_dates"] = int(df["trade_date"].nunique())
        if "ts_code" in df:
            out["n_stocks"] = int(df["ts_code"].nunique())
            out["stock_sample"] = df["ts_code"].dropna().astype(str).head(5).tolist()
        if {"ts_code", "trade_date"}.issubset(df.columns):
            out["duplicate_keys"] = int(df.duplicated(["ts_code", "trade_date"]).sum())
        out["missing_pct"] = {
            c: round(float(df[c].isna().mean()), 6) for c in df.columns
        }
        if "amount" in df:
            out["zero_amount_rows"] = int((df["amount"].fillna(0) <= 0).sum())
        if "vol" in df:
            out["zero_vol_rows"] = int((df["vol"].fillna(0) <= 0).sum())
    return out


def csv_group_summary(group: Path) -> dict:
    files = sorted([p for p in group.glob("*.csv") if p.is_file()])
    out = {"path": str(group), "files": len(files)}
    if not files:
        return out
    dates = []
    for p in files:
        stem = p.stem.split("_")[0]
        if stem.isdigit():
            dates.append(stem)
    if dates:
        out["file_date_min"] = min(dates)
        out["file_date_max"] = max(dates)
    samples = [files[0], files[len(files) // 2], files[-1]]
    sample_rows = []
    col_counter = Counter()
    for p in samples:
        try:
            df = pd.read_csv(p, nrows=500)
        except Exception as exc:
            sample_rows.append({"file": p.name, "error": str(exc)})
            continue
        col_counter.update(df.columns)
        item = {
            "file": p.name,
            "columns": list(df.columns),
            "sample_rows": len(df),
            "missing_pct_sample": {
                c: round(float(df[c].isna().mean()), 4) for c in df.columns[:25]
            },
        }
        if "ts_code" in df:
            item["sample_n_stocks"] = int(df["ts_code"].nunique())
        if "trade_date" in df:
            item["sample_trade_date_min"] = str(df["trade_date"].min())
            item["sample_trade_date_max"] = str(df["trade_date"].max())
        sample_rows.append(item)
    out["sample_files"] = sample_rows
    out["columns_seen"] = list(col_counter)
    return out


def infer_field_groups(columns: list[str]) -> dict[str, list[str]]:
    needles = {
        "daily_ohlcv": ["open", "high", "low", "close", "pre_close", "pct_chg", "vol", "amount", "vwap"],
        "adjustment_or_shares": ["total_share", "float_share", "free_share"],
        "valuation_size": ["pe", "pe_ttm", "pb", "ps", "ps_ttm", "total_mv", "circ_mv"],
        "liquidity_turnover": ["turnover_rate", "turnover_rate_f", "volume_ratio", "turn", "amihud"],
        "moneyflow": ["buy_lg", "sell_lg", "buy_elg", "sell_elg", "net_mf", "mf_"],
        "factor_rank": ["rk_", "wq_"],
        "labels": ["y", "y_raw", "drop_reason"],
    }
    found: dict[str, list[str]] = {}
    for group, pats in needles.items():
        vals = [c for c in columns if any(p in c for p in pats)]
        if vals:
            found[group] = vals
    return found


def main() -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "file_tree": file_tree_summary(ROOT),
        "parquet": [],
        "csv_groups": {},
    }
    for p in sorted(ROOT.rglob("*.parquet")):
        summary["parquet"].append(parquet_summary(p))
    for group in sorted((ROOT / "A股数据").iterdir()):
        if group.is_dir():
            summary["csv_groups"][group.name] = csv_group_summary(group)

    all_cols = []
    for item in summary["parquet"]:
        all_cols.extend(item["columns"])
    for item in summary["csv_groups"].values():
        all_cols.extend(item.get("columns_seen", []))
    summary["field_groups"] = infer_field_groups(sorted(set(all_cols)))

    json_path = ARTIFACT_DIR / "data_profile.json"
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# A股本地数据盘点",
        "",
        f"生成时间：{summary['generated_at']}",
        f"数据根目录：`{ROOT}`",
        f"文件数：{summary['file_tree']['total_files']}，总大小：{summary['file_tree']['size_gb']} GB",
        "",
        "## 文件分布",
        "",
        "| 类型/目录 | 数量 |",
        "|---|---:|",
    ]
    for k, v in summary["file_tree"]["by_ext"].items():
        lines.append(f"| ext {k} | {v} |")
    for k, v in summary["file_tree"]["by_parent_top"].items():
        lines.append(f"| {k} | {v} |")

    lines += ["", "## Parquet 表", "", "| 文件 | 行数 | 列数 | 日期范围 | 股票数 | 重复键 | 关键字段 |", "|---|---:|---:|---|---:|---:|---|"]
    for item in summary["parquet"]:
        fields = ", ".join(item["columns"][:14]) + ("..." if len(item["columns"]) > 14 else "")
        lines.append(
            f"| `{Path(item['path']).relative_to(ROOT)}` | {item['rows']} | {item['num_columns']} | "
            f"{item.get('date_min','?')} - {item.get('date_max','?')} | {item.get('n_stocks','?')} | "
            f"{item.get('duplicate_keys','?')} | {fields} |"
        )

    lines += ["", "## CSV 目录", "", "| 目录 | 文件数 | 文件日期范围 | 样例字段 |", "|---|---:|---|---|"]
    for name, item in summary["csv_groups"].items():
        cols = ", ".join(item.get("columns_seen", [])[:16])
        lines.append(f"| `{name}` | {item['files']} | {item.get('file_date_min','?')} - {item.get('file_date_max','?')} | {cols} |")

    lines += ["", "## 字段能力推断", ""]
    for group, cols in summary["field_groups"].items():
        lines.append(f"- **{group}**: {', '.join(cols[:40])}{'...' if len(cols) > 40 else ''}")

    lines += [
        "",
        "## 初步风险结论",
        "",
        "- 主面板覆盖日频 OHLCV、成交额、换手率、估值、市值与资金流；可先做日频 1-20 日持仓 alpha。",
        "- `stock_st` 可用于剔除 ST/风险警示股票；`index_weight` 只有指数权重，不能把未来成分权重用于历史行业/指数中性。",
        "- 未发现明确的停复牌、涨跌停、退市、上市日期专表；首轮回测必须用 `vol/amount`、价格限制近似和每只股票首次出现后冷却期来降级控制。",
        "- `labels*` 是预计算未来收益标签，首轮只用于交叉检查，不作为回测收益来源，避免未知构造方式带来泄漏。",
        "- 新闻数据没有个股代码映射，第一阶段不作为可交易信号使用。",
        "",
        f"详细 JSON：`{json_path}`",
    ]
    (OUT_DIR / "DATA_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
