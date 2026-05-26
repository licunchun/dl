---
name: A-share daily pre-market signal
description: Run the trained deep-learning model on the latest A-share panel and produce a 10-stock target list for tomorrow's open.
---

# A-share daily pre-market signal

Use this skill when the user says something like "跑一下今天的选股" / "生成明天的持仓清单" / "run today's A-share signal".

## Prerequisites

* `data/` is populated by extracting the latest `documents-export-*.zip` from USTC 云盘 into the project root.
* `checkpoints/transformer_ic.pt` exists (trained via `python -m src.train --model transformer --loss ic`).

## Steps

1. Ensure the panel cache reflects the latest CSV day:

   ```bash
   python -m src.data_loader build-panel --start 2019-01-01 --end YYYY-MM-DD
   ```

   Replace `YYYY-MM-DD` with the latest date present under `data/daily/`.

2. Run the pre-market predictor.  The `--date` argument is the *information-as-of* date: the model will rank stocks using data up to that date's close and produce the list of holdings to submit at next morning's open.

   ```bash
   python -m src.predict_daily --date YYYY-MM-DD --model transformer --n 10
   ```

   Output file: `reports/daily_logs/YYYYMMDD_targets.csv` with columns
   `rank, ts_code, name, industry, y_pred, ref_vwap, ref_close`.

3. Diff with yesterday's `targets.csv` to produce the buy/sell list:

   ```bash
   python - <<'EOF'
   import pandas as pd, pathlib as P
   logs = sorted(P.Path("reports/daily_logs").glob("*_targets.csv"))
   today, prev = pd.read_csv(logs[-1]), pd.read_csv(logs[-2])
   buy = set(today.ts_code) - set(prev.ts_code)
   sell = set(prev.ts_code) - set(today.ts_code)
   print("BUY :", buy)
   print("SELL:", sell)
   EOF
   ```

## Manual order placement (同花顺 APP)

* Market: 同花顺 APP → 交易 → 模拟 → 深度学习基础-2026
* Place **限价单**; anchor price = `ref_vwap` ± 0.5 %.  If the stock opened above +9 % it's at 涨停 — skip and log the miss.
* A-share is T+1 — a stock bought today cannot be sold today.
* Target: fully invested at all times (比赛规则).  Check cash balance after each session.

## Post-close reconciliation

Append to `reports/daily_logs/YYYYMMDD_fills.csv` with columns
`ts_code, action, qty, avg_price, filled`.  Used in the final report to
document execution slippage vs model intent.
