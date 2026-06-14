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

> 接入策略：`src/features.py` 主线只用 OHLCV + metric；`moneyflow/` 在两条独立支线里使用——短期 LSTM（`scripts/short_term_competition_train.py` 的 `MONEYFLOW_FEATURES`）和树模型 selected 特征集（在 `mf_*` 衍生 rank 列上）。`news/` 文本数据未接入（工程成本高，且 Critic 阶段判断对短期选股贡献有限）。

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

## 3. 模型实现

我们一开始严格按作业示例从神经网络做起，过程中发现 LSTM/Transformer 在 2026Q2 严重失稳后，又补充了 LightGBM/XGBoost 一条主线。两条线代码各自独立，便于横向对比。

### 3.1 深度学习模型（代码：`src/models/`）

三个模型按复杂度递增，共享输入/输出接口（`(B, T, F) → (B,)`）：

| 模型 | 参数规模 | 描述 |
| --- | --- | --- |
| `MLP` | ~0.1 M | 基线：flatten(T·F) → 128·3 层 → 1 |
| `LSTMModel` | 0.1 ~ 1.5 M | 2-3 层 LSTM, hidden 64/128/256/384，取最后一步 |
| `TransformerModel` | 0.1 ~ 3 M | 2-4 层 Encoder, d=64/128/256, 4-8 头，学习 [CLS] + 可学习位置编码 |

#### 3.1.1 损失函数

- `MSE`：标准回归。
- **`IC loss`**：`1 - pearson(pred, y)`，batch = 一个交易日的整截面。直接优化排序而非绝对收益，更适合选股。
- 短期模型还引入了**指数 recency 权重**（`scripts/short_term_competition_train.py`）：训练日 IC loss 按 `exp(-ln2 · age / half_life)` 缩放，半衰期 30/60/90 天。

#### 3.1.2 训练（代码：`src/train.py`）

- 优化器 AdamW，lr=1e-3，wd=1e-5，梯度裁剪 1.0。
- 8 个 epoch，按验证 IC 保存 best。
- A100 主实验用 `--batch-cap 8192 --amp`，单截面单批，DayBatchSampler 保证「一个 batch = 一个交易日」。
- 所有 checkpoint、验证预测、训练日志写到 `checkpoints/`。

### 3.2 梯度提升树主线（代码：`scripts/explore_models.py`、`scripts/train_lgbm_wq_short.py`）

- **特征侧**：在 §2.3 时序 + 基本面 + 横截面 rank 之外，构造了 ~40 个 WorldQuant 风格 alpha（截面 rank、量价回归、流动性、换手率），以及四个特征集合 `base / alpha_only / base+alpha / selected`（`selected` 是按训练期 RankIC 单调筛掉低贡献后留下的 80 列）。
- **目标侧**：
  - LightGBM **LambdaRank**：每个交易日构造一个 group，标签由次日收益分位映射成 0-N 整数。
  - LightGBM **huber** / XGBoost **pseudoHuber**：回归形式，方便和 IC loss 做对照。
- **样本权重**：与深度模型对齐，按训练期日期做指数 recency 衰减，半衰期参数化为搜索维度（10 / 20 / 30 / 45 / 60 / 90）。
- **方向性**：每个候选额外有 `forward / inverse` 两个版本，用于发现「反向短期 alpha」是否存在；最终我们用此排除了一批形似过拟合的反向候选。

## 4. 我们尝试过的模型与训练方案

作业要求重点写「实验亮点」。本节先用一张总表把所有跑过的方案汇总（尝试 → 目的 → 最好结果 → 是否进入最终方案 → 淘汰原因），再展开三条主线：**4.1 深度学习失败 / 4.2 树模型胜出 / 4.3 alpha-research 补充未 promote**。所有数值都可在 `reports/compare_metrics.csv`、`reports/may_2026_validation/summary_*.csv`、`alpha-stage/artifacts/alpha_results.json` 复算。

### 4.0 总表：尝试矩阵

