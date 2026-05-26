# A 股量化大作业（USTC 深度学习基础 2026 春）

基于日频量价 + 基本面数据，训练深度学习模型预测次日收益，构建 Top-N 选股组合，在 2026-06-01 ~ 06-12 同花顺模拟大赛中实盘演练。

## 目录

```
src/
  data_loader.py      # 日切片 -> 长表，股票池过滤
  features.py         # 技术面 + 截面 + 基本面因子
  labels.py           # 次日 pct_chg 标签，涨跌停剔除
  dataset.py          # T=20 滑窗 + 窗口内 z-score
  models/             # MLP / LSTM / Transformer
  train.py            # 训练入口（MSE / IC-loss）
  eval.py             # IC / RankIC / ICIR / 胜率
  backtest.py         # vectorbt 回测
  predict_daily.py    # 每日 as-of CLI → reports/daily_logs/YYYYMMDD_targets.csv
  compare.py          # 与指数 / baseline 对比
tests/                # 防泄露单测
skills/               # Claude Code SKILL.md 加分项
reports/              # 最终报告 + 图表 + daily_log
data/                 # 解压后的数据（gitignore）
```

## 数据准备

```
# 把云盘同步来的 documents-export-YYYY-M-D.zip 放在项目根
unzip -oq documents-export-2026-5-12.zip -d data/
```

## 复现流程

```
pip install -r requirements.txt

# 1. 构建特征 parquet（慢，首次 ~5-10 分钟）
python -m src.data_loader build-panel --start 2019-01-01 --end 2026-04-30

# 2. 训练
python -m src.train --model mlp
python -m src.train --model lstm
python -m src.train --model transformer --loss ic

# 3. 回测 + 出图
python -m src.backtest --model transformer
python -m src.compare

# 4. 比赛期每日盘前出单：--date 是数据截止日，输出下一交易日目标
python -m src.predict_daily --date 2026-05-29 --model transformer --tag transformer_ic_large
```

## 关键约束

- **禁止数据泄露**：特征仅使用 t-1 及之前；窗口内标准化（不用全量 mean/std）；涨跌停剔除标签。
- 股票池：全 A 股排除 ST 与北交所（与比赛口径一致）。
- 策略：首日等权 10 只，之后每日换出/换入各 2 只。
- A100 训练推荐完整横截面 batch：`--batch-cap 8192` 或 `--batch-cap 0`。

## 作业信息

- 课程：深度学习基础 2026 春，USTC
- 截止：2026-06-14 BB 提交
- 比赛：同花顺 APP，搜索「深度学习基础-2026」，验证答案 `USTC`
- 比赛期：2026-06-01 ~ 2026-06-12（10 个交易日）
