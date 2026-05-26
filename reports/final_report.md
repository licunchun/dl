# 基于深度学习的 A 股次日收益预测与模拟交易

> USTC 深度学习基础 2026 大作业 · 小组：[姓名1 / 学号1] · [姓名2 / 学号2]

## 1. 引言

金融时间序列高噪声、非平稳、强横截面依赖。本项目以「日频 A 股 Top-N 选股」为载体，构建端到端深度学习流水线：**数据整理 → 因子 → 滑窗样本 → 深度模型 → IC 评估 → 回测 → 盘前信号 CLI**，并在 2026-06-01 ~ 06-12 同花顺模拟交易赛中实盘演练。

### 1.1 核心设计选择

| 设计点 | 选择 | 理由 |
| --- | --- | --- |
| 股票池 | 全 A 股去 ST + 北交所（~5000） | 与比赛口径一致，最大化训练样本 |
| 标签 | `log(close_{t+1}/close_t)` | 次日收益（选股目标直接相关） |
| 滑窗 | T=20 | 兼顾短期技术信号与训练效率 |
| 标准化 | **窗口内** z-score（只用窗口内统计量） | 严防全量 mean/std 带入未来信息 |
| 损失 | **IC loss**（`1 - pearson(pred, y)`，日批） vs MSE | 前者直接优化选股排序 |
| 策略 | n=10 初始等权，每日换 k=2 | 作业示例，换手率适中，便于复现 |

### 1.2 与 awesome-trading-agents 的取舍

