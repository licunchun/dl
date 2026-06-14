# A股本地数据盘点

生成时间：2026-06-03T02:34:48
数据根目录：`/home/lcc17/pan_sync_20260528`
文件数：12915，总大小：15.321 GB

## 文件分布

| 类型/目录 | 数量 |
|---|---:|
| ext .csv | 12883 |
| ext .parquet | 31 |
| ext .md | 1 |
| A股数据/news | 2701 |
| A股数据/daily | 2526 |
| A股数据/moneyflow | 2526 |
| A股数据/metric | 2526 |
| A股数据/stock_st | 2349 |
| A股数据/index_weight | 250 |
| shortterm_cache | 17 |
| may_eval_cache | 12 |
| A股数据 | 3 |
| A股数据/market | 3 |
| daily_predict_cache | 1 |
| strategy_cache | 1 |

## Parquet 表

| 文件 | 行数 | 列数 | 日期范围 | 股票数 | 重复键 | 关键字段 |
|---|---:|---:|---|---:|---:|---|
| `daily_predict_cache/panel_2019-01-01_2026-05-28.parquet` | 7725295 | 25 | ? - ? | ? | ? | ts_code, trade_date, open, high, low, close, pre_close, change, pct_chg, vol, amount, vwap, turnover_rate, turnover_rate_f... |
| `may_eval_cache/may_features_2024-01-01_2026-05-28.parquet` | 2865883 | 32 | ? - ? | ? | ? | ts_code, trade_date, ret_1, ret_5, ret_20, ma_5, ma_20, std_5, std_20, vol_ratio_5, amihud_20, vwap_dev, rsi_14, macd... |
| `may_eval_cache/may_features_2026-01-01_2026-05-28.parquet` | 467875 | 32 | ? - ? | ? | ? | ts_code, trade_date, ret_1, ret_5, ret_20, ma_5, ma_20, std_5, std_20, vol_ratio_5, amihud_20, vwap_dev, rsi_14, macd... |
| `may_eval_cache/may_features_2026-03-01_2026-05-28.parquet` | 298505 | 32 | ? - ? | ? | ? | ts_code, trade_date, ret_1, ret_5, ret_20, ma_5, ma_20, std_5, std_20, vol_ratio_5, amihud_20, vwap_dev, rsi_14, macd... |
| `may_eval_cache/may_labels_2026-01-01_2026-05-28.parquet` | 467875 | 7 | ? - ? | ? | ? | ts_code, trade_date, close, pct_chg, y_raw, y, drop_reason |
| `may_eval_cache/may_labels_2026-03-01_2026-05-28.parquet` | 298505 | 7 | ? - ? | ? | ? | ts_code, trade_date, close, pct_chg, y_raw, y, drop_reason |
| `may_eval_cache/may_labels_default_2026-01-01_2026-05-28.parquet` | 467875 | 7 | ? - ? | ? | ? | ts_code, trade_date, close, pct_chg, y_raw, y, drop_reason |
| `may_eval_cache/may_labels_nofuturelimit_2024-01-01_2026-05-28.parquet` | 2865883 | 7 | ? - ? | ? | ? | ts_code, trade_date, close, pct_chg, y_raw, y, drop_reason |
| `may_eval_cache/may_labels_nofuturelimit_2026-01-01_2026-05-28.parquet` | 467875 | 7 | ? - ? | ? | ? | ts_code, trade_date, close, pct_chg, y_raw, y, drop_reason |
| `may_eval_cache/may_panel_2024-01-01_2026-05-28.parquet` | 2865883 | 31 | ? - ? | ? | ? | ts_code, trade_date, open, high, low, close, pre_close, change, pct_chg, vol, amount, vwap, turnover_rate, turnover_rate_f... |
| `may_eval_cache/may_panel_2026-01-01_2026-05-28.parquet` | 467875 | 31 | ? - ? | ? | ? | ts_code, trade_date, open, high, low, close, pre_close, change, pct_chg, vol, amount, vwap, turnover_rate, turnover_rate_f... |
| `may_eval_cache/may_panel_2026-03-01_2026-05-28.parquet` | 298505 | 31 | ? - ? | ? | ? | ts_code, trade_date, open, high, low, close, pre_close, change, pct_chg, vol, amount, vwap, turnover_rate, turnover_rate_f... |
| `may_eval_cache/sklearn_target_panel_2024-01-01_2026-05-28.parquet` | 2865883 | 31 | ? - ? | ? | ? | ts_code, trade_date, open, high, low, close, pre_close, change, pct_chg, vol, amount, vwap, turnover_rate, turnover_rate_f... |
| `shortterm_cache/features_moneyflow_2019-01-01_2026-05-28.parquet` | 7725295 | 32 | ? - ? | ? | ? | ts_code, trade_date, ret_1, ret_5, ret_20, ma_5, ma_20, std_5, std_20, vol_ratio_5, amihud_20, vwap_dev, rsi_14, macd... |
| `shortterm_cache/features_moneyflow_2025-01-01_2026-05-28.parquet` | 1672759 | 32 | ? - ? | ? | ? | ts_code, trade_date, ret_1, ret_5, ret_20, ma_5, ma_20, std_5, std_20, vol_ratio_5, amihud_20, vwap_dev, rsi_14, macd... |
| `shortterm_cache/features_wq_2024-01-01_2026-05-28.parquet` | 2865883 | 92 | ? - ? | ? | ? | ts_code, trade_date, ret_1, ret_5, ret_20, ma_5, ma_20, std_5, std_20, vol_ratio_5, amihud_20, vwap_dev, rsi_14, macd... |
| `shortterm_cache/features_wq_2025-01-01_2026-05-28.parquet` | 1672759 | 92 | ? - ? | ? | ? | ts_code, trade_date, ret_1, ret_5, ret_20, ma_5, ma_20, std_5, std_20, vol_ratio_5, amihud_20, vwap_dev, rsi_14, macd... |
| `shortterm_cache/features_wq_daily_2026-05-29.parquet` | 1677929 | 92 | ? - ? | ? | ? | ts_code, trade_date, ret_1, ret_5, ret_20, ma_5, ma_20, std_5, std_20, vol_ratio_5, amihud_20, vwap_dev, rsi_14, macd... |
| `shortterm_cache/features_wq_daily_2026-05-31.parquet` | 1677929 | 92 | ? - ? | ? | ? | ts_code, trade_date, ret_1, ret_5, ret_20, ma_5, ma_20, std_5, std_20, vol_ratio_5, amihud_20, vwap_dev, rsi_14, macd... |
| `shortterm_cache/labels_2019-01-01_2026-05-28.parquet` | 7725295 | 7 | ? - ? | ? | ? | ts_code, trade_date, close, pct_chg, y_raw, y, drop_reason |
| `shortterm_cache/labels_2025-01-01_2026-05-28.parquet` | 1672759 | 7 | ? - ? | ? | ? | ts_code, trade_date, close, pct_chg, y_raw, y, drop_reason |
| `shortterm_cache/labels_nofuturelimit_2024-01-01_2026-05-28.parquet` | 2865883 | 7 | ? - ? | ? | ? | ts_code, trade_date, close, pct_chg, y_raw, y, drop_reason |
| `shortterm_cache/labels_nofuturelimit_2025-01-01_2026-05-28.parquet` | 1672759 | 7 | ? - ? | ? | ? | ts_code, trade_date, close, pct_chg, y_raw, y, drop_reason |
| `shortterm_cache/labels_nofuturelimit_daily_2026-05-29.parquet` | 1677929 | 7 | ? - ? | ? | ? | ts_code, trade_date, close, pct_chg, y_raw, y, drop_reason |
| `shortterm_cache/labels_nofuturelimit_daily_2026-05-31.parquet` | 1677929 | 7 | ? - ? | ? | ? | ts_code, trade_date, close, pct_chg, y_raw, y, drop_reason |
| `shortterm_cache/panel_2019-01-01_2026-05-28.parquet` | 7725295 | 31 | ? - ? | ? | ? | ts_code, trade_date, open, high, low, close, pre_close, change, pct_chg, vol, amount, vwap, turnover_rate, turnover_rate_f... |
| `shortterm_cache/panel_2024-01-01_2026-05-28.parquet` | 2865883 | 31 | ? - ? | ? | ? | ts_code, trade_date, open, high, low, close, pre_close, change, pct_chg, vol, amount, vwap, turnover_rate, turnover_rate_f... |
| `shortterm_cache/panel_2025-01-01_2026-05-28.parquet` | 1672759 | 31 | ? - ? | ? | ? | ts_code, trade_date, open, high, low, close, pre_close, change, pct_chg, vol, amount, vwap, turnover_rate, turnover_rate_f... |
| `shortterm_cache/panel_daily_2026-05-29.parquet` | 1677929 | 31 | ? - ? | ? | ? | ts_code, trade_date, open, high, low, close, pre_close, change, pct_chg, vol, amount, vwap, turnover_rate, turnover_rate_f... |
| `shortterm_cache/panel_daily_2026-05-31.parquet` | 1677929 | 31 | ? - ? | ? | ? | ts_code, trade_date, open, high, low, close, pre_close, change, pct_chg, vol, amount, vwap, turnover_rate, turnover_rate_f... |
| `strategy_cache/strategy_panel_2026-01-01_2026-05-28.parquet` | 467875 | 25 | ? - ? | ? | ? | ts_code, trade_date, open, high, low, close, pre_close, change, pct_chg, vol, amount, vwap, turnover_rate, turnover_rate_f... |

