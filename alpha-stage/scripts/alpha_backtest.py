#!/usr/bin/env python3
"""Pilot and backtest daily A-share alpha candidates with explicit timing."""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq


DATA_ROOT = Path.home() / "pan_sync_20260528"
OUT_DIR = Path("alpha-stage")
REFINE_DIR = Path("refine-logs")
REVIEW_DIR = Path("review-stage")
ARTIFACT_DIR = OUT_DIR / "artifacts"
ST_DIR = DATA_ROOT / "A股数据" / "stock_st"
DAILY_DIR = DATA_ROOT / "A股数据" / "daily"
METRIC_DIR = DATA_ROOT / "A股数据" / "metric"
MONEYFLOW_DIR = DATA_ROOT / "A股数据" / "moneyflow"
PANEL_CACHE_VERSION = 4
MAX_EXIT_DELAY_DAYS = int(os.environ.get("ALPHA_MAX_EXIT_DELAY_DAYS", "10"))


def use_torch_cuda_backend() -> bool:
    if os.environ.get("ALPHA_BACKEND", "").lower() != "torch_cuda":
        return False
    try:
        import torch

        return bool(torch.cuda.is_available())
    except Exception:
        return False


def torch_rank_corr(score: np.ndarray, ret: np.ndarray) -> float | None:
    import torch

    s = torch.as_tensor(score, device="cuda", dtype=torch.float32)
    r = torch.as_tensor(ret, device="cuda", dtype=torch.float32)
    mask = torch.isfinite(s) & torch.isfinite(r)
    s = s[mask]
    r = r[mask]
    if s.numel() < 100 or torch.unique(s).numel() < 10:
        return None
    s_order = torch.argsort(s)
    r_order = torch.argsort(r)
    s_rank = torch.empty_like(s)
    r_rank = torch.empty_like(r)
    ranks = torch.arange(s.numel(), device="cuda", dtype=torch.float32)
    s_rank[s_order] = ranks
    r_rank[r_order] = ranks
    s_rank = s_rank - s_rank.mean()
    r_rank = r_rank - r_rank.mean()
    denom = torch.linalg.vector_norm(s_rank) * torch.linalg.vector_norm(r_rank)
    if float(denom.item()) == 0.0:
        return None
    return float((s_rank @ r_rank / denom).item())


def torch_top_decile_returns(score: np.ndarray, ret: np.ndarray, buy_fillable: np.ndarray) -> tuple[float | None, float | None, np.ndarray, np.ndarray]:
    import torch

    s = torch.as_tensor(score, device="cuda", dtype=torch.float32)
    r = torch.as_tensor(ret, device="cuda", dtype=torch.float32)
    b = torch.as_tensor(buy_fillable, device="cuda", dtype=torch.bool)
    valid_score = torch.isfinite(s)
    idx_all = torch.nonzero(valid_score, as_tuple=False).flatten()
    if idx_all.numel() < 300:
        return None, None, np.array([], dtype=np.int64), np.array([], dtype=np.int64)
    k = max(int(idx_all.numel() * 0.1), 1)
    s_valid = s[idx_all]
    long_local = torch.topk(s_valid, k=k, largest=True, sorted=False).indices
    short_local = torch.topk(s_valid, k=k, largest=False, sorted=False).indices
    long_idx = idx_all[long_local]
    short_idx = idx_all[short_local]
    long_trade = long_idx[b[long_idx] & torch.isfinite(r[long_idx])]
    short_trade = short_idx[b[short_idx] & torch.isfinite(r[short_idx])]
    if long_trade.numel() < 20 or short_trade.numel() < 20:
        return None, None, np.array([], dtype=np.int64), np.array([], dtype=np.int64)
    long_mean = float(r[long_trade].mean().item())
    short_mean = float(r[short_trade].mean().item())
    return long_mean, short_mean, long_trade.cpu().numpy(), short_trade.cpu().numpy()


def torch_long_top_decile_return(score: np.ndarray, ret: np.ndarray, buy_fillable: np.ndarray) -> tuple[float | None, np.ndarray]:
    import torch

    s = torch.as_tensor(score, device="cuda", dtype=torch.float32)
    r = torch.as_tensor(ret, device="cuda", dtype=torch.float32)
    b = torch.as_tensor(buy_fillable, device="cuda", dtype=torch.bool)
    valid_score = torch.isfinite(s)
    idx_all = torch.nonzero(valid_score, as_tuple=False).flatten()
    if idx_all.numel() < 300:
        return None, np.array([], dtype=np.int64)
    k = max(int(idx_all.numel() * 0.1), 1)
    long_local = torch.topk(s[idx_all], k=k, largest=True, sorted=False).indices
    long_idx = idx_all[long_local]
    long_trade = long_idx[b[long_idx] & torch.isfinite(r[long_idx])]
    if long_trade.numel() < 20:
        return None, np.array([], dtype=np.int64)
    return float(r[long_trade].mean().item()), long_trade.cpu().numpy()


@dataclass(frozen=True)
class Candidate:
    alpha_id: str
    name: str
    formula: str
    field: str
    ascending: bool
    neutral: str = "none"