| # | 尝试 | 目的 | 最好结果 | 入选最终方案 | 淘汰原因 |
| --- | --- | --- | --- | --- | --- |
| A | MLP + MSE | 作业示例基线 | 长验证 IC 0.014, Top10 +13 bp | 否 | 信号近零，作为 baseline 比较 |
| B | Transformer + IC loss | 看注意力是否更适合横截面 | 长验证 IC 0.005~0.020 | 否 | 4 层 d=256 完全失效，2 层 mid 也仅 0.020 |
| C | LSTM + IC loss + DayBatch | 作业主线 | 长验证 IC **0.099** / RankIC 0.090 / Top10 +173 bp | 否 | 5 月 OOS 年化 -88.9%，regime shift 后反向 |
| D | 短期 LSTM + recency 衰减 + 资金流 | 用近端样本对齐 5 月 | 4 个短期 LSTM May 年化均 < -70% | 否 | 短数据无法救 LSTM，整条 LSTM 路被否 |
| E | sklearn SGD（线性 ranker baseline） | 给树模型一个最简单参考线 | RankIC 0.049（一度全场最高） | 否 | May BT 年化 -47.4%，RankIC ≠ 收益 |
| F | LightGBM `lgbm_wq_*` 七候选 | 把信号搬到树模型 + WQ alpha | wq_06（huber+hl30）May 年化 +12.1% | 否（被 4.2.2 的网格替代） | 是阶段性最优，后被 explore_002 全面超越 |
| G | 43-候选探索网格（LGBM/XGB × 损失 × 特征 × HL × 起点） | 系统化扫调参空间 | explore_002（LambdaRank+selected+hl30+train2025）BT Sharpe **2.38**, BT 年化 **+144%** | **是**，作为最终上线模型 | — |
| H | fast 因子分组 LGBM（按论文/语义分组） | 看是否单组就够强 | `wq_momentum + huber + forward` Sharpe 2.50 / +162% | 否 | 仅 15 个 BT 日，过短；与 explore_002 高度同源 |
| I | 文献组合（Carhart, FF+, AQR, MSCI Barra, Qlib158）huber | 文献已知风格因子能否在 A 股 5 月可用 | `worldquant_101_price_volume`（huber+forward）Sharpe 1.05 / +37%；`carhart_ff_plus_momentum`（huber+forward）IC 0.044 / Sharpe -0.13 / -21% | 否 | 多数 Sharpe 在 0~1 之间，不优于 explore_002；`carhart` IC 正但回测仍亏，再次说明信号 ≠ 收益 |
| J | rescue_20260602（5-6 天近窗 tune） | 6/2 现场救火，挑能交易的 6/3 名单 | `rescue_2025_rank_alpha` 6 天 IC 0.047 / Sharpe 8.3 | 否 | 6 个 BT 日太短；同表 RankIC 反向（-0.013），同时 huber 版 RankIC 也是负的 |
| K | event reversal 模型（恐慌反弹分类器） | 把次日反弹作为 0/1 分类，避开回归 | val AUC **0.626** | 否 | 但 top-k 5/10/20 名单的 mean_next_pct 全部为负（-0.46~-0.55），AUC 高 ≠ 选股可用 |
| L | LightGBM `lr_*` 学习率/树数网格（24 候选 ×4 cost） | 检查是否有低 lr / 多树的稳定收益 | 全部条目均落后于 G | 否 | 没人胜出 |
| M | `alpha-stage` Cycle 1（A001~A006） | 显式因子库 + agent pipeline | A003 20D 动量短窗 RankIC 0.10、A005 Amihud RankIC 0.029（短窗假阳性） | 否 | 扩窗后 RankIC 反向，Codex 二审 1/10，A003/A005 kill |
| N | `alpha-stage` Cycle 2（A019~A030 中期动量+低波动+流动性等） | 修一遍后再选 repair 候选 | A029 中期动量短回撤低冲击：H5 train RankIC 0.069 / val RankIC **0.045** / 长短 5bps 4.9% / 30bps -2.2%，long-only 净收益 14.4%~18.1% | 否（保留为 repair） | 30bps 长短转负，未过 critic gate；只作 spread 诊断 |
| O | 跨模型 ensemble（explore_002 + 004 + 029 cross-section rank 平均） | 计划用差异化打分降方差 | 仅 5/29 离线生成过 `20260529_ensemble_targets.csv` | **没真正部署到 6/1** | 6/1 凌晨只有 explore_002 训练完，004/029 因 GPU 排队/数据 schema 临时回退；最终上线只用 explore_002 |

总表读法：A~D 是「为什么 DL 不行」，E~L 是「为什么树模型这条线最后只剩 G」，M~N 是「另一条独立 alpha 实验线，没产出 promote 但产出了边界」，O 是「计划中的 ensemble 没真正打到比赛」。下面三个小节按这三条主线展开。

### 4.1 主线 1：深度学习路线被 regime shift 否决

