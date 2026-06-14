# Daily Quant Research Report

Run date: 20260605

## Agent Status

- preflight: ok
- market_intelligence: ok
- research_agent: ok
- factor_design: ok
- data_agent: ok
- backtest_agent: ok
- critic_agent: ok
- evolution_agent: ok
- knowledge_base: ok
- schedule: ok
- self_audit: ok
- readiness_report: ok

## Summary

- events collected: 1
- market source mode: offline (0/6 ok)
- research ideas: 3
- research source mode: offline (0/3 ok)
- candidate factors: 5
- skipped failed factors: 0
- backtested factors: 5
- backtest dataset sha256: f2c5fb3cf62c
- raw backtest candidates: 4
- promoted after critic: 1
- data health: ok
- preflight: ok
- self audit: pass (1.00)

## Top Backtest Results

| factor | decision | RankIC | long_only_ann | long_short_ann_diag | Sharpe | turnover |
|---|---|---:|---:|---:|---:|---:|
| F_VOL_REV_5 | raw_candidate | 0.03685 | 0.31005 | 0.05179 | 1.700 | 0.519 |
| F_VALUE_LIQ_DEF_5 | raw_candidate | 0.03439 | 0.18452 | -0.12779 | 1.385 | 0.046 |
| F_MF_EXHAUST_5 | raw_candidate | 0.02742 | 0.27147 | -0.01939 | 1.476 | 0.590 |
| F_VWAP_REV_5 | raw_candidate | 0.01875 | 0.32821 | 0.10194 | 1.735 | 0.692 |
| F_MF_CONFIRM_5 | kill | -0.02544 | 0.25602 | -0.07928 | 1.445 | 0.604 |

## Files

- `daily_events.json`
- `preflight.json`
- `research_ideas.json`
- `candidate_factors/`
- `daily_dataset.parquet`
- `data_health.json`
- `backtest_results/`
- `failure_analysis.md`
- `next_generation_factors/`
- `knowledge_base/factor_database/factors.json`
- `pipeline_state.json`
- `self_audit.json`
- `schedule.json`
- `cron_example.txt`
- `knowledge_base/run_history.jsonl`
- `reports/READINESS_REPORT.md`