BASE_CANDIDATES = [
    Candidate("A001", "1日反转", "-rank(ret_1)", "ret_1", True),
    Candidate("A002", "5日反转", "-rank(ret_5)", "ret_5", True),
    Candidate("A003", "20日动量", "rank(ret_20)", "ret_20", False),
    Candidate("A004", "低波动", "-rank(std_20)", "std_20", True),
    Candidate("A005", "Amihud流动性", "-rank(amihud_20)", "amihud_20", True),
    Candidate("A006", "小市值", "-rank(mv_log)", "mv_log", True),
    Candidate("A007", "换手反转", "-rank(turn)", "turn", True),
    Candidate("A008", "大单资金流", "rank(mf_lg_amt_ratio)", "mf_lg_amt_ratio", False),
    Candidate("A009", "超大单资金压力", "rank(mf_buy_pressure)", "mf_buy_pressure", False),
    Candidate("A010", "VWAP偏离反转", "-rank(vwap_dev)", "vwap_dev", True),
    Candidate("A011", "放量5日反转", "rank((1-rank(ret_5))*rank(amount_ratio_20))", "score_shock_rev_5", False),
    Candidate("A012", "放量1日反转", "rank((1-rank(ret_1))*rank(amount_ratio_20))", "score_shock_rev_1", False),
    Candidate("A013", "资金流耗尽反转", "rank((1-rank(ret_5))*rank(mf_buy_pressure))", "score_mf_exhaust_rev", False),
    Candidate("A014", "资金流顺势", "rank(rank(ret_5)*rank(mf_buy_pressure))", "score_mf_confirm_mom", False),
    Candidate("A015", "低换手动量", "rank(rank(ret_20)*(1-rank(turn)))", "score_low_turn_mom", False),
    Candidate("A016", "价值流动性防御", "rank(rank(pb_inv)+rank(liq_inv)+rank(low_vol))", "score_value_liq_def", False),
    Candidate("A017", "VWAP放量反转", "rank((1-rank(vwap_dev))*rank(amount_ratio_20))", "score_vwap_shock_rev", False),
    Candidate("A018", "小市值流动性约束", "rank((1-rank(mv_log))*rank(liq_inv))", "score_small_liq", False),
    Candidate("A019", "跳过短反转的中期动量", "rank(ret_20_skip5)", "ret_20_skip5", False),
    Candidate("A020", "高流动低波中期动量", "rank(rank(ret_20_skip5)*rank(liq_inv)*rank(low_vol))", "score_liq_lowvol_mid_mom", False),
    Candidate("A021", "流动性改善", "rank(amihud_20-amihud_5)", "score_liq_improve", False),
    Candidate("A022", "低换手高流动低波中期动量", "rank(rank(ret_20_skip5)*rank(liq_inv)*rank(low_vol)*(1-rank(turn)))", "score_liq_lowvol_lowturn_mid_mom", False),
    Candidate("A023", "高流动低波长周期动量", "rank(rank(ret_60_skip20)*rank(liq_inv)*rank(low_vol))", "score_liq_lowvol_long_mom", False),
    Candidate("A024", "低换手长周期防御动量", "rank(rank(ret_60_skip20)*rank(liq_inv)*rank(low_vol)*(1-rank(turn)))", "score_liq_lowvol_lowturn_long_mom", False),
    Candidate("A025", "价值流动低波中期动量", "rank(rank(ret_20_skip5)*rank(pb_inv)*rank(liq_inv)*rank(low_vol))", "score_value_liq_lowvol_mid_mom", False),
    Candidate("A026", "中长周期动量共振防御", "rank(rank(ret_20_skip5)*rank(ret_60_skip20)*rank(liq_inv)*rank(low_vol))", "score_mid_long_def_mom", False),
    Candidate("A027", "容量约束低换手中期动量", "rank(rank(ret_20_skip5)*rank(liq_inv)*rank(amount)*rank(low_vol)*(1-rank(turn)))", "score_capacity_lowturn_mid_mom", False),
    Candidate("A028", "长动量短回撤防御", "rank(rank(ret_60_skip20)*(1-rank(ret_5))*rank(liq_inv)*rank(low_vol)*(1-rank(turn)))", "score_long_mom_short_pullback_def", False),
    Candidate("A029", "中期动量短回撤低冲击", "rank(rank(ret_20_skip5)*(1-rank(ret_5))*rank(liq_inv)*rank(low_vol)*(1-rank(turn)))", "score_mid_mom_short_pullback_liq", False),
    Candidate("A030", "资金确认低换手防御动量", "rank(rank(ret_20_skip5)*rank(mf_buy_pressure)*rank(liq_inv)*rank(low_vol)*(1-rank(turn)))", "score_mf_confirm_lowturn_def_mom", False),
]


def normalize_date(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s.astype(str), format="%Y%m%d", errors="coerce")


def load_st_dates() -> pd.DataFrame:
    rows = []
    for p in sorted(ST_DIR.glob("*.csv")):
        stem = p.stem.split("_")[0]
        if stem.isdigit() and (stem < DEFAULT_START or stem > DEFAULT_END):
            continue
        try:
            df = pd.read_csv(p, usecols=["ts_code", "trade_date"])
        except Exception:
            continue
        rows.append(df)
    if not rows:
        return pd.DataFrame(columns=["ts_code", "trade_date", "is_st"])
    st = pd.concat(rows, ignore_index=True).drop_duplicates(["ts_code", "trade_date"])
    st["trade_date"] = normalize_date(st["trade_date"])
    st["is_st"] = True
    return st