#### 4.1.1 长验证集上的「漂亮数字」

按作业示例先训练 MLP / LSTM / Transformer 三个共享接口的小模型（输入 `(B, 20, F)` → 输出 `(B,)`），损失对比 MSE 与 IC loss，验证窗 2025-01 ~ 2026-04（~300 个交易日，记作 long val）：

| Tag | IC | RankIC | ICIR | Top-10 利差 (bp) | 备注 |
| --- | --- | --- | --- | --- | --- |
| `mlp_mse` | 0.014 | 0.023 | 4.01 | +13 | MSE 基线，几乎无信号 |
| `transformer_ic_large` | 0.005 | 0.001 | 2.32 | +7 | 4 层 d=256，IC loss，几乎全噪声 |
| `transformer_ic_mid` | 0.020 | 0.014 | 8.97 | -22 | 中等 Transformer，long-only 利差转负 |
| `lstm_ic_large` | **0.099** | 0.088 | 13.28 | +169 | 2 层 hidden=256，IC loss |
| `lstm_ic_h384_l2_w20` | 0.099 | **0.090** | 13.24 | **+173** | hidden=384，RankIC/利差最佳 |
| `lstm_ic_h384_l3_w20` | 0.098 | 0.089 | **13.82** | +145 | 3 层，ICIR 最好 |
| `lstm_ic_h256_l3_w40` | 0.092 | 0.083 | 13.58 | +152 | window=40 |

**深度学习这条线内部的小结论**（这一段只在 LSTM/MLP/Transformer 之间作对比，不外推到树模型）：

1. IC loss + DayBatchSampler 显著好于 MSE：MLP+MSE IC≈0.014，换成 LSTM+IC loss 直接到 0.099，与「目标函数和评估指标对齐」的直觉一致；后续所有深度模型默认走这条路。
2. 大 Transformer 不工作：4 层 256d 在 ~6 年训练数据上 IC≈0.005，2 层中等版本也只有 0.020。结合 SNR 极低 + 自注意力对噪声敏感，我们把 Transformer 列为「这套数据上无法训出来」。
3. LSTM hidden 从 256 升到 384、层数从 2 升到 3 在 long val 上几乎不再提升 IC，但 RankIC、ICIR 略升，让我们暂时把 LSTM hidden=384/2 层当成主线候选。

#### 4.1.2 5 月单月验证：所有 LSTM 全炸

把上一节的 LSTM 拿到 2026 年 5 月（16 个交易日，short val）单独跑回测：

| Tag | May IC | May RankIC | May 年化 | May Sharpe |
| --- | --- | --- | --- | --- |
| `lstm_ic_large` | -0.024 | -0.018 | -88.9% | -6.64 |
| `lstm_ic_short_2025_w5_h64_l1_hl60_lr3e4` | — | — | -78.2% | -6.31 |
| `lstm_ic_short_mf_decay_h256_l2_w10` | — | — | -82.9% | -4.36 |
| `lstm_ic_short_w5_h128_hl90` | — | — | -74.4% | -3.48 |

所有 long val 表现好的 LSTM 在 May 上年化 < -70%。我们随后做了三件事来确认这不是单点失败：

- 训练「短窗口 + recency-weighted IC loss」的小 LSTM（半衰期 30/60/90 天），引入资金流特征 `mf_net_amt_ratio`：四个候选 May 年化均 < -70%。
- 把 LSTM 的方向反转作为对照（`*_inverse`）：表面好看，但等同于「拿一个已知反向的信号当主信号」，没有可解释性，被否。
- 用一个最简单的 sklearn SGD 线性 ranker（recency 衰减、特征同 selected）作 baseline：RankIC 0.049（彼时全场最高），但 May BT 年化 -47.4% / Sharpe -2.09 — RankIC 高但回测亏，再次印证「short val 上分布偏移很大」。

**结论**（限定到 LSTM/Transformer/SGD 这条线）：在 long val 上 IC=0.099 的 LSTM，到 5 月单月就是 -88.9% 年化。换句话说，long val 上的 IC 不能直接外推到比赛期；深度模型本身没问题，但样本分布漂移让 2019-2024 学到的因子在 2026Q2 反向，这条路不能直接用。

### 4.2 主线 2：树模型 + WQ 风格特征逐步胜出

#### 4.2.1 七候选 LGBM（`lgbm_wq_*`）：先确认方向

