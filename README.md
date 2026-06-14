# A 股量化大作业（USTC 深度学习基础 2026 春）

基于日频量价 + 基本面数据，训练深度学习模型预测次日收益，构建 Top-N 选股组合，在 2026-06-01 ~ 06-12 同花顺模拟大赛中实盘演练。

## Multi-Agent Quant Research System MVP

本仓库现在包含一个可长期扩展的最小可运行 AI 量化研究团队。每日执行：

```bash
bash run_daily.sh
```

默认使用 `~/pan_sync_20260528` 作为本地 A 股数据源，并把当日结果写入 `reports/daily_logs/YYYYMMDD/`。可用环境变量覆盖：

```bash
QUANT_DATE=20260604 \
QUANT_DATA_ROOT=~/pan_sync_20260528 \
QUANT_OUTPUT_ROOT=reports \
QUANT_KNOWLEDGE_ROOT=knowledge_base \
QUANT_FACTOR_LIBRARY=factor_library \
QUANT_AGENT_RETRIES=1 \
QUANT_RETENTION_DAYS=370 \
QUANT_MAX_DATA_STALENESS_DAYS=7 \
QUANT_LOCK_STALE_MINUTES=180 \
QUANT_MIN_FREE_DISK_MB=512 \
bash run_daily.sh
```

`QUANT_DATE` 是主运行日期变量；`QUANT_RUN_DATE` 作为兼容别名也可使用。两者同时设置时，`QUANT_DATE` 优先。

离线测试或网络不可用时：

```bash
QUANT_OFFLINE=1 bash run_daily.sh
```

Alpha 全量回测需要通过 Slurm 申请 GPU；登录节点看不到 CUDA 属于预期。推荐用 launcher 提交，避免在 `sbatch --export` 里手写逗号变量导致参数被截断：

```bash
SLURM_PARTITION=A800 \
SLURM_QOS=normal \
SLURM_GPUS=1 \
SLURM_CPUS_PER_TASK=8 \
SLURM_TIME=02:00:00 \
ALPHA_CANDIDATES='A029' \
ALPHA_HORIZONS='5' \
ALPHA_COSTS='5,10,20,30' \
ALPHA_START=20190101 \
ALPHA_END=20260528 \
ALPHA_FAST=0 \
ALPHA_BACKEND=torch_cuda \
bash scripts/submit_alpha_gpu_backtest.sh
```

如果集群要求账号/项目号，再加 `SLURM_ACCOUNT=<account>`；launcher 会把这些参数传给 `sbatch`，而不是在登录节点直接运行 CUDA。

连续多日无人值守压测：

```bash
QUANT_OFFLINE=1 QUANT_SIM_DAYS=7 python -m agent.daily_simulation
```

每日调度助手会在每个 run directory 写入 `schedule.json` 和 `cron_example.txt`。该文件只生成示例，不会自动安装 crontab；readiness 会检查它是否为每日 `bash run_daily.sh`、脚本是否存在、cron 日志目录是否存在且可写。cron 输出默认写入 `reports/daily_cron.log`。

### Agent 架构

- Agent 1 `agent.market_intelligence`: 联网/离线降级收集公告、新闻、行业、政策和研报上下文，输出 `daily_events.json` 与源质量摘要。
- Agent 2 `agent.research_agent`: 读取论文、公开因子库和社区研究上下文，结合市场事件生成研究方向，输出 `research_ideas.json` 与源质量摘要。
- Agent 3 `agent.factor_design`: 生成候选因子，输出 `candidate_factors/`，记录 provenance，并按 id/formula/expression/normalized formula key 跳过知识库中已 kill 的重复因子。
- Agent 4 `agent.data_agent`: 从本地 OHLCV/metric/moneyflow/ST 构建标准数据集，输出 `daily_dataset.parquet`。
- Agent 5 `agent.backtest_agent`: 自动回测候选因子，输出 `backtest_results/`，包括 long-only 组合、long-short 诊断、成本敏感性和日度 RankIC 序列。
- Agent 6 `agent.critic_agent`: 检查失败原因、泄漏/稳定性/共线性风险，输出 `failure_analysis.md` 和结构化 `critique.json`。
- Agent 7 `agent.evolution_agent`: 基于成功/失败因子生成下一代候选，输出 `next_generation_factors/`。
- `agent.knowledge_base`: 更新长期因子数据库 `knowledge_base/factor_database/factors.json`。