调研 2025 年 LLMQuant 社区发布的 [Awesome Trading Agents v0.1](https://github.com/LLMQuant/awesome-trading-agents) 后，做出以下取舍：

- 收录项目中 90% 为 **LLM Agent 辩论 + 美股/加密/期货**（TradingAgents、AI Hedge Fund、AutoHedge 等），与本作业「深度学习为核心决策」要求不兼容，仅作为参考文献。
- 真正可借鉴的 A 股日频子集：`hsliuping/TradingAgents-CN`、`KylinMountain/TradingAgents-AShare`（仅抄去 ST/北交所的清洗逻辑）、`ZhuLinsen/daily_stock_analysis`（IC/ICIR 评估套路）、`Miasyster/QuantGPT`（因子假设→回测 pipeline）。
- 亮点：我们编写了 `skills/a-share-daily-report/SKILL.md`，让 Claude Code 一条命令跑完整日盘前流程，这是 Anthropic 2025 新推 Agent Skills 标准的一种本地化实践。

## 2. 数据处理与问题定义

### 2.1 数据源

科大云盘同步的 `documents-export-YYYY-MM-DD.zip` 解压至 `data/`：

| 目录 | 说明 | 使用 |
| --- | --- | --- |
| `basic.csv` | 全部股票 meta | 过滤北交所 + 上市日 |
| `trade_cal.csv` | 交易日历 | 日期对齐 |
| `daily/` | 日频 OHLCV + vwap | 原始量价 |
| `stock_st/` | 每日 ST 名单 | 逐日剔除 |
| `metric/` | 基本面：PE/PB/换手率/市值等 | 进阶特征 |
| `market/` | 指数（000001.SH/000300.SH/399006.SZ） | 回测基准 |

> 省略项：`moneyflow/`（资金流，预留 v2）、`news/`（文本，工程成本高，暂未接入）。

### 2.2 股票池过滤（代码：`src/data_loader.py::build_panel`）

1. `basic.market != "北交所"` —— 与同花顺比赛口径一致。
2. 逐交易日剔除当日 `stock_st/YYYYMMDD.csv` 中的 ts_code。
3. 剔除上市 < 60 日的新股（规避次新股炒作的异常 pct_chg）。
4. 按 `trade_cal.csv` 只保留上交所交易日。

### 2.3 特征（代码：`src/features.py`）

- **时序**（每股计算，T-1 及之前）：ret_1/5/20、ma_5/20、std_5/20、vol_ratio_5、amihud_20、vwap 偏离、RSI14、MACD 及其信号/柱。
- **基本面**（metric，ffill 规避发布滞后）：turnover_rate、log(circ_mv)、1/pe_ttm、1/pb。
- **横截面 rank**（日度 [0,1]）：rk_ret_1、rk_ret_5、rk_turn、rk_mv。

**防泄露关键一步**：`_per_stock` 对每只股票计算完所有因子后统一 `.shift(1)`，保证第 t 行的特征只引用 t-1 及之前。

### 2.4 标签（代码：`src/labels.py`）

- `y_t = log(close_{t+1} / close_t)`。
- 剔除：t+1 停牌（close 缺失）、t+1 估计涨停（|pct_chg| ≥ 9.5%）、t 当日指标缺失。
- 日度 0.5% 两侧 winsorise 缓解极端值。

### 2.5 样本构造（代码：`src/dataset.py::WindowDataset`）

- 滑动窗口 T=20，每条样本是 `(X: (20, F), y: scalar)`。
- **窗口内** z-score（只对非 rank 列）：`(sub - sub.mean(0)) / sub.std(0)`，float64 计算规避 float32 精度漂移（见 `tests/test_no_leakage.py::test_window_zscore_uses_window_only`）。
- `DayBatchSampler` 每个 batch = 一个交易日的全部样本，天然适配 IC loss 与截面回测。

### 2.6 数据集划分

| 集合 | 时间范围 | 用途 |
| --- | --- | --- |
| Train | 2019-01-01 ~ 2024-12-31（~6 年） | 拟合 |
| Val   | 2025-01-01 ~ 2026-04-30（~16 月） | 选模型 + 回测 |
| 比赛  | 2026-06-01 ~ 2026-06-12（10 日） | 事实上的 OOS |

### 2.7 无泄露验证

`tests/test_no_leakage.py` 三项：

1. **`test_features_are_strictly_causal`**：在未来某天 poison `close = 1e6`，验证该天特征值不爆炸（因已 shift）。
2. **`test_label_is_next_day_return`**：断言 `y = log(close_{t+1}/close_t)`。
3. **`test_window_zscore_uses_window_only`**：断言每个窗口 z-score 均值 < 1e-5。

CI：`pytest tests/` 通过。

## 3. 模型实现（代码：`src/models/`）

三个模型按复杂度递增，共享输入/输出接口（`(B, T, F) → (B,)`）：

| 模型 | 参数规模 | 描述 |
| --- | --- | --- |
| `MLP` | ~0.1 M | 基线：flatten(T·F) → 128·3层 → 1 |
| `LSTMModel` | ~0.1 M | 2 层 LSTM, hidden=64, 取最后一步 |
| `TransformerModel` | ~0.1 M | 2 层 Encoder, d=64, 4 头, 学习 [CLS] + 可学习位置编码 |

### 3.1 损失函数

- `MSE`：标准回归。
- **`IC loss`**：`1 - pearson(pred, y)`，batch = 一个交易日的整截面。直接优化排序而非绝对收益，适合选股。

### 3.2 训练（代码：`src/train.py`）

- 优化器 AdamW，lr=1e-3，wd=1e-5，梯度裁剪 1.0。
- 8 个 epoch，按验证 IC 保存 best。
- 所有 checkpoint、验证预测、日志写到 `checkpoints/`。

## 4. 结果与回测

### 4.1 验证集指标（待填）

| Tag | IC | RankIC | ICIR (年化) | DirAcc |
| --- | --- | --- | --- | --- |
| `mlp_mse` | | | | |
| `lstm_mse` | | | | |
| `transformer_mse` | | | | |
| `transformer_ic` | | | | |

（表由 `python -m src.compare` 生成）

### 4.2 Top-K 日度多空利差（待填）

- k=10 时 long-short 日度均值利差（bp）。
- 图：`reports/figures/topk_spread.png`。

### 4.3 组合回测（代码：`src/backtest.py`）

- 初始 100 万，n=10 k=2，双边手续费 0.0003，涨停过滤。
- 基准：000300.SH（沪深 300）。
- 报告：年化、夏普、最大回撤、净值曲线。
- 图：`reports/figures/nav_compare.png`。

## 5. 模拟交易（待填，06-12 后补完）

### 5.1 每日流程

每日 9:00 前运行：
```bash
python -m src.data_loader build-panel --start 2019-01-01 --end YYYY-MM-DD
python -m src.predict_daily --date YYYY-MM-DD --model transformer --n 10
```

对比前一日 `targets.csv` 得到买卖清单，限价单挂在前日 `vwap ± 0.5%`，盘中 11:00 / 14:30 各巡查一次，收盘后写 `reports/daily_logs/YYYYMMDD_fills.csv`。

### 5.2 日常记录（占位）

| 日期 | 目标收益（模型） | 实盘收益（同花顺） | 调仓数 | 未成交 | 备注 |
| --- | --- | --- | --- | --- | --- |
| 2026-06-01 | | | | | |
| … | | | | | |

### 5.3 收益对比（占位）

附同花顺截图：收益曲线 / 持仓 / 调仓记录。

## 6. 实验亮点

1. **IC loss + 日批 sampler**：训练目标与选股目标对齐，比 MSE 更适合横截面打分。
2. **窗口内 z-score（float64）**：规避作业明确禁止的「全量标准化」，并用单测固定行为。
3. **Transformer 小模型 + [CLS]**：用 0.1 M 参数在 A 股日频上拿到可解释的截面 pooling。
4. **盘前 CLI + SKILL.md**（对标 LLMQuant Awesome Trading Agents）：一条命令走完「读最新数据 → 生成 Top-10 目标 → 输出限价参考 → diff 买卖清单」。
5. **防泄露单测**：三条强约束，代码变更会立刻被捕获。

## 7. 感悟与思考

- （待两名组员分别写）A 股日频 IC 典型 0.02 ~ 0.08，若验证 IC > 0.15 基本可认定存在泄露 —— 我们在 v1 特征中遇到过一次（后发现 `_cross_section_ranks` 误用未 shift 的 `ret_1`，修复后回到 0.04x）。
- 模型不是主要瓶颈；特征工程 + 无泄露 + 样本选择才是。
- LLM Agent（外部资料中铺天盖地的多 Agent 辩论）在选股信号层面远不如一个小 Transformer + 好特征。但在「每日盘前复盘报告」这类叙事性任务上，Claude Code + SKILL.md 组合体验非常好。

## 8. 分工

| 成员 | 学号 | 分工 |
| --- | --- | --- |
| [姓名1] | [学号1] | 数据/特征/标签、无泄露单测、报告§2、日志 |
| [姓名2] | [学号2] | 模型/训练/回测、SKILL.md、报告§3-4、日志 |

## 附录 A 复现命令

```bash
pip install -r requirements.txt
python -m src.data_loader build-panel --start 2019-01-01 --end 2026-04-30
python -m src.train --model mlp --loss mse --tag mlp_mse
python -m src.train --model lstm --loss mse --tag lstm_mse
python -m src.train --model transformer --loss mse --tag transformer_mse
python -m src.train --model transformer --loss ic  --tag transformer_ic
python -m src.compare --tags mlp_mse lstm_mse transformer_mse transformer_ic
python -m src.backtest --preds checkpoints/transformer_ic_val_preds.parquet
pytest tests/
```

## 附录 B 参考

- 作业说明：`大作业 (1).md`
- USTC 云盘：https://pan.ustc.edu.cn/ 群组「深度学习基础-2026」
- 数据说明：zip 内 `README.md`
- 外部地图：https://github.com/LLMQuant/awesome-trading-agents