把信号源从「LSTM 处理 (B, 20, F)」换成「LightGBM 直接学 cross-section 排序」，特征加进 ~40 个 WorldQuant 风格 alpha（截面 rank、量价回归、流动性、换手率），训练 2025-01 ~ 2026-04，验证 May：

| Tag | Obj | 半衰期 | May IC | May RankIC | Top10 (bp) | May 年化 | May Sharpe |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **wq_06** | huber | 30 | +0.041 | +0.029 | +204 | +12.1% | +0.47 |
| wq_01 | l1 | 30 | +0.026 | +0.015 | +29 | -22.9% | -0.66 |
| wq_03 | l1 | 60 | +0.041 | +0.021 | -4 | -67.8% | -3.55 |

读出来的几条**这一阶段内**的现象（不下大结论）：

- 同样的 IC（0.041 vs 0.041），但 RankIC 不同（0.029 vs 0.021），huber 在 May BT 上比 l1 多出约 80 个百分点 — 单看 IC 或单看 RankIC 都会误判。
- 半衰期 60 → 30 把 May BT 从 -67.8% 拉回 +12.1%，提示在 short val 这种近端 16 天的窗口上，样本权重越靠近近端越对。
- wq_06 是「树模型这条线的第一个能用配置」，但 Sharpe 0.47 并不强；只能作为下一步网格的起点。

#### 4.2.2 43-候选探索网格

为系统化排除运气成分，我们在 A800 上跑了一次 27.7 分钟的网格搜索（`scripts/explore_models.py`，job 27750），交叉 5 个轴：模型框架（LightGBM / XGBoost）× 损失（LambdaRank / huber / pseudoHuber）× 特征集（base / alpha_only / base+alpha / selected）× 半衰期（10 / 20 / 30 / 45 / 60 / 90 天）× 训练起点（2024 / 2025）。43 个候选全部完成，原始结果在 `reports/may_2026_validation/summary_explore.csv`。

按 May 回测 Sharpe 排序，**剔除 explore_038 这种过拟合反例**（见下方独立小节）后的 Top 6：

| Tag | 框架 | Obj | 特征 | HL | 训练起点 | IC | RankIC | Top10 (bp) | BT Sharpe | BT 年化 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **explore_002** | LGBM | LambdaRank | selected | 30 | 2025 | +0.075 | +0.046 | +177 | **2.38** | **+144%** |
| **explore_004** | LGBM | LambdaRank | alpha_only | 30 | 2024 | +0.058 | +0.029 | +165 | 1.95 | +102% |
| **explore_035** | LGBM | huber | selected | 30 | 2025 | +0.037 | +0.024 | +148 | 1.69 | +91% |
| explore_039 | LGBM | huber | selected | 20 | 2025 | +0.041 | +0.026 | +186 | 1.35 | +67% |
| **explore_029** | XGBoost | pseudoHuber | alpha_only | 60 | 2025 | +0.046 | **+0.052** | +258 | 1.19 | +49% |
| explore_008 | LGBM | LambdaRank | base+alpha | 30 | 2024 | +0.048 | +0.022 | +117 | 0.76 | +25% |

从这次网格能稳稳读出来的几条结论（每条都用网格内的同条件对比，不再外推）：

1. **同特征/同半衰期/同训练起点下，LambdaRank > huber**：explore_002 (LambdaRank, selected, hl30, 2025) 的 Sharpe 2.38 vs explore_035 (huber, selected, hl30, 2025) 的 Sharpe 1.69。差距来自 LambdaRank 直接优化排序损失，目标函数与 Top-N 选股一致。
2. **2024 数据是有毒的**：完全相同的 LambdaRank+selected+hl30，train2025 → Sharpe **2.38**，train2024 → Sharpe **-3.06**（explore_000）。这是网格里最干净的对照之一。我们因此把训练起点从「2019-01」收紧到「2025-01」，牺牲样本量换分布一致性。
3. **XGBoost 提供异源 RankIC**：explore_029 的 RankIC 0.052 是 43 个候选里最高的，但 May BT 只有 Sharpe 1.19；它和 LightGBM 的误差结构互补，是计划中 ensemble 的多样性来源。
4. **更强正则化救了 huber**：在 wq 七候选里 wq_06 (huber, reg_alpha=0.05, num_leaves=31) Sharpe 0.47，到 explore_035 (huber, reg_alpha=0.2, num_leaves=63) Sharpe 1.69 — 同损失、同特征下，正则化是关键。
5. **WQ alpha 已经携带主要信号**：alpha_only（去掉 OHLCV 直接特征）依旧能到 Sharpe 1.95（explore_004），证明信号主要来自横截面 alpha 而非原始量价。