DEFAULT_START = os.environ.get("ALPHA_START", "20190101").replace("-", "")
DEFAULT_END = os.environ.get("ALPHA_END", "20260528").replace("-", "")


def read_csv_dir_by_date(path: Path, start: str = DEFAULT_START, end: str = DEFAULT_END, usecols: list[str] | None = None) -> pd.DataFrame:
    frames = []
    for p in sorted(path.glob("*.csv")):
        stem = p.stem.split("_")[0]
        if not stem.isdigit() or stem < start or stem > end:
            continue
        try:
            frames.append(pd.read_csv(p, usecols=usecols))
        except ValueError:
            frames.append(pd.read_csv(p))
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def source_signature(paths: list[Path], start: str = DEFAULT_START, end: str = DEFAULT_END) -> dict:
    out = {}
    for path in paths:
        count = 0
        total_size = 0
        max_mtime_ns = 0
        for p in path.glob("*.csv"):
            stem = p.stem.split("_")[0]
            if not stem.isdigit() or stem < start or stem > end:
                continue
            try:
                st = p.stat()
            except OSError:
                continue
            count += 1
            total_size += st.st_size
            max_mtime_ns = max(max_mtime_ns, st.st_mtime_ns)
        out[str(path)] = {
            "csv_count": count,
            "total_size": total_size,
            "max_mtime_ns": max_mtime_ns,
        }
    return out


def panel_cache_paths(start: str = DEFAULT_START, end: str = DEFAULT_END) -> tuple[Path, Path]:
    cache_dir = ARTIFACT_DIR / "panel_cache"
    name = f"daily_panel_{start}_{end}_v{PANEL_CACHE_VERSION}"
    return cache_dir / f"{name}.parquet", cache_dir / f"{name}.meta.json"


def panel_cache_meta(start: str = DEFAULT_START, end: str = DEFAULT_END) -> dict:
    return {
        "version": PANEL_CACHE_VERSION,
        "start": start,
        "end": end,
        "data_root": str(DATA_ROOT),
        "sources": source_signature([DAILY_DIR, METRIC_DIR, MONEYFLOW_DIR, ST_DIR], start, end),
    }


def read_panel_cache(start: str = DEFAULT_START, end: str = DEFAULT_END, columns: list[str] | None = None) -> pd.DataFrame | None:
    if os.environ.get("ALPHA_PANEL_CACHE", "1") == "0" or os.environ.get("ALPHA_REFRESH_CACHE", "0") == "1":
        return None
    data_path, meta_path = panel_cache_paths(start, end)
    if not data_path.exists() or not meta_path.exists():
        return None
    try:
        old_meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if old_meta != panel_cache_meta(start, end):
        return None
    if columns is None:
        return pd.read_parquet(data_path)
    available = set(pq.read_schema(data_path).names)
    selected = [col for col in columns if col in available]
    return pd.read_parquet(data_path, columns=selected)


