# 实验结果总结

本文记录当前 A 股次日收益预测实验的训练设置、验证切分、模型指标和阶段性结论。结果来自 Slurm 任务 `dl_a100_full-25295`，日志位于 `reports/slurm/dl_a100_full-25295.out` 和 `reports/slurm/dl_a100_full-25295.err`。

## 1. 任务与数据设定

本项目目标是用日频量价与基本面特征预测股票次日收益，并用模型分数做 Top-N 选股。标签定义为：

```text
y_t = log(close_{t+1} / close_t)
```

特征使用 20 日窗口，且特征工程中统一做 `shift(1)`，避免使用当日收盘后才知道的信息。股票池过滤规则包括剔除 ST、北交所、上市时间不足等样本；标签侧剔除停牌、涨跌停等不可交易或异常样本。

当前训练/验证时间切分：

| 集合 | 时间范围 | 用途 |
|---|---|---|
| 训练集 | 2019-01-01 至 2024-12-31 | 参数训练 |
| 验证集 | 2025-01-01 至 2026-04-30 | 模型选择、指标对比、回测 |
| 比赛/实盘期 | 2026-06-01 至 2026-06-12 | 每日盘前生成目标持仓 |

本次 A100 任务中，训练样本数约 `5,657,138`，验证样本数约 `1,440,564`，验证覆盖 `300` 个交易日。

## 2. 训练环境与参数

Slurm 任务配置：

| 项目 | 设置 |
|---|---|
| 分区 | `A100` |
| GPU | 1 张 NVIDIA A100-SXM4-80GB |
| CPU | 4 |
| 时间限制 | 3 天 |
| Python | 3.11.15 |
| PyTorch | 2.12.0+cu126 |
| CUDA 可用 | 是 |

通用训练参数：

| 参数 | 设置 |
|---|---|
| 窗口长度 | 20 个交易日 |
| epoch | 8 |
| batch 组织 | 按交易日横截面采样 |
| `batch-cap` | 8192 |
| optimizer | AdamW |
| 学习率 | 1e-3 |
| weight decay | 1e-5 |
| 随机种子 | 42 |
| 验证指标 | 日度 IC / RankIC / ICIR / DirAcc / Top10-bottom10 |

本次训练模型：

| tag | 模型 | loss | 关键参数 | 参数量 |
|---|---|---|---|---:|
| `mlp_mse` | MLP | MSE | 默认 MLP 配置 | 89,601 |
| `lstm_ic_large` | LSTM | IC loss | hidden=256, layers=3, dropout=0.2, AMP | 1,340,161 |
| `transformer_ic_large` | Transformer | IC loss | d_model=256, heads=8, layers=4, dropout=0.2, AMP | 3,171,329 |
| `transformer_ic_mid` | Transformer | IC loss | d_model=128, heads=8, layers=4, dropout=0.15, AMP | 799,233 |

## 3. 指标解释

这些指标衡量的是模型的选股效果，不是训练速度或 GPU 性能。

| 指标 | 含义 | 作用 |
|---|---|---|
| `IC` | 每个交易日横截面上，`y_pred` 与真实次日收益 `y_true` 的 Pearson 相关系数，再跨日平均 | 判断模型分数和未来收益是否同方向 |
| `RankIC` | 每个交易日横截面上，预测排名与真实收益排名的 Spearman 相关性，再跨日平均 | 更贴近选股排序，因为策略主要买排名靠前的股票 |
| `ICIR` | 平均 IC / IC 标准差，并乘 `sqrt(252)` 年化 | 衡量信号稳定性，类似因子信号的 Sharpe |
| `DirAcc` | 预测收益正负号与真实收益正负号一致的比例 | 衡量涨跌方向准确率；本项目主要做横截面排序，所以它只是辅助指标 |
| `Top10-bottom10` | 每天预测分数最高 10 只股票的真实收益均值，减去最低 10 只股票的真实收益均值，单位 bp | 直观衡量模型能否把好股票排到前面、差股票排到后面 |

说明：`1 bp = 0.01%`。例如 `Top10-bottom10 = 164.7 bp`，表示验证期平均每天模型预测前 10 名股票的真实次日收益比后 10 名高约 `1.647%`。这个不是实盘每日收益，而是排序信号强度；实盘还要考虑只能做多、换仓、手续费、涨跌停、停牌和容量约束。

## 4. 验证集指标结果

结果文件：`reports/compare_metrics.csv`。