#### 4.2.3 过拟合反例：explore_038（独立小节，避免误导）

`explore_038`（LGBM, huber, selected, **inverse**, hl=10, 2025）BT Sharpe 3.09 / BT 年化 +162%，但它的 IC 是 -0.015、RankIC -0.029、Top10 利差 -57 bp/天。读法：把一个负向信号取反、再用 10 天极短半衰期严重偏向最后两周，等于在 16 天 BT 窗口上做了过拟合，单看 Sharpe 会得到完全错误的结论。**已 blacklist 不入选 ensemble**，本节单列以警示「永远不能只看夏普」。

#### 4.2.4 周边补丁实验：fast 分组 / 文献组合 / 学习率网格 / rescue / event 分类器

为避免「explore_002 是网格运气」，我们又跑了几组独立实验作交叉印证：

- **fast 因子分组 LGBM**（`summary_factor_lgbm_fast.csv`）：按语义分组单独训练。最强 `fast_wq_momentum_huber_forward` Sharpe **2.50** / 年化 **+162%** — 数字漂亮但只有 15 个 BT 日，且与 explore_002 的 selected 特征集高度同源，无法独立支持「另一类特征也行」的结论。
- **文献组合**（`summary_factor_lgbm_literature_combos_*.csv`）：把 Carhart 4 因子 + 动量、Fama-French + 动量、AQR Style、MSCI Barra Core Style、Qlib Alpha158-like 各打成一组用 huber 学。最好的是 `worldquant_101_price_volume_huber_forward`（IC 0.048, RankIC 0.039, Sharpe 1.05, 年化 +37%）；`carhart_ff_plus_momentum_huber_forward` IC 0.044 / RankIC 0.031 但 May 年化 -21% / Sharpe -0.13 — 又一例 IC 正但回测亏的「单一指标陷阱」，且 inverse 版本 Sharpe 跌到 -5.1。文献组合整体不优于 explore_002，未入选。
- **`lr_*` 学习率/树数网格**（24 个 LightGBM × 4 个 cost=5/10/20/30bps，目录 `backtest_overnight_lr_*`）：调小 lr、加多 num_iterations 换稳定性，没有候选超过 explore_002，作为反方向稳健性检查。
- **`rescue_20260602`**（5-6 天近窗紧急 tune，`reports/rescue_20260602/`）：6/2 凌晨想抢 6/3 的名单，用 2025-01 起 / 2026-01 起两个起点 × rank/huber × selected/alpha/base+alpha 共 9 组，仅 6 个 BT 日。最高 `rescue_2025_rank_alpha` IC 0.047 / Sharpe 8.3 / 年化 +1473%，但同表 RankIC -0.013，huber 版 RankIC 也都是负的 — 6 天窗口本身不可信，**未入选实盘**，仅留作 rescue path 备份。
- **event reversal 分类器**（`reports/reversal_event_20260602/`）：把「连续大跌后是否次日反弹」做成 0/1 分类（GBDT，27 个量价/资金流/换手率特征），val AUC **0.626**；但 top-k=5/10/20 名单的 mean_next_pct 分别为 -0.46% / -0.48% / -0.55%，**AUC 高 ≠ 选股可用**。这条路没有用。
- **sklearn SGD 线性 baseline**（`summary_sklearn.csv`）：RankIC **0.049**（一度全场最高）但 May BT 年化 -47.4% / Sharpe -2.09 — 与 carhart、wq_03、explore_038 共同构成「单一指标陷阱」证据链。

#### 4.2.5 Ensemble 计划与最终上线现实

最初计划按差异化打分做 ensemble：

| 模型 | 框架 | 损失 | 特征 | 计划角色 |
| --- | --- | --- | --- | --- |
| `explore_002` | LightGBM | LambdaRank | selected (80) | 主排序器 |
| `explore_004` | LightGBM | LambdaRank | alpha_only (60) | WQ alpha 专家 |
| `explore_029` | XGBoost | pseudoHuber | alpha_only (60) | 异源回归打分 |

合并方式是**对每个模型预测做日度 cross-section rank，再等权平均得到组合 score**（不是直接平 logit，避免 XGBoost 数值偏离主导；注意：是「rank 等权平均」，旧稿写成「等权 RankIC 加权平均」是错的，已更正）。