### MVP 输出

每次运行生成：

```text
reports/daily_logs/YYYYMMDD/
  daily_events.json
  preflight.json
  research_ideas.json
  candidate_factors/
  candidate_factors.json
  daily_dataset.parquet
  dataset_manifest.json
  data_health.json
  backtest_results/
  backtest_results.json
  failure_analysis.md
  critique.json
  next_generation_factors/
  next_generation_factors.json
  daily_report.md
  artifact_manifest.json
  artifact_verification.json
  pipeline_state.json
  run_audit.json
  self_audit.json
  self_audit.md
  gpu_alpha_submission.json
  schedule.json
  cron_example.txt
  errors/                 # only when an agent fails

knowledge_base/factor_database/factors.json
knowledge_base/research_log.jsonl
knowledge_base/research_log_latest.json
knowledge_base/source_snapshots.jsonl
knowledge_base/source_snapshots_latest.json
knowledge_base/data_health.jsonl
knowledge_base/data_health_latest.json
knowledge_base/failure_memory.jsonl
knowledge_base/run_history.jsonl
knowledge_base/run_history_latest.json
reports/READINESS_REPORT.json
reports/READINESS_REPORT.md
reports/artifact_manifest_latest.json
reports/artifact_verification_latest.json
reports/gpu_alpha_submission_latest.json
reports/run_daily_invocations.jsonl
reports/run_daily_invocation_latest.json
factor_library/
```

### Long-Run Reliability

