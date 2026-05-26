# 项目工程说明（供协作者 + AI 工具阅读）

> 本文件是 **本作业仓库** 的入口说明。`AGENTS.md` 是用户全局的 OMX 编排合约，不由本项目修改。

## 1. 背景

USTC《深度学习基础》2026 春大作业：用深度学习模型预测 A 股次日收益，2026-06-01 ~ 06-12 在同花顺模拟大赛演练，2026-06-14 提交实验报告 + 源码。

核心行动计划：`C:\Users\lcc\.claude\plans\floofy-wishing-lightning.md`。

## 2. 目录速览

```
src/
  data_loader.py      # 原始 CSV → 过滤 → 长表 parquet 缓存（build-panel 子命令）
  features.py         # 因子（时序 + 基本面 + 横截面 rank），全部 shift(1)
  labels.py           # 次日 log 收益标签，剔除停牌/涨停
  dataset.py          # T=20 滑窗 + 窗口内 float64 z-score + DayBatchSampler
  models/             # MLP / LSTM / Transformer（~0.1 M 参数）
  train.py            # 训练循环（MSE or IC loss）
  eval.py             # 日度 IC / RankIC / ICIR / DirAcc
  backtest.py         # 自写回测（T+1、涨停过滤、0.0003 手续费）
  predict_daily.py    # as-of 数据截止日 CLI → reports/daily_logs/YYYYMMDD_targets.csv
  compare.py          # 跨 tag 指标汇总
tests/test_no_leakage.py   # 三条无泄露强单测（pytest）
skills/a-share-daily-report/SKILL.md  # Claude Code 每日盘前 Skill（加分项）
reports/final_report.md    # 报告骨架，§2-3 已写，§4-5 等训练/比赛后补
data/                      # zip 解压（~4.4 GB，.gitignore）
checkpoints/               # 训练产物，.gitignore
```

## 3. 运行环境

- **推荐环境**：`D:\Anaconda3\envs\dlenv`（Python 3.10，torch 2.10 CPU，pandas 2.3.3）。
- GPU：当前 torch 是 CPU 版本；如装 CUDA torch，用 `pip install torch --index-url https://download.pytorch.org/whl/cu124`。
- 其他依赖：`pip install -r requirements.txt`（pyarrow/tqdm/pytest/sklearn 必须；vectorbt/pandas-ta 暂未强依赖）。

## 4. 常用命令

```bash
# 首次 / 每次数据更新后
python -m src.data_loader build-panel --start 2019-01-01 --end 2026-04-30

# 训练 4 个模型（对比用）
python -m src.train --model mlp --loss mse         --tag mlp_mse
python -m src.train --model lstm --loss mse        --tag lstm_mse
python -m src.train --model transformer --loss mse --tag transformer_mse
python -m src.train --model transformer --loss ic  --tag transformer_ic

# A100 large models（推荐主实验）
python -m src.train --model lstm --loss ic --tag lstm_ic_large \
  --hidden 256 --layers 3 --dropout 0.2 --epochs 8 --batch-cap 8192
python -m src.train --model transformer --loss ic --tag transformer_ic_large \
  --d-model 256 --heads 8 --layers 4 --dropout 0.2 --epochs 8 --batch-cap 8192

# 指标对比 + 回测
python -m src.compare --tags mlp_mse lstm_mse transformer_mse transformer_ic
python -m src.backtest --preds checkpoints/transformer_ic_val_preds.parquet

# 盘前选股（每日比赛期）：--date 是数据截止日，输出下一交易日目标
python -m src.predict_daily --date 2026-05-29 --model transformer --tag transformer_ic_large --n 10

# 测试
pytest tests/
```

## 5. 关键约束（已写入代码 + 单测，勿绕过）

1. **特征严格因果**：`features.py::_per_stock` 末尾统一 `.shift(1)`。
2. **窗口内标准化**：`dataset.py::_zscore` 只用当前窗口统计量，float64 计算。
3. **标签剔除**：停牌、涨停、首日缺失直接 NaN，`WindowDataset` 默认跳过。
4. **股票池与比赛口径一致**：去 ST（逐日）+ 去北交所 + 上市 ≥ 60 日。

## 6. 与 awesome-trading-agents 的取舍

外部 99% 的项目是 LLM Agent 辩论 / 美股 / 加密，不符合作业「深度学习神经网络为核心决策」的要求。**仅把 `skills/a-share-daily-report/SKILL.md` 作为工程亮点**（体现 Anthropic 2025 Agent Skills 标准本地化）。

## 7. 已知 TODO

- [ ] 修复后跑完 A100 large tags：`lstm_ic_large`、`transformer_ic_large`。
- [ ] 补 `reports/final_report.md` §4.1-4.3 指标与图。
- [ ] 5/26 起跑盘前彩排 5 个交易日。
- [ ] 6/01–6/12 比赛期每日 `daily_logs/`。
- [ ] 6/13 报告定稿 + 打包。
- [ ] 可选：加 `moneyflow/` 特征；跑 n=20 k=3 备选策略。