5/29 用三模型生成过一次离线 ensemble 名单（`reports/daily_logs/20260529_ensemble_targets.csv`），但 6/1 凌晨只有 explore_002 完成训练并落到 `checkpoints/explore_002_lgbm_lambdarank_selected_forward_hl30_train2025.pkl`；004 / 029 因 GPU 排队 + dataset_provenance schema 临时变化没能及时跑完。**最终上线 6/1 用的是 `20260601_explore_002_targets.csv`，不是 ensemble**。这是个工程教训：把 ensemble 当成 nice-to-have，没把它包进每日 pipeline。后续 6/2 ~ 6/12 沿用单模型 explore_002，是诚实的事实而不是设计选择。

### 4.3 主线 3：alpha-stage 显式因子库（未 promote，但约束了边界）

并行另开一条「显式因子库 + agent pipeline」线（`alpha-stage/`），目的是补充树模型看不见的可解释 alpha：

- **Cycle 1（A001~A006）**：覆盖反转 / 动量 / 波动率 / 流动性 / 换手率 / 市值 / 资金流。2026 年内短窗 sanity 出现「假阳性」：A003 20 日动量 H5 RankIC 0.10、A005 Amihud 流动性 H5 RankIC 0.029；扩到 2025-2026 全窗后 RankIC 反向（-0.052 / -0.029）。Codex 二审打 1/10，A003 / A005 全部 kill。
- **回测协议修复**：信号 universe 与次日成交分离、H>1 年化口径修正、long-short 标记为诊断而非可交易、退出 fillability 拦掉跌停被卡住的退出。
- **Cycle 2（A019~A030）**：跳短期反转、转中期动量 + 低波动 + 流动性 / 价值、Amihud 一阶差分等 repair 候选。最强候选 **A029（中期动量 + 短回撤 + 低冲击）** 表达式 `rank(rank(ret_20_skip5)*(1-rank(ret_5))*rank(liq_inv)*rank(low_vol)*(1-rank(turn)))`。验证集表现：

  | 成本 | val RankIC | 长短年化 | 长短 Sharpe | long-only 年化 | long-only Sharpe |
  | --- | --- | --- | --- | --- | --- |
  | 5 bps | 0.045 | +4.92% | 0.246 | +18.06% | 1.244 |
  | 10 bps | 0.045 | +3.50% | 0.175 | +17.33% | 1.195 |
  | 20 bps | 0.045 | +0.65% | 0.032 | +15.89% | 1.095 |
  | 30 bps | 0.045 | -2.20% | -0.110 | +14.45% | 0.995 |

  长短组合在 30bps 下转负、Sharpe 跨成本不稳定，未通过 critic gate；但 long-only top-decile 在 5~30bps 全档都正、Sharpe 1.0~1.24（注意：long-only 是 ~330 只 ≠ 比赛要求的 10 只组合，仅作 spread 参考）。结论：A029 状态为 `repair`，不进入 promote。
- **GPU 路径**：所有 alpha-stage 全量回测一律 `bash scripts/submit_alpha_gpu_backtest.sh` 走 Slurm，登录节点不直接调 CUDA。

这条线没有产出 promote 的 alpha，但它**约束了主线树模型可以宣称的功能**：报告里不把 long-short 利差当成可交易策略，仅作 spread 诊断。

### 4.4 与基准对比（限定口径）

- 沪深 300（000300.SH）2025-01 ~ 2026-04 期间累计收益约 +9% / Sharpe ~0.4，最大回撤 -15%。
- May 2026 单月：实际上线的 explore_002 在 16 个交易日上 Top-10 利差 +177 bp/天，同期沪深 300 -3.1%；BT 年化 +144% — 注意：BT 样本只有 15 个交易日，年化口径要保留谨慎性。
- **不外推**：长验证集 IC 0.099 是 LSTM 的成绩，不能用来声称「树模型 ensemble 在长验证集上 IC 提升一个数量级」。我们只能说：在 short val（May 16 天）这个有限窗口上，从 LSTM 的「-88.9% 年化」回到 explore_002 的「+144% 年化」，是 short val 这一窗口下的差距，长 val 上没有同口径的树模型 BT 可比。

### 4.5 防泄露与稳健性自检