## CSV 目录

| 目录 | 文件数 | 文件日期范围 | 样例字段 |
|---|---:|---|---|
| `daily` | 2526 | 20160104 - 20260601 | ts_code, trade_date, open, high, low, close, pre_close, change, pct_chg, vol, amount, vwap |
| `index_weight` | 250 | 201601 - 202605 | index_code, con_code, trade_date, weight |
| `market` | 3 | ? - ? | ts_code, trade_date, close, open, high, low, pre_close, change, pct_chg, vol, amount |
| `metric` | 2526 | 20160104 - 20260601 | ts_code, trade_date, close, turnover_rate, turnover_rate_f, volume_ratio, pe, pe_ttm, pb, ps, ps_ttm, dv_ratio, dv_ttm, total_share, float_share, free_share |
| `moneyflow` | 2526 | 20160104 - 20260601 | ts_code, trade_date, buy_sm_vol, buy_sm_amount, sell_sm_vol, sell_sm_amount, buy_md_vol, buy_md_amount, sell_md_vol, sell_md_amount, buy_lg_vol, buy_lg_amount, sell_lg_vol, sell_lg_amount, buy_elg_vol, buy_elg_amount |
| `news` | 2701 | 20190101 - 20260528 | datetime, content, title |
| `stock_st` | 2349 | 20160809 - 20260528 | ts_code, name, trade_date, type, type_name |