| 模型 | IC | RankIC | ICIR | DirAcc | Top10-bottom10 |
|---|---:|---:|---:|---:|---:|
| `mlp_mse` | 0.0140 | 0.0234 | 4.01 | 0.4996 | 13.1 bp |
| `lstm_ic_large` | 0.0984 | 0.0891 | 14.62 | 0.5000 | 164.7 bp |
| `transformer_ic_large` | 0.0046 | 0.0012 | 2.32 | 0.5000 | 7.0 bp |
| `transformer_ic_mid` | 0.0201 | 0.0143 | 8.97 | 0.5000 | -22.3 bp |

从验证指标看，`lstm_ic_large` 是当前最好的模型。它的 IC、RankIC、ICIR 和 Top10-bottom10 都明显高于其他模型，说明它能较稳定地把次日收益更高的股票排在前面。

`DirAcc` 基本都在 50% 附近，这说明当前模型并不是主要靠判断单只股票“明天涨还是跌”获得效果，而是靠横截面排序。对于 Top-N 选股任务，这是合理的：只要排名靠前的股票平均表现更好，方向准确率不一定显著高于 50%。

## 5. 回测结果

回测使用验证集预测结果，策略规则为首日等权持有 10 只，之后每天卖出当前持仓中模型分数最低的 2 只，并买入未持仓股票中模型分数最高的 2 只。手续费为 `0.0003`，回测中包含涨停/不可交易过滤。

| 模型 | 年化收益 | Sharpe | 最大回撤 | 天数 |
|---|---:|---:|---:|---:|
| `lstm_ic_large` | 75.70% | 2.43 | -16.24% | 299 |
| `transformer_ic_large` | 19.90% | 0.86 | -25.15% | 299 |
| `transformer_ic_mid` | -1.27% | 0.11 | -25.18% | 299 |

对应产物：

| 模型 | 回测目录 | 图 |
|---|---|---|
| `lstm_ic_large` | `reports/backtest_lstm_ic_large/` | `reports/figures/nav_compare_lstm_ic_large_val_preds.png` |
| `transformer_ic_large` | `reports/backtest_transformer_ic_large/` | `reports/figures/nav_compare_transformer_ic_large_val_preds.png` |
| `transformer_ic_mid` | `reports/backtest_transformer_ic_mid/` | `reports/figures/nav_compare_transformer_ic_mid_val_preds.png` |

回测同样支持 `lstm_ic_large` 作为当前主模型：它在验证期取得最高年化收益、最高 Sharpe 和较低最大回撤。

## 6. 当前结论

当前最优模型是 `lstm_ic_large`。可以概括为：

```text
lstm_ic_large 在 2025-01-01 至 2026-04-30 验证集上取得
IC=0.0984、RankIC=0.0891、ICIR=14.62、Top10-bottom10=164.7bp。
回测年化收益 75.70%，Sharpe 2.43，最大回撤 -16.24%。
```

这表明 LSTM 的横截面排序信号显著强于 MLP baseline 和两个 Transformer 配置。当前 Transformer 配置没有跑出预期效果，尤其 `transformer_ic_large` 的 IC 与 RankIC 接近 0，说明其验证期排序能力较弱。

需要注意的是，`Top10-bottom10` 超过 1%/天是很强的信号。若没有数据泄露，它说明模型有明显选股能力；但正因为数值较强，后续报告中需要重点说明防泄露设计，并继续做更保守验证。

## 7. 已完成的验证

本次 Slurm 任务中已完成：

| 验证项 | 结果 |
|---|---|
| 特征/标签缓存重建 | 完成 |
| 防泄露与训练管线测试 | `6 passed` |
| 4 个模型训练 | 完成 |
| 指标对比 | 完成，写入 `reports/compare_metrics.csv` |
| 3 个模型回测 | 完成 |
| 回测图输出 | 完成 |

## 8. 注意事项与后续建议

当前 `src.train` 会保存 best checkpoint，但最终写出的 `*_val_preds.parquet` 是最后一个 epoch 的预测，不一定对应 best epoch。例如 `lstm_ic_large` 的 best IC 出现在 epoch 6，最后用于 compare/backtest 的预测来自 epoch 7。两者差距不大，但严格实验报告建议后续用 best checkpoint 重新推理并生成验证预测。

后续建议：

1. 用 best checkpoint 重新生成 `val_preds`，再重新跑 `compare` 和 `backtest`。
2. 增加更保守的 walk-forward 验证，避免单一验证区间偶然性。
3. 继续检查特征时间戳、基本面数据可得性、涨跌停/停牌过滤，确保没有未来信息。
4. 将 `lstm_ic_large` 作为比赛期盘前出单主模型，Transformer 作为备选或继续调参对象。