- `run_daily.sh` uses a run lock under `reports/.quant_daily.lock` to avoid overlapping daily jobs.
- `run_daily.sh` records every shell entrypoint invocation in `reports/run_daily_invocations.jsonl` and updates `reports/run_daily_invocation_latest.json`, including exit code, duration, host, pid, and traceback on entrypoint failure.
- Failed shell entrypoints also refresh `READINESS_REPORT.*` and artifact-manifest evidence when config can be loaded, so unattended failures are visible in the latest audit outputs instead of only in the invocation JSONL.
- Production readiness requires the latest `run_daily.sh` invocation record to exist, have `status=success`, have `exit_code=0`, and match the current run date; it also requires 365 consecutive unique dates with successful `run_daily.sh` invocation records. Direct internal `python -m agent.daily_pipeline` runs are useful for tests but do not satisfy shell-level production evidence.
- Daily GPU alpha acceleration is Slurm-only: `gpu_alpha_submission.json` and `reports/gpu_alpha_submission_latest.json` record whether the run submitted `scripts/submit_alpha_gpu_backtest.sh` through `sbatch`, or explicitly skipped because the run was offline. Production readiness requires the latest GPU submission record to match the current run and forbids silent login-node CUDA fallback.
- Production readiness also requires the latest `run_history.jsonl` record to match the current run date and current daily outputs, including counts, source quality, data health, self-audit status, and agent status, so a current shell invocation cannot be paired with stale or forged historical pipeline records.
- Stale lock files older than `QUANT_LOCK_STALE_MINUTES` are automatically recovered, and the recovery is recorded in `pipeline_state.json` and `run_audit.json`.
- `run_audit.json` records the run date, active config, lock evidence, retry settings, retention policy, and final state snapshot; production readiness requires this audit to match the current config/run date and the current `pipeline_state.json` instead of merely existing.
- Every agent status is written to `pipeline_state.json`.
- `pipeline_state.json` is checkpointed while the run is in progress; uncaught interruptions write `status=interrupted`, the active agent, completed agents, and traceback before the lock is released, and `run_audit.json` is updated with the same interrupted state.
- `artifact_manifest.json` records file sizes, mtimes, and SHA256 hashes for daily run artifacts plus key readiness and knowledge-base files.
- `artifact_verification.json` recomputes manifest SHA256 hashes for stable artifacts, records missing files or hash mismatches, and records the manifest generation timestamp it verified.
- Production readiness requires `reports/artifact_manifest_latest.json` to match the current run's `artifact_manifest.json` on stable artifact paths, so latest artifact evidence cannot point at a stale manifest; self-referential readiness outputs are skipped in this stable comparison because they are rewritten by the readiness step itself.
- `READINESS_REPORT` checks that the artifact manifest exists, matches the current run date, contains required files, includes SHA256 hashes, and passes artifact verification before allowing production-ready status. The readiness payload exposes the verifier's `manifest_generated_at` so the final report can prove it checked the final manifest.
- `preflight.json` checks required output directories are writable and verifies free disk against `QUANT_MIN_FREE_DISK_MB`; low disk becomes an auditable warning instead of an invisible mid-run surprise.
- Agents are retried with `QUANT_AGENT_RETRIES` before being marked failed.
- Agent status records keep retry evidence for transient failures, including failed attempt number, duration, error message, and traceback summary, so flaky unattended runs remain debuggable even when the final retry succeeds.
- If an agent fails, the pipeline records `errors/<agent>.json`, marks the run `complete_with_errors`, and still writes `daily_report.md`.
- Production readiness requires `daily_report.md` to summarize the current run date, required agent statuses, core research/backtest counts, source modes, data/preflight/self-audit status, readiness status/score/blocker count, backtest dataset hash, and key output file references; a stale, placeholder, count-mismatched, readiness-summary-missing, or readiness-summary-mismatched daily report blocks production-ready status.
- JSON writes use atomic temp-file replacement to reduce corruption risk during interrupted runs.
- JSONL appends are flushed/fsynced; readiness checks valid records separately from malformed lines and quarantines bad JSONL lines under `knowledge_base/jsonl_quarantine/`.
- `market_intelligence` records per-source status plus `source_quality` so live collection failures are visible instead of silently becoming research input.
- `research_agent` records paper/factor-library/community source quality, so research idea provenance and fallback mode are auditable.
- Market and research source snapshots are cached under `source_snapshots/` in each run and appended to `knowledge_base/source_snapshots.jsonl` for later source-audit replay; each snapshot records `snapshot_written_at`, per-source URLs, and live fetch metadata such as response bytes and content SHA256 when available. Production readiness requires 365 consecutive dates with production-grade snapshots from both market and research agents.
- Production readiness requires current-run `source_snapshots/market_intelligence.json` and `source_snapshots/research_agent.json`, plus same-day JSONL records, to match the current market/research source statuses, source quality, and item counts.
- `data_agent` writes `data_health.json` with row/date/stock coverage, required-column checks, duplicate-key checks, missing-rate diagnostics, and `data_source_detail` showing which local CSV directories/files were inspected and why synthetic fallback was used when applicable.
- `data_agent` checks data freshness against `QUANT_MAX_DATA_STALENESS_DAYS`; stale or future-dated local data marks `data_health.json` as `warning`.
- `data_agent` also appends `knowledge_base/data_health.jsonl`; production readiness requires 365 consecutive dates with production-grade real-data artifact records, not only run-history summaries.
- Production readiness requires `knowledge_base/data_health_latest.json` to match the current `data_health.json` and `dataset_manifest.json`, including dataset hash, size, row/stock/date counts, freshness, checks, and domain coverage.
- Old daily run directories are pruned according to `QUANT_RETENTION_DAYS` to keep 365-day operation bounded.
- `factor_design` checks `factor_id`, `formula`, and `expression` against `knowledge_base/factor_database/factors.json` so killed ideas are not repeatedly regenerated.
- Candidate factors include `formula_key` and `provenance`, and the knowledge base persists `formula_key` for stronger cross-day semantic deduplication. Failure-memory matching re-normalizes stored formula keys, so older records with whitespace/case formatting differences still block repeated failed formulas.
- Production readiness requires every latest candidate factor to have a matching run-local JSON file under `reports/daily_logs/YYYYMMDD/candidate_factors/`, with aligned `factor_id`, `created_at_run`, `formula_key`, `expression`, and `status`.
- Production readiness requires every latest candidate factor to have a matching current-run JSON file under `factor_library/`, with aligned `factor_id`, `created_at_run`, `formula_key`, and `expression`.
- Production readiness requires every latest backtest result to have a matching run-local JSON file under `reports/daily_logs/YYYYMMDD/backtest_results/`, with aligned factor id, formula key, expression, RankIC, decision, and portfolio metrics.
- Production readiness requires `backtest_results.json.dataset_provenance` to match the current `dataset_manifest.json`, including verified hash, dataset size, row/stock/date counts, source mode, and health status.
- `critic_agent` runs structured leakage, stability, and collinearity checks before a factor can remain promoted.
- Production readiness requires `failure_analysis.md` to match current `critique.json`, including run date, factor ids, decisions, issues, leakage check, stability score, and collinearity score.
- `self_audit` writes `self_audit.json` and `self_audit.md`, giving each run a machine-readable health score; production readiness requires the latest self-audit to match the current run date, have `status=pass`, have `score>=0.9`, include all required check results, and match the current daily outputs for counts, preflight, freshness, and source quality.
- `schedule` writes `cron_example.txt` and `schedule.json` so the daily job can be installed deliberately with `crontab -e`; both files are required in self-audit and artifact-manifest evidence, and readiness requires the cron example to contain the same cron line recorded in `schedule.json`.
- Each completed run appends a compact record to `knowledge_base/run_history.jsonl` and updates `run_history_latest.json`, preserving cross-day health, data, promote/kill, and agent status history for 365-day audits.
- `knowledge_base` appends `research_log.jsonl` and updates `research_log_latest.json`, preserving the daily chain from events and research ideas through candidate factors, backtests, critiques, and next-generation factors.
- Production readiness requires `research_log_latest.json` to match the current daily outputs for event count, idea count, candidate ids, backtest result ids, backtest dataset provenance, critique count, next-generation ids, and data health summary.
- Production readiness requires `knowledge_base/factor_database/factors.json` to contain same-day records for every latest backtest result, with matching formula identity, expression, RankIC, portfolio metrics, critic-resolved decision, and critic issues.
- Production readiness requires `next_generation_factors.json` to match every per-factor JSON under `reports/daily_logs/YYYYMMDD/next_generation_factors/`, with aligned `factor_id`, `parent_factor_id`, `formula_key`, and `status`.
- Production readiness checks that `run_history_latest.json`, `research_log_latest.json`, `source_snapshots_latest.json`, and `data_health_latest.json` all point at the current run date, so JSONL history cannot be paired with stale latest pointers.
- Failed factors are also persisted in `failure_memory.jsonl`, and future factor design reads that memory to avoid repeated failed formulas.
- Production readiness requires factors killed by the latest `critic_agent` run to appear in same-day `failure_memory.jsonl`, so a run cannot pass with critique failures that were never saved as reusable failure experience.
- Production readiness also requires same-day failure-memory records to match the latest killed factor's `formula_key`, critique issues/checks, and parent backtest metrics, so failure memory is reusable debug evidence rather than only an id list.
- `agent.readiness_report` aggregates run history, self-audit, factor database, and failure memory into `reports/READINESS_REPORT.md/json`; it explicitly blocks production-ready status until 365 successful audited runs are recorded.
- Production readiness also requires a 365-day consecutive streak of unique run dates with real non-synthetic fresh data backed by data artifact logs, successful shell invocations, and live market/research source evidence backed by source snapshots; duplicate records, date gaps, offline runs, and synthetic smoke runs remain useful validation but do not count as 365-day production evidence.
- `agent.daily_simulation` can run multiple consecutive daily jobs in one local smoke test and writes `reports/multi_day_simulation.json`; this output is marked `production_ready_evidence=false` because it calls `daily_pipeline` directly instead of the shell-level `run_daily.sh` entrypoint.