## 字段能力推断

- **daily_ohlcv**: amount, buy_elg_amount, buy_elg_vol, buy_lg_amount, buy_lg_vol, buy_md_amount, buy_md_vol, buy_sm_amount, buy_sm_vol, close, high, low, mf_net_vol_ratio, net_mf_amount, net_mf_vol, open, pct_chg, pre_close, sell_elg_amount, sell_elg_vol, sell_lg_amount, sell_lg_vol, sell_md_amount, sell_md_vol, sell_sm_amount, sell_sm_vol, vol, vol_ratio_5, volume_ratio, vwap, vwap_dev, wq_amt_per_vol_rk, wq_low_vol_20_rk, wq_low_vol_5_rk, wq_mf_vol_rk, wq_mf_vwap_rk, wq_raw_vwap_revert_indrk, wq_raw_vwap_revert_rk, wq_vol_breakout_indrk, wq_vol_breakout_rk...
- **adjustment_or_shares**: float_share, free_share, total_share
- **valuation_size**: circ_mv, open, pb, pb_inv, pe, pe_inv, pe_ttm, ps, ps_ttm, total_mv, type, type_name, wq_amt_per_vol_rk, wq_value_pb_rk, wq_value_pe_rk
- **liquidity_turnover**: amihud_20, rk_turn, turn, turnover_rate, turnover_rate_f, volume_ratio, wq_amihud_liq_rk, wq_rank_turn_rk, wq_turn_reversal_rk, wq_turnover_rk
- **moneyflow**: buy_elg_amount, buy_elg_vol, buy_lg_amount, buy_lg_vol, mf_buy_pressure, mf_elg_amt_ratio, mf_lg_amt_ratio, mf_net_amt_ratio, mf_net_vol_ratio, net_mf_amount, net_mf_vol, rk_mf_buy_pressure, rk_mf_lg_amt, rk_mf_net_amt, sell_elg_amount, sell_elg_vol, sell_lg_amount, sell_lg_vol, wq_mf_elg_rk, wq_mf_lg_indrk, wq_mf_lg_rk, wq_mf_net_indrk, wq_mf_net_rk, wq_mf_pressure_indrk, wq_mf_pressure_rk, wq_mf_reversal_rk, wq_mf_vol_rk, wq_mf_vwap_rk, wq_price_mf_combo_indrk, wq_price_mf_combo_rk, wq_rank_mf_lg_rk, wq_rank_mf_net_rk, wq_rank_mf_pressure_rk
- **factor_rank**: rk_mf_buy_pressure, rk_mf_lg_amt, rk_mf_net_amt, rk_mv, rk_ret_1, rk_ret_5, rk_turn, wq_amihud_liq_rk, wq_amt_per_vol_rk, wq_intraday_reversal_rk, wq_low_vol_20_rk, wq_low_vol_5_rk, wq_ma_revert_20_rk, wq_ma_revert_5_rk, wq_macd_hist_rk, wq_macd_rk, wq_mf_elg_rk, wq_mf_lg_indrk, wq_mf_lg_rk, wq_mf_net_indrk, wq_mf_net_rk, wq_mf_pressure_indrk, wq_mf_pressure_rk, wq_mf_reversal_rk, wq_mf_vol_rk, wq_mf_vwap_rk, wq_mom_1_rk, wq_mom_20_indrk, wq_mom_20_rk, wq_mom_5_20_rk, wq_mom_5_indrk, wq_mom_5_rk, wq_price_mf_combo_indrk, wq_price_mf_combo_rk, wq_range_breakout_rk, wq_rank_mf_lg_rk, wq_rank_mf_net_rk, wq_rank_mf_pressure_rk, wq_rank_mom_1_rk, wq_rank_mom_5_rk...
- **labels**: buy_elg_amount, buy_elg_vol, buy_lg_amount, buy_lg_vol, buy_md_amount, buy_md_vol, buy_sm_amount, buy_sm_vol, drop_reason, mf_buy_pressure, rk_mf_buy_pressure, type, type_name, wq_intraday_reversal_rk, y, y_raw

## 初步风险结论

- 主面板覆盖日频 OHLCV、成交额、换手率、估值、市值与资金流；可先做日频 1-20 日持仓 alpha。
- `stock_st` 可用于剔除 ST/风险警示股票；`index_weight` 只有指数权重，不能把未来成分权重用于历史行业/指数中性。
- 未发现明确的停复牌、涨跌停、退市、上市日期专表；首轮回测必须用 `vol/amount`、价格限制近似和每只股票首次出现后冷却期来降级控制。
- `labels*` 是预计算未来收益标签，首轮只用于交叉检查，不作为回测收益来源，避免未知构造方式带来泄漏。
- 新闻数据没有个股代码映射，第一阶段不作为可交易信号使用。

详细 JSON：`alpha-stage/artifacts/data_profile.json`