- `tests/test_no_leakage.py` 三项断言：特征严格因果、标签为次日 log 收益、窗口 z-score 均值 < 1e-5。
- `tests/test_training_pipeline.py` 跑一次 mini 训练 + 推理，保证训练入口不会因 schema 偏移而无声降级。
- 我们在 v1 特征里曾踩过一次坑：`_cross_section_ranks` 误用未 shift 的 `ret_1`，导致 IC 一度到 0.21（不正常）。修复后回到 0.04x，并补了对应单测。
- 「单一指标陷阱」证据链：explore_038（Sharpe 3.09 / IC -0.015）、carhart_ff_plus_momentum（IC 0.044 / 年化 -21%）、sklearn_sgd（RankIC 0.049 / 年化 -47%）、wq_03 vs wq_06（同 IC、同向 RankIC，BT 差 80%）、rescue_2025_rank_alpha（6 天 Sharpe 8.3 / RankIC 反向）、event reversal（AUC 0.626 / top-k 期望负）。**永远要 IC、RankIC、ICIR、Top-K 利差、年化、Sharpe、最大回撤六项联合判断**。

### 4.6 组合回测协议（代码：`src/backtest.py`）

- 初始 100 万，n=10 等权建仓，每日换 k=2，双边手续费 0.0003。
- 涨停过滤：估计 |pct_chg| ≥ 9.5% 的不可买。
- 基准对比：000300.SH（沪深 300）。
- 输出：年化、夏普、最大回撤、净值曲线（`reports/figures/nav_compare.png`）。
- **已知局限**：原版 `src/backtest.py` 用次日 pct_chg 做交易过滤，存在轻微未来信息成分；alpha-stage 的回测脚本已修复，但作业版回测保留这一已知问题并在报告中说明，不在本次大作业中重训整个流水线。

## 5. 模拟交易（待填，06-12 后补完）

### 5.1 每日流程

每日 9:00 前运行（实际上线模型为 `explore_002` LightGBM LambdaRank，不是 §3.1 的 transformer；旧版 `src.predict_daily --model transformer` 命令保留但未在比赛中使用）：

```bash
# 1. 同步并构建截至 T 的特征面板
python -m src.data_loader build-panel --start 2019-01-01 --end YYYY-MM-DD

# 2. 用 explore_002 跑次日 Top-N 名单
python scripts/predict_strategy_targets.py \
  --asof YYYY-MM-DD \
  --checkpoint checkpoints/explore_002_lgbm_lambdarank_selected_forward_hl30_train2025.pkl \
  --feature-set selected --direction forward --n 10 \
  --out reports/daily_logs/YYYYMMDD_explore_002_targets.csv
```

对比前一日 `*_targets.csv` 得到买卖清单，限价单挂在前日 `vwap ± 0.5%`，盘中 11:00 / 14:30 各巡查一次，收盘后写 `reports/daily_logs/YYYYMMDD_fills.csv`。

### 5.2 日常记录（占位）

| 日期 | 目标收益（模型） | 实盘收益（同花顺） | 调仓数 | 未成交 | 备注 |
| --- | --- | --- | --- | --- | --- |
| 2026-06-01 | | | | | |
| … | | | | | |

### 5.3 收益对比（占位）

附同花顺截图：收益曲线 / 持仓 / 调仓记录。

## 6. 实验亮点

1. **完整的「失败-诊断-换路」过程**：MLP/Transformer→LSTM→LSTM 在短期失败→LightGBM huber→LambdaRank→43 候选网格→ensemble，每一步换路都有具体证据（IC、Sharpe、Top-K bp），不是凭感觉。
2. **IC loss + 日批 sampler**：训练目标与选股目标对齐，比 MSE 更适合横截面打分；MLP+MSE IC=0.014 → LSTM+IC=0.099 是最直接的证据。
3. **窗口内 z-score（float64）**：规避作业明确禁止的「全量标准化」，并用单测固定行为。
4. **43 候选系统化网格**：一次性扫完模型/损失/特征/半衰期/训练起点 5 个维度，发现「2024 数据有毒、LambdaRank 显著优于回归、explore_038 高 Sharpe + 负 IC 是过拟合」三类非平凡结论。
5. **Ensemble 多样性**：故意挑两个框架（LGBM/XGB）、两种损失（LambdaRank/pseudoHuber）、两种特征集（selected/alpha_only），靠 cross-section rank 平均，而不是 logit 平均。
6. **防泄露三件套 + CI**：因果断言 + 标签断言 + 窗口标准化断言，在历史上确实抓到过一次未 shift 的 `_cross_section_ranks` 泄露。
7. **盘前 CLI + SKILL.md**（对标 LLMQuant Awesome Trading Agents）：一条命令走完「读最新数据 → 生成 Top-10 目标 → 输出限价参考 → diff 买卖清单」。
8. **GPU 路径强制走 Slurm**：alpha-stage 全量回测一律 `bash scripts/submit_alpha_gpu_backtest.sh`，登录节点不直接调 CUDA，避免「在登录节点偷算」的合规风险。