### Scheduling

The system does not edit crontab automatically. After a successful smoke run, review:

```text
reports/daily_logs/YYYYMMDD/cron_example.txt
```

Then install the line manually with `crontab -e` if the paths and environment are correct.

### 当前 MVP 限制

- 联网采集是 best-effort；网络失败不会阻塞每日流程。
- 回测输出 long-only top-quantile 指标和 `long_short_diagnostic_not_directly_tradable`；后者仅作因子 spread 诊断，不代表 A 股可直接做空交易。复杂行业中性、指数对冲和真实成交队列后续扩展。
- 数据缺失时会生成合成 fallback 数据以保证 pipeline 可测；生产运行应设置 `QUANT_DATA_ROOT` 指向真实数据。合成 fallback 的 freshness 会标记为 `not_applicable_synthetic`，不能作为生产数据新鲜的证据。
- `daily_simulation` 是本地连续运行压测，输出 `simulation_pass` 只表示本地多日 pipeline smoke 通过，不会替代真实 365 天 `run_daily.sh` 生产运行记录。
- `READINESS_REPORT.md` 是生产就绪证据聚合器；在真实连续 365 个唯一运行日期、真实数据证据、live source 证据、shell-level `run_daily.sh` 调用证据、逐源 snapshot、每日 data artifact 或每日 knowledge-base save 证据不足时会保持 `not_production_ready`。

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