def write_panel_cache(df: pd.DataFrame, start: str = DEFAULT_START, end: str = DEFAULT_END) -> None:
    if os.environ.get("ALPHA_PANEL_CACHE", "1") == "0":
        return
    data_path, meta_path = panel_cache_paths(start, end)
    data_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_data = data_path.with_suffix(".tmp.parquet")
    tmp_meta = meta_path.with_suffix(".tmp.json")
    df.to_parquet(tmp_data, index=False)
    tmp_meta.write_text(json.dumps(panel_cache_meta(start, end), ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp_data, data_path)
    os.replace(tmp_meta, meta_path)


def add_delayed_exit_returns(df: pd.DataFrame, horizons: list[int], max_delay_days: int = MAX_EXIT_DELAY_DAYS) -> pd.DataFrame:
    g = df.groupby("ts_code", sort=False)
    for h in horizons:
        ret = pd.Series(np.nan, index=df.index, dtype=float)
        delay_days = pd.Series(np.nan, index=df.index, dtype=float)
        for delay in range(max_delay_days + 1):
            exit_open = g["open"].shift(-(h + delay + 1))
            shifted_blocked = g["sell_blocked_limit"].shift(-(h + delay))
            exit_blocked = pd.Series(np.where(shifted_blocked.isna(), True, shifted_blocked), index=df.index, dtype=bool)
            fill_now = ret.isna() & df["next_open"].notna() & exit_open.notna() & ~exit_blocked
            ret.loc[fill_now] = exit_open.loc[fill_now] / df.loc[fill_now, "next_open"] - 1
            delay_days.loc[fill_now] = delay
        df[f"exit_delay_{h}d"] = delay_days
        df[f"exit_fillable_{h}d"] = ret.notna()
        df[f"ret_o2o_{h}d"] = ret
    return df


def build_panel() -> pd.DataFrame:
    daily_cols = ["ts_code", "trade_date", "open", "high", "low", "close", "pre_close", "pct_chg", "vol", "amount", "vwap"]
    metric_cols = ["ts_code", "trade_date", "turnover_rate", "pe", "pb", "total_mv", "circ_mv"]
    mf_cols = ["ts_code", "trade_date", "buy_lg_amount", "sell_lg_amount", "buy_elg_amount", "sell_elg_amount", "net_mf_amount"]
    panel = read_csv_dir_by_date(DAILY_DIR, usecols=daily_cols)
    metric = read_csv_dir_by_date(METRIC_DIR, usecols=metric_cols)
    moneyflow = read_csv_dir_by_date(MONEYFLOW_DIR, usecols=mf_cols)
    if panel.empty:
        raise RuntimeError(f"No daily CSV data found in {DAILY_DIR}")
    panel["trade_date"] = normalize_date(panel["trade_date"])
    metric["trade_date"] = normalize_date(metric["trade_date"])
    moneyflow["trade_date"] = normalize_date(moneyflow["trade_date"])
    df = panel.merge(metric, on=["ts_code", "trade_date"], how="left")
    df = df.merge(moneyflow, on=["ts_code", "trade_date"], how="left")
    st = load_st_dates()
    df = df.merge(st, on=["ts_code", "trade_date"], how="left")
    df["is_st"] = pd.Series(np.where(df["is_st"].isna(), False, df["is_st"]), index=df.index, dtype=bool)
    df = df.sort_values(["ts_code", "trade_date"]).reset_index(drop=True)

    g = df.groupby("ts_code", sort=False)
    df["ret_1"] = g["close"].pct_change(1)
    df["ret_5"] = g["close"].pct_change(5)
    df["ret_20"] = g["close"].pct_change(20)
    df["ret_20_skip5"] = g["close"].shift(5) / g["close"].shift(20) - 1
    df["ret_60_skip20"] = g["close"].shift(20) / g["close"].shift(60) - 1
    df["std_20"] = g["ret_1"].rolling(20, min_periods=12).std().reset_index(level=0, drop=True)
    df["turn"] = df["turnover_rate"]
    df["mv_log"] = np.log1p(df["total_mv"])
    df["vwap_dev"] = df["close"] / df["vwap"] - 1
    amount_yuan = df["amount"].replace(0, np.nan) * 1000.0
    df["amihud_1"] = df["ret_1"].abs() / amount_yuan
    df["amihud_5"] = g["amihud_1"].rolling(5, min_periods=3).mean().reset_index(level=0, drop=True)
    df["amihud_20"] = g["amihud_1"].rolling(20, min_periods=12).mean().reset_index(level=0, drop=True)
    df["mf_lg_amt_ratio"] = (df["buy_lg_amount"] - df["sell_lg_amount"]) / df["amount"].replace(0, np.nan)
    df["mf_buy_pressure"] = (
        (df["buy_lg_amount"] + df["buy_elg_amount"]) - (df["sell_lg_amount"] + df["sell_elg_amount"])
    ) / df["amount"].replace(0, np.nan)
    df["amount_ma20"] = g["amount"].rolling(20, min_periods=12).mean().reset_index(level=0, drop=True)
    df["amount_ratio_20"] = df["amount"] / df["amount_ma20"].replace(0, np.nan)
    df["pb_inv"] = 1.0 / df["pb"].replace(0, np.nan)

    by_date = df.groupby("trade_date", sort=False)
    r_ret1 = by_date["ret_1"].rank(pct=True)
    r_ret5 = by_date["ret_5"].rank(pct=True)
    r_ret20 = by_date["ret_20"].rank(pct=True)
    r_ret20_skip5 = by_date["ret_20_skip5"].rank(pct=True)
    r_ret60_skip20 = by_date["ret_60_skip20"].rank(pct=True)
    r_amount_ratio = by_date["amount_ratio_20"].rank(pct=True)
    r_amount = by_date["amount"].rank(pct=True)
    r_turn = by_date["turn"].rank(pct=True)
    r_mf_pressure = by_date["mf_buy_pressure"].rank(pct=True)
    r_vwap_dev = by_date["vwap_dev"].rank(pct=True)
    r_pb_inv = by_date["pb_inv"].rank(pct=True)
    r_liq_inv = 1 - by_date["amihud_20"].rank(pct=True)
    r_low_vol = 1 - by_date["std_20"].rank(pct=True)
    r_mv_low = 1 - by_date["mv_log"].rank(pct=True)
    r_liq_improve = by_date["amihud_20"].rank(pct=True) - by_date["amihud_5"].rank(pct=True)
    df["score_shock_rev_5"] = (1 - r_ret5) * r_amount_ratio
    df["score_shock_rev_1"] = (1 - r_ret1) * r_amount_ratio
    df["score_mf_exhaust_rev"] = (1 - r_ret5) * r_mf_pressure
    df["score_mf_confirm_mom"] = r_ret5 * r_mf_pressure
    df["score_low_turn_mom"] = r_ret20 * (1 - r_turn)
    df["score_value_liq_def"] = (r_pb_inv + r_liq_inv + r_low_vol) / 3.0
    df["score_vwap_shock_rev"] = (1 - r_vwap_dev) * r_amount_ratio
    df["score_small_liq"] = r_mv_low * r_liq_inv
    df["score_liq_lowvol_mid_mom"] = r_ret20_skip5 * r_liq_inv * r_low_vol
    df["score_liq_improve"] = r_liq_improve
    df["score_liq_lowvol_lowturn_mid_mom"] = r_ret20_skip5 * r_liq_inv * r_low_vol * (1 - r_turn)
    df["score_liq_lowvol_long_mom"] = r_ret60_skip20 * r_liq_inv * r_low_vol
    df["score_liq_lowvol_lowturn_long_mom"] = r_ret60_skip20 * r_liq_inv * r_low_vol * (1 - r_turn)
    df["score_value_liq_lowvol_mid_mom"] = r_ret20_skip5 * r_pb_inv * r_liq_inv * r_low_vol
    df["score_mid_long_def_mom"] = r_ret20_skip5 * r_ret60_skip20 * r_liq_inv * r_low_vol
    df["score_capacity_lowturn_mid_mom"] = r_ret20_skip5 * r_liq_inv * r_amount * r_low_vol * (1 - r_turn)
    df["score_long_mom_short_pullback_def"] = r_ret60_skip20 * (1 - r_ret5) * r_liq_inv * r_low_vol * (1 - r_turn)
    df["score_mid_mom_short_pullback_liq"] = r_ret20_skip5 * (1 - r_ret5) * r_liq_inv * r_low_vol * (1 - r_turn)
    df["score_mf_confirm_lowturn_def_mom"] = r_ret20_skip5 * r_mf_pressure * r_liq_inv * r_low_vol * (1 - r_turn)

    df["days_since_first_seen"] = g.cumcount()
    df["next_open"] = g["open"].shift(-1)
    df["next_date"] = g["trade_date"].shift(-1)
    df["next_pre_close"] = g["pre_close"].shift(-1)
    df["next_amount"] = g["amount"].shift(-1)
    df["next_vol"] = g["vol"].shift(-1)
    shifted_next_is_st = g["is_st"].shift(-1)
    df["next_is_st"] = pd.Series(np.where(shifted_next_is_st.isna(), True, shifted_next_is_st), index=df.index, dtype=bool)
    code = df["ts_code"].astype(str)
    df["limit_pct"] = 0.10
    df.loc[code.str.startswith("688"), "limit_pct"] = 0.20
    df.loc[code.str.startswith("300") & (df["trade_date"] >= pd.Timestamp("2020-08-24")), "limit_pct"] = 0.20
    df.loc[code.str.startswith(("8", "4", "9")), "limit_pct"] = 0.30
    df.loc[df["is_st"], "limit_pct"] = 0.05
    df["next_open_ret_vs_preclose"] = df["next_open"] / df["next_pre_close"] - 1
    df["buy_blocked_limit"] = df["next_open_ret_vs_preclose"] >= (df["limit_pct"] - 0.005)
    df["sell_blocked_limit"] = df["next_open_ret_vs_preclose"] <= -(df["limit_pct"] - 0.005)
    df["signal_eligible"] = (
        df["days_since_first_seen"].ge(60)
        & ~df["is_st"]
        & df["amount"].ge(20_000)
        & df["vol"].gt(0)
    )
    df["buy_fillable"] = (
        df["next_open"].notna()
        & ~df["next_is_st"]
        & df["next_amount"].ge(20_000)
        & df["next_vol"].gt(0)
        & ~df["buy_blocked_limit"]
    )
    add_delayed_exit_returns(df, [1, 5, 10, 20])
    return df


def required_panel_columns(candidates: list[Candidate], horizons: list[int]) -> list[str]:
    cols = {
        "ts_code",
        "trade_date",
        "signal_eligible",
        "buy_fillable",
        "sell_blocked_limit",
        "total_mv",
        "amount",
    }
    cols.update(c.field for c in candidates)
    cols.update(f"ret_o2o_{h}d" for h in horizons)
    return sorted(cols)


def load_panel(candidates: list[Candidate] | None = None, horizons: list[int] | None = None) -> pd.DataFrame:
    columns = required_panel_columns(candidates, horizons) if candidates and horizons else None
    cached = read_panel_cache(columns=columns)
    if cached is not None:
        return cached
    df = build_panel()
    write_panel_cache(df)
    if columns is None:
        return df
    return df[[col for col in columns if col in df.columns]].copy()


def spearman_by_date(x: pd.DataFrame, score_col: str, ret_col: str) -> pd.Series:
    vals = []
    use_cuda = use_torch_cuda_backend()
    for dt, g in x.groupby("trade_date", sort=True):
        if use_cuda:
            corr = torch_rank_corr(g[score_col].to_numpy(), g[ret_col].to_numpy())
            if corr is not None:
                vals.append((dt, corr))
        else:
            sub = g[[score_col, ret_col]].replace([np.inf, -np.inf], np.nan).dropna()
            if len(sub) < 100 or sub[score_col].nunique() < 10:
                continue
            vals.append((dt, sub[score_col].rank().corr(sub[ret_col].rank())))
    return pd.Series(dict(vals), dtype=float)


def decile_portfolio(x: pd.DataFrame, score_col: str, ret_col: str, cost_bps: float) -> dict:
    daily = []
    prev_long = set()
    prev_short = set()
    use_cuda = use_torch_cuda_backend()
    for dt, g in x.groupby("trade_date", sort=True):
        sub = g[[score_col, ret_col, "ts_code", "buy_fillable"]]
        if use_cuda:
            long_mean, short_mean, long_pos, short_pos = torch_top_decile_returns(
                sub[score_col].to_numpy(),
                sub[ret_col].to_numpy(),
                sub["buy_fillable"].to_numpy(dtype=bool),
            )
            if long_mean is None or short_mean is None:
                continue
            codes = sub["ts_code"].to_numpy()
            long_set = set(codes[long_pos])
            short_set = set(codes[short_pos])
            n_long = len(long_set)
            n_short = len(short_set)
            gross = long_mean - short_mean
        else:
            sub = sub.replace([np.inf, -np.inf], np.nan)
            sub = sub.dropna(subset=[score_col, "ts_code"])
            if len(sub) < 300:
                continue
            ranks = sub[score_col].rank(method="first", pct=True)
            long = sub.loc[ranks >= 0.9]
            short = sub.loc[ranks <= 0.1]
            long = long.loc[long["buy_fillable"]].dropna(subset=[ret_col])
            short = short.loc[short["buy_fillable"]].dropna(subset=[ret_col])
            if len(long) < 20 or len(short) < 20:
                continue
            long_set, short_set = set(long["ts_code"]), set(short["ts_code"])
            n_long = len(long)
            n_short = len(short)
            gross = float(long[ret_col].mean() - short[ret_col].mean())
        turnover = 0.0
        if prev_long:
            turnover += 1 - len(long_set & prev_long) / max(len(long_set), 1)
        if prev_short:
            turnover += 1 - len(short_set & prev_short) / max(len(short_set), 1)
        turnover /= 2
        prev_long, prev_short = long_set, short_set
        net = gross - turnover * cost_bps / 10000.0 * 2
        daily.append((dt, gross, net, turnover, n_long, n_short))
    if not daily:
        return {}
    d = pd.DataFrame(daily, columns=["date", "gross", "net", "turnover", "n_long", "n_short"]).set_index("date")
    horizon = int(ret_col.split("_")[-1].removesuffix("d"))
    ann = 252 / max(horizon, 1)
    mean = d["net"].mean()
    std = d["net"].std()
    equity = (1 + d["net"].fillna(0)).cumprod()
    dd = equity / equity.cummax() - 1
    return {
        "days": int(len(d)),
        "gross_mean_daily": float(d["gross"].mean()),
        "net_mean_daily": float(mean),
        "ann_return_net": float(mean * ann),
        "sharpe_net": float(mean / std * math.sqrt(ann)) if std and not np.isnan(std) else None,
        "max_drawdown": float(dd.min()),
        "turnover_mean": float(d["turnover"].mean()),
        "n_long_mean": float(d["n_long"].mean()),
        "n_short_mean": float(d["n_short"].mean()),
        "portfolio_type": "long_short_diagnostic_not_directly_tradable",
        "annualization_periods": float(ann),
    }


def long_only_top_portfolio(x: pd.DataFrame, score_col: str, ret_col: str, cost_bps: float) -> dict:
    daily = []
    prev_long = set()
    use_cuda = use_torch_cuda_backend()
    for dt, g in x.groupby("trade_date", sort=True):
        sub = g[[score_col, ret_col, "ts_code", "buy_fillable"]]
        if use_cuda:
            long_mean, long_pos = torch_long_top_decile_return(
                sub[score_col].to_numpy(),
                sub[ret_col].to_numpy(),
                sub["buy_fillable"].to_numpy(dtype=bool),
            )
            if long_mean is None:
                continue
            codes = sub["ts_code"].to_numpy()
            long_set = set(codes[long_pos])
            n_long = len(long_set)
            gross = long_mean
        else:
            sub = sub.replace([np.inf, -np.inf], np.nan)
            sub = sub.dropna(subset=[score_col, "ts_code"])
            if len(sub) < 300:
                continue
            ranks = sub[score_col].rank(method="first", pct=True)
            long = sub.loc[ranks >= 0.9]
            long = long.loc[long["buy_fillable"]].dropna(subset=[ret_col])
            if len(long) < 20:
                continue
            long_set = set(long["ts_code"])
            n_long = len(long)
            gross = float(long[ret_col].mean())
        turnover = 1.0 if not prev_long else 1 - len(long_set & prev_long) / max(len(long_set), 1)
        prev_long = long_set
        net = gross - turnover * cost_bps / 10000.0
        daily.append((dt, gross, net, turnover, n_long))
    if not daily:
        return {}
    d = pd.DataFrame(daily, columns=["date", "gross", "net", "turnover", "n_long"]).set_index("date")
    horizon = int(ret_col.split("_")[-1].removesuffix("d"))
    ann = 252 / max(horizon, 1)
    mean = d["net"].mean()
    std = d["net"].std()
    equity = (1 + d["net"].fillna(0)).cumprod()
    dd = equity / equity.cummax() - 1
    return {
        "days": int(len(d)),
        "gross_mean_period": float(d["gross"].mean()),
        "net_mean_period": float(mean),
        "ann_return_net": float(mean * ann),
        "sharpe_net": float(mean / std * math.sqrt(ann)) if std and not np.isnan(std) else None,
        "max_drawdown": float(dd.min()),
        "turnover_mean": float(d["turnover"].mean()),
        "n_long_mean": float(d["n_long"].mean()),
        "portfolio_type": "long_only_top_decile",
        "annualization_periods": float(ann),
    }


def evaluate_candidate(df: pd.DataFrame, cand: Candidate, horizon: int, cost_bps: float) -> dict:
    fast = os.environ.get("ALPHA_FAST", "0") == "1"
    ret_col = f"ret_o2o_{horizon}d"
    cols = ["ts_code", "trade_date", "signal_eligible", "buy_fillable", "sell_blocked_limit", cand.field, ret_col, "total_mv", "amount"]
    x = df.loc[df["signal_eligible"], cols].copy()
    x = x.replace([np.inf, -np.inf], np.nan).dropna(subset=[cand.field])
    x["score"] = x[cand.field]
    if cand.ascending:
        x["score"] = -x["score"]
    splits = {
        "train": ("2019-01-01", "2022-12-31"),
        "validation": ("2023-01-01", "2024-12-31"),
        "test": ("2025-01-01", "2026-05-28"),
    }
    out = {
        "alpha_id": cand.alpha_id,
        "name": cand.name,
        "formula": cand.formula,
        "field": cand.field,
        "horizon_days": horizon,
        "cost_bps": cost_bps,
        "neutral": cand.neutral,
        "splits": {},
    }
    for name, (lo, hi) in splits.items():
        sub = x[(x["trade_date"] >= lo) & (x["trade_date"] <= hi)]
        ic = spearman_by_date(sub, "score", ret_col)
        port = decile_portfolio(sub, "score", ret_col, cost_bps)
        long_only = long_only_top_portfolio(sub, "score", ret_col, cost_bps)
        years = {}
        if not fast:
            for y, yg in sub.groupby(sub["trade_date"].dt.year):
                yic = spearman_by_date(yg, "score", ret_col)
                years[str(y)] = {
                    "rankic_mean": float(yic.mean()) if len(yic) else None,
                    "rankic_days": int(len(yic)),
                }
        out["splits"][name] = {
            "rows": int(len(sub)),
            "dates": int(sub["trade_date"].nunique()),
            "stocks": int(sub["ts_code"].nunique()),
            "rankic_mean": float(ic.mean()) if len(ic) else None,
            "rankic_ir": float(ic.mean() / ic.std() * math.sqrt(252)) if len(ic) > 2 and ic.std() else None,
            "rankic_positive_frac": float((ic > 0).mean()) if len(ic) else None,
            "portfolio": port,
            "long_only": long_only,
            "yearly": years,
            "size_corr": None if fast else (float(sub["score"].corr(np.log1p(sub["total_mv"]).replace([np.inf, -np.inf], np.nan))) if len(sub) else None),
            "amount_corr": None if fast else (float(sub["score"].corr(np.log1p(sub["amount"]).replace([np.inf, -np.inf], np.nan))) if len(sub) else None),
        }
    return out


def decision(result: dict) -> tuple[str, str, int]:
    val = result["splits"]["validation"]
    test = result["splits"]["test"]
    score = 0
    if (test.get("rankic_mean") or 0) > 0:
        score += 2
    if (val.get("rankic_mean") or 0) > 0:
        score += 1
    p = test.get("long_only") or {}
    if (p.get("ann_return_net") or 0) > 0:
        score += 2
    if (p.get("sharpe_net") or 0) > 0.5:
        score += 1
    if (p.get("max_drawdown") or -1) > -0.25:
        score += 1
    yearly = test.get("yearly") or {}
    pos_years = sum(1 for y in yearly.values() if (y.get("rankic_mean") or 0) > 0)
    if pos_years >= max(1, len(yearly) - 1):
        score += 1
    if score >= 6:
        return "repair", "positive but requires Codex reviewer before promote", score
    if score >= 4:
        return "repair", "mixed positive; inspect costs/exposures/leakage", score
    if (test.get("rankic_mean") or 0) > 0:
        return "pivot", "weak IC without enough portfolio support", score
    return "kill", "negative or inconclusive pilot", score


def write_reports(results: list[dict], df: pd.DataFrame) -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    REFINE_DIR.mkdir(exist_ok=True)
    REVIEW_DIR.mkdir(exist_ok=True)
    results_path = ARTIFACT_DIR / "alpha_results.json"
    results_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    ranked = []
    for r in results:
        dec, reason, score = decision(r)
        ranked.append((score, dec, r, reason))
    ranked.sort(key=lambda x: (x[0], x[2]["splits"]["test"].get("rankic_mean") or -9), reverse=True)

    idea_lines = [
        "# Alpha 候选与 Pilot 结果",
        "",
        f"生成时间：{datetime.now().isoformat(timespec='seconds')}",
        "",
        "时间点约定：所有信号在 `t` 日收盘后形成，组合在 `t+1` 开盘建立，收益为 `t+1` 开盘到退出日开盘；未使用预制未来收益 label。",
        "",
        "| 排名 | alpha | 持仓 | Test RankIC | Test AnnRet net | Sharpe | MDD | Turnover | 决策 | 分数 |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---|---:|",
    ]
    ledger_lines = []
    for i, (score, dec, r, reason) in enumerate(ranked, 1):
        t = r["splits"]["test"]
        p = t.get("portfolio") or {}
        idea_lines.append(
            f"| {i} | {r['alpha_id']} {r['name']} | {r['horizon_days']} | "
            f"{(t.get('rankic_mean') or 0):.5f} | {(p.get('ann_return_net') or 0):.4f} | "
            f"{(p.get('sharpe_net') or 0):.3f} | {(p.get('max_drawdown') or 0):.3f} | "
            f"{(p.get('turnover_mean') or 0):.3f} | {dec} | {score} |"
        )
        ledger_lines += [
            f"## {datetime.now().isoformat(timespec='seconds')} — {r['alpha_id']} {r['name']} H{r['horizon_days']}",
            "",
            f"- alpha id: `{r['alpha_id']}`",
            f"- alpha 公式/逻辑: {r['formula']}",
            f"- 使用字段: `{r['field']}`；收益字段由 panel open 重新计算",
            "- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28",
            "- 实际可用样本: "
            f"train rows={r['splits']['train']['rows']}, dates={r['splits']['train']['dates']}; "
            f"validation rows={r['splits']['validation']['rows']}, dates={r['splits']['validation']['dates']}; "
            f"test rows={r['splits']['test']['rows']}, dates={r['splits']['test']['dates']}",
            "- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买",
            f"- 是否行业/市值中性: {r['neutral']}；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`",
            f"- 回测指标: Test RankIC={(t.get('rankic_mean') or 0):.6f}, ICIR={(t.get('rankic_ir') or 0):.3f}, Long-short Sharpe={(p.get('sharpe_net') or 0):.3f}, MDD={(p.get('max_drawdown') or 0):.3f}, turnover={(p.get('turnover_mean') or 0):.3f}",
            f"- 成本后表现: cost={r['cost_bps']}bps/side proxy, annual net={(p.get('ann_return_net') or 0):.6f}",
            f"- reviewer score: pending Codex reviewer; pilot heuristic score={score}",
            "- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label",
            f"- decision: {dec}",
            f"- next action: {reason}",
            "",
        ]

    (OUT_DIR / "IDEA_REPORT.md").write_text("\n".join(idea_lines) + "\n", encoding="utf-8")
    (OUT_DIR / "ALPHA_CANDIDATES.md").write_text("\n".join(idea_lines) + "\n", encoding="utf-8")
    ledger = Path("ALPHA_DISCOVERY_LEDGER.md")
    prefix = "" if ledger.exists() else "# A股 Alpha Discovery Ledger\n\n"
    with ledger.open("a", encoding="utf-8") as f:
        f.write(prefix + "\n".join(ledger_lines) + "\n")

    (REFINE_DIR / "EXPERIMENT_PLAN.md").write_text(
        "# Alpha 实验计划\n\n"
        "1. 使用日频 panel 与 features，信号 t 日收盘后生成，t+1 开盘交易。\n"
        "2. 对 pilot 正向 alpha 做 1/5/10/20 日持仓、5/10/20 bps 成本敏感性。\n"
        "3. 强制过滤 ST、IPO 初期、停牌/低成交额、疑似涨停不可买；记录复权/退市/行业字段缺口。\n"
        "4. Codex reviewer 检查 lookahead、幸存者偏差、复权使用、交易规则和指标支持。\n\n"
        "## Post-kill improvement policy\n\n"
        "`kill` 只表示当前 alpha 公式、当前实现、当前回测协议下不能 promote，不表示整个因子方向终止。"
        "若 reviewer 指出的是框架或交易规则问题，后续必须先修复协议；若修复后样本外仍为负，"
        "再 pivot 到方向内变体或下一因子族。\n\n"
        "### A003/A005 continuation plan\n\n"
        "1. 回测协议修复：把点时点选股 universe 与次日成交可行性分离；次日字段只用于成交仿真，不用于信号排名池。\n"
        "2. 交易约束修复：纳入 T+1、停牌、涨跌停无法买卖、卖出受阻、低流动性和换手成本；H>1 使用重叠或非重叠子组合计账。\n"
        "3. 指标修复：long-short 标为诊断指标，同时输出 long-only、指数对冲或股指期货可实现版本；恢复非空 train/validation/test。\n"
        "4. A003 变体：行业/市值/流动性中性 20 日动量、跳过最近 1-5 日的中期动量、低波动/高流动性子池内动量。\n"
        "5. A005 变体：Amihud 分位截尾、成交额异常与低冲击组合、行业内流动性改善/恶化信号，而非单纯 `-rank(amihud_20)`。\n"
        "6. 停止条件：只有方向内变体在修复协议后连续负、成本后不可交易、或 reviewer 仍判 leakage/bias 不可修复，才把该方向族归档。\n",
        encoding="utf-8",
    )
    (REFINE_DIR / "EXPERIMENT_RESULTS.md").write_text(
        "# Alpha 实验结果\n\n详见 `alpha-stage/artifacts/alpha_results.json` 与 `alpha-stage/IDEA_REPORT.md`。\n",
        encoding="utf-8",
    )
    (REFINE_DIR / "EXPERIMENT_TRACKER.md").write_text(
        "# Alpha 实验跟踪\n\n- first_pass: completed local daily pilot/backtest batch.\n",
        encoding="utf-8",
    )


def main() -> None:
    horizons = [int(x) for x in os.environ.get("ALPHA_HORIZONS", "1,5,10,20").split(",") if x.strip()]
    costs = [float(x) for x in os.environ.get("ALPHA_COSTS", "10.0").split(",") if x.strip()]
    results = []
    max_candidates = int(os.environ.get("ALPHA_MAX_CANDIDATES", str(len(BASE_CANDIDATES))))
    selected = {x.strip() for x in os.environ.get("ALPHA_CANDIDATES", "").split(",") if x.strip()}
    candidates = [c for c in BASE_CANDIDATES if not selected or c.alpha_id in selected][:max_candidates]
    df = load_panel(candidates, horizons)
    for cand in candidates:
        if cand.field not in df.columns:
            continue
        for h in horizons:
            for c in costs:
                results.append(evaluate_candidate(df, cand, h, c))
    write_reports(results, df)


if __name__ == "__main__":
    main()