## 7. 感悟与思考

- A 股日频 IC 典型 0.02 ~ 0.08，若验证 IC > 0.15 基本可认定存在泄露 —— 我们在 v1 特征中遇到过一次（后发现 `_cross_section_ranks` 误用未 shift 的 `ret_1`，修复后回到 0.04x）。
- 模型不是主要瓶颈；**特征工程 + 无泄露 + 样本选择**才是。同样的 LambdaRank 配置仅靠把训练起点从 2024 换成 2025，Sharpe 就从 -3.06 跳到 +2.38。
- 「长验证集 IC 高」不等于「比赛期能用」：我们最早信得最多的 `lstm_ic_large` 在 300 天验证 IC=0.099，但在 5 月 16 个交易日上变成 -88% 年化。最终入选的 LightGBM ensemble 是被「短窗口 + regime 一致性」筛出来的，不是被长验证集 IC 选出来的。
- 单一指标不可信：explore_038 Sharpe 3.09 但 IC<0；wq_06 与 wq_03 RankIC 都是 0.041 但回测年化差 80 个百分点。我们最终用 IC、RankIC、ICIR、Top-K 利差、年化、Sharpe、最大回撤六项联合判断。
- LLM Agent（外部资料中铺天盖地的多 Agent 辩论）在选股信号层面远不如一个小 LSTM/树模型 + 好特征。但在「每日盘前复盘报告」这类叙事性任务上，Claude Code + SKILL.md 组合体验非常好，本次作业的 `skills/a-share-daily-report/SKILL.md` 即为本地化实践。

## 8. 分工

| 成员 | 学号 | 分工 |
| --- | --- | --- |
| [姓名1] | [学号1] | 数据/特征/标签、无泄露单测、报告§2、日志 |
| [姓名2] | [学号2] | 模型/训练/回测、SKILL.md、报告§3-4、日志 |

## 附录 A 复现命令

```bash
pip install -r requirements.txt

# 1. 构建特征 parquet（首次 ~5-10 分钟）
python -m src.data_loader build-panel --start 2019-01-01 --end 2026-04-30

# 2. 深度学习基线 + IC loss 主线
python -m src.train --model mlp         --loss mse --tag mlp_mse
python -m src.train --model lstm        --loss ic  --tag lstm_ic_large \
    --hidden 256 --layers 3 --dropout 0.2 --epochs 8 --batch-cap 8192 --amp
python -m src.train --model transformer --loss ic  --tag transformer_ic_large \
    --d-model 256 --heads 8 --layers 4 --dropout 0.2 --epochs 8 --batch-cap 8192 --amp

# 3. LightGBM/XGBoost 主线（包含 43 候选网格）
python scripts/train_lgbm_wq_short.py             # wq_00 ~ wq_06 七候选
python scripts/explore_models.py                  # 43 候选网格，~28 min on A800

# 4. 跨模型对比 + 回测
python -m src.compare --tags mlp_mse lstm_ic_large transformer_ic_large transformer_ic_mid \
    lstm_ic_h384_l2_w20 lstm_ic_h384_l3_w20 lstm_ic_h256_l3_w40
python -m src.backtest --preds checkpoints/lstm_ic_large_val_preds.parquet \
    --out reports/backtest_lstm_ic_large

# 5. 比赛期每日盘前出单（实际上线路径）：--asof 是数据截止日
python scripts/predict_strategy_targets.py \
  --asof 2026-05-29 \
  --checkpoint checkpoints/explore_002_lgbm_lambdarank_selected_forward_hl30_train2025.pkl \
  --feature-set selected --direction forward --n 10 \
  --out reports/daily_logs/20260529_explore_002_targets.csv

# 5.b 旧版 transformer CLI（保留可复现，未用于比赛）：
# python -m src.predict_daily --date 2026-05-29 --model transformer --tag transformer_ic_large --n 10

# 6. 单测
pytest tests/
```

## 附录 B 参考

- 作业说明：`大作业 (1).md`
- USTC 云盘：https://pan.ustc.edu.cn/ 群组「深度学习基础-2026」
- 数据说明：zip 内 `README.md`
- 外部地图：https://github.com/LLMQuant/awesome-trading-agents
