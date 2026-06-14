# Results

## 2026-06-03 — A股 alpha discovery first pass

- 数据盘点已完成，输出见 `alpha-stage/DATA_REPORT.md` 与 `alpha-stage/artifacts/data_profile.json`。
- 本地数据根目录 `/home/lcc17/pan_sync_20260528` 约 15.321 GB，含 12,915 个文件：CSV 12,883 个、parquet 31 个、md 1 个。
- 原始 CSV 覆盖：`daily`、`metric`、`moneyflow` 从 2016-01-04 到 2026-06-01；`stock_st` 从 2016-08-09 到 2026-05-28；`index_weight` 从 2016-01 到 2026-05；`market` 含 3 个指数行情文件；`news` 从 2019-01-01 到 2026-05-28。
- 首轮策略范围：日频中低频，信号 t 日收盘后形成，t+1 开盘建仓，持仓 1/5/10/20 个交易日；不使用预制未来收益 label。
- 首轮硬约束：剔除 ST/次日 ST、首次出现后 60 个交易日内股票、低成交额、无成交/疑似停牌、疑似涨停不可买；涨跌停和停牌字段缺失时用价格限制与成交量/成交额近似。
- 当前状态：CSV 路径 backtest 正在运行，parquet 路径已因读取错误转为数据质量风险记录。

### 2026 sanity pilot

- 配置：`ALPHA_START=20260101 ALPHA_END=20260528 ALPHA_MAX_CANDIDATES=6 ALPHA_HORIZONS=1,5`。
- 正向候选：A003 20 日动量，H5 Test RankIC 0.10249，成本后年化 8.9733，Sharpe 27.34，MDD -0.004；H1 RankIC 0.02720，成本后年化 1.5456。
- 正向候选：A005 Amihud 流动性，H5 Test RankIC 0.02918，成本后年化 3.2423，Sharpe 11.05，MDD -0.031；H1 RankIC 0.01746，成本后年化 0.8890。
- 负向/淘汰：A001 1 日反转、A002 5 日反转、A004 低波动、A006 小市值在 2026 sanity 窗口多为负 IC 或负成本后收益。
- 验证结论：2026 sanity 仅用于框架和方向筛选，样本太短且 train/validation 不完整，不能 promote。已启动 A003/A005 的 2024-2026 扩展验证。

### 2025-2026 A003/A005 H5 验证

- 配置：`ALPHA_FAST=1 ALPHA_START=20250101 ALPHA_END=20260528 ALPHA_CANDIDATES=A003,A005 ALPHA_HORIZONS=5`。
- A003 20 日动量：Test rows 1,371,180，dates 271，stocks 5,431；RankIC -0.05216，ICIR -6.45，RankIC positive fraction 0.303；long-short 成本后年化 -0.5691，Sharpe -1.268，最大回撤 -0.814，平均换手 0.214。结论：kill。
- A005 Amihud 流动性：Test rows 1,371,180，dates 271，stocks 5,431；RankIC -0.02938，ICIR -3.54，RankIC positive fraction 0.417；long-short 成本后年化 -0.4258，Sharpe -1.180，最大回撤 -0.669，平均换手 0.066。结论：kill。
- 验证结论：2026 短窗强信号不具备 2025-2026 稳健性，当前没有 alpha 可以 promote；继续 pivot 到新候选或修复回测性能后扩展搜索。

### Reviewer 与框架修复

- Codex secondary reviewer score: 1/10。
- Reviewer decision: A003/A005 均为 kill，不允许 promote。
- 负结论支持范围：当前 A003/A005 实现不应进入 promote；不代表 A 股动量或流动性方向整体无效。
- 已修复：信号 universe 与次日成交模拟分离；H>1 年化尺度修正；long-short 标记为诊断而非直接可交易；退出跌停不可卖纳入收益有效性。
- 修复后 sanity：`ALPHA_FAST=1 ALPHA_START=20260101 ALPHA_END=20260528 ALPHA_CANDIDATES=A003,A005 ALPHA_HORIZONS=5` 完成。该短窗仍只用于框架验证，不覆盖 reviewer 对 2025-2026 负结果的 kill 结论。

### Post-fix 2025-2026 A003/A005 H5

- 配置：`ALPHA_FAST=1 ALPHA_START=20250101 ALPHA_END=20260528 ALPHA_CANDIDATES=A003,A005 ALPHA_HORIZONS=5`。
- A003 20 日动量：RankIC -0.05250，成本后年化 -0.1271，Sharpe -0.631，MDD -0.822，平均换手 0.215。
- A005 Amihud 流动性：RankIC -0.02835，成本后年化 -0.0786，Sharpe -0.485，MDD -0.673，平均换手 0.069。
- 指标说明：long-short 输出已标记为 `long_short_diagnostic_not_directly_tradable`；H5 年化周期修正为 50.4。
- 结论：修复后正式窗口仍支持 kill；当前 promote 列表为空。
- 解释更新：`kill` 仅针对当前 A003/A005 公式和实现，原因是修复后正式窗口仍为负且 reviewer score 1/10；这不是对 20 日动量或 Amihud/流动性方向的永久否定。后续应继续修复交易/回测协议，并测试行业/市值/流动性中性变体、跳过短期反转的中期动量、成交额异常与冲击成本组合等方向内改进。

## 2026-06-04 — Multi-Agent Quant Research System MVP

- 已实现最小可运行 agent pipeline：Market Intelligence、Research、Factor Design、Data、Backtest、Critic、Evolution、Knowledge Base。
- 入口：`bash run_daily.sh`，内部执行 `python -m agent.daily_pipeline`。
- 输出：`reports/daily_logs/YYYYMMDD/` 下生成事件、研究想法、候选因子、标准数据集、回测结果、失败分析、下一代因子和日报。
- 知识库：`knowledge_base/factor_database/factors.json` 记录因子公式、回测结果、decision 和失败问题；`factor_library/` 存储候选因子定义。
- 验证：Agent 1 单测 `2 passed`；Agent 2-4 单测 `3 passed`；Agent 5-7 单测 `2 passed`；pipeline 单测 `1 passed`。
- 追加验证：新增 `backtest_engine` 包后，MVP 测试集合 `9 passed`；使用临时目录执行 `QUANT_OFFLINE=1 ... bash run_daily.sh` smoke 通过，并生成 `daily_report.md` 与 `knowledge_base/factor_database/factors.json`。
- 长期运行增强：新增 pipeline lock、`pipeline_state.json`、agent error JSON、原子 JSON 写入，以及按 `factor_id/formula/expression` 禁止重复生成已 kill 因子。
- 验证：resilience 后新增测试集合 `11 passed`；临时目录端到端 `QUANT_OFFLINE=1 ... bash run_daily.sh` 输出 `pipeline_state=complete`，记录 8 个组件状态。
- 进一步增强：新增 `QUANT_AGENT_RETRIES` 重试策略、`data_health.json` 数据健康检查、`run_audit.json` 运行审计、`QUANT_RETENTION_DAYS` 日志保留策略。
- 验证：增强后新增测试集合 `13 passed`；端到端 smoke 输出 `complete 8 ok 1`，表示 8 个组件完成、数据健康 ok、agent retry 配置为 1。
- 新增 self-audit 与 schedule helper：`self_audit.json/.md` 给每日运行健康评分，`schedule.json` 与 `cron_example.txt` 生成 crontab 示例但不自动修改系统 crontab。
- 验证：包含 self-audit/schedule 后新增测试集合 `16 passed`；端到端 smoke 输出 `complete 10 pass 1.0 True`，表示 10 个组件状态、self-audit 通过、cron 示例包含 `run_daily.sh`。
- 新增长期运行历史：每日 pipeline 在 self-audit 后追加 `knowledge_base/run_history.jsonl`，并更新 `run_history_latest.json`，记录 agent 状态、审计分、数据健康、候选/回测/promote/kill 数量；失败因子跨日期仍按 `factor_id/formula/expression` 从长期知识库跳过。
- 验证：`python -m py_compile agent/*.py backtest_engine/*.py` 通过；MVP 测试集合 `18 passed`；端到端 `QUANT_OFFLINE=1 ... bash run_daily.sh` smoke 输出 `0 complete 10 pass 1.0 1 20260604 True`，证明入口运行成功、10 个组件完成、self-audit 通过、run history 写入 1 条。
- 新增数据新鲜度健康门槛：`RunConfig.max_data_staleness_days` / `QUANT_MAX_DATA_STALENESS_DAYS` 默认 7 天；`data_health.json` 记录 `freshness.status`、`staleness_days` 和最大允许滞后。真实本地 CSV 过期或未来日期会使 data health 变为 `warning`；synthetic fallback 标为 `not_applicable_synthetic`，用于测试可运行性但不作为生产新鲜数据证据。
- 验证：编译通过；目标测试 `13 passed`；完整 MVP 测试集合 `19 passed`；端到端 smoke 输出 `0 complete 10 pass 1.0 True not_applicable_synthetic 1`，证明入口仍可运行、self-audit 包含 freshness 检查、run history 正常写入。
- 增强 Critic Agent：`backtest_agent` 现在输出 `rankic_by_date`；`critic_agent` 读取候选因子与数据集，输出结构化 `checks.leakage`、`checks.stability`、`checks.collinearity`。显式引用 `forward_`/`next_`/`label`/`target` 等未来字段会被判为潜在 lookahead；RankIC 样本天数、日度正 IC 比例、月度正 IC 比例用于稳定性；因子分数与基础特征的秩相关用于共线性告警。
- 验证：编译通过；Backtest/Critic 目标测试 `3 passed`；完整 MVP 测试集合 `20 passed`；端到端 smoke 输出 `0 complete 10 pass 1.0 ['collinearity', 'leakage', 'stability'] pass`，证明 `run_daily.sh` 仍完整运行且 critique 输出三类审计。
- 增强 Backtest Agent 指标完整性：每个因子结果新增 `long_short`，类型标记为 `long_short_diagnostic_not_directly_tradable`；新增 `cost_sensitivity`，默认输出 5/10/20 bps long-only 成本敏感性；日报 Top Backtest Results 增加 `long_short_ann_diag` 列。
- 验证：编译通过；Backtest/Pipeline 目标测试 `8 passed`；完整 MVP 测试集合 `20 passed`；端到端 smoke 输出 `0 complete 10 pass 1.0 long_short_diagnostic_not_directly_tradable ['10', '20', '5'] True`，证明 `run_daily.sh` 结果包含 long-short 诊断、成本敏感性和日报列。
- 增强 Market Intelligence Agent 源质量审计：在线源扩展为公告、新闻、行业、政策、研报上下文 6 个轻量适配器；`daily_events.json` 新增 `source_quality`，记录 mode、ok/error/skipped source 数、coverage ratio、covered/missing kinds、fallback 是否使用；`self_audit.json`、日报和 `knowledge_base/run_history_latest.json` 均保留该摘要。
- 验证：编译通过；Market/Self-audit/Pipeline 目标测试 `10 passed`；完整 MVP 测试集合 `21 passed`；端到端 smoke 输出 `0 complete 10 pass 1.0 offline 6 offline True`，证明离线降级下仍记录 6 个源的质量状态并写入日报和长期历史。
- 新增连续多日模拟运行：`agent.daily_simulation` 支持 `QUANT_SIM_DAYS=N python -m agent.daily_simulation`，复用真实 `daily_pipeline.run` 连续生成多个 run date，输出 `reports/multi_day_simulation.json`，验证 daily_logs 隔离、run_history 追加、latest 指针更新、失败因子跨日去重。
- 验证：编译通过；Pipeline/Research/Data 目标测试 `12 passed`；完整 MVP 测试集合 `22 passed`；命令行 simulation smoke 输出 `0 pass 3 3 20260606 20260606 [5, 2, 2]`，证明连续 3 天运行成功、history 写入 3 行、latest 指向最后一天、候选因子在首日 kill 后跨日减少。
- 增强 Research Agent 源质量审计：新增 paper、factor_library、community 三类轻量研究源适配器；`research_ideas.json` 新增 `research_context`、`source_status`、`source_quality`，记录 mode、ok/error/skipped source 数、coverage ratio、covered/missing kinds 和 fallback 是否使用；日报、`self_audit.json` 和 `run_history_latest.json` 均保留 research source 摘要。
- 验证：编译通过；Research/Pipeline/Self-audit 目标测试 `16 passed`；完整 MVP 测试集合 `24 passed`；端到端 smoke 输出 `0 complete 10 pass 1.0 offline 3 offline True`，证明离线降级下仍记录 3 个研究源状态并写入日报和长期历史。
- 增强 Factor Design Agent 可追溯与语义去重：候选因子新增 `formula_key`，通过小写化并移除非公式字符规范化公式；新增 `provenance`，记录 source idea、theme、hypothesis、evidence、research source quality 和 run date；`knowledge_base` 保存 `formula_key`，后续按 factor_id/formula/formula_key/expression 跳过已 kill 方案，可挡住空格/大小写等格式变化造成的重复研究。
- 验证：编译通过；Factor/Backtest/Pipeline 目标测试 `18 passed`；完整 MVP 测试集合 `25 passed`；端到端 smoke 输出 `0 complete 5 True True True`，证明候选因子带 formula key 与 provenance，知识库保存 formula key。
- 增强 Evolution Agent 持续改进能力：被 kill 的父因子不再只生成泛泛 pivot，而是根据 `non_positive_rankic`、`non_positive_cost_adjusted_return`、`high_turnover`、`large_drawdown`、稳定性问题等失败原因生成方向翻转、换手过滤、防御流动性/低波动交互等 repair/pivot 变体；promote 父因子生成成本敏感和流动性容量变体。所有 next-generation 因子包含 `formula_key`、`rationale`、父因子指标和 provenance。
- 新增长期失败记忆：`knowledge_base/failure_memory.jsonl` 记录被 kill 因子的公式、formula key、失败 issues、critic checks、父指标和下一步变体；Factor Design Agent 会读取该 JSONL，未来按 factor_id/formula/formula_key/expression 跳过重复失败公式。
- 验证：`python -m py_compile agent/*.py` 通过；Backtest/Critic/Evolution 目标测试 `5 passed`；量化 MVP 子集 `27 passed`；端到端 smoke 输出 `complete 10 True True True`，证明 `run_daily.sh` 完成、生成 10 个 next-generation 变体、failure memory 落盘、变体带 formula key 与 rationale。
- 新增生产就绪度报告：`agent.readiness_report` 聚合 `run_history.jsonl`、latest self-audit、factor database、failure memory 和 agent 状态，输出 `reports/READINESS_REPORT.json` 与 `reports/READINESS_REPORT.md`。报告显式检查 `has_365_successful_runs`，在真实 365 条成功审计运行记录不足时保持 `not_production_ready`，防止把短期 smoke 当作无人值守证明。
- 验证：`python -m py_compile agent/*.py` 通过；Readiness/Pipeline 目标测试 `9 passed`；量化 MVP 子集 `28 passed`；端到端 smoke 输出 `complete not_production_ready False True False`，证明 `run_daily.sh` 仍完整运行，readiness 报告生成，并正确暴露 365 天证明缺口。
- 增强 Knowledge Base 研究日志：`agent.knowledge_base` 在保存因子数据库后追加 `knowledge_base/research_log.jsonl` 并更新 `research_log_latest.json`，记录每日 events/source quality、research ideas/themes、candidate factor ids/formula keys、backtest top RankIC、critic issue counts、next-generation factor ids 和 data health。`agent.readiness_report` 已纳入 `research_log_present` 与 JSONL parse 检查。
- 验证：`python -m py_compile agent/*.py` 通过；Knowledge/Readiness 目标测试 `8 passed`；量化 MVP 子集 `28 passed`；端到端 smoke 输出 `complete 1 3 5 5 True`，证明 `run_daily.sh` 完成、research log 追加 1 条、latest 记录 3 个 idea/5 个候选/5 个 critique，readiness 确认 research log 存在。
- 增强 pipeline lock 长期可靠性：`RunConfig.lock_stale_minutes` / `QUANT_LOCK_STALE_MINUTES` 默认 180 分钟；`reports/.quant_daily.lock` 写入 JSON metadata，fresh lock 继续阻止并发运行，stale lock 自动清理并重新获取，恢复信息写入 `pipeline_state.json` 和 `run_audit.json`。
- 验证：`python -m py_compile agent/*.py` 通过；Pipeline lock 目标测试 `8 passed`；量化 MVP 子集 `30 passed`；端到端 stale-lock smoke 输出 `complete True True False`，证明旧格式 stale lock 可恢复，pipeline 完成，state/audit 记录恢复，结束后 lock 被释放。
- 增强 JSONL 长期日志完整性：`append_jsonl` 追加后 flush/fsync；`readiness_report` 读取 `run_history.jsonl`、`failure_memory.jsonl`、`research_log.jsonl` 时区分有效记录和 malformed lines，坏行写入 `knowledge_base/jsonl_quarantine/*.corrupt.jsonl`。坏行不会污染 latest valid run 计算，但 `no_jsonl_parse_errors` 会失败并阻止 `production_ready`。
- 验证：`python -m py_compile agent/*.py` 通过；Readiness corruption 目标测试 `4 passed`；量化 MVP 子集 `31 passed`；端到端 corrupt-JSONL smoke 输出 `complete True False 1 True`，证明 pipeline 完成、有效 run history 仍可用、parse error 被计数并生成 quarantine。
- 增强 pipeline 运行中 checkpoint：`daily_pipeline.run` 启动后立即写 `pipeline_state.json`，每个 agent 前后更新 `current_agent`、`completed_agents`、`started_at`、`updated_at` 和 lock metadata；未捕获中断会写 `status=interrupted`、当前 agent、已完成 agent 和 traceback，然后释放 lock。
- 验证：`python -m py_compile agent/*.py` 通过；Pipeline checkpoint/self-audit 定向测试 `10 passed`；量化 MVP 子集 `32 passed`；端到端 checkpoint smoke 输出 `complete True True 11 True None`，证明 `run_daily.sh` 完成后 state 保留 started/updated、11 个完成 agent、lock metadata，且 current agent 已清空。
- 增强外部信息源审计缓存：新增 `agent.source_cache`，Market Intelligence 与 Research Agent 每日把 `source_status`、`source_quality` 和最多 50 条事件/研究上下文摘要写入 `reports/daily_logs/YYYYMMDD/source_snapshots/*.json`，并追加 `knowledge_base/source_snapshots.jsonl`、更新 `source_snapshots_latest.json`；`readiness_report` 纳入 `source_snapshots_present` 和 JSONL 完整性检查。
- 验证：`python -m py_compile agent/*.py` 通过；Source/Readiness 目标测试 `16 passed`；量化 MVP 子集 `32 passed`；端到端 source snapshot smoke 输出 `2 market_intelligence research_agent True 2`，证明 Market/Research 两类 snapshot 写入知识库，run_dir 文件存在，readiness 确认 source snapshot 记录。
- 新增资源 preflight：`agent.preflight` 在每日 core agents 前写 `preflight.json`，检查 `output_root`、`knowledge_root`、`factor_library`、`run_dir` 可写性和 `QUANT_MIN_FREE_DISK_MB` 最小空闲磁盘；结果进入 pipeline、日报和 self-audit。磁盘不足会使 self-audit 保持 warning，但不阻止最小流程继续产生日志。
- 验证：`python -m py_compile agent/*.py` 通过；Pipeline/Self-audit 定向测试 `14 passed`；量化 MVP 子集 `33 passed`；端到端 preflight smoke 输出 `ok True True True True`，证明默认门槛下 preflight ok、目录可写、磁盘检查通过、self-audit 纳入 preflight、日报包含 preflight 状态。
- 新增 artifact manifest：`agent.artifact_manifest` 在每日流程最后生成 `reports/daily_logs/YYYYMMDD/artifact_manifest.json` 和 `reports/artifact_manifest_latest.json`，记录 run_dir 文件、`READINESS_REPORT`、factor database/latest knowledge files 的 size、mtime 和 SHA256，用于长期审计输出完整性。
- 验证：`python -m py_compile agent/*.py` 通过；Pipeline manifest 目标测试 `10 passed`；量化 MVP 子集 `33 passed`；端到端 manifest smoke 输出 `True True True True True`，证明 latest manifest 同步，`daily_report.md`、`pipeline_state.json`、`READINESS_REPORT.md` 被记录，且所有 manifest 文件项都有 SHA256。
- 增强 readiness artifact gate：`READINESS_REPORT` 现在要求 `artifact_manifest.json` 存在，且包含 `daily_report.md`、`pipeline_state.json`、`self_audit.json`、`READINESS_REPORT.md` 和 SHA256；manifest 缺失或缺关键文件会阻止 `production_ready`。
- 验证：`python -m py_compile agent/*.py` 通过；Readiness/Manifest 目标测试 `15 passed`；量化 MVP 子集 `34 passed`；端到端 readiness-manifest smoke 输出 `True True True True`，证明最终 `READINESS_REPORT` 能看到 artifact manifest，关键文件和 SHA256 检查均通过。
- 新增 artifact manifest verifier：`agent.artifact_verifier` 读取 `artifact_manifest.json`，重新计算稳定产物 SHA256，输出 `artifact_verification.json` 与 `artifact_verification_latest.json`；`READINESS_REPORT` 新增 `artifact_manifest_verification_passed` 门槛，manifest 文件缺失、缺 hash 或 hash mismatch 会阻止 `production_ready`。
- 验证：`python -m py_compile agent/*.py` 通过；Readiness/Pipeline 定向测试 `16 passed`；量化 MVP 子集 `35 passed`；端到端 verifier smoke 输出 `True pass 44 0 47`，证明 `run_daily.sh` 完成后 readiness 看到 artifact verification pass、校验 44 个文件且 0 个 hash mismatch。
- 增强 production evidence gate：`run_history.jsonl` 现在记录 `data_source_mode`、`data_freshness`、market/research source quality；`READINESS_REPORT` 新增 `latest_data_is_production_evidence`、`latest_market_sources_are_production_evidence`、`latest_research_sources_are_production_evidence` 与 `has_365_production_evidence_runs`。365 条 offline/synthetic smoke 不再可能误判为 `production_ready`。
- 验证：`python -m py_compile agent/*.py` 通过；Self-audit/Readiness 定向测试 `7 passed`；Pipeline 定向测试 `10 passed`；量化 MVP 子集 `36 passed`；端到端 offline smoke 输出 `not_production_ready False False False False synthetic_fallback offline offline`，证明离线合成数据运行仍完整完成但不计入生产证据。
- 增强 365 天唯一日期门槛：`READINESS_REPORT` 新增 `has_365_unique_successful_run_dates` 和 `has_365_unique_production_evidence_dates`，并在 evidence 中记录 unique successful / production-evidence date 数；重复写入同一天 365 次不再能通过生产就绪审计。
- 验证：`python -m py_compile agent/*.py` 通过；Self-audit/Readiness 定向测试 `8 passed`；Pipeline 定向测试 `10 passed`；量化 MVP 子集 `37 passed`；端到端 smoke 输出 `not_production_ready False False 1 0`，证明单日 smoke 只有 1 个唯一 successful date 和 0 个唯一 production evidence date。
- 增强连续 365 天门槛与调度口径：`READINESS_REPORT` 新增 `has_365_consecutive_successful_run_dates` 和 `has_365_consecutive_production_evidence_dates`，并记录最长 successful / production-evidence 日期 streak；`schedule.cron_line` 从工作日 `1-5` 改为每日 `* * *`，对齐“每天运行”的目标。365 个非连续日期不再能通过生产就绪审计。
- 验证：`python -m py_compile agent/*.py` 通过；Schedule/Readiness 定向测试 `10 passed`；Pipeline 定向测试 `10 passed`；量化 MVP 子集 `38 passed`；端到端 smoke 输出 `not_production_ready False False 1 0 ['30', '18', '*', '*', '*']`，证明单日 smoke 只有 1 天 streak，cron 示例为每日运行。

## 2026-06-04 — A股 alpha post-kill continuation

- 结论修正：A003/A005 的 `kill` 只适用于原始 `rank(ret_20)` 和 `-rank(amihud_20)` 当前实现，不应解释为停止动量/流动性方向改进。
- 回测协议修复：`alpha-stage/scripts/alpha_backtest.py` 不再在组合排名前按未来收益 `ret_col` 缺失做 `dropna`，避免“未来能否退出/是否有收益”污染排序池；次日买入可行性和退出可用性只在选后成交仿真阶段影响组合收益。
- 新增方向内变体：A019 `rank(ret_20_skip5)`，A020 `rank(rank(ret_20_skip5)*rank(liq_inv)*rank(low_vol))`，A021 `rank(amihud_20-amihud_5)`。
- 2025-2026 smoke：A020 Test RankIC 0.01015，long-short annual net -0.1343，long-only annual net 0.2268，decision=repair；A019 RankIC -0.03104，long-short annual net 0.0258，long-only annual net 0.4227；A021 RankIC -0.01752，long-short annual net -0.0894，long-only annual net 0.3117。
- 限制：该 smoke 使用 `ALPHA_START=20250101`，train/validation rows 为 0，不能 promote；下一步必须优化 panel 缓存后重跑 2019-2026 非空 train/validation/test。
- 已新增 2019-2026 panel parquet cache 和按需列读取，cache 文件为 `alpha-stage/artifacts/panel_cache/daily_panel_20190101_20260528_v1.parquet`；源 CSV 文件数量、总大小、mtime 变化会使 cache 失效。
- 正式 2019-2026 H5 重跑完成，train/validation/test 均非空。A020：train RankIC 0.03769，validation RankIC 0.03115，test RankIC 0.00821；test long-short 年化 -0.16769，long-only 年化 0.18658，long-only Sharpe 1.314，MDD -0.308，turnover 0.178；decision=repair，不 promote。A019：test RankIC -0.03418，long-short 年化 -0.02331，decision=kill。A021：test RankIC -0.01498，long-short 年化 -0.07502，decision=kill。
- GPU 可用性检查：登录 shell 无 `nvidia-smi`、无 `/dev/nvidia*`，`numba.cuda.is_available()` 为 false，`cupy/cudf/torch` 均未安装；GPU 需要通过 Slurm/sbatch 申请。已提交 `scripts/alpha_gpu_probe.sbatch`，job `29430` 在 A800 节点 `gpu4` 验证 `torch 2.12.0+cu126`、`numba.cuda_available=True`，但 `cudf/cupy` 不存在。
- 新增 PyTorch CUDA 评估后端：`ALPHA_BACKEND=torch_cuda` 时，RankIC 的 rank/corr 和 top-decile 组合均值使用 CUDA tensor 计算；parquet 读取仍由 pandas/pyarrow 完成。新增 `scripts/alpha_gpu_backtest.sbatch` 申请 A800 单卡运行正式回测。
- GPU 正式作业：`sbatch scripts/alpha_gpu_backtest.sbatch` 提交 job `29432`，在 A800 节点 `gpu4` 完成 A019/A020/A021 2019-2026 H5。结果与 CPU 路径基本一致：A020 test RankIC 0.00819，long-short 年化 -0.16765，long-only 年化 0.18662，long-only Sharpe 1.314；A019/A021 RankIC 仍为负。结论不变：A020 repair，A019/A021 kill。

## 2026-06-04 — Knowledge base incomplete-run guard

- 增强 Knowledge Base Agent：`agent.knowledge_base` 现在读取 `pipeline_state.json`，在 research log 中记录 `pipeline.run_quality`、`pipeline_status`、`current_agent` 和 agent errors。
- 安全门槛：完整 pipeline 中如果任一上游 agent 出错导致 `complete_with_errors`，Knowledge Base 仍会写 `research_log.jsonl` 记录失败运行，但跳过 `factor_database/factors.json` 追加，避免把不完整/错误运行的因子当成有效长期记忆。
- 独立 agent 调用：没有 `pipeline_state.json` 时标记为 `run_quality=standalone`，允许单元测试或手动重建知识库继续写入；这不放宽完整 pipeline 的错误运行门槛。
- 验证：`python -m py_compile agent/*.py` 通过；聚焦测试 `2 passed`；量化 MVP 子集 `39 passed`。新增失败路径断言：模拟 `data_agent` 失败时 pipeline 状态为 `complete_with_errors`，research log 标记 `incomplete`，factor database 不追加因子。

## 2026-06-04 — Strict live-source production evidence gate

- 收紧 `READINESS_REPORT` 的 live source production evidence：market/research source quality 必须 `total_sources>0`、`ok_sources==total_sources`、`error_sources==0`、`missing_kinds=[]`、`coverage_ratio>=1.0` 且 `fallback_used=false`。只有部分联网源成功不再能计入 365 天生产证据。
- 新增 regression：365 天运行即使都是 `pipeline_status=complete` 和 `self_audit=pass`，只要 market/research live source 有一个 source error 或 missing kind，`has_365_production_evidence_runs` 仍为 false，latest live-source evidence checks 也为 false。
- 验证：`python -m py_compile agent/*.py` 通过；Readiness/self-audit 定向测试 `10 passed`；量化 MVP 子集 `40 passed`。

## 2026-06-04 — Data Agent domain coverage evidence

- 增强 Data Agent：本地 CSV 构建现在读取 `basic.csv`，把 `industry`、`area`、`market`、`list_date` 合并进 `daily_dataset.parquet`；`metric` 缺失时保留 PB/市值/换手列为 NaN，避免崩溃并交给 health gate 降级。
- `data_health.json` 新增 `domain_coverage`，按 `ohlcv`、`financial_metric`、`industry`、`moneyflow`、`risk_flags`、`derived_features` 记录 required/present/missing columns、null rates 和 `usable`。`checks.required_data_domains_usable` 必须全部通过，生产数据证据才可成立。
- `run_history.jsonl` 现在记录 `data_checks` 和 `data_domain_coverage`；`READINESS_REPORT` 的 `latest_data_is_production_evidence` 除了要求非 synthetic 和 freshness ok，还要求数据域 coverage 可用。
- 验证：`python -m py_compile agent/*.py` 通过；Data/Readiness 定向测试 `21 passed`；量化 MVP 子集 `42 passed`。新增测试覆盖 basic 行业合并、domain coverage 通过，以及 PB 财务域缺失时 health warning。

## 2026-06-04 — Critic-gated alpha promotion

- Backtest Agent 不再直接输出 `decision=promote`；原始回测只输出 `raw_candidate` 或 `kill`，并写入 `decision_note`。进入长期知识库的 promote 语义必须来自 Critic Agent 审查。
- Critic Agent 增强 promote gate：除正 RankIC 和 long-only 成本后收益外，还检查 20bps 高成本档收益、最少回测日期、turnover、drawdown、RankIC 稳定性、未来字段引用、共线性和 long-short 诊断。`raw_candidate` 只有无 issues 才能变成 `promote`。
- Daily report / run history 现在区分 `raw backtest candidates` 和 `promoted after critic`，避免把粗筛结果误报为最终 alpha。
- 验证：`python -m py_compile agent/*.py` 通过；Backtest/Critic/Pipeline 定向测试 `16 passed`；量化 MVP 子集 `43 passed`。新增测试确认 Backtest 不直接 promote，Critic 会因高成本收益为负和 long-short 诊断为负 kill 候选。

## 2026-06-04 — run_daily entrypoint invocation audit

- 新增 `agent.run_entrypoint`，`run_daily.sh` 现在执行 `python -m agent.run_entrypoint`。每次 shell 入口调用都会追加 `reports/run_daily_invocations.jsonl`，并更新 `reports/run_daily_invocation_latest.json`。
- invocation record 包含 run date、pid、host、cwd、argv、output/knowledge root、offline flag、开始/结束时间、耗时、exit code 和 status；如果 entrypoint 层抛异常，会记录 error type/message/traceback 后以非零退出。
- `artifact_manifest` 纳入 `reports/run_daily_invocation_latest.json`，README 输出清单和可靠性说明已更新。
- 验证：`python -m py_compile agent/*.py` 通过；入口/调度/Pipeline/Readiness 定向测试 `23 passed`；量化 MVP 子集 `45 passed`；真实临时目录 `QUANT_OFFLINE=1 ... bash run_daily.sh` smoke 输出 `success 0 complete True`，证明入口 latest 和 JSONL 写入且 pipeline complete。

## 2026-06-04 — run_daily invocation readiness gate

- 增强 `READINESS_REPORT`：新增 `run_daily_invocation_present`、`run_daily_invocation_success`、`run_daily_invocation_matches_run_date` 三个硬门槛，要求 `reports/run_daily_invocation_latest.json` 存在、`status=success`、`exit_code=0` 且 `run_date` 等于当前运行日期。
- 修复入口时序：`run_entrypoint` 在 pipeline 成功后先写 shell invocation record，再刷新 readiness 和 artifact manifest，使最终 `READINESS_REPORT.json` 与 `artifact_manifest.json` 都能看到入口层证据。
- 新增 regression：365 天生产证据齐全但缺失 invocation、invocation exit code 非 0、invocation run_date 不匹配时均保持 `not_production_ready`。
- 验证：`python -m py_compile agent/*.py` 通过；入口/readiness 定向测试 `15 passed`；真实临时目录 `QUANT_OFFLINE=1 ... bash run_daily.sh` smoke 输出 `success 0 20260604 True True True not_production_ready True`，证明最终 readiness 三个 invocation gate 为 true 且 manifest 包含 `run_daily_invocation_latest.json`；量化 MVP 子集 `48 passed`。

## 2026-06-04 — 365-day run_daily invocation evidence gate

- 增强 `READINESS_REPORT`：解析 `reports/run_daily_invocations.jsonl`，新增 `has_365_successful_run_daily_invocations`、`has_365_unique_successful_run_daily_invocation_dates`、`has_365_consecutive_successful_run_daily_invocation_dates` 和 `production_evidence_dates_have_successful_run_daily_invocations`。
- 生产就绪现在要求 365 天生产证据日期都被成功的 shell-level `run_daily.sh` invocation 覆盖；单独伪造或重建 `run_history.jsonl` 不足以通过 `production_ready`。
- `run_daily_invocations.jsonl` 解析错误会进入 `knowledge_base/jsonl_quarantine/run_daily_invocations.jsonl.corrupt.jsonl`，并纳入 `no_jsonl_parse_errors`。
- 验证：`python -m py_compile agent/*.py` 通过；readiness 定向测试 `14 passed`；entrypoint 定向测试 `2 passed`；真实临时目录 smoke 输出 `not_production_ready True True True False False 1`，证明最新 invocation 可见但单日运行不满足 365 invocation gate；量化 MVP 子集 `49 passed`。

## 2026-06-04 — 365-day source snapshot evidence gate

- 增强 `READINESS_REPORT`：解析 `knowledge_base/source_snapshots.jsonl`，按 run_date 聚合 `market_intelligence` 和 `research_agent` 两类 source snapshot，且每条 snapshot 自身的 `source_quality` 必须满足 production evidence。
- 新增门槛：`has_365_source_snapshot_dates`、`has_365_consecutive_source_snapshot_dates`、`production_evidence_dates_have_source_snapshots`。生产就绪现在要求 365 天 production-evidence 日期都有可回放的 market/research 逐源快照，不能只靠 run_history 中的 source_quality 摘要。
- 新增 regression：365 条完整 production run history 和 365 条 successful invocation，但缺少 365 天 production-grade source snapshots 时保持 `not_production_ready`。
- 验证：`python -m py_compile agent/*.py` 通过；readiness 定向测试 `15 passed`；真实临时目录 smoke 输出 `not_production_ready True False False True 2`，证明单日 smoke 写入 2 条 snapshot 但不满足 365 snapshot gate；量化 MVP 子集 `50 passed`。

## 2026-06-04 — 365-day data artifact evidence gate

- 增强 Data Agent：每次运行除 `data_health.json` 和 `dataset_manifest.json` 外，还追加 `knowledge_base/data_health.jsonl` 并更新 `knowledge_base/data_health_latest.json`，记录 dataset manifest、source mode、freshness、domain coverage 和 data checks。
- 增强 `READINESS_REPORT`：解析 `data_health.jsonl`，新增 `data_health_log_present`、`has_365_data_artifact_dates`、`has_365_consecutive_data_artifact_dates`、`production_evidence_dates_have_data_artifacts`。生产就绪现在要求 365 天 production-evidence 日期都有 production-grade real-data artifact 记录，不能只靠 run_history 中的数据摘要。
- `artifact_manifest` 现在纳入 `data_health_latest.json`，使最新数据证据进入 artifact hash 记录。
- 新增 regression：365 条完整 production run history、365 条 successful invocation、365 天 source snapshots，但缺少 data artifacts 时保持 `not_production_ready`。
- 验证：`python -m py_compile agent/*.py` 通过；readiness/data 定向测试 `27 passed`；真实临时目录 smoke 输出 `not_production_ready True True True False False 1`，证明单日运行写入 data health JSONL/latest 且不满足 365 data artifact gate；量化 MVP 子集 `51 passed`。

## 2026-06-05 — 365-day knowledge-save evidence gate

- 增强 `READINESS_REPORT`：解析 `knowledge_base/research_log.jsonl` 中 `pipeline.run_quality == complete` 且 `factor_database_write.status == updated` 的日期，新增 `has_365_knowledge_save_dates`、`has_365_consecutive_knowledge_save_dates` 和 `production_evidence_dates_have_knowledge_saves`。
- 生产就绪现在要求 365 天 production-evidence 日期都有完整 knowledge-base save 证据；不能只靠 `run_history.jsonl` 声称 pipeline 完成，也不能用 skipped/incomplete research log 代替因子库保存。
- 新增 regression：365 条完整 production run history、365 条 successful invocation、365 天 production source snapshots、365 天 production data artifacts 都齐全，但 research log 没有 365 天完整 factor database update 时仍保持 `not_production_ready`。
- 验证：`python -m py_compile agent/*.py` 通过；`pytest -q tests/test_quant_self_audit.py` 为 `17 passed`；快速入口 smoke `QUANT_OFFLINE=1 QUANT_DATA_ROOT=<missing> ... bash run_daily.sh` 输出 `SMOKE 0 not_production_ready True False False True 1 True True`，证明单日 knowledge save 写入但 365 数量/连续门槛不满足；量化 MVP 子集 `52 passed`。

## 2026-06-05 — Current run-history date readiness gate

- 增强 `READINESS_REPORT`：新增 `latest_run_history_matches_run_date`，要求最新 `knowledge_base/run_history.jsonl` 记录的 `run_date` 等于当前配置 run date。
- 生产就绪现在不能用“当前成功 shell invocation + 旧的 365 天 run_history”拼接通过；今天的 `bash run_daily.sh` 必须同时产生今天的完整 pipeline/run history 记录。
- 新增 regression：365 天历史 production evidence 到前一天为止、当前 invocation 成功且日期匹配时，仍因 latest run_history stale 保持 `not_production_ready`。
- 验证：`python -m py_compile agent/*.py` 通过；`pytest -q tests/test_quant_self_audit.py` 为 `18 passed`；快速入口 smoke 输出 `SMOKE 0 not_production_ready True 20260605 20260605`，证明真实 `run_daily.sh` 会写入当前日期 run_history；量化 MVP 子集 `53 passed`。

## 2026-06-05 — Artifact manifest run-date readiness gate

- 增强 `READINESS_REPORT`：新增 `artifact_manifest_matches_run_date`，要求当前 run_dir 下的 `artifact_manifest.json.run_date` 等于当前配置 run date。
- 生产就绪现在不能复制旧 artifact manifest 到当前目录并依赖 hash 校验通过；manifest 自身必须证明它是本次运行生成的产物清单。
- 新增 regression：manifest 文件、required paths 和 SHA256 都存在且 artifact verification 可运行，但 manifest `run_date` 过期时保持 `not_production_ready`。
- 验证：`python -m py_compile agent/*.py` 通过；`pytest -q tests/test_quant_self_audit.py` 为 `19 passed`；快速入口 smoke 输出 `SMOKE 0 not_production_ready True True 20260605 20260605`；量化 MVP 子集 `54 passed`。

## 2026-06-05 — Alpha GPU sbatch launcher

- 结论：GPU alpha 回测应通过 `bash scripts/submit_alpha_gpu_backtest.sh` 提交 Slurm 作业；launcher 用 shell 环境变量传递 `ALPHA_CANDIDATES` 和 `ALPHA_HORIZONS`，避免 `sbatch --export=ALL,ALPHA_HORIZONS=1,5,...` 被逗号拆分。
- 默认参数面向 A022/A024/A025 repair 队列：`ALPHA_HORIZONS=1,5,10,20`、`ALPHA_FAST=0`、`ALPHA_BACKEND=torch_cuda`、`ALPHA_START=20190101`、`ALPHA_END=20260528`。
- 验证：`bash -n scripts/submit_alpha_gpu_backtest.sh scripts/alpha_gpu_backtest.sbatch scripts/alpha_gpu_probe.sbatch` 通过；`python -m py_compile agent/*.py alpha-stage/scripts/alpha_backtest.py` 通过；`pytest -q tests/test_quant_self_audit.py` 为 `19 passed`；`pytest -q tests/test_quant_entrypoint.py` 为 `5 passed`；量化 MVP 子集为 `57 passed`。
- 入口 smoke：`QUANT_OFFLINE=1 QUANT_RUN_DATE=20260605 ... bash run_daily.sh` 输出 `SMOKE not_production_ready None True True 20260605 20260605 20260605`，证明 `QUANT_RUN_DATE` alias 写入 run_history 和 artifact manifest；单日 smoke 不满足 365 天 readiness 属于预期。
- Slurm 提交：`ALPHA_CANDIDATES=A022,A024,A025 ALPHA_HORIZONS=1,5,10,20 ALPHA_FAST=0 bash scripts/submit_alpha_gpu_backtest.sh` 提交 job `29516`，状态检查显示 A800 分区 `gpu4` 运行。
- Slurm 完成：job `29516` 在 `gpu4` 完成，`reports/slurm/alpha_gpu_backtest-29516.err` 为空；日志确认 `torch.cuda_available=True`、device `NVIDIA A800-SXM4-80GB`。结果与 29491 对 A022/A024/A025 一致：RankIC 和 long-only 为正，但 long-short 诊断全负，仍为 repair，不 promote。

## 2026-06-05 — Daily schedule evidence readiness gate

- 增强 `schedule.json`：新增机器可读字段 `cadence=daily`、cron 五段字段、`command` 和 `script_path`，不再只依赖人读的 `cron_line`。
- 增强 `READINESS_REPORT`：新增 `latest_schedule_is_daily_run_daily`，要求当前 schedule 证明每日 cadence，`day_of_month/month/day_of_week` 均为 `*`，且命令包含 `bash` 和 `run_daily.sh`。
- 新增 regression：365 天其它生产证据齐全但当前 `schedule.json` 改成 weekday cadence / `day_of_week=1-5` 时，readiness 保持 `not_production_ready`。
- 真实入口 smoke：`QUANT_OFFLINE=1 QUANT_RUN_DATE=20260605 ... bash run_daily.sh` 退出 0；`READINESS_REPORT.checks.latest_schedule_is_daily_run_daily=True`，`schedule_evidence.daily_run_daily=True`，`cadence=daily`，`day_of_week=*`。
- 验证：`python -m py_compile agent/*.py` 通过；`pytest -q tests/test_quant_schedule.py tests/test_quant_self_audit.py` 为 `23 passed`；`pytest -q tests/test_quant_schedule.py tests/test_quant_self_audit.py tests/test_quant_daily_pipeline.py tests/test_quant_entrypoint.py` 为 `40 passed`；量化 MVP 子集为 `65 passed`。

## 2026-06-05 — Evolution Agent now skips failed-memory duplicate variants

- 增强 `evolution_agent`：生成 next-generation repair/pivot 子因子后，会读取 `factor_database` killed records 和 `failure_memory.jsonl` 的 failed keys；若 child 的 `factor_id`、`formula`、`formula_key` 或 `expression` 命中失败记忆，则跳过并写入 `skipped_evolution_factors`。
- `next_generation_factors.json` 新增 `skipped_evolution_factors` 和 `failed_memory_audit`，长期运行时可以解释 next-gen 数量减少的原因。
- `research_log_latest.json.evolution` 新增 `skipped_failed_count` 和 `skipped_factor_ids`。
- 新增 regression：当 `failure_memory.jsonl` 已记录某个 turnover-filtered repair 的 `formula_key` 时，`evolution_agent` 不再写出对应 child JSON，也不会把它列入 `next_generation_factors`。
- 入口 smoke：`QUANT_OFFLINE=1 QUANT_RUN_DATE=20260605 ... bash run_daily.sh` 退出 0；`next_generation_factors.json` 包含 skip 字段，research log 包含 `evolution.skipped_failed_count`。
- 验证：`python -m py_compile agent/*.py` 通过；`pytest -q tests/test_quant_agents_backtest_critic.py` 为 `8 passed`；`pytest -q tests/test_quant_agents_research_data.py tests/test_quant_agents_backtest_critic.py` 为 `20 passed`；量化 MVP 子集为 `64 passed`。

## 2026-06-05 — Artifact manifest now requires full daily agent output chain

- 增强 `READINESS_REPORT`：artifact manifest required paths 现在覆盖完整每日产物链，包括 `preflight.json`、`daily_events.json`、`research_ideas.json`、`candidate_factors.json`、`daily_dataset.parquet`、`dataset_manifest.json`、`data_health.json`、`backtest_results.json`、`failure_analysis.md`、`critique.json`、`next_generation_factors.json`、`run_audit.json`、`schedule.json`、`self_audit.*`、`READINESS_REPORT.*` 和 `run_daily_invocation_latest.json`。
- 生产意义：不能只靠 `daily_report.md` / `pipeline_state.json` / readiness 文件通过 artifact gate；每天必须有可哈希、可回放的 agent 输出链。
- 测试增强：daily pipeline 测试显式断言 manifest 包含核心 agent 输出；readiness regression 明确检查缺少 `candidate_factors.json` / `backtest_results.json` 会阻止 production-ready。
- shell smoke：`QUANT_OFFLINE=1 QUANT_RUN_DATE=20260605 ... bash run_daily.sh` 退出 0；manifest 包含 daily events、research ideas、candidate factors、dataset、backtest、failure analysis、next generation 和 `run_daily_invocation_latest.json`，`artifact_manifest_required_files_present=True`。
- 验证：`python -m py_compile agent/*.py` 通过；`pytest -q tests/test_quant_self_audit.py tests/test_quant_daily_pipeline.py tests/test_quant_entrypoint.py` 为 `38 passed`；量化 MVP 子集为 `63 passed`。

## 2026-06-05 — Active research/backtest readiness gate

- 增强 `READINESS_REPORT`：production evidence 现在要求每条 run history 同时有 `counts.ideas > 0`、`counts.candidate_factors > 0`、`counts.backtest_results > 0`，不能用 365 天“完整但空跑”的记录通过生产就绪。
- 新增 checks：`latest_run_has_research_activity`、`has_365_research_activity_runs`、`has_365_unique_research_activity_dates`、`has_365_consecutive_research_activity_dates`、`production_evidence_dates_have_research_activity`。
- 新增 regression：365 天 live source、fresh data、successful shell invocation、source snapshots、knowledge saves 都齐，但 `candidate_factors=0` / `backtest_results=0` 时保持 `not_production_ready`。
- 真实入口 smoke：`QUANT_OFFLINE=1 QUANT_RUN_DATE=20260605 ... bash run_daily.sh` 退出 0；最新 run history counts 为 `ideas=3`、`candidate_factors=5`、`backtest_results=5`，`latest_run_has_research_activity=True`，单日仍不满足 365 gate。
- 验证：`python -m py_compile agent/*.py` 通过；`pytest -q tests/test_quant_self_audit.py` 为 `21 passed`；量化 MVP 子集 `pytest -q tests/test_alpha_backtest_cache.py tests/test_quant_*.py tests/test_backtest_engine_package.py` 为 `63 passed`。

## 2026-06-05 — A027-A030 GPU repair batch submitted

- 新增 A027-A030 repair/pivot 因子，针对 A022/A024/A025 “RankIC 与 long-only 为正但 long-short 诊断全负”的问题，转向容量约束、低换手、短回撤过滤和资金确认的 long-only 可交易候选。
- `PANEL_CACHE_VERSION` 从 2 升到 3，避免旧 panel cache 缺少新增 score 字段。
- 验证：`python -m py_compile alpha-stage/scripts/alpha_backtest.py agent/*.py` 通过；`bash -n scripts/submit_alpha_gpu_backtest.sh scripts/alpha_gpu_backtest.sbatch scripts/alpha_gpu_probe.sbatch` 通过；`pytest -q tests/test_alpha_backtest_cache.py` 为 `1 passed`。
- Slurm：用 `ALPHA_CANDIDATES=A027,A028,A029,A030 ALPHA_HORIZONS=1,5,10,20 ALPHA_FAST=0 ALPHA_BACKEND=torch_cuda bash scripts/submit_alpha_gpu_backtest.sh` 提交 job `29532`；`squeue` 显示 A800 分区 `gpu2` 运行，stderr 初始为空。
- GPU 结果：job `29532` 完成，CUDA 可用。A029 H5 最强：Test RankIC=0.044898，10bps long-short annual net=0.022270，long-only annual net=0.174633，Sharpe=1.206；但 Codex reviewer score 仅 5/10，decision=repair，不能 promote。
- 成本敏感性：新增 `ALPHA_COSTS` 参数并提交 A029 H5 job `29537`。5/10/20/30bps long-short annual net 为 0.036556 / 0.022270 / -0.006300 / -0.034871；long-only annual net 为 0.181849 / 0.174633 / 0.160203 / 0.145772。结论仍是 repair。
- 验证：量化 MVP 子集 `pytest -q tests/test_alpha_backtest_cache.py tests/test_quant_*.py tests/test_backtest_engine_package.py` 为 `62 passed`。

## 2026-06-05 — A029 GPU sbatch rerun evidence

- 修正 GPU 提交入口：`scripts/submit_alpha_gpu_backtest.sh` 和 `scripts/alpha_gpu_backtest.sbatch` 默认改为 A029 H5 多成本 repair 验证，并在提交/作业日志中显式打印 `ALPHA_COSTS`。
- Slurm：`ALPHA_CANDIDATES=A029 ALPHA_HORIZONS=5 ALPHA_COSTS=5,10,20,30 ALPHA_FAST=0 ALPHA_BACKEND=torch_cuda bash scripts/submit_alpha_gpu_backtest.sh` 提交 job `29557`，在 A800 `gpu2` 完成；stdout 记录 `torch.cuda_available=True`、device `NVIDIA A800-SXM4-80GB`，stderr 为空。
- 结果：A029 H5 Test RankIC 0.044898；5/10/20/30bps long-short annual net 为 0.036556 / 0.022270 / -0.006300 / -0.034871；long-only annual net 为 0.181849 / 0.174633 / 0.160203 / 0.145772；long-only Sharpe 为 1.256 / 1.206 / 1.106 / 1.007；test size_corr 约 0.43。
- 结论：GPU 已通过 sbatch 正确使用，但 A029 仍是 repair，不 promote。阻塞项仍是 delayed-exit / true H5 ledger / size-industry neutral diagnostics，而不是计算资源。
- 验证：`bash -n scripts/submit_alpha_gpu_backtest.sh scripts/alpha_gpu_backtest.sbatch scripts/alpha_gpu_probe.sbatch` 通过；`python -m py_compile alpha-stage/scripts/alpha_backtest.py` 通过。

## 2026-06-05 — Run audit production evidence gate

- 增强 `READINESS_REPORT`：新增 `latest_run_audit_is_current_evidence` gate，要求 `run_audit.json` 的 `run_date`、config、lock、state、retention 与当前 `RunConfig` 和当天运行一致，不能只靠空文件或陈旧 audit 通过生产证据。
- `run_audit_evidence` 输出现在记录 present、run_date、config、lock、state_status 和 retention，便于审计每日 lock/retry/retention 证据。
- 新增 regression：构造 365 天生产证据齐全但最新 `run_audit.json` 的 run_date/config 陈旧时，`READINESS_REPORT` 保持 `not_production_ready` 并给出 run_audit blocker。
- README Long-Run Reliability 已同步说明 `run_audit.json` 不只是存在性文件，而是 current config/run date/lock/retention 证据。
- 验证：`python -m py_compile agent/*.py` 通过；`pytest -q tests/test_quant_self_audit.py` 为 `23 passed`；`pytest -q tests/test_quant_schedule.py tests/test_quant_self_audit.py tests/test_quant_daily_pipeline.py tests/test_quant_entrypoint.py` 为 `41 passed`；量化 MVP 子集为 `66 passed`；离线 `bash run_daily.sh` smoke 输出 `SMOKE not_production_ready True True True 20260605 complete 370`。

## 2026-06-05 — Same-day failure memory readiness gate

- 增强 `READINESS_REPORT`：新增 `latest_killed_factors_have_failure_memory` gate，要求最新 `critique.json` 中 `decision=kill` 的因子必须在同一 `run_date` 的 `failure_memory.jsonl` 中出现。
- `knowledge_base` readiness 输出新增 `latest_killed_factor_ids` 和 `same_day_failure_memory_factor_ids`，可审计当天 critic kill 是否真正变成可复用失败经验。
- 新增 regression：构造 365 天生产证据齐全但 latest critique kill 的 `F1` 只存在前一天 failure memory，系统保持 `not_production_ready`。
- 生产意义：不能只靠 `failure_memory.jsonl` 存在通过；当天失败因子若未保存，长期无人值守会更容易重复研究刚失败的方案。
- 验证：`python -m py_compile agent/*.py` 通过；`pytest -q tests/test_quant_self_audit.py` 为 `24 passed`；`pytest -q tests/test_quant_schedule.py tests/test_quant_self_audit.py tests/test_quant_daily_pipeline.py tests/test_quant_entrypoint.py` 为 `42 passed`；量化 MVP 子集为 `67 passed`；离线 `bash run_daily.sh` smoke 输出当天 killed ids 与 same-day failure memory ids 对齐。

## 2026-06-05 — Latest knowledge pointer alignment gate

- 增强 `READINESS_REPORT`：新增 `latest_knowledge_pointers_match_run_date` gate，要求 `run_history_latest.json`、`research_log_latest.json`、`source_snapshots_latest.json`、`data_health_latest.json` 均指向当前 `run_date`。
- `knowledge_base.latest_pointer_alignment` 和 `knowledge_base.latest_pointers` 现在输出每个 latest 指针的 present/run_date/agent，便于排查 JSONL 与 latest 文件不一致。
- 新增 regression：构造 365 天生产证据齐全但 `run_history_latest.json` 指向 `20260603`，当前 run date 为 `20260604` 时，系统保持 `not_production_ready`。
- 生产意义：不能只靠 JSONL 中有 365 天记录通过；日报、readiness、manifest 和用户常看的 latest 指针必须和当前运行一致。
- 验证：`python -m py_compile agent/*.py` 通过；`pytest -q tests/test_quant_self_audit.py` 为 `25 passed`；`pytest -q tests/test_quant_schedule.py tests/test_quant_self_audit.py tests/test_quant_daily_pipeline.py tests/test_quant_entrypoint.py` 为 `43 passed`；量化 MVP 子集为 `68 passed`；离线 `bash run_daily.sh` smoke 输出四个 latest 指针全部匹配 `20260605`。

## 2026-06-05 — Failure memory detail consistency readiness gate

- 增强 `READINESS_REPORT`：新增 `latest_killed_factor_failure_memory_details_match` gate，在原有同日 factor_id 存在检查之外，要求 killed factor 的 failure memory 记录与最新 `critique.json`/`backtest_results.json` 对齐。
- 详情检查要求：同日 failure memory 的 `formula_key` 匹配 backtest result，`issues` 匹配 critic issues，`checks` 非空，`parent_metrics.rankic_mean` 与 `parent_metrics.ann_return_net` 匹配 backtest 指标。
- `knowledge_base.failure_memory_detail_match` 现在输出该详情匹配状态，生产就绪不能只靠 failure memory 有 id。
- 新增 regression：365 天生产证据齐全且同日 failure memory 有 `factor_id/formula_key`，但缺 issues/checks/parent_metrics 时，系统保持 `not_production_ready`。
- README Long-Run Reliability 已同步说明 failure memory 必须是可复用 debug evidence，而不是只有 id list。
- 验证：`python -m py_compile agent/*.py` 通过；`pytest -q tests/test_quant_self_audit.py` 为 `31 passed`；`pytest -q tests/test_quant_schedule.py tests/test_quant_self_audit.py tests/test_quant_daily_pipeline.py tests/test_quant_entrypoint.py` 为 `49 passed`；量化 MVP 子集为 `74 passed`；离线 `bash run_daily.sh` smoke 输出 `latest_killed_factors_have_failure_memory=True`、`latest_killed_factor_failure_memory_details_match=True`，killed ids 与同日 memory ids 均为 `F_MF_EXHAUST_5,F_VOL_REV_5,F_VWAP_REV_5`。

## 2026-06-05 — Factor database backtest consistency readiness gate

- 增强 `READINESS_REPORT`：新增 `latest_factor_database_matches_backtests` gate，要求最新 `backtest_results.json` 中每个结果都在 `knowledge_base/factor_database/factors.json` 有同 `run_date` 记录，并且 `formula_key`、`rankic_mean` 与 backtest 一致，`decision` 与 critic 结论一致。
- `factor_database_evidence` 现在输出 latest_backtest_result_count、same_day_factor_records、matches_latest_backtests、latest_backtest_factor_ids，生产就绪不能只靠 factor database 非空。
- 新增 regression：365 天生产证据齐全但 factor database 中 F1 记录指向前一天时，系统保持 `not_production_ready`。
- README Long-Run Reliability 已同步说明 factor database 必须保存当天 backtest/critic 结论。
- 验证：`python -m py_compile agent/*.py` 通过；`pytest -q tests/test_quant_self_audit.py` 为 `30 passed`；`pytest -q tests/test_quant_schedule.py tests/test_quant_self_audit.py tests/test_quant_daily_pipeline.py tests/test_quant_entrypoint.py` 为 `48 passed`；量化 MVP 子集为 `73 passed`；离线 `bash run_daily.sh` smoke 输出 `latest_factor_database_matches_backtests=True`、`latest_backtest_result_count=5`、`same_day_factor_records=5`。

## 2026-06-05 — Factor library candidate consistency readiness gate

- 增强 `READINESS_REPORT`：新增 `latest_factor_library_matches_candidates` gate，要求最新 `candidate_factors.json` 中每个候选因子都在 `factor_library/<factor_id>.json` 有对应文件，并且 `factor_id`、`created_at_run`、`formula_key`、`expression` 与当天候选一致。
- `factor_library_evidence` 现在输出 candidate_count、factor_library_root、matches_current_candidates、candidate_factor_ids，生产就绪不能只靠 `candidate_factors.json` 存在。
- 新增 regression：365 天生产证据齐全但 `factor_library/F1.json.created_at_run` 指向前一天时，系统保持 `not_production_ready`。
- README Long-Run Reliability 已同步说明 candidate factor 必须写入当前 run 的 `factor_library/` 文件。
- 验证：`python -m py_compile agent/*.py` 通过；`pytest -q tests/test_quant_self_audit.py` 为 `29 passed`；`pytest -q tests/test_quant_schedule.py tests/test_quant_self_audit.py tests/test_quant_daily_pipeline.py tests/test_quant_entrypoint.py` 为 `47 passed`；量化 MVP 子集为 `72 passed`；离线 `bash run_daily.sh` smoke 输出 `latest_factor_library_matches_candidates=True`、`candidate_count=5`、候选 ids 为 `F_VOL_REV_5,F_VWAP_REV_5,F_MF_EXHAUST_5,F_MF_CONFIRM_5,F_VALUE_LIQ_DEF_5`。

## 2026-06-05 — Daily report current evidence readiness gate

- 增强 `READINESS_REPORT`：新增 `latest_daily_report_is_current_evidence` gate，要求 `daily_report.md` 存在、非空，包含当前 `Run date`、日报标题、Agent Status/Summary/Top Backtest Results/Files 核心章节、核心 research/backtest 计数字段、关键输出文件引用，以及除 `artifact_manifest` 外的 required agent 状态行。
- `daily_report_evidence` 现在输出 present/path/current_complete_evidence、required_agents、required_snippets，生产就绪不能只靠 manifest 中有 `daily_report.md` 文件。
- 新增 regression：365 天生产证据齐全但 `daily_report.md` 写成前一天 run date 且缺少完整章节/agent 证据时，系统保持 `not_production_ready`。
- README Long-Run Reliability 已同步说明 stale 或 placeholder daily report 会阻塞 production-ready。
- 验证：`python -m py_compile agent/*.py` 通过；`pytest -q tests/test_quant_self_audit.py` 为 `28 passed`；`pytest -q tests/test_quant_schedule.py tests/test_quant_self_audit.py tests/test_quant_daily_pipeline.py tests/test_quant_entrypoint.py` 为 `46 passed`；量化 MVP 子集为 `71 passed`；离线 `bash run_daily.sh` smoke 输出 `latest_daily_report_is_current_evidence=True`、`daily_report_current_complete_evidence=True`、`required_agents=12`、`required_snippets=14`。

## 2026-06-05 — Current self-audit production evidence gate

- 增强 `READINESS_REPORT`：新增 `latest_self_audit_is_current_evidence` gate，要求最新 `self_audit.json` 的 `run_date` 等于当前运行日期、`status=pass`、`score>=0.9`，并且包含全部关键自审 checks 且结果为 true。
- `latest_self_audit` 输出现在包含 `run_date`、`current_complete_evidence`、`required_checks`、`missing_required_checks`，用于审计自审文件是否真来自当天完整 pipeline，而不是陈旧或空壳 pass 文件。
- 新增 regression：365 天生产证据齐全、run history 为 pass，但把 `self_audit.json.run_date` 改成前一天时，系统保持 `not_production_ready`。
- README Long-Run Reliability 已同步说明 production readiness 对 self-audit 的当前日期、分数和完整 checks 要求。
- 验证：`python -m py_compile agent/*.py` 通过；`pytest -q tests/test_quant_self_audit.py` 为 `27 passed`；`pytest -q tests/test_quant_schedule.py tests/test_quant_self_audit.py tests/test_quant_daily_pipeline.py tests/test_quant_entrypoint.py` 为 `45 passed`；量化 MVP 子集为 `70 passed`；离线 `bash run_daily.sh` smoke 输出 `latest_self_audit_is_current_evidence=True`、`self_audit_current_complete_evidence=True`、`self_audit_run_date=20260605`、`missing_required_checks=0`。

## 2026-06-05 — Cron example schedule consistency readiness gate

- 增强 `READINESS_REPORT`：新增 `latest_cron_example_matches_schedule` gate，要求 `reports/daily_logs/YYYYMMDD/cron_example.txt` 存在、非空，并包含 `schedule.json.cron_line` 里的同一条 `bash run_daily.sh` cron 命令。
- `schedule_evidence` 现在输出 `cron_example_present`、`cron_example_path`、`cron_example_matches_schedule`，生产就绪不能只靠机器可读 `schedule.json`，还必须证明实际安装提示没有陈旧或错频率。
- 新增 regression：365 天生产证据齐全、`schedule.json` 为 daily，但 `cron_example.txt` 被改成旧 weekday cron line 时，系统保持 `not_production_ready`。
- README Long-Run Reliability 已同步说明 readiness 要求 `cron_example.txt` 与 `schedule.json` 的 cron line 一致。
- 验证：`python -m py_compile agent/*.py` 通过；`pytest -q tests/test_quant_schedule.py tests/test_quant_self_audit.py tests/test_quant_daily_pipeline.py` 为 `37 passed`；`pytest -q tests/test_quant_schedule.py tests/test_quant_self_audit.py tests/test_quant_daily_pipeline.py tests/test_quant_entrypoint.py` 为 `44 passed`；量化 MVP 子集为 `69 passed`；离线 `bash run_daily.sh` smoke 输出 `latest_cron_example_matches_schedule=True`、`cron_example_matches_schedule=True`、`cron_example_present=True`、`daily_run_daily=True`。

## 2026-06-05 — Cron example required artifact evidence

- 增强 self-audit/manifest：`cron_example.txt` 现在加入 `REQUIRED_RUN_FILES`，因此也进入 `READINESS_REPORT.REQUIRED_MANIFEST_PATHS`，每日调度示例不再只是可选文本文件。
- Daily report 文件清单同步加入 `cron_example.txt`，README Long-Run Reliability 说明 `schedule.json` 和 `cron_example.txt` 都是 required evidence。
- 生产意义：`schedule.json` 证明机器可读 daily cadence，`cron_example.txt` 提供人工安装 crontab 的可审计命令；两者都必须非空且被 artifact manifest 哈希。
- 验证：`python -m py_compile agent/*.py` 通过；`pytest -q tests/test_quant_schedule.py tests/test_quant_self_audit.py tests/test_quant_daily_pipeline.py` 为 `36 passed`；`pytest -q tests/test_quant_schedule.py tests/test_quant_self_audit.py tests/test_quant_daily_pipeline.py tests/test_quant_entrypoint.py` 为 `43 passed`；量化 MVP 子集为 `68 passed`；离线 `bash run_daily.sh` smoke 输出 `cron_example.txt` self-audit file check、manifest path 和 required manifest gate 均为 true。

## 2026-06-05 — Replayable source snapshot readiness gate

- 增强 `READINESS_REPORT`：365 天 production-grade source snapshot 现在不仅要求 `source_quality` 为 live/full coverage，还要求 snapshot 本身有 `item_count > 0`，且 `source_status` 非空、每个 source 为 `ok` 并记录正的 `items` 数。
- 生产就绪现在不能只靠 source quality 摘要声称 live source 覆盖；必须有可回放的市场/研究源快照内容支撑。
- 新增 regression：365 天 run history、shell invocation、data artifact、knowledge save 都齐全，且 source_quality 看似全绿，但 source snapshots 的 `item_count=0`/`items=[]` 时仍保持 `not_production_ready`。
- 验证：`python -m py_compile agent/*.py` 通过；`pytest -q tests/test_quant_self_audit.py` 为 `20 passed`；`pytest -q tests/test_quant_agents_market.py tests/test_quant_agents_research_data.py` 为 `14 passed`；离线 `run_daily.sh` smoke 输出 `SMOKE not_production_ready True False 1 0`，证明离线 snapshot 会生成但不会误计为 365 天 production source evidence；量化 MVP 子集 `58 passed`。

## 2026-06-05 — Final run-history agent-status alignment

- 修复 daily pipeline 证据链：`run_history.jsonl` 原先在 `readiness_report` 和 `artifact_manifest` 运行前写入，导致长期历史中的 `agent_status` 缺少这两个生产证据代理。
- 现在 pipeline 先写临时 run history 供 readiness 初次读取，最终 `readiness_report` 和 `artifact_manifest` 完成后，用当前日期的最终记录替换 JSONL 中该 run_date 的最后一条记录，并同步 `run_history_latest.json`；保持单日一条有效 run history，不追加重复日期。
- `READINESS_REPORT.REQUIRED_AGENT_NAMES` 现在包含 `readiness_report` 和 `artifact_manifest`，365 天生产证据必须覆盖完整闭环。
- 验证：`python -m py_compile agent/*.py` 通过；`pytest -q tests/test_quant_daily_pipeline.py tests/test_quant_self_audit.py` 为 `30 passed`；临时目录 `run_daily.sh` smoke 输出 `SMOKE 1 20260605 ok ok True not_production_ready`，证明 run_history JSONL 只有 1 行且 latest 记录包含 `readiness_report=ok`、`artifact_manifest=ok`；量化 MVP 子集 `58 passed`。

## 2026-06-05 — Strict run-date config validation

- 增强 `load_config`：`QUANT_DATE` / `QUANT_RUN_DATE` 现在必须是 8 位数字且能解析为真实日历日期的 `YYYYMMDD`；`QUANT_DATE` 仍优先于 alias。
- 增强 `run_entrypoint`：即使配置解析阶段失败，也会用环境变量中的 output/knowledge root 写入 `reports/run_daily_invocation_latest.json` 和 JSONL error record，避免坏日期导致无入口审计。
- 生产意义： malformed run date 不再能创建错误 daily_logs 目录或污染 run_history；失败会在 shell invocation 层留下可审计证据。
- 验证：`python -m py_compile agent/*.py` 通过；`pytest -q tests/test_quant_entrypoint.py tests/test_quant_schedule.py tests/test_quant_daily_pipeline.py` 为 `18 passed`；正常 `QUANT_RUN_DATE=20260605 bash run_daily.sh` smoke 输出 `SMOKE success 20260605 20260605 True True`；非法 `QUANT_DATE=20260631 bash run_daily.sh` smoke 输出 `BADDATE 1 error 1 20260631 False ValueError`；量化 MVP 子集 `60 passed`。

## 2026-06-05 — Factor skip audit from failure memory

- 增强 Factor Design Agent：读取 `failure_memory.jsonl` 改用统一 JSONL reader，坏行写入 `knowledge_base/jsonl_quarantine/failure_memory.jsonl.corrupt.jsonl`，不再静默吞掉 parse error。
- `candidate_factors.json` 新增 `skipped_factors` 和 `failed_memory_audit`，记录哪些候选因子因命中失败记忆被跳过、命中的 key、失败记忆来源计数和 parse error 数。
- Daily report 新增 `skipped failed factors`；`research_log_latest.json` 的 `factor_design` 节点新增 `skipped_failed_count` 和 `failed_memory_audit`，长期无人值守时可以解释某天候选减少的原因。
- 验证：`python -m py_compile agent/*.py` 通过；`pytest -q tests/test_quant_agents_research_data.py tests/test_quant_agents_backtest_critic.py` 为 `18 passed`；临时目录 `run_daily.sh` smoke 输出 `SMOKE True 0 True True`，证明日报、candidate JSON、research log 均包含失败记忆审计；量化 MVP 子集 `61 passed`。

## 2026-06-05 — Dataset hash provenance for backtests

- 增强 Data Agent：`dataset_manifest.json` 现在记录 `daily_dataset.parquet` 的 `dataset_sha256` 和 `dataset_size_bytes`。
- 增强 Backtest Agent：读取 dataset 前重新计算 parquet SHA256，若与 manifest 不一致或 manifest 缺 hash 直接失败；`backtest_results.json` 新增 `dataset_provenance`，记录 dataset path/hash/size/rows/stocks/dates/source mode/health status 和 `hash_verified=true`。
- Daily report 新增 `backtest dataset sha256`；`research_log_latest.json` 的 `backtest.dataset_provenance` 保存同一份 hash 证据，长期审计可证明回测确实基于当日标准数据集。
- 验证：`python -m py_compile agent/*.py` 通过；`pytest -q tests/test_quant_agents_research_data.py tests/test_quant_agents_backtest_critic.py tests/test_quant_daily_pipeline.py` 为 `29 passed`；临时目录 `run_daily.sh` smoke 输出 `SMOKE True True True True True`，证明 dataset manifest hash、backtest provenance hash、日报和 research log 一致；量化 MVP 子集 `62 passed`。

## 2026-06-05 — Next-generation factor file consistency gate

- 增强 `READINESS_REPORT`：新增 `latest_next_generation_files_match_payload` gate，要求最新 `next_generation_factors.json` 中每个 child factor 都有同名逐因子 JSON 文件，且 `factor_id`、`parent_factor_id`、`formula_key`、`status` 对齐。
- `next_generation_evidence` 现在输出 next-generation 数量、factor ids 和逐文件匹配状态；长期运行不能只靠汇总 payload 声称 evolution agent 已落盘候选。
- 新增 regression：构造 365 天生产证据齐全后篡改 `next_generation_factors/F1_PIVOT_DEF.json.formula_key`，确认 readiness 降为 `not_production_ready`。
- 验证：`python -m py_compile agent/*.py` 通过；`pytest -q tests/test_quant_self_audit.py` 为 `32 passed`；`pytest -q tests/test_quant_schedule.py tests/test_quant_self_audit.py tests/test_quant_daily_pipeline.py tests/test_quant_entrypoint.py` 为 `50 passed`；量化 MVP 子集为 `75 passed`；离线 `bash run_daily.sh` smoke 输出 `SMOKE not_production_ready True True 10`。

## 2026-06-05 — Research log current-output consistency gate

- 增强 `agent.knowledge_base`：`research_log_latest.json.backtest` 现在记录完整 `result_factor_ids`，不只记录 result count 和 top RankIC。
- 增强 `READINESS_REPORT`：新增 `latest_research_log_matches_current_outputs` gate，要求 `research_log_latest.json` 与当天 `daily_events.json`、`research_ideas.json`、`candidate_factors.json`、`backtest_results.json`、`critique.json`、`next_generation_factors.json`、`data_health.json` 的关键计数和 ids 对齐。
- 新增 regression：构造 365 天生产证据齐全后把 `research_log_latest.json.backtest.result_factor_ids` 改成 `STALE_FACTOR`，确认 readiness 降为 `not_production_ready`。
- 验证：`python -m py_compile agent/*.py` 通过；`pytest -q tests/test_quant_self_audit.py` 为 `33 passed`；`pytest -q tests/test_quant_schedule.py tests/test_quant_self_audit.py tests/test_quant_daily_pipeline.py tests/test_quant_entrypoint.py` 为 `51 passed`；量化 MVP 子集为 `76 passed`；离线 `bash run_daily.sh` smoke 输出 `SMOKE not_production_ready True True 5 5`。

## 2026-06-05 — Data health latest consistency gate

- 增强 `READINESS_REPORT`：新增 `latest_data_health_latest_matches_current_outputs` gate，要求 `knowledge_base/data_health_latest.json` 与当天 `data_health.json`、`dataset_manifest.json` 的状态、source mode、row/stock/date 数、freshness、checks、domain coverage、dataset SHA256 和 size 对齐。
- `data_latest_evidence` 现在输出 latest/current rows、stocks、dates、status 和 dataset hash，便于定位 latest 数据证据漂移。
- 新增 regression：构造 365 天生产证据齐全后把 `data_health_latest.json.dataset_manifest.dataset_sha256` 改成 stale 值，确认 readiness 降为 `not_production_ready`。
- 验证：`python -m py_compile agent/*.py` 通过；`pytest -q tests/test_quant_self_audit.py` 为 `34 passed`；`pytest -q tests/test_quant_schedule.py tests/test_quant_self_audit.py tests/test_quant_daily_pipeline.py tests/test_quant_entrypoint.py` 为 `52 passed`；量化 MVP 子集为 `77 passed`；离线 `bash run_daily.sh` smoke 输出 `SMOKE not_production_ready True True True`。

## 2026-06-05 — Current source snapshot consistency gate

- 增强 `READINESS_REPORT`：新增 `latest_source_snapshots_match_current_outputs` gate，要求当前 run 的 `source_snapshots/market_intelligence.json`、`source_snapshots/research_agent.json` 和同日 `source_snapshots.jsonl` 记录都与当天 `daily_events.json` / `research_ideas.json` 的 `source_status`、`source_quality`、item count 对齐。
- `source_snapshot_evidence` 现在输出当前快照文件存在状态、同日 JSONL snapshot agents 和匹配状态；latest pointer 不能再只证明最后一个 source snapshot 写入。
- 新增 regression：构造 365 天生产证据齐全后篡改 `source_snapshots/research_agent.json.item_count`，确认 readiness 降为 `not_production_ready`。
- 验证：`python -m py_compile agent/*.py` 通过；`pytest -q tests/test_quant_self_audit.py` 为 `35 passed`；`pytest -q tests/test_quant_schedule.py tests/test_quant_self_audit.py tests/test_quant_daily_pipeline.py tests/test_quant_entrypoint.py` 为 `53 passed`；量化 MVP 子集为 `78 passed`；离线 `bash run_daily.sh` smoke 输出 `SMOKE not_production_ready True True ['market_intelligence', 'research_agent']`。

## 2026-06-05 — Artifact manifest latest consistency gate

- 增强 `READINESS_REPORT`：新增 `artifact_manifest_latest_matches_current_manifest` gate，要求 `reports/artifact_manifest_latest.json` 与当前 run 的 `artifact_manifest.json` 在 run date、file count、total size 和每个 relative path 的 SHA256 上一致。
- `artifact_manifest` evidence 现在输出 latest run date、latest file count、latest total size 和 latest/current 匹配状态；长期审计不能只看 run-dir manifest。
- 新增 regression：构造 365 天生产证据齐全后把 `artifact_manifest_latest.json.file_count` 改成 stale 值，确认 readiness 降为 `not_production_ready`。
- 验证：`python -m py_compile agent/*.py` 通过；`pytest -q tests/test_quant_self_audit.py` 为 `36 passed`；`pytest -q tests/test_quant_schedule.py tests/test_quant_self_audit.py tests/test_quant_daily_pipeline.py tests/test_quant_entrypoint.py` 为 `54 passed`；量化 MVP 子集为 `79 passed`；离线 `bash run_daily.sh` smoke 输出 `SMOKE not_production_ready True True 49 49`。

## 2026-06-05 — Self-audit current-output consistency gate

- 增强 `READINESS_REPORT`：新增 `latest_self_audit_matches_current_outputs` gate，要求最新 `self_audit.json` 的 counts、preflight、data freshness、market source quality 和 research source quality 与当前 run-dir 产物一致。
- `latest_self_audit` evidence 现在同时输出 self-audit 记录值和 current 值，便于定位是回测数量、知识库因子数量、preflight 还是源质量漂移。
- 新增 regression：构造 365 天生产证据齐全后把 `self_audit.json.counts.backtest_results` 改成 `999`，确认 readiness 降为 `not_production_ready`。
- 验证：`python -m py_compile agent/*.py` 通过；`pytest -q tests/test_quant_self_audit.py` 为 `37 passed`；`pytest -q tests/test_quant_schedule.py tests/test_quant_self_audit.py tests/test_quant_daily_pipeline.py tests/test_quant_entrypoint.py` 为 `55 passed`；量化 MVP 子集为 `80 passed`；离线 `bash run_daily.sh` smoke 输出 `SMOKE not_production_ready True True {'backtest_results': 5, 'candidate_factors': 5, 'events': 1, 'ideas': 3, 'knowledge_factors': 5} {'backtest_results': 5, 'candidate_factors': 5, 'events': 1, 'ideas': 3, 'knowledge_factors': 5}`。

## 2026-06-05 — Candidate factor per-file consistency gate

- 增强 `READINESS_REPORT`：新增 `latest_candidate_factor_files_match_payload` gate，要求 `candidate_factors.json` 中每个候选都存在 run-local `candidate_factors/<factor_id>.json`，且 `factor_id`、`created_at_run`、`formula_key`、`expression`、`status` 对齐。
- `factor_library_evidence` 现在输出 `candidate_files_root` 和 `candidate_files_match_payload`，区分 run-local Agent 3 输出漂移和全局 `factor_library/` 漂移。
- 新增 regression：构造 365 天生产证据齐全后只篡改 `candidate_factors/F1.json.formula_key`，保持全局 `factor_library/F1.json` 正确，确认 readiness 降为 `not_production_ready`。
- 验证：`python -m py_compile agent/*.py` 通过；`pytest -q tests/test_quant_self_audit.py` 为 `38 passed`；`pytest -q tests/test_quant_schedule.py tests/test_quant_self_audit.py tests/test_quant_daily_pipeline.py tests/test_quant_entrypoint.py` 为 `56 passed`；量化 MVP 子集为 `81 passed`；离线 `bash run_daily.sh` smoke 输出 `SMOKE not_production_ready True True ['F_VOL_REV_5', 'F_VWAP_REV_5', 'F_MF_EXHAUST_5', 'F_MF_CONFIRM_5', 'F_VALUE_LIQ_DEF_5']`。

## 2026-06-05 — Failure analysis critique consistency gate

- 增强 `READINESS_REPORT`：新增 `latest_failure_analysis_matches_critique` gate，要求 `failure_analysis.md` 与当前 `critique.json` 对齐。
- 检查内容包括当前 run date、每个 critique 的 factor id、decision、issues、leakage check、stability score 和 collinearity score；`failure_analysis_evidence` 输出匹配状态、critique 数量和 factor ids。
- 新增 regression：构造 365 天生产证据齐全后把 `failure_analysis.md` 改成前一天 run date 和 stale factor，确认 readiness 降为 `not_production_ready`。
- 验证：`python -m py_compile agent/*.py` 通过；`pytest -q tests/test_quant_self_audit.py` 为 `39 passed`；`pytest -q tests/test_quant_schedule.py tests/test_quant_self_audit.py tests/test_quant_daily_pipeline.py tests/test_quant_entrypoint.py` 为 `57 passed`；量化 MVP 子集为 `82 passed`；离线 `bash run_daily.sh` smoke 输出 `SMOKE not_production_ready True True ['F_VOL_REV_5', 'F_VWAP_REV_5', 'F_MF_EXHAUST_5', 'F_MF_CONFIRM_5', 'F_VALUE_LIQ_DEF_5']`。

## 2026-06-05 — Backtest result per-file consistency gate

- 增强 `READINESS_REPORT`：新增 `latest_backtest_result_files_match_payload` gate，要求 `backtest_results.json` 中每个结果都存在 run-local `backtest_results/<factor_id>.json`，且 factor id、formula key、expression、RankIC、decision、portfolio metrics 对齐。
- `factor_database_evidence` 现在输出 `backtest_result_files_root` 和 `backtest_result_files_match_payload`，区分 run-local Backtest Agent 输出漂移和 factor database 漂移。
- 新增 regression：构造 365 天生产证据齐全后只篡改 `backtest_results/F1.json.rankic_mean`，保持汇总和 factor database 正确，确认 readiness 降为 `not_production_ready`。
- 验证：`python -m py_compile agent/*.py` 通过；`pytest -q tests/test_quant_self_audit.py` 为 `40 passed`；`pytest -q tests/test_quant_schedule.py tests/test_quant_self_audit.py tests/test_quant_daily_pipeline.py tests/test_quant_entrypoint.py` 为 `58 passed`；量化 MVP 子集为 `83 passed`；离线 `bash run_daily.sh` smoke 输出 `SMOKE not_production_ready True True ['F_VOL_REV_5', 'F_VWAP_REV_5', 'F_MF_EXHAUST_5', 'F_MF_CONFIRM_5', 'F_VALUE_LIQ_DEF_5']`。

## 2026-06-05 — Backtest dataset provenance readiness gate

- 增强 `READINESS_REPORT`：新增 `latest_backtest_dataset_provenance_matches_manifest` gate，要求 `backtest_results.json.dataset_provenance` 与当前 `dataset_manifest.json` 的 dataset SHA256、size、rows、stocks、dates、source mode、health status 一致，且 `hash_verified=true`。
- `factor_database_evidence` 现在输出 backtest/current dataset hash 和 size，便于定位 backtest summary 是否来自旧数据集或未验证数据集。
- 新增 regression：构造 365 天生产证据齐全后只篡改 `backtest_results.json.dataset_provenance.dataset_sha256`，确认 readiness 降为 `not_production_ready`，同时逐因子 backtest 文件和 factor database gate 保持 true。
- 验证：`python -m py_compile agent/*.py` 通过；`pytest -q tests/test_quant_self_audit.py` 为 `41 passed`；`pytest -q tests/test_quant_schedule.py tests/test_quant_self_audit.py tests/test_quant_daily_pipeline.py tests/test_quant_entrypoint.py` 为 `59 passed`；量化 MVP 子集为 `84 passed`；离线 `bash run_daily.sh` smoke 输出 `SMOKE not_production_ready True 190670903a66e90d5b743f162f0f9a312d50abdcb3c53ddf2760a3963e456bb8 190670903a66e90d5b743f162f0f9a312d50abdcb3c53ddf2760a3963e456bb8`。

## 2026-06-05 — Research log backtest provenance consistency gate

- 增强 `READINESS_REPORT`：`latest_research_log_matches_current_outputs` 现在同时要求 `research_log_latest.json.backtest.dataset_provenance` 与当前 `backtest_results.json.dataset_provenance` 完全一致。
- `research_log_evidence` 现在输出 research log 和 current backtest 的 dataset SHA256，便于定位长期知识库记录是否保存了旧数据来源。
- 新增 regression：构造 365 天生产证据齐全后只篡改 `research_log_latest.json.backtest.dataset_provenance.dataset_sha256`，确认 readiness 降为 `not_production_ready`，同时 `latest_backtest_dataset_provenance_matches_manifest` 保持 true。
- 验证：`python -m py_compile agent/*.py` 通过；`pytest -q tests/test_quant_self_audit.py` 为 `42 passed`；`pytest -q tests/test_quant_schedule.py tests/test_quant_self_audit.py tests/test_quant_daily_pipeline.py tests/test_quant_entrypoint.py` 为 `60 passed`；量化 MVP 子集为 `85 passed`；离线 `bash run_daily.sh` smoke 输出 `SMOKE not_production_ready True 190670903a66e90d5b743f162f0f9a312d50abdcb3c53ddf2760a3963e456bb8 190670903a66e90d5b743f162f0f9a312d50abdcb3c53ddf2760a3963e456bb8`。

## 2026-06-05 — Factor database full backtest consistency gate

- 增强 `READINESS_REPORT`：`latest_factor_database_matches_backtests` 现在要求同日 `knowledge_base/factor_database/factors.json` 记录与当前 `backtest_results.json` / `critique.json` 在 `decision`、`issues`、`name`、`formula`、`formula_key`、`expression`、`rankic_mean`、`portfolio` 上一致。
- `factor_database_evidence` 现在输出 `matched_fields`，明确长期 factor database 审计覆盖的字段集合。
- 新增 regression：构造 365 天生产证据齐全后只篡改 factor database 中 `portfolio.ann_return_net`，确认 readiness 降为 `not_production_ready`，同时当前 backtest 逐文件和 dataset provenance gate 保持 true。
- 验证：`python -m py_compile agent/*.py` 通过；`pytest -q tests/test_quant_self_audit.py` 为 `43 passed`；`pytest -q tests/test_quant_schedule.py tests/test_quant_self_audit.py tests/test_quant_daily_pipeline.py tests/test_quant_entrypoint.py` 为 `61 passed`；量化 MVP 子集为 `86 passed`；离线 `bash run_daily.sh` smoke 输出 `SMOKE not_production_ready True 5 ['decision', 'issues', 'name', 'formula', 'formula_key', 'expression', 'rankic_mean', 'portfolio']`。

## 2026-06-05 — Run history current-output consistency gate

- 增强 `READINESS_REPORT`：新增 `latest_run_history_matches_current_outputs` gate，要求 `run_history.jsonl` 最新记录与当前 run-dir 产物在 pipeline status、self-audit status/score、agent status、counts、market/research source quality、data health/source/freshness/checks/domain coverage 上一致。
- `history` evidence 现在输出 `latest_matches_current_outputs`、`latest_counts` 和 `current_counts`，便于定位主历史账本与当天产物漂移。
- 新增 regression：构造 365 天生产证据齐全后只篡改最新 run history 的 `counts.backtest_results=999`，确认 readiness 降为 `not_production_ready`，同时 run date 仍匹配当前日期。
- 验证：`python -m py_compile agent/*.py` 通过；`pytest -q tests/test_quant_self_audit.py` 为 `44 passed`；`pytest -q tests/test_quant_schedule.py tests/test_quant_self_audit.py tests/test_quant_daily_pipeline.py tests/test_quant_entrypoint.py` 为 `62 passed`；量化 MVP 子集为 `87 passed`；离线 `bash run_daily.sh` smoke 输出 `SMOKE not_production_ready True {'backtest_results': 5, 'candidate_factors': 5, 'events': 1, 'ideas': 3, 'killed': 3, 'promoted': 2, 'raw_candidates': 2} {'backtest_results': 5, 'candidate_factors': 5, 'events': 1, 'ideas': 3, 'killed': 3, 'promoted': 2, 'raw_candidates': 2}`。

## 2026-06-05 — Daily report current-output consistency gate

- 增强 `READINESS_REPORT`：`latest_daily_report_is_current_evidence` 现在要求 `daily_report.md` 中的事件数、source mode、研究想法数、候选数、回测数、backtest dataset hash、raw candidate 数、critic promote 数、data health、preflight 和 self-audit 状态都匹配当前 run-dir 产物。
- 新增 regression：构造 365 天生产证据齐全后只把 `daily_report.md` 的 `backtested factors` 改成 `999`，确认 readiness 降为 `not_production_ready`。
- 验证：`python -m py_compile agent/*.py` 通过；`pytest -q tests/test_quant_self_audit.py` 为 `45 passed`；`pytest -q tests/test_quant_schedule.py tests/test_quant_self_audit.py tests/test_quant_daily_pipeline.py tests/test_quant_entrypoint.py` 为 `63 passed`；量化 MVP 子集为 `88 passed`；离线 `bash run_daily.sh` smoke 输出 `SMOKE not_production_ready True ['- events collected: 1', '- research ideas: 3', '- candidate factors: 5', '- backtested factors: 5', '- backtest dataset sha256: 190670903a66']`。

## 2026-06-04 — Alpha GPU sbatch policy

- 结论：alpha 全量回测和后续 repair/pivot 搜索需要通过 Slurm `sbatch` 申请 GPU；登录节点只做轻量检查/CPU fallback，不应作为 GPU 可用性判断。
- 已验证：`scripts/alpha_gpu_probe.sbatch` job `29430` 在 A800 分区节点 `gpu4` 拿到 1 张 NVIDIA A800-SXM4-80GB，`torch 2.12.0+cu126`、`torch.cuda_available=True`、`numba.cuda_available=True`；`cupy/cudf` 未安装。
- 已验证：`scripts/alpha_gpu_backtest.sbatch` job `29432` 使用 `ALPHA_BACKEND=torch_cuda` 完成 A019/A020/A021 2019-2026 H5；结果与 CPU 路径一致，A020 保持 repair，A019/A021 kill。
- 后续作业：job `29460` 因 Slurm `--export` 逗号语法只跑到 H1；已用 shell 环境变量方式重提 job `29464`，参数为 `ALPHA_CANDIDATES=A020`、`ALPHA_HORIZONS=1,5,10,20`、`ALPHA_START=20190101`、`ALPHA_END=20260528`、`ALPHA_BACKEND=torch_cuda`。
- A020 GPU 多持仓期结果：H1/H5/H10/H20 Test RankIC 为 0.010715 / 0.008193 / 0.002126 / -0.011087；long-short 年化全为负，分别 -0.2596 / -0.1676 / -0.1611 / -0.1767；long-only 年化为 0.1545 / 0.1866 / 0.1949 / 0.1848，Sharpe 为 1.018 / 1.314 / 1.524 / 1.493。结论：A020 继续 repair，不能 promote。
- 继续改进：新增 A022-A026，围绕 A020 的问题做方向内 repair，包括低换手约束、60 日跳短反转长周期动量、价值/流动性/低波动交互和中长周期动量共振；`PANEL_CACHE_VERSION` 提升到 2，避免旧 cache 缺新特征列。
- GPU 申请：已用正确的 shell 环境变量方式提交 `sbatch --export=ALL scripts/alpha_gpu_backtest.sbatch`，job `29491`，参数为 `ALPHA_CANDIDATES=A022,A023,A024,A025,A026`、`ALPHA_HORIZONS=1,5,10,20`、`ALPHA_FAST=0`、`ALPHA_BACKEND=torch_cuda`。提交后状态为 A800 分区 `PD (Priority)`，等待 GPU 资源。
- 本地验证：`python -m py_compile alpha-stage/scripts/alpha_backtest.py`、`bash -n scripts/alpha_gpu_backtest.sbatch scripts/alpha_gpu_probe.sbatch`、`pytest -q tests/test_alpha_backtest_cache.py` 均通过。
- GPU 结果：job `29491` 在 A800 `gpu5` 完成。A022 是本批最强 repair 候选，H1/H5/H10/H20 Test RankIC 为 0.03148 / 0.03658 / 0.03395 / 0.02893，long-only 年化为 0.0964 / 0.1417 / 0.1551 / 0.1582，long-only Sharpe 为 0.749 / 1.124 / 1.366 / 1.485；但 long-short 年化全为负，分别 -0.1787 / -0.0634 / -0.0899 / -0.1088，不能 promote。
- A023/A024/A025/A026：long-only 多数为正，但 long-short 诊断全为负；A023 H10/H20 和 A026 H5/H10/H20 RankIC 转负。结论：A022/A024/A025 进入 repair/reviewer 队列，A023/A026 暂不扩大，不能宣称可交易 alpha。

## 2026-06-05 — Run audit final-state consistency gate

- 增强 `READINESS_REPORT`：`latest_run_audit_is_current_evidence` 现在要求 `run_audit.json.state` 与当前 `pipeline_state.json` 的 run date、status、completed agents、agent statuses、lock、retention 和关键产物路径一致。
- 修复每日 pipeline：`run_audit.json` 在最终 `pipeline_state.json` 写完后重写，并对 state/lock 做深拷贝，避免中途快照或共享列表引用污染最终审计证据。
- 新增 regression：构造 365 天生产证据齐全但篡改 `run_audit.state.agents` 少一个 agent，确认 readiness 降为 `not_production_ready`，并输出 `state_matches_pipeline_state=false`、audit/pipeline agent count。
- GPU 策略确认：alpha GPU 回测仍必须通过 `bash scripts/submit_alpha_gpu_backtest.sh` 触发 `sbatch` 申请 A800；登录节点只做轻量检查，不能作为 CUDA 可用性判断。
- 验证：`python -m py_compile agent/*.py` 通过；`bash -n scripts/submit_alpha_gpu_backtest.sh scripts/alpha_gpu_backtest.sbatch scripts/alpha_gpu_probe.sbatch` 通过；`pytest -q tests/test_quant_self_audit.py` 为 `46 passed`；`pytest -q tests/test_quant_schedule.py tests/test_quant_self_audit.py tests/test_quant_daily_pipeline.py tests/test_quant_entrypoint.py` 为 `64 passed`；量化测试全集为 `89 passed`；离线 `bash run_daily.sh` smoke 输出 `run_audit_current=True`、`state_matches_pipeline_state=True`、`manifest_verified=True`、`daily_report_current=True`。

## 2026-06-05 — Artifact manifest stable latest comparison

- 增强 `READINESS_REPORT`：`artifact_manifest_latest_matches_current_manifest` 现在比较 stable artifact records，忽略 `READINESS_REPORT.json` / `READINESS_REPORT.md` 这类 readiness 自身会重写的 mutable 输出；稳定记录仍核对 SHA256 和 size。
- `artifact_manifest` evidence 新增 `stable_file_count`、`stable_total_size_bytes`、`latest_stable_file_count`、`latest_stable_total_size_bytes` 和 `mutable_readiness_paths`，用于区分真实产物漂移和 readiness 自引用文件大小变化。
- 新增 regression：篡改 latest manifest 中稳定文件 `backtest_results.json` 的 hash 会阻塞 production readiness；只篡改 latest manifest 中 `READINESS_REPORT.json` 的 hash/size 不会误报。
- 离线入口 smoke 证明最终自引用漂移已被隔离：raw latest total 为 `308521` vs final latest total `307086`，但 stable total 均为 `269445`，`manifest_gate=True`、`manifest_verified=True`。
- 验证：`python -m py_compile agent/*.py` 通过；`bash -n scripts/submit_alpha_gpu_backtest.sh scripts/alpha_gpu_backtest.sbatch scripts/alpha_gpu_probe.sbatch` 通过；`pytest -q tests/test_quant_self_audit.py` 为 `47 passed`；`pytest -q tests/test_quant_schedule.py tests/test_quant_self_audit.py tests/test_quant_daily_pipeline.py tests/test_quant_entrypoint.py` 为 `65 passed`；量化测试全集为 `90 passed`。

## 2026-06-05 — Failed run_daily entrypoints refresh audit evidence

- 增强 `agent.run_entrypoint`：成功路径保持原有 readiness/manifest 多轮刷新；失败路径在 config 已加载时也 best-effort 刷新 `READINESS_REPORT.*` 和 `artifact_manifest_latest.json`，让无人值守失败显示在最新审计产物里。
- `run_daily_invocation_latest.json` 现在对正常配置路径显式记录 `config_loaded=true`；配置加载失败仍使用 fallback record，并保留 `config_loaded=false`。
- 新增 regression：模拟 `daily_pipeline.run` 抛出异常后，入口退出 `1`，invocation 为 `error`，`READINESS_REPORT.json` 为 `not_production_ready` 且 `run_daily_invocation_success=false`，manifest 包含 `run_daily_invocation_latest.json`。
- 真实失败 smoke：预置 fresh `.quant_daily.lock` 后运行 `python -m agent.run_entrypoint`，输出 `FAIL_SMOKE_EXIT 1`、`invocation error 1 RuntimeError`、`readiness not_production_ready True False`、`manifest_has_invocation True`。
- 验证：`python -m py_compile agent/*.py` 通过；`pytest -q tests/test_quant_entrypoint.py` 为 `7 passed`；聚合测试为 `65 passed`；量化测试全集为 `90 passed`；sbatch 脚本 `bash -n` 通过。

## 2026-06-05 — Interrupted pipeline states are persisted in run_audit

- 修复 `agent.daily_pipeline` 异常分支：未捕获异常或 `KeyboardInterrupt` 写入 `pipeline_state.json(status=interrupted)` 后，现在同步写 `run_audit.json`，保留同一份 interrupted state、active agent、completed agents、lock/config 和 traceback。
- 新增 regression：模拟 `fatal_agent` 抛出 `KeyboardInterrupt`，要求 `run_audit.state == pipeline_state`、`state.status=interrupted`、`current_agent=fatal_agent`，且 lock 已释放。
- 正常入口 smoke 仍通过：`bash run_daily.sh` 输出 `run_audit_current=True`、`state_matches_pipeline_state=True`、`audit_state_status complete True`、`manifest_gate=True`。
- 验证：`python -m py_compile agent/*.py` 通过；`pytest -q tests/test_quant_daily_pipeline.py tests/test_quant_entrypoint.py` 为 `17 passed`；聚合测试为 `65 passed`；量化测试全集为 `90 passed`；sbatch 脚本 `bash -n` 通过。

## 2026-06-05 — Agent retry attempts are auditable after transient recovery

- 增强 `agent.daily_pipeline._run_agent_with_retries`：每次失败尝试会记录到 agent status 的 `retries` 列表，包含 attempt、duration、error 和 traceback 摘要；最终成功的 transient retry 也保留失败尝试证据。
- 永久失败路径继续写 `errors/<agent>.json`，现在该错误 JSON 也包含完整 `retries` 列表，便于区分单次失败和多轮重试失败。
- 新增 regression：`market_intelligence` 首次失败、第二次成功时，`pipeline_state.json` 中该 agent `attempt=2` 且 `retries[0].error` 包含 transient，同时不生成 `errors/market_intelligence.json`；`data_agent` 永久失败时 `errors/data_agent.json.retries[0]` 记录失败详情。
- 正常入口 smoke 仍通过：状态 `complete`、13 个 agent、无 retry 记录、`run_audit_current=True`、manifest gate 为 true。
- 验证：`python -m py_compile agent/*.py` 通过；`pytest -q tests/test_quant_daily_pipeline.py` 为 `10 passed`；聚合测试为 `65 passed`；量化测试全集为 `90 passed`；sbatch 脚本 `bash -n` 通过。

## 2026-06-05 — Daily simulation evidence is explicitly local-only

- 增强 `agent.daily_simulation`：输出状态从泛化的 `pass` 改为 `simulation_pass` / `simulation_warning`，并新增 `uses_shell_entrypoint=false`、`production_ready_evidence=false`、`evidence_scope=local_simulation_only`。
- 修复配置继承：simulation 中每个 `RunConfig` 现在继承 `lock_stale_minutes` 和 `min_free_disk_mb`，避免本地多日压测绕过长期运行配置。
- 新增 regression：3 日 simulation 必须输出 local-only evidence 标记，并检查每日 `run_audit.config` 继承自定义 lock/disk 配置。
- Simulation smoke：`QUANT_SIM_DAYS=2 python -m agent.daily_simulation` 输出 `SIM_SMOKE simulation_pass False False local_simulation_only`，history 为 2，latest run date 为 `20260606`，run audit 配置为 `77/1`。
- 验证：`python -m py_compile agent/*.py` 通过；`pytest -q tests/test_quant_daily_pipeline.py` 为 `10 passed`；聚合测试为 `65 passed`；量化测试全集为 `90 passed`；sbatch 脚本 `bash -n` 通过。

## 2026-06-05 — A029 GPU rerun submitted through Slurm

- 结论：正式 alpha GPU 回测已按 Slurm 申请 GPU 路径执行，而不是登录节点 CPU/CUDA 直跑。提交命令为 `ALPHA_CANDIDATES='A029' ALPHA_HORIZONS='5' ALPHA_COSTS='5,10,20,30' ALPHA_FAST=0 ALPHA_BACKEND=torch_cuda bash scripts/submit_alpha_gpu_backtest.sh`。
- Slurm 证据：job `29571` 在 A800 分区 `gpu2` 完成；日志显示 `CUDA_VISIBLE_DEVICES=0`、`torch.cuda_available=True`、device `NVIDIA A800-SXM4-80GB`，stderr 为空。
- A029 H5 成本敏感性：RankIC `0.04490`；5/10/20/30bps 下 long-short 年化分别为 `0.03656`、`0.02227`、`-0.00630`、`-0.03487`，long-only 年化分别为 `0.18185`、`0.17463`、`0.16020`、`0.14577`。
- 决策：GPU 不是当前 blocker；A029 仍需 repair，原因是高成本下 long-short 转负，不能据此 promote。
- 验证：`bash -n scripts/submit_alpha_gpu_backtest.sh scripts/alpha_gpu_backtest.sbatch scripts/alpha_gpu_probe.sbatch` 通过；`pytest -q tests/test_alpha_backtest_cache.py tests/test_quant_*.py tests/test_backtest_engine_package.py` 为 `91 passed`。

## 2026-06-05 — Schedule evidence includes cron log writability

- 增强 `agent.schedule`：cron 示例现在把输出重定向到绝对路径 `reports/daily_cron.log`，并在 `schedule.json` 记录 `log_path`、`log_parent`、`log_parent_exists` 和 `log_parent_writable`。
- 增强 `READINESS_REPORT`：`latest_schedule_is_daily_run_daily` 除了要求每日 `bash run_daily.sh`、脚本存在、未自动安装 crontab 外，现在还要求 cron 日志目录存在且可写，避免长期无人值守失败时没有日志落盘。
- 新增 regression：schedule 指向不存在/不可写 cron 日志目录时，即使 cadence 和 run_daily.sh 正确，也保持 `not_production_ready`。
- 离线入口 smoke：`bash run_daily.sh` 生成 `schedule_gate=True`、`cron_example_gate=True`、`log_path=/home/lcc17/dl/reports/daily_cron.log`、`log_parent=True/True`、manifest gate 和 invocation gate 均为 true；整体仍为 `not_production_ready`，因为真实 365 天生产证据缺失。
- 验证：`python -m py_compile agent/*.py` 通过；`pytest -q tests/test_quant_schedule.py tests/test_quant_self_audit.py` 为 `50 passed`；`pytest -q tests/test_quant_schedule.py tests/test_quant_self_audit.py tests/test_quant_daily_pipeline.py tests/test_quant_entrypoint.py` 为 `67 passed`；量化测试全集 `pytest -q tests/test_alpha_backtest_cache.py tests/test_quant_*.py tests/test_backtest_engine_package.py` 为 `92 passed`。

## 2026-06-05 — Source snapshots carry fetch replay metadata

- 增强 `market_intelligence` 和 `research_agent`：每条 source status 现在记录源 URL；live 成功时记录 `response_bytes`、`content_sha256`、`fetched_at` 和 latency；失败时记录 `error_type`、错误摘要、URL 和 `fetched_at`；离线跳过也保留 URL。
- 增强 `source_cache`：每个 source snapshot 记录 `snapshot_written_at`，使 offline/fallback 路径也有可审计的快照写入时间。
- 目的：365 天生产证据不仅证明“source quality 通过”，还保留当天每个联网源的地址、响应指纹和错误类型，便于后续复盘数据源变化或抓取失败。
- 离线入口 smoke：`bash run_daily.sh` 输出 `snapshot_written_at=True/True`、`source_status_urls=True/True`、`latest_source_snapshots_match_current_outputs=True`、manifest gate 为 true；整体仍为 `not_production_ready`，因为真实 365 天生产证据缺失。
- 验证：`python -m py_compile agent/*.py` 通过；`pytest -q tests/test_quant_agents_market.py tests/test_quant_agents_research_data.py tests/test_quant_self_audit.py` 为 `64 passed`；聚合测试为 `67 passed`；量化测试全集为 `92 passed`。

## 2026-06-05 — Failure-memory formula keys are re-normalized before matching

- 增强 `factor_design`：失败因子 identity key 现在同时包含 raw 和 normalized 的 `formula` / `formula_key`，不再假设历史 `formula_key` 已经标准化；旧记录中大小写、空格等格式差异仍能阻止重复研究同一失败公式。
- 增强 `evolution_agent`：repair/pivot 子因子的失败记忆匹配也使用同一套 identity key，避免下一代因子反复生成格式不同但语义相同的失败修复。
- 新增 regression：factor database 中存储格式化 `formula_key` 时，`F_VOL_REV_5` 会被跳过；failure memory 中格式化成本修复公式时，`BAD_VOL_PIVOT_COST` 会被跳过。
- 离线入口 smoke：`bash run_daily.sh` 输出 `readiness_factor_db=True`、manifest gate 为 true；临时空知识库下 failed key count 为 0 属于预期。
- 验证：`python -m py_compile agent/*.py` 通过；`pytest -q tests/test_quant_agents_research_data.py tests/test_quant_agents_backtest_critic.py tests/test_quant_self_audit.py` 为 `71 passed`；聚合测试为 `67 passed`；量化测试全集为 `94 passed`。

## 2026-06-05 — Data source detail records fallback root cause

- 增强 `data_agent`：`dataset_manifest.json`、`data_health.json` 和 `knowledge_base/data_health_latest.json` 现在包含 `data_source_detail`，记录 `data_root`、日期窗口、daily/metric/moneyflow/ST CSV 目录是否存在、CSV 文件数、窗口内选中文件数、样例路径、`basic.csv` 是否存在，以及 fallback 原因。
- 合成数据 fallback 现在显式记录 `fallback_reason=daily_csv_missing_or_empty`，用于区分“数据目录不存在/空窗口”与真实本地 CSV 构建。
- 本地 CSV 构建时记录各数据域目录的 selected CSV 数和 basic 文件存在性；这为 365 天生产证据中的每日数据来源提供可复盘路径。
- 离线入口 smoke：`bash run_daily.sh` 输出 `source_mode=synthetic_fallback`、`fallback_reason=daily_csv_missing_or_empty`、daily exists/selected 为 `False/0`，`latest_data_is_production_evidence=False`，manifest gate 为 true。
- 验证：`python -m py_compile agent/*.py` 通过；`pytest -q tests/test_quant_agents_research_data.py tests/test_quant_self_audit.py` 为 `62 passed`；聚合测试为 `67 passed`；量化测试全集为 `94 passed`。

## 2026-06-05 — Factor database persists complete backtest audit evidence

- 增强 `knowledge_base`：写入 `factor_database/factors.json` 时除 RankIC 和 long-only portfolio 外，现在持久化 `horizon_days`、`rankic_ir`、`rankic_positive_frac`、`long_short`、`cost_sensitivity`、`rows`、`dates` 和 `decision_note`。
- 增强 `READINESS_REPORT`：`latest_factor_database_matches_backtests` 现在要求上述完整字段与 `backtest_results.json` 一致，避免知识库只保存结论而丢失成本敏感性、long-short 诊断和样本规模证据。
- 新增 regression：篡改 factor database 中 `cost_sensitivity["20"].ann_return_net` 会阻塞 production readiness；knowledge base 单测要求完整字段落库。
- 离线入口 smoke：`bash run_daily.sh` 生成 5 条 factor database 记录，增强字段全部存在；`READINESS_REPORT.json` 中 `latest_factor_database_matches_backtests=True`。整体仍为 `not_production_ready`，因为这是离线 synthetic fallback，不满足 365 天真实生产证据。
- 验证：`python -m py_compile agent/*.py` 通过；`pytest -q tests/test_quant_agents_backtest_critic.py tests/test_quant_self_audit.py` 为 `59 passed`；聚合测试为 `68 passed`；量化测试全集为 `95 passed`。

## 2026-06-05 — Production source snapshots require replay metadata

- 增强 `READINESS_REPORT`：source snapshot 计入 365 天生产级 source evidence 前，现在要求 snapshot 有 `snapshot_written_at`，且每个 ok source status 都有 URL、`fetched_at`、`content_sha256` 和正数 `response_bytes`。
- 目的：避免只有 `status=ok/items>0` 的弱记录被当作“联网源生产证据”；365 天后仍能用 URL、响应指纹和写入时间复盘当日信息源。
- 新增 regression：365 天其它证据齐全时，删掉其中一天 market source 的 `content_sha256` 会使 `has_365_source_snapshot_dates=False`，生产级 source snapshot 日期数降为 364。
- 离线入口 smoke：`bash run_daily.sh` 仍可运行，`latest_source_snapshots_match_current_outputs=True`；离线 `skipped_offline` 源保留 URL 和 snapshot 写入时间，但无响应 hash，因此 `production_source_snapshot_dates=0`，整体保持 `not_production_ready`。
- 验证：`python -m py_compile agent/*.py` 通过；`pytest -q tests/test_quant_self_audit.py` 为 `51 passed`；聚合测试为 `69 passed`；量化测试全集为 `96 passed`；sbatch 脚本 `bash -n` 通过。

## 2026-06-05 — Production data artifacts require manifest hash and source detail

- 增强 `READINESS_REPORT`：365 天生产级 data artifact 日期现在要求 `data_health.jsonl` 记录包含 `dataset_manifest`、`data_health`、dataset SHA256、正数 size/rows/stocks/dates、manifest 与 health 的 rows/stocks/dates/source mode 一致，以及 `data_source_detail` 中真实 daily CSV 路径、存在性和窗口内选中文件数。
- 新增 latest gate：`latest_data_artifact_is_production_evidence` 要求 `data_health_latest.json` 同样证明 hashed real data artifact；仅 `run_history` 中写 `source_mode=local_csv` 不再足够。
- 新增 regression：365 天其它证据齐全时，删掉其中一天 `dataset_manifest.dataset_sha256` 会使 `has_365_data_artifact_dates=False`，生产级 data artifact 日期数降为 364。
- 离线入口 smoke：`bash run_daily.sh` 仍可运行并生成 dataset hash；但 `source_mode=synthetic_fallback` 且 `fallback_reason=daily_csv_missing_or_empty`，所以 `latest_data_artifact_is_production_evidence=False`、`production_data_artifact_dates=0`，整体保持 `not_production_ready`。
- 验证：`python -m py_compile agent/*.py` 通过；`pytest -q tests/test_quant_self_audit.py` 为 `52 passed`；聚合测试为 `70 passed`；量化测试全集为 `97 passed`；sbatch 脚本 `bash -n` 通过。

## 2026-06-05 — run_daily invocation requires shell provenance

- 增强 `run_daily.sh`：执行 `python -m agent.run_entrypoint` 前设置 `QUANT_RUN_DAILY_SH=1`、`QUANT_RUN_DAILY_SCRIPT=$PWD/run_daily.sh` 和 `QUANT_RUN_DAILY_COMMAND="bash run_daily.sh"`。
- 增强 `run_entrypoint`：每条 invocation record 记录 `shell_entrypoint`、`entrypoint_script`、`entrypoint_script_exists`、`entrypoint_command` 和 `config_loaded`。
- 增强 `READINESS_REPORT`：`run_daily_invocation_success` 和 365 天 successful invocation 计数现在要求成功记录来自 shell `bash run_daily.sh`，脚本路径存在且命令包含 `bash run_daily.sh`；直接 `python -m agent.run_entrypoint` 不再算作 shell-level production invocation。
- 新增 regression：latest invocation 即使 `status=success/exit_code=0`，只要缺少 shell provenance，readiness 仍阻断；entrypoint 单测分别覆盖直接 Python 调用和 run_daily shell provenance。
- 离线入口 smoke：真实 `bash run_daily.sh` 写出 `shell_entrypoint=True`、`entrypoint_script=/home/lcc17/dl/run_daily.sh`、`entrypoint_script_exists=True`、`entrypoint_command="bash run_daily.sh"`，且 `run_daily_invocation_success=True`。整体仍为 `not_production_ready`，因为缺少真实 365 天生产证据。
- 验证：`python -m py_compile agent/*.py` 通过；`pytest -q tests/test_quant_entrypoint.py tests/test_quant_self_audit.py` 为 `61 passed`；聚合测试为 `72 passed`；量化测试全集为 `99 passed`；`bash -n run_daily.sh` 和 sbatch 脚本检查通过。

## 2026-06-05 — Knowledge saves require saved factor ids

- 增强 `knowledge_base`/`READINESS_REPORT`：complete pipeline 的 `factor_database_write` 现在记录 `saved_factor_count` 和 `saved_factor_ids`，readiness 只把 saved ids/count 与同日 `backtest.result_factor_ids` 精确一致的 research log 计入 knowledge-save production evidence。
- 新增 regression：365 天其它生产证据齐全时，篡改其中一天 `saved_factor_ids=[]` 会使 `has_365_knowledge_save_dates=False`，knowledge save 日期数降为 364。
- 离线入口 smoke：`bash run_daily.sh` 写出 5 个 saved factor ids，和 backtest ids 一致；shell provenance 为 true。整体仍为 `not_production_ready`，因为只有 1/365 天生产证据。
- GPU 约束：GPU alpha backtest 入口保持为 Slurm 申请，使用 `ALPHA_CANDIDATES='A029' ALPHA_HORIZONS='5' ALPHA_COSTS='5,10,20,30' ALPHA_FAST=0 ALPHA_BACKEND=torch_cuda bash scripts/submit_alpha_gpu_backtest.sh` 提交到 `scripts/alpha_gpu_backtest.sbatch`，不在登录节点直接跑 CUDA。
- 验证：`python -m py_compile agent/*.py` 通过；`pytest -q tests/test_quant_agents_backtest_critic.py tests/test_quant_self_audit.py` 为 `63 passed`；聚合测试为 `73 passed`；量化测试全集为 `100 passed`；`bash -n run_daily.sh scripts/submit_alpha_gpu_backtest.sh scripts/alpha_gpu_backtest.sbatch scripts/alpha_gpu_probe.sbatch` 通过。

## 2026-06-05 — Source snapshots require replayable counts and metadata formats

- 增强 `READINESS_REPORT`：source snapshot 计入 production evidence 前，现在要求 `snapshot_written_at` 和每个 `fetched_at` 是可解析 ISO 时间，`content_sha256` 是 64 位 hex，URL 使用 `https://`，且 snapshot `item_count` 与所有 ok source 的 `items` 总数一致。
- 新增 regression：365 天其它生产证据齐全时，把其中一天 market snapshot 的 `item_count` 改为与 source status 不一致，会使 `has_365_source_snapshot_dates=False`，production source snapshot 日期数降为 364。
- 离线入口 smoke：`bash run_daily.sh` 仍完整运行，shell invocation 为 true；offline source snapshot 写入时间存在，但 `latest_market_sources_are_production_evidence=False`、`latest_research_sources_are_production_evidence=False`、`production_source_snapshot_dates=0`，不会被误计为 live source 生产证据。
- 验证：`python -m py_compile agent/*.py` 通过；source/readiness 目标测试 `71 passed`；schedule/self-audit/daily/entrypoint 聚合测试 `74 passed`；量化测试全集 `101 passed`；Slurm/入口脚本 `bash -n` 通过。

## 2026-06-05 — run_daily invocation requires complete timing evidence

- 增强 `READINESS_REPORT`：successful `bash run_daily.sh` invocation 现在除 shell provenance/config loaded 外，还要求 `started_at` 和 `finished_at` 为可解析 ISO 时间，`duration_sec` 为正数，避免缺少运行时长证据的记录计入 365 天无人值守证明。
- 新增 regression：365 天其它证据齐全时，删掉其中一天 invocation 的 `finished_at` 会使 successful run_daily invocation 数降为 364，并阻断 365 天 shell invocation gates。
- 离线入口 smoke：真实 `bash run_daily.sh` 写出 `started_at`、`finished_at`、`duration_sec=6.013`，`run_daily_invocation_success=True`；整体仍为 `not_production_ready`，因为缺少真实 365 天 production evidence。
- 验证：`python -m py_compile agent/*.py` 通过；entrypoint+self-audit `64 passed`；schedule/self-audit/daily/entrypoint 聚合测试 `75 passed`；量化测试全集 `102 passed`；入口和 Slurm 脚本 `bash -n` 通过。

## 2026-06-05 — Failure memory must link to generated next actions

- 增强 `READINESS_REPORT`：被 kill 因子的同日 failure memory 不只核对 issues/checks/formula/parent metrics，现在还要求 `next_actions` 非空，且与当前 `next_generation_factors.json` 中同一 `parent_factor_id` 生成的子因子 id 精确一致。
- 新增 regression：365 天其它证据齐全时，把 failure memory 的 `next_actions` 改为 `STALE_PIVOT` 会阻断 `latest_killed_factor_failure_memory_details_match`，防止“记录失败但没有真实 repair/pivot 产物”被当作完成。
- 离线入口 smoke：真实 `bash run_daily.sh` 生成 3 条 failure memory 和 10 个 next-generation factors，`latest_killed_factor_failure_memory_details_match=True`；第一条 failure memory 的 next actions 对应当前生成子因子。
- 验证：`python -m py_compile agent/*.py` 通过；self-audit `57 passed`；schedule/self-audit/daily/entrypoint 聚合测试 `76 passed`；量化测试全集 `103 passed`；入口和 Slurm 脚本 `bash -n` 通过。

## 2026-06-05 — Backtest result files require full audit fields

- 增强 `READINESS_REPORT`：`backtest_results/<factor_id>.json` 现在必须与聚合 `backtest_results.json` 的完整审计字段一致，包括 `rankic_ir`、`rankic_positive_frac`、`rankic_by_date`、`long_short`、`cost_sensitivity`、rows/dates 和 decision note。
- 新增 regression：365 天其它证据齐全时，删除单因子 backtest 文件中的 `cost_sensitivity` 会阻断 `latest_backtest_result_files_match_payload`；防止单因子文件丢失成本敏感性证据但仍被认为可审计。
- 离线入口 smoke：真实 `bash run_daily.sh` 的单因子 backtest 文件包含 `rankic_by_date`、`cost_sensitivity` 和 `long_short`，且 `latest_backtest_result_files_match_payload=True`。
- 验证：`python -m py_compile agent/*.py` 通过；self-audit `58 passed`；backtest/critic `9 passed`；schedule/self-audit/daily/entrypoint 聚合测试 `77 passed`；量化测试全集 `104 passed`；入口和 Slurm 脚本 `bash -n` 通过。

## 2026-06-05 — A029 GPU rerun submitted through sbatch allocation

- 结论：A 股 alpha GPU 回测必须通过 Slurm 申请资源；本次没有在登录节点直接跑 CUDA/CPU fallback，而是用 `ALPHA_CANDIDATES='A029' ALPHA_HORIZONS='5' ALPHA_COSTS='5,10,20,30' ALPHA_FAST=0 ALPHA_BACKEND=torch_cuda bash scripts/submit_alpha_gpu_backtest.sh` 提交。
- Slurm 证据：job `29572` 在 A800 分区 `gpu2` 完成；stdout 记录 `CUDA_VISIBLE_DEVICES=0`、`torch 2.12.0+cu126`、`torch.cuda_available=True`、device `NVIDIA A800-SXM4-80GB`，stderr 为 0 字节。
- 结果：A029 H5 test RankIC `0.044898`；5/10/20/30bps long-short annual net 分别为 `0.036556 / 0.022270 / -0.006300 / -0.034871`；long-only annual net 分别为 `0.181849 / 0.174633 / 0.160203 / 0.145772`。
- 决策：GPU 使用路径已经验证，A029 仍为 `repair`，不是因为 CPU/GPU 资源问题被 kill；主要 blocker 是高成本 long-short 转负、H>1 真账本和 size/industry neutral diagnostics 缺口。

## 2026-06-05 — Daily report carries readiness evidence

- 增强 `daily_report.md`：新增 `## Readiness` 区块，写入 readiness status、score、blocker count 和 top blocker，使每日人工阅读报告直接暴露 production readiness 状态。
- 增强 `READINESS_REPORT`：`latest_daily_report_is_current_evidence` 现在要求日报包含 readiness 摘要字段；缺少该区块会阻断 production readiness。
- Pipeline 收敛：最终 readiness 生成后重写日报，并重新生成 artifact manifest，确保 manifest 中 `daily_report.md` 的 SHA256 覆盖最终日报内容。
- 离线入口 smoke：`bash run_daily.sh` 输出 `SMOKE_DAILY_READINESS_SECTION True True True`、`SMOKE_DAILY_GATE True`、`SMOKE_MANIFEST_DAILY_HASH True`、`SMOKE_INVOCATION True`；整体仍为 `not_production_ready`，首要 blocker 是 `1/365 successful audited runs recorded`。
- 验证：`python -m py_compile agent/*.py` 通过；`pytest -q tests/test_quant_self_audit.py` 为 `59 passed`；`pytest -q tests/test_quant_daily_pipeline.py` 为 `10 passed`；聚合测试为 `78 passed`；量化测试全集为 `105 passed`；入口和 Slurm 脚本 `bash -n` 通过。

## 2026-06-05 — Daily report readiness summary matches final artifact

- 发现并修复 shell-entrypoint 不一致：`run_entrypoint` 在 `daily_pipeline.run()` 后写入 `run_daily_invocation_latest.json` 并刷新 readiness/manifest，会改变 final readiness score，但此前不会同步 `daily_report.md` 的 readiness 摘要。
- 增强 `READINESS_REPORT`：`latest_daily_report_is_current_evidence` 现在要求日报中的 readiness status、score、blocker count、top blocker 与最新 `reports/READINESS_REPORT.json` 精确一致；只包含字段名不再足够。
- 增强收敛流程：`daily_pipeline` 和 `run_entrypoint` 都会循环刷新 readiness、日报 readiness 区块和 artifact manifest，直到 readiness 摘要稳定。
- 离线入口 smoke：真实 `bash run_daily.sh` 输出 `SMOKE_DAILY_GATE True`、`SMOKE_SUMMARY_MATCH True`、`SMOKE_MANIFEST_DAILY_HASH True`、`SMOKE_INVOCATION True`；日报和 final JSON 均为 `not_production_ready`、score `0.6765`、blockers `22`。
- 验证：`python -m py_compile agent/*.py` 通过；entrypoint+daily pipeline `18 passed`；self-audit/readiness `60 passed`；聚合测试 `79 passed`；量化测试全集 `106 passed`；入口和 Slurm 脚本 `bash -n` 通过。

## 2026-06-05 — Artifact manifest records final run_audit hash

- 发现并修复 direct pipeline 审计顺序问题：`daily_pipeline` 先刷新 readiness/manifest，随后才写最终 `run_audit.json`，导致 `artifact_manifest.json` 中的 `run_audit.json` SHA256 落后于最终文件。
- 修复：最终 `_write_run_audit` 移到最终 readiness/manifest 收敛刷新之前，使 artifact manifest 和 verifier 看到最终 run audit。
- 新增 regression：`test_daily_pipeline_runs_all_agents` 直接重算 `run_audit.json` SHA256，并要求它与 manifest 记录一致。
- Direct pipeline smoke：`RUN_AUDIT_HASH_MATCH True`、`DAILY_GATE True`、`MANIFEST_VERIFICATION True pass 0`。
- Shell smoke：真实 `bash run_daily.sh` 输出 `SMOKE_RUN_AUDIT_HASH_MATCH True`、`SMOKE_DAILY_GATE True`、`SMOKE_SUMMARY_MATCH True`、`SMOKE_MANIFEST_VERIFICATION True 0`、`SMOKE_INVOCATION True`。
- 验证：`python -m py_compile agent/*.py` 通过；daily pipeline `10 passed`；entrypoint+self-audit `68 passed`；聚合测试 `79 passed`；量化测试全集 `106 passed`；入口和 Slurm 脚本 `bash -n` 通过。

## 2026-06-05 — Artifact verification proves final manifest freshness

- 发现并修复 verification freshness 问题：最终 `artifact_verification.json.manifest_generated_at` 落后于最终 `artifact_manifest.json.generated_at`，说明 verifier 校验的是上一版 manifest。
- 修复：readiness/manifest 收敛循环在 readiness 摘要稳定时停止，不再额外重写 manifest；最终 readiness 运行会生成指向当前 manifest 的 verification。
- 增强 `READINESS_REPORT`：artifact manifest verification 摘要现在暴露 verifier `generated_at` 和 `manifest_generated_at`，便于审计 final readiness 是否校验了最终 manifest。
- Regression：`test_daily_pipeline_runs_all_agents` 要求 `artifact_verification.json.manifest_generated_at` 和 readiness 内嵌 `artifact_manifest.verification.manifest_generated_at` 都等于最终 manifest `generated_at`。
- Direct pipeline smoke：`VERIFICATION_FRESH True`、`READINESS_VERIFICATION_FRESH True`、`DAILY_GATE True`、`MANIFEST_VERIFICATION True 0`。
- Shell smoke：真实 `bash run_daily.sh` 输出 `SMOKE_VERIFICATION_FRESH True`、`SMOKE_READINESS_VERIFICATION_FRESH True`、`SMOKE_RUN_AUDIT_HASH_MATCH True`、`SMOKE_DAILY_GATE True`、`SMOKE_MANIFEST_VERIFICATION True 0`。
- 验证：`python -m py_compile agent/*.py` 通过；daily+entrypoint `18 passed`；daily pipeline `10 passed`；entrypoint+self-audit `68 passed`；聚合测试 `79 passed`；量化测试全集 `106 passed`；入口和 Slurm 脚本 `bash -n` 通过。

## 2026-06-05 — Agent failure artifacts remain manifest-verifiable

- 审计失败路径：模拟 `data_agent` 永久失败时，pipeline 仍保持 `complete_with_errors`，写出 `errors/data_agent.json`、`daily_report.md`、`run_audit.json`、artifact manifest、artifact verification 和 readiness。
- 补强 regression：`test_daily_pipeline_records_agent_error_and_continues` 现在直接重算 `daily_report.md`、`run_audit.json`、`errors/data_agent.json` 的 SHA256，要求与 manifest 记录一致，并要求 artifact verification fresh/pass、daily report gate true。
- 失败路径 smoke：error artifact、run audit 和日报都在 manifest 中且 hash 正确；`verification fresh True pass 0`；readiness 仍为 `not_production_ready`，但 `latest_daily_report_is_current_evidence=True`、`artifact_manifest_verification_passed=True`。
- 成功 shell smoke：真实 `bash run_daily.sh` 输出 `SMOKE_RUN_AUDIT_HASH_MATCH True`、`SMOKE_VERIFICATION_FRESH True`、`SMOKE_DAILY_GATE True`、`SMOKE_MANIFEST_VERIFICATION True 0`、`SMOKE_INVOCATION True`。
- 验证：`python -m py_compile agent/*.py` 通过；daily pipeline `10 passed`；entrypoint+self-audit `68 passed`；聚合测试 `79 passed`；量化测试全集 `106 passed`；入口和 Slurm 脚本 `bash -n` 通过。

## 2026-06-05 — Alpha GPU sbatch command aligned in README

- 结论：alpha GPU 回测仍必须通过 Slurm/sbatch 申请 GPU，登录节点只做轻量检查，不能用登录节点 `torch.cuda.is_available()` 代表正式执行环境。
- 文档修正：README 的 alpha GPU 示例从旧的 A022/A024/A025 repair 队列更新为当前 A029 H5 多成本命令：`ALPHA_CANDIDATES='A029' ALPHA_HORIZONS='5' ALPHA_COSTS='5,10,20,30' ALPHA_FAST=0 ALPHA_BACKEND=torch_cuda bash scripts/submit_alpha_gpu_backtest.sh`。
- 当前 Slurm 状态：`squeue -u "$USER"` 无运行或排队作业；最近完成证据仍是 A029 job `29572` 在 A800 `gpu2`，`torch.cuda_available=True`，stderr 为空。
- 验证：`bash -n scripts/submit_alpha_gpu_backtest.sh scripts/alpha_gpu_backtest.sbatch scripts/alpha_gpu_probe.sbatch` 通过。

## 2026-06-05 — Artifact verification latest pointer gate

- 新增 readiness 门禁：`artifact_verification_latest_matches_current_verification` 要求 `artifact_verification_latest.json` 的稳定摘要与当前 run 的 `artifact_verification.json` 一致，包括 run_date、manifest path/generated_at、检查文件数量、缺失/不匹配列表和 skipped files。
- 报告增强：`READINESS_REPORT.json` 的 `artifact_manifest.verification` 现在暴露 latest verification 的 status、generated_at、manifest_generated_at 和是否匹配当前 verification，便于审计 latest pointer 是否漂移。
- Regression：新增 stale latest verification 测试，模拟 verifier 返回当前 pass 结果但 latest pointer 仍指向旧 manifest timestamp，readiness 必须保持 `not_production_ready` 并输出 blocker。
- 验证：`python -m py_compile agent/*.py` 通过；`pytest -q tests/test_quant_self_audit.py` 为 `61 passed`；聚合测试为 `80 passed`；量化测试全集为 `107 passed`；入口和 Slurm 脚本 `bash -n` 通过。

## 2026-06-05 — Failed shell entrypoint evidence is hash-verifiable

- 补强 shell failure regression：`test_run_entrypoint_records_failed_invocation` 现在验证失败入口写出的 `run_daily_invocation_latest.json` SHA256 与 `artifact_manifest_latest.json` 记录一致。
- 同一测试还验证失败路径下 run-local `artifact_verification.json`、`artifact_verification_latest.json` 和 `READINESS_REPORT.json` 都指向最终 manifest `generated_at`，并且 `artifact_verification_latest_matches_current_verification=True`。
- 结论：当 `daily_pipeline.run()` 在 shell entrypoint 内抛出异常时，系统不只记录 error invocation，还会刷新 readiness/manifest/verifier/latest pointer，使无人值守失败日可审计。
- 验证：`python -m py_compile agent/*.py` 通过；`pytest -q tests/test_quant_entrypoint.py` 为 `8 passed`；entrypoint+daily+self-audit 聚合为 `79 passed`；量化测试全集为 `107 passed`；入口和 Slurm 脚本 `bash -n` 通过。

## 2026-06-05 — Artifact verification is a required manifest artifact

- 增强 readiness manifest gate：`artifact_verification.json` 现在是 `REQUIRED_MANIFEST_PATHS`，生产就绪不能缺少 run-local verifier 输出。
- 测试 helper 对齐真实闭环：synthetic production fixtures 现在按 manifest -> verification -> manifest 的顺序生成证据，使 manifest 包含 `artifact_verification.json`，而 verifier 在校验时把它列入 skipped files，避免自输出 hash 循环。
- Regression：daily pipeline 成功和 agent failure 路径均断言 manifest 包含 `artifact_verification.json`，且 `artifact_verification.json.skipped_files` 明确跳过该文件。
- 验证：`python -m py_compile agent/*.py` 通过；daily+self-audit 为 `71 passed`；schedule+entrypoint+daily+self-audit 聚合为 `80 passed`；量化测试全集为 `107 passed`；入口和 Slurm 脚本 `bash -n` 通过。

## 2026-06-05 — Artifact verification must check the current manifest

- 新增 readiness gate：`artifact_manifest_verification_matches_current_manifest` 要求 verifier 输出为 pass、run_date 匹配、manifest_path 指向当前 run 的 `artifact_manifest.json`，且 `manifest_generated_at` 等于当前 manifest 的 `generated_at`。
- 报告增强：`READINESS_REPORT.json.artifact_manifest.verification.matches_current_manifest` 直接暴露该 freshness 判断，避免只看到 `status=pass` 却不知道是否校验了最终 manifest。
- Regression：新增 stale current verifier 测试，模拟 verifier 返回 `status=pass` 但 `manifest_generated_at` 为旧值；readiness 必须保持 `not_production_ready` 并输出 blocker。
- 验证：`python -m py_compile agent/*.py` 通过；self-audit/readiness 为 `62 passed`；schedule+entrypoint+daily+self-audit 聚合为 `81 passed`；量化测试全集为 `108 passed`；入口和 Slurm 脚本 `bash -n` 通过。

## 2026-06-05 — Readiness Markdown exposes verifier freshness evidence

- 增强 `READINESS_REPORT.md`：Evidence 章节现在写出 `artifact manifest verification matches current manifest`、`artifact verification latest matches current verification` 和 `artifact verification manifest generated at`。
- 目的：长期人工巡检不用只打开 JSON 才能确认 verifier 是否校验最终 manifest、latest pointer 是否对齐当前 run-local verification。
- Regression：production-ready fixture 现在读取 `READINESS_REPORT.md` 并要求上述三行出现，其中两个布尔值必须为 `True`。
- 验证：`python -m py_compile agent/*.py` 通过；self-audit/readiness 为 `62 passed`；schedule+entrypoint+daily+self-audit 聚合为 `81 passed`；量化测试全集为 `108 passed`；入口和 Slurm 脚本 `bash -n` 通过。

## 2026-06-05 — Readiness Markdown must match current JSON

- 新增 readiness gate：`readiness_markdown_matches_current_json`，`run()` 写出 `READINESS_REPORT.md` 后会读取 Markdown，并核对当前 `READINESS_REPORT.json` 的 run date、status、score、每个 check、blocker、artifact verifier freshness、run_daily invocation 和 schedule 关键证据行。
- 报告增强：`READINESS_REPORT.json.readiness_markdown` 现在记录 Markdown 是否存在、路径、是否匹配当前 JSON 和 required line count；production-ready fixture 要求该 gate 为 true。
- Regression：新增 `test_readiness_blocks_mismatched_markdown_renderer`，monkeypatch Markdown renderer 返回旧 run date/status，readiness 必须降级为 `not_production_ready` 并输出 `READINESS_REPORT.md does not match current READINESS_REPORT.json` blocker。
- 验证：`python -m py_compile agent/*.py` 通过；`pytest -q tests/test_quant_self_audit.py -q` 为 `63 passed`；`pytest -q tests/test_quant_schedule.py tests/test_quant_entrypoint.py tests/test_quant_daily_pipeline.py tests/test_quant_self_audit.py` 为 `82 passed`；agent/backtest 相关测试 `27 passed`；入口和 Slurm 脚本 `bash -n` 通过。

## 2026-06-05 — Repository deliverables readiness gate

- 新增 readiness gate：`repository_deliverables_present`，要求仓库交付物 `README.md`、可执行 `run_daily.sh`、关键 `agent/*.py`、`backtest_engine/*.py` 存在，并要求当前配置的 `reports/`、`knowledge_base/`、`factor_library/` 目录存在且可写。
- 报告增强：`READINESS_REPORT.json.repository_deliverables` 记录 repo root、required files/directories、missing files/directories、unwritable directories、`run_daily_executable` 和 `all_present`；Markdown Evidence 同步显示缺失路径。
- Regression：新增 `test_readiness_blocks_missing_repository_deliverable`，构造缺少 `README.md` 的临时 repo root，365 天其它生产证据齐全时仍必须保持 `not_production_ready`。
- 验证：`python -m py_compile agent/*.py` 通过；`pytest -q tests/test_quant_self_audit.py -q` 为 `64 passed`；`pytest -q tests/test_quant_schedule.py tests/test_quant_entrypoint.py tests/test_quant_daily_pipeline.py tests/test_quant_self_audit.py` 为 `83 passed`；agent/backtest 相关测试 `27 passed`；入口和 Slurm 脚本 `bash -n` 通过。

## 2026-06-05 — Live source required-kind coverage gate

- 收紧 production source evidence：market live source 现在必须覆盖 `announcement`、`industry`、`news`、`policy`、`research_context`；research live source 必须覆盖 `community`、`factor_library`、`paper`。不能只靠 `missing_kinds=[]` 和 `coverage_ratio=1.0` 通过。
- `READINESS_REPORT.json.source_snapshot_evidence` 和 `latest_production_evidence` 现在暴露 required market/research source kinds，方便审计 365 天 live source 证据按哪些来源种类判定。
- Regression：新增 `test_readiness_blocks_live_sources_without_required_kind_coverage`，模拟 market 只覆盖 `news`、research 只覆盖 `paper` 且 `missing_kinds=[]`，readiness 仍必须保持 `not_production_ready`。
- 测试 fixture 同步：production-ready fixture 现在生成完整 market/research 多 kind source status、source quality、source snapshots、run_history/self_audit/research_log/daily_report 计数。
- 验证：`python -m py_compile agent/*.py` 通过；`pytest -q tests/test_quant_self_audit.py -q` 为 `65 passed`；`pytest -q tests/test_quant_schedule.py tests/test_quant_entrypoint.py tests/test_quant_daily_pipeline.py tests/test_quant_self_audit.py` 为 `84 passed`；agent/source/backtest 子集 `27 passed`；入口和 Slurm 脚本 `bash -n` 通过。

## 2026-06-05 — run_daily audited-entrypoint contract gate

- 收紧 repository deliverables gate：`run_daily.sh` 不仅要存在且可执行，还必须设置 `QUANT_RUN_DAILY_SH=1`、`QUANT_RUN_DAILY_SCRIPT`、`QUANT_RUN_DAILY_COMMAND`，并调用 `python -m agent.run_entrypoint`。
- 目的：防止入口脚本被改成直接 `python -m agent.daily_pipeline`，绕过 shell-level invocation JSONL、failure refresh、final readiness/manifest 证据链。
- 报告增强：`READINESS_REPORT.json.repository_deliverables.run_daily_uses_audited_entrypoint` 和 Markdown Evidence 现在显示入口脚本是否使用审计入口。
- Regression：新增 `test_readiness_blocks_run_daily_without_audited_entrypoint`，构造可执行但直接调用 `agent.daily_pipeline` 的 `run_daily.sh`，365 天其它证据齐全时仍必须保持 `not_production_ready`。
- 验证：`python -m py_compile agent/*.py` 通过；`pytest -q tests/test_quant_self_audit.py -q` 为 `66 passed`；`pytest -q tests/test_quant_schedule.py tests/test_quant_entrypoint.py tests/test_quant_daily_pipeline.py tests/test_quant_self_audit.py` 为 `85 passed`；entrypoint/agent/backtest 子集 `35 passed`；入口和 Slurm 脚本 `bash -n` 通过。

## 2026-06-05 — A029 GPU rerun through sbatch allocation job 29573

- 结论：GPU alpha 回测已按用户要求通过 Slurm 申请资源执行；没有在登录节点直接运行 CUDA，也没有使用 CPU fallback。
- 提交命令：`ALPHA_CANDIDATES='A029' ALPHA_HORIZONS='5' ALPHA_COSTS='5,10,20,30' ALPHA_FAST=0 ALPHA_BACKEND=torch_cuda bash scripts/submit_alpha_gpu_backtest.sh`。
- Slurm 证据：job `29573` 在 A800 分区 `gpu2` 完成；stdout 记录 `CUDA_VISIBLE_DEVICES=0`、`torch 2.12.0+cu126`、`torch.cuda_available=True`、device `NVIDIA A800-SXM4-80GB`；stderr 为 0 字节。
- A029 H5 结果：test RankIC `0.044898`；5/10/20/30bps long-short annual net 分别为 `0.036556 / 0.022270 / -0.006300 / -0.034871`；long-only annual net 分别为 `0.181849 / 0.174633 / 0.160203 / 0.145772`；long-only Sharpe 分别为 `1.256 / 1.206 / 1.106 / 1.007`。
- 决策：GPU 路径不是 blocker；A029 仍是 `repair`，因为高成本 long-short 转负，且仍需修复 delayed-exit、真实 H>1 持仓账本和 size/industry exposure diagnostics。

## 2026-06-05 — README audited-readiness deliverable gate

- 收紧 repository deliverables gate：`README.md` 不再只要求存在，还必须写明 `bash run_daily.sh` 主入口、`reports/run_daily_invocations.jsonl` shell-level 审计证据、`365 consecutive unique dates` 生产就绪语义，以及 `not_production_ready` 未满足状态。
- 报告增强：`READINESS_REPORT.json.repository_deliverables` 现在暴露 `required_readme_snippets`、`missing_readme_snippets` 和 `readme_documents_audited_readiness`；Markdown Evidence 同步显示 README 文档门禁。
- Regression：新增 `test_readiness_blocks_readme_without_audited_readiness_docs`，在 365 天其它生产证据齐全但 README 只有弱说明时仍必须保持 `not_production_ready`。
- 验证：`python -m py_compile agent/*.py` 通过；`pytest -q tests/test_quant_self_audit.py -q` 为 `67 passed`；`pytest -q tests/test_quant_schedule.py tests/test_quant_entrypoint.py tests/test_quant_daily_pipeline.py tests/test_quant_self_audit.py` 为 `86 passed`；`bash -n run_daily.sh scripts/submit_alpha_gpu_backtest.sh scripts/alpha_gpu_backtest.sbatch scripts/alpha_gpu_probe.sbatch` 通过。
- 入口 smoke：临时目录 `QUANT_OFFLINE=1 QUANT_RUN_DATE=20260605 ... bash run_daily.sh` 输出 `SMOKE not_production_ready True True True False False success 0`，证明 README 门禁为真、shell invocation 成功、单日离线 smoke 仍不会误判为 production-ready。

## 2026-06-05 — run_daily invocation bound to repository script

- 收紧 shell invocation gate：成功的 `run_daily` invocation 不再只检查 `entrypoint_script` 以 `run_daily.sh` 结尾，还必须解析为当前仓库 `_repository_root()/run_daily.sh` 的绝对路径。
- 报告增强：`READINESS_REPORT.json.run_daily_invocation.expected_entrypoint_script` 和 Markdown Evidence 暴露期望入口路径，方便审计 invocation JSONL 绑定的是哪个仓库脚本。
- Regression：新增 `test_readiness_blocks_invocation_from_different_run_daily_script`，构造另一个目录下的同名 `run_daily.sh`，即使 365 天 run history/source/data/knowledge 证据齐全且 invocation 其它字段成功，仍不能计入当前仓库的 365 天 shell-level 证据。
- 验证：`python -m py_compile agent/*.py` 通过；`pytest -q tests/test_quant_self_audit.py -q` 为 `68 passed`；`pytest -q tests/test_quant_schedule.py tests/test_quant_entrypoint.py tests/test_quant_daily_pipeline.py tests/test_quant_self_audit.py` 为 `87 passed`；入口和 Slurm 脚本 `bash -n` 通过。
- 入口 smoke：临时目录 `QUANT_OFFLINE=1 QUANT_RUN_DATE=20260605 ... bash run_daily.sh` 输出 `SMOKE not_production_ready True /home/lcc17/dl/run_daily.sh /home/lcc17/dl/run_daily.sh False`，证明真实入口路径通过绑定，单日证据仍不满足 365 天完成条件。

## 2026-06-05 — 365 successful runs require complete agent roster

- 收紧 365-day successful audited run 定义：`has_365_successful_runs` 现在要求每条 run history 不仅 `pipeline_status=complete`、`self_audit_status=pass`，还必须 `self_audit_score>=0.9`，且 `agent_status` 覆盖全部 `REQUIRED_AGENT_NAMES` 并全为 `ok`。
- `has_365_production_evidence_runs` 复用该 audited-run 定义，避免 365 天 live source / real data 证据建立在缺少某个 agent 的 run_history 上。
- Regression：新增 `test_readiness_blocks_365_successful_runs_with_missing_agent_roster`，构造 365 条缺 `artifact_manifest` agent 的 complete/pass run_history，再追加当前完整 latest run；latest agent roster 通过，但 365 successful/production evidence 仍必须失败。
- 验证：`python -m py_compile agent/*.py` 通过；`pytest -q tests/test_quant_self_audit.py -q` 为 `69 passed`；`pytest -q tests/test_quant_schedule.py tests/test_quant_entrypoint.py tests/test_quant_daily_pipeline.py tests/test_quant_self_audit.py` 为 `88 passed`；入口和 Slurm 脚本 `bash -n` 通过。
- 入口 smoke：临时目录 `QUANT_OFFLINE=1 QUANT_RUN_DATE=20260605 ... bash run_daily.sh` 输出 `SMOKE not_production_ready False True 1 True`，证明当前 run 有完整 agent roster，但单日 audited run 不能满足 365 天门槛。

## 2026-06-05 — 365 successful runs require recorded timestamps

- 收紧 365-day successful audited run 定义：每条 run history 现在必须有合法 `YYYYMMDD` run_date 和 ISO `recorded_at`，否则不能计入 `has_365_successful_runs`。
- 目的：防止只拼接 `pipeline_status=complete`、`self_audit_status=pass` 和 agent 状态的历史 JSONL 被当作长期无人值守运行证据；每条长期记录必须有可审计写入时间。
- Regression：新增 `test_readiness_blocks_365_successful_runs_without_recorded_at`，构造 365 条缺 `recorded_at` 的完整生产记录，再追加当前完整 latest run；365 successful/production gates 仍必须失败。
- 验证：`python -m py_compile agent/*.py` 通过；`pytest -q tests/test_quant_self_audit.py -q` 为 `70 passed`；`pytest -q tests/test_quant_schedule.py tests/test_quant_entrypoint.py tests/test_quant_daily_pipeline.py tests/test_quant_self_audit.py` 为 `89 passed`；入口和 Slurm 脚本 `bash -n` 通过。
- 入口 smoke：临时目录 `QUANT_OFFLINE=1 QUANT_RUN_DATE=20260605 ... bash run_daily.sh` 输出 `SMOKE not_production_ready False 1 True 2026-06-05T01:49:52.889231+00:00`，证明真实 run_history_latest 写入 `recorded_at`，但单日证据仍不满足 365 天门槛。

## 2026-06-05 — A029 GPU rerun through sbatch allocation job 29576

- 结论：GPU alpha 回测必须通过 Slurm 申请资源；本次 A029 H5 重新使用 `sbatch` 分配 A800 GPU 执行，未在登录节点直接运行 CUDA。
- 提交命令：`ALPHA_CANDIDATES='A029' ALPHA_HORIZONS='5' ALPHA_COSTS='5,10,20,30' ALPHA_FAST=0 ALPHA_BACKEND=torch_cuda bash scripts/submit_alpha_gpu_backtest.sh`。
- Slurm 证据：job `29576` 在 A800 分区 `gpu2` 完成；stdout 记录 `CUDA_VISIBLE_DEVICES=0`、`torch 2.12.0+cu126`、`torch.cuda_available=True`、device `NVIDIA A800-SXM4-80GB`；stderr 为 0 字节。
- A029 H5 结果：test RankIC `0.044898`；5/10/20/30bps long-short annual net 分别为 `0.036556 / 0.022270 / -0.006300 / -0.034871`；long-only annual net 分别为 `0.181849 / 0.174633 / 0.160203 / 0.145772`；long-only Sharpe 分别为 `1.256 / 1.206 / 1.106 / 1.007`。
- 决策：GPU 路径已验证，不是 A029 未 promote 的原因；A029 仍为 `repair`，因为高成本 long-short 转负，且 delayed-exit、真实 H>1 持仓账本、size/industry exposure diagnostics 仍需修复。

## 2026-06-05 — Alpha GPU launcher accepts Slurm allocation overrides

- 结论：正式 alpha GPU 回测入口继续固定为 Slurm 申请路径，不能在登录节点直接跑 CUDA 或依赖 CPU fallback。
- 修复：`scripts/submit_alpha_gpu_backtest.sh` 现在支持 `SLURM_PARTITION`、`SLURM_QOS`、`SLURM_GPUS`、`SLURM_CPUS_PER_TASK`、`SLURM_TIME` 和可选 `SLURM_ACCOUNT`，并把这些参数显式传给 `sbatch`。
- 用法：例如 `SLURM_PARTITION=A800 SLURM_QOS=normal SLURM_GPUS=1 ALPHA_CANDIDATES='A029' ALPHA_HORIZONS='5' ALPHA_COSTS='5,10,20,30' ALPHA_BACKEND=torch_cuda bash scripts/submit_alpha_gpu_backtest.sh`。

## 2026-06-05 — 365-day proof timestamps must match run dates

- 收紧 readiness gate：successful audited run 现在要求 `run_history.recorded_at` 的日期等于该记录的 `run_date`；successful `run_daily` invocation 现在要求 `started_at`/`finished_at` 都落在 invocation `run_date` 且 `finished_at >= started_at`。
- 报告增强：新增 checks `latest_run_history_recorded_at_matches_run_date` 和 `run_daily_invocation_timestamps_match_run_date`；JSON/Markdown Evidence 同步暴露最新 run_history 和 invocation 的时间绑定状态。
- Regression：新增 `test_readiness_blocks_run_history_recorded_at_date_mismatch` 和 `test_readiness_blocks_successful_invocation_with_cross_date_timestamps`，防止 365 条记录用错日时间戳或跨日 invocation 被计为无人值守生产证明。
- 验证：`python -m py_compile agent/*.py` 通过；`pytest -q tests/test_quant_self_audit.py -q` 通过；`pytest -q tests/test_quant_schedule.py tests/test_quant_entrypoint.py tests/test_quant_daily_pipeline.py tests/test_quant_self_audit.py` 为 `91 passed`；入口和 Slurm 脚本 `bash -n` 通过。
- 入口 smoke：临时目录 `QUANT_OFFLINE=1 QUANT_RUN_DATE=20260605 ... bash run_daily.sh` 输出 `SMOKE not_production_ready True True 1 1`，证明真实入口写出的时间绑定门禁为真，但单日离线运行仍不会误判为 production-ready。

## 2026-06-05 — Source snapshots require replayable cached items

- 收紧 production-grade source snapshot evidence：`source_snapshots.jsonl` 中每条 production snapshot 不再只信任 `source_status.items` 和 `item_count`，还要求 `items` 缓存数量等于 `min(item_count, 50)`，每条 cached item 有 `https://` URL，kind 必须来自 `source_status`；market item 必须有 `title`，research item 必须有 `text`。
- 目的：365 天 source evidence 不能只写“某来源抓到 N 条”但不保存可回放 item 摘要；长期审计至少要能抽查每日抓取内容的 kind、URL 和摘要字段。
- Regression：新增 `test_readiness_blocks_source_snapshot_without_cached_items`，在 365 天其它 production evidence 齐全时只清空一天 market snapshot 的 `items`，该日期不再计入 production-grade source snapshot dates。
- 验证：`python -m py_compile agent/*.py` 通过；`pytest -q tests/test_quant_self_audit.py -q` 通过；`pytest -q tests/test_quant_schedule.py tests/test_quant_entrypoint.py tests/test_quant_daily_pipeline.py tests/test_quant_self_audit.py` 为 `92 passed`；入口和 Slurm 脚本 `bash -n` 通过。
- 入口 smoke：临时目录 `QUANT_OFFLINE=1 QUANT_RUN_DATE=20260605 ... bash run_daily.sh` 输出 `SMOKE not_production_ready True 1 1 0 0`，证明当前 source snapshot 文件与当前输出匹配；离线单日仍不会误判为 production-ready。

## 2026-06-05 — Readiness blocks candidates that repeat historical failed formulas

- 新增 readiness gate：`latest_candidate_factors_avoid_historical_failures`，从历史 `factor_database` kill 记录和历史/无日期 `failure_memory.jsonl` 构造 failed identity keys，检查最新 `candidate_factors.json` 是否重复已失败方案。
- 语义边界：同一天刚生成、回测、再被 critic kill 的候选不会反向阻断当天 readiness；门禁只阻断历史失败记忆或无日期失败记忆，符合“禁止重复研究已失败方案”的长期约束。
- 报告增强：`factor_library_evidence` 新增 `historical_failed_key_count`、`candidate_failed_memory_matches` 和 `candidates_avoid_historical_failures`，方便审计命中的 factor id / formula key。
- Regression：新增 `test_readiness_blocks_candidate_repeating_historical_failed_formula`，在其它 365 天 production evidence 齐全时写入一条 `20260603` 历史 failed formula key；最新候选重复该 key 时 readiness 保持 `not_production_ready`。
- 验证：`python -m py_compile agent/*.py` 通过；`pytest -q tests/test_quant_self_audit.py -q` 通过；`pytest -q tests/test_quant_schedule.py tests/test_quant_entrypoint.py tests/test_quant_daily_pipeline.py tests/test_quant_self_audit.py` 为 `93 passed`；入口和 Slurm 脚本 `bash -n` 通过。
- 入口 smoke：临时目录 `QUANT_OFFLINE=1 QUANT_RUN_DATE=20260605 ... bash run_daily.sh` 输出 `SMOKE not_production_ready True 0 0`，证明正常单日运行不会被同日失败候选误拦，且单日仍不会误判为 production-ready。

## 2026-06-05 — Data artifact evidence is date-bound to dataset manifest

- 收紧 production-grade data artifact evidence：`data_health.jsonl` 的 row run_date、`dataset_manifest.run_date` 和 `data_health.run_date` 必须一致；`dataset_manifest.dataset_path` 必须指向对应 `daily_logs/<run_date>/daily_dataset.parquet`；`data_health.date_min/date_max` 必须是合法日期且顺序有效。
- 目的：365 天数据证据不能只靠一条 JSONL 记录的外层 `run_date`，还必须证明该记录内部 manifest/health 和实际 daily log 路径绑定到同一天。
- Regression：新增 `test_readiness_blocks_data_artifact_date_mismatch`，在其它 production evidence 齐全时只篡改第一天 `dataset_manifest.run_date`，该日期不再计入 production-grade data artifact dates。
- 验证：`python -m py_compile agent/*.py` 通过；`pytest -q tests/test_quant_self_audit.py -q` 通过；`pytest -q tests/test_quant_schedule.py tests/test_quant_entrypoint.py tests/test_quant_daily_pipeline.py tests/test_quant_self_audit.py` 为 `94 passed`；入口和 Slurm 脚本 `bash -n` 通过。
- 入口 smoke：临时目录 `QUANT_OFFLINE=1 QUANT_RUN_DATE=20260605 ... bash run_daily.sh` 输出 `SMOKE not_production_ready True False 20260605 20260605 True`；latest data health 与当前输出匹配，manifest run_date/path 绑定正确，离线 synthetic 数据仍不计 production evidence。

## 2026-06-05 — Knowledge-save evidence requires recorded timestamps

- 增强 Knowledge Base Agent：每条 `research_log.jsonl` / `research_log_latest.json` 现在写入 UTC `recorded_at`。
- 收紧 readiness gate：完整 knowledge save 不再只看 `run_date`、`pipeline.run_quality=complete` 和 `factor_database_write`，还要求 `recorded_at` 是合法 ISO datetime 且日期等于该条 `run_date`。
- 目的：365 天知识库保存证据不能只靠手写 run_date 和 saved ids；每条长期研究日志必须有可审计写入时间。
- Regression：新增 `test_readiness_blocks_knowledge_saves_without_recorded_at`，365 天其它 production evidence 齐全时删除一天 research log 的 `recorded_at`，该日期不再计入 complete knowledge-save dates。
- 验证：`python -m py_compile agent/*.py` 通过；`pytest -q tests/test_quant_self_audit.py -q` 通过；`pytest -q tests/test_quant_schedule.py tests/test_quant_entrypoint.py tests/test_quant_daily_pipeline.py tests/test_quant_self_audit.py` 为 `95 passed`；入口和 Slurm 脚本 `bash -n` 通过。
- 入口 smoke：临时目录 `QUANT_OFFLINE=1 QUANT_RUN_DATE=20260605 ... bash run_daily.sh` 输出 `SMOKE not_production_ready 20260605 True False 1`，证明真实 Knowledge Base 写出 `recorded_at`，单日 knowledge save 可计数但 365 门槛仍未满足。

## 2026-06-05 — Data artifact evidence requires recorded timestamps

- 增强 Data Agent：`knowledge_base/data_health.jsonl` 和 `data_health_latest.json` 中每条 data artifact record 现在写入 UTC `recorded_at`。
- 收紧 readiness gate：production-grade data artifact evidence 不再只看 row/manifest/health 的 run_date 绑定，还要求 `recorded_at` 日期等于该条 `run_date`。
- 目的：365 天真实数据证据不能由旧 `data_health.jsonl` 记录拼接冒充；每条长期数据产物记录必须有同日写入时间证据。
- Regression：新增 `test_readiness_blocks_data_artifact_without_recorded_at`，365 天其它 production evidence 齐全时删除一天 data artifact 的 `recorded_at`，该日期不再计入 production-grade data artifact dates。
- 验证：`python -m py_compile agent/*.py` 通过；`pytest -q tests/test_quant_self_audit.py -q` 通过；`pytest -q tests/test_quant_schedule.py tests/test_quant_entrypoint.py tests/test_quant_daily_pipeline.py tests/test_quant_self_audit.py` 为 `96 passed`；入口和 Slurm 脚本 `bash -n` 通过。
- 入口 smoke：临时目录 `QUANT_OFFLINE=1 QUANT_RUN_DATE=20260605 ... bash run_daily.sh` 输出 `SMOKE not_production_ready success 0 20260605 True True False False`，证明真实 Data Agent 写出 `recorded_at`；离线 synthetic 数据仍不计 production evidence，365 天门槛未被误放行。

## 2026-06-05 — Source snapshot evidence requires same-day timestamps

- 收紧 production-grade source snapshot evidence：每条 `source_snapshots.jsonl` 记录的 `snapshot_written_at` 日期必须等于该条 `run_date`；每个 source status 的 `fetched_at` 也必须落在同一天。
- 目的：365 天 live-source 证据不能由旧联网快照复制拼接；market/research 逐源快照必须证明是在对应运行日抓取和写入。
- Regression：新增 `test_readiness_blocks_source_snapshot_timestamp_date_mismatch`，365 天其它 production evidence 齐全时只把一天 market snapshot 的 `snapshot_written_at` 改成次日，该日期不再计入 production-grade source snapshot dates。
- 验证：`python -m py_compile agent/*.py` 通过；`pytest -q tests/test_quant_self_audit.py -q` 通过；`pytest -q tests/test_quant_schedule.py tests/test_quant_entrypoint.py tests/test_quant_daily_pipeline.py tests/test_quant_self_audit.py` 为 `97 passed`；入口和 Slurm 脚本 `bash -n` 通过。
- 入口 smoke：临时目录 `QUANT_OFFLINE=1 QUANT_RUN_DATE=20260605 ... bash run_daily.sh` 输出 `SMOKE not_production_ready success 0 20260605 True 2026-06-05 True False`，证明真实 source snapshot 写入同日时间；离线单日仍不满足 365 天 source evidence。

## 2026-06-05 — Current source snapshots must replay current items

- 收紧 current-output match gate：`latest_source_snapshots_match_current_outputs` 现在不只比较 source status、source quality 和 item count，还要求 run-dir snapshot 与 JSONL 同日记录的 `items` 等于当前 `daily_events.json.events[:50]` / `research_ideas.json.research_context[:50]`，并要求 `snapshot_written_at` 日期等于当前 run date。
- 目的：当前运行的 source snapshot 不能用相同计数但不同内容的旧事件/研究上下文冒充；日报和长期源审计必须能回放当前输入。
- Regression：新增 `test_readiness_blocks_source_snapshot_items_mismatch`，只改当前 run-dir market snapshot 第一条 title、保持 item_count 不变，readiness 仍阻断 `latest_source_snapshots_match_current_outputs`。
- 验证：`python -m py_compile agent/*.py` 通过；`pytest -q tests/test_quant_self_audit.py -q` 通过；`pytest -q tests/test_quant_schedule.py tests/test_quant_entrypoint.py tests/test_quant_daily_pipeline.py tests/test_quant_self_audit.py` 为 `98 passed`；入口和 Slurm 脚本 `bash -n` 通过。
- 入口 smoke：临时目录 `QUANT_OFFLINE=1 QUANT_RUN_DATE=20260605 ... bash run_daily.sh` 输出 `SMOKE not_production_ready success 0 True 1 1 True False`，证明真实 market snapshot items 与当前 events 完全匹配；单日仍不满足 365 天门槛。

## 2026-06-05 — Backtest result directory must match payload exactly

- 收紧 backtest evidence：`latest_backtest_result_files_match_payload` 现在要求 `reports/daily_logs/<run_date>/backtest_results/*.json` 文件集合等于当前 `backtest_results.json.results[].factor_id`，不能有额外旧因子文件残留。
- 目的：当前回测证据不能只验证 payload 中列出的因子文件；历史残留的 per-factor JSON 不应被 artifact manifest/hash 记录成当前运行输出。
- Regression：新增 `test_readiness_blocks_extra_stale_backtest_result_file`，当前 payload 只有 `F1` 时额外写入 `backtest_results/STALE.json`，readiness 必须阻断。
- 验证：`python -m py_compile agent/*.py` 通过；`pytest -q tests/test_quant_self_audit.py -q` 通过；`pytest -q tests/test_quant_schedule.py tests/test_quant_entrypoint.py tests/test_quant_daily_pipeline.py tests/test_quant_self_audit.py` 为 `99 passed`；入口和 Slurm 脚本 `bash -n` 通过。
- 入口 smoke：临时目录 `QUANT_OFFLINE=1 QUANT_RUN_DATE=20260605 ... bash run_daily.sh` 输出 `SMOKE not_production_ready success 0 True 5 True False`，证明真实回测 result ids 与 per-factor 文件集合完全一致；单日仍不满足 365 天门槛。

## 2026-06-05 — Candidate and next-generation directories must match payloads exactly

- 收紧 factor artifact evidence：`latest_candidate_factor_files_match_payload` 和 `latest_next_generation_files_match_payload` 现在要求 per-factor 目录下 `*.json` 文件集合分别等于当前 payload 中的 candidate / next-generation factor ids，不能有额外旧因子文件残留。
- 目的：当前候选生成和下一代修复候选证据不能只验证 payload 中列出的文件；历史残留 JSON 不应被 artifact manifest/hash 误纳入当前运行输出。
- Regression：新增 `test_readiness_blocks_extra_stale_candidate_factor_file` 和 `test_readiness_blocks_extra_stale_next_generation_file`，分别额外写入 `candidate_factors/STALE.json` 与 `next_generation_factors/STALE_NEXT.json` 后，readiness 必须阻断。
- GPU/Slurm 约束：日常入口保持 CPU/离线可跑；需要 GPU 的 alpha 回测通过 `scripts/submit_alpha_gpu_backtest.sh` / `scripts/alpha_gpu_backtest.sbatch` 申请 Slurm 资源，不在登录节点直接启 CUDA。
- 验证：`python -m py_compile agent/*.py` 通过；`pytest -q tests/test_quant_self_audit.py -q` 通过；`pytest -q tests/test_quant_schedule.py tests/test_quant_entrypoint.py tests/test_quant_daily_pipeline.py tests/test_quant_self_audit.py` 为 `101 passed`；入口和 Slurm 脚本 `bash -n run_daily.sh scripts/submit_alpha_gpu_backtest.sh scripts/alpha_gpu_backtest.sbatch scripts/alpha_gpu_probe.sbatch` 通过。
- 入口 smoke：临时目录 `QUANT_OFFLINE=1 QUANT_RUN_DATE=20260605 ... bash run_daily.sh` 输出 `SMOKE not_production_ready success 0 True True True True False`，证明真实 candidate / next-generation ids 与 per-factor 文件集合完全一致；单日仍不满足 365 天生产门槛。

## 2026-06-05 — A029 GPU fast rerun through Slurm A800

- 提交方式：`ALPHA_CANDIDATES=A029 ALPHA_HORIZONS=5 ALPHA_COSTS=5,10,20,30 ALPHA_FAST=1 SLURM_PARTITION=A800 SLURM_TIME=00:30:00 bash scripts/submit_alpha_gpu_backtest.sh`，Slurm job `29596`。
- GPU 证据：作业运行在 `gpu2`，`CUDA_VISIBLE_DEVICES=0`，PyTorch `2.12.0+cu126`，`cuda_available=True`，设备 `NVIDIA A800-SXM4-80GB`。
- 结果：A029 test RankIC `0.04489848307429551`；cost 5/10/20/30 bps 下 long-short net ann return 分别为 `0.03655576158999612` / `0.02227042891378345` / `-0.006300236438641839` / `-0.03487090179106713`；long-only net ann return 分别为 `0.1818485618176095` / `0.17463330825564882` / `0.16020280113172758` / `0.14577229400780628`。
- 结论：A029 有正 RankIC 和 long-only 成本后收益，但 long-short 对成本敏感且高成本转负；维持 `repair` / 组合改进方向，不作为 promote 证据。

## 2026-06-05 — Same-day factor database records must match current backtests exactly

- 收紧 Knowledge Base evidence：`latest_factor_database_matches_backtests` 现在要求 `knowledge_base/factor_database/factors.json` 中当天 `run_date` 的 factor id 集合等于当前 `backtest_results.json.results[].factor_id`，不能混入额外 same-day 因子记录。
- 目的：长期因子库不能只证明“当前回测结果已保存”，还必须证明当天知识库没有夹带旧候选或手写因子，避免污染每日研究闭环和 365 天保存证据。
- Regression：新增 `test_readiness_blocks_extra_same_day_factor_database_record`，在 production-ready fixture 中额外追加 `STALE_SAME_DAY` 后，readiness 必须阻断 `latest_factor_database_matches_backtests`；evidence 暴露 `same_day_factor_ids` 便于定位。
- 验证：`python -m py_compile agent/*.py` 通过；定向测试 `2 passed`；`pytest -q tests/test_quant_self_audit.py -q` 通过；`pytest -q tests/test_quant_schedule.py tests/test_quant_entrypoint.py tests/test_quant_daily_pipeline.py tests/test_quant_self_audit.py` 为 `102 passed`；入口和 Slurm 脚本 `bash -n` 通过。
- 入口 smoke：临时目录 `QUANT_OFFLINE=1 QUANT_RUN_DATE=20260605 ... bash run_daily.sh` 输出 `SMOKE not_production_ready success 0 True True 5 False`，证明真实 factor database 当天 ids 与 backtest ids 完全一致；单日仍不满足 365 天生产门槛。

## 2026-06-05 — Same-day failure memory must match killed factors exactly

- 收紧 failure-memory evidence：`latest_killed_factors_have_failure_memory` 现在要求当天 `failure_memory.jsonl` 的 factor ids 与当前 `critique.json` 中 `decision=kill` 的 factor ids 完全一致，不能缺失，也不能混入额外 same-day 失败记录。
- 目的：长期失败经验不能只证明“每个 kill 都有记录”，还必须证明当天失败记忆没有夹带旧候选或手写失败项，避免后续 factor design / evolution 错误跳过未实际失败的研究方向。
- Regression：新增 `test_readiness_blocks_extra_same_day_failure_memory_record`，在 production-ready fixture 中额外追加 `STALE_FAILURE` 后，readiness 必须阻断 `latest_killed_factors_have_failure_memory`；原有 missing/detail/stale-next-actions 负例继续覆盖。
- 验证：`python -m py_compile agent/*.py` 通过；定向测试 `4 passed`；`pytest -q tests/test_quant_self_audit.py -q` 通过；`pytest -q tests/test_quant_schedule.py tests/test_quant_entrypoint.py tests/test_quant_daily_pipeline.py tests/test_quant_self_audit.py` 为 `103 passed`；入口和 Slurm 脚本 `bash -n` 通过。
- 入口 smoke：临时目录 `QUANT_OFFLINE=1 QUANT_RUN_DATE=20260605 ... bash run_daily.sh` 输出 `SMOKE not_production_ready success 0 True True ['F_MF_EXHAUST_5', 'F_VOL_REV_5', 'F_VWAP_REV_5'] False`，证明真实 killed ids 与 same-day failure memory ids 完全一致；单日仍不满足 365 天生产门槛。

## 2026-06-05 — Research log critic summary must match current critique

- 收紧 research log evidence：`latest_research_log_matches_current_outputs` 现在不仅核对 `critique_count`，还要求 `research_log_latest.json.critic.promoted`、`critic.killed`、`critic.issue_counts` 与当前 `critique.json` 完全一致；同时核对 backtest summary 的 `promoted_raw` / `killed_raw`。
- 目的：长期研究日志不能用相同数量的审稿结果掩盖 promote/kill 结论或失败原因漂移；日报复盘和后续 evolution/failure-memory 判断必须基于真实审稿摘要。
- Regression：新增 `test_readiness_blocks_research_log_critic_summary_mismatch`，保持 critique count 不变但把 research log 的 killed/promoted/issue_counts 改错，readiness 必须阻断 `latest_research_log_matches_current_outputs`。
- 验证：`python -m py_compile agent/*.py` 通过；定向测试 `4 passed`；`pytest -q tests/test_quant_self_audit.py -q` 通过；`pytest -q tests/test_quant_schedule.py tests/test_quant_entrypoint.py tests/test_quant_daily_pipeline.py tests/test_quant_self_audit.py` 为 `104 passed`；入口和 Slurm 脚本 `bash -n` 通过。
- 入口 smoke：临时目录 `QUANT_OFFLINE=1 QUANT_RUN_DATE=20260605 ... bash run_daily.sh` 输出 `SMOKE not_production_ready success 0 True True {'promoted': 2, 'killed': 3, 'issue_counts': {'insufficient_rankic_sample': 1, 'negative_long_short_diagnostic': 3, 'non_positive_rankic': 2, 'unstable_rankic': 3}} False`，证明真实 research log critic summary 与 critique 输出一致；单日仍不满足 365 天生产门槛。

## 2026-06-05 — A029 delayed-exit repair rerun through Slurm job 29601

- 修复：`alpha-stage/scripts/alpha_backtest.py` 新增 `add_delayed_exit_returns()`，计划退出日若卖出受阻则最多顺延 `ALPHA_MAX_EXIT_DELAY_DAYS=10` 个交易日寻找下一可卖开盘；panel cache 升级到 v4，避免复用旧收益。
- GPU/Slurm 证据：用 `SLURM_PARTITION=A800 SLURM_QOS=normal SLURM_GPUS=1 SLURM_CPUS_PER_TASK=8 SLURM_TIME=02:00:00 ALPHA_CANDIDATES='A029' ALPHA_HORIZONS='5' ALPHA_COSTS='5,10,20,30' ALPHA_FAST=0 ALPHA_BACKEND=torch_cuda bash scripts/submit_alpha_gpu_backtest.sh` 提交 job `29601`；作业在 `gpu2` A800 上运行，`torch.cuda_available=True`。
- 结果：A029 H5 delayed-exit 后 Test RankIC=`0.04537045658113058`；long-short 5/10/20/30bps annual net=`0.04919740156922802` / `0.0349640913645631` / `0.006497470955233239` / `-0.02196914945409663`；long-only annual net=`0.18055127519149888` / `0.1733387907177123` / `0.15891382177013919` / `0.14448885282256604`。
- Codex reviewer：score `5/10`，decision=`repair`。修复是正向改进，20bps long-short 从负转正，但 30bps 仍为负，且 unresolved exits、真实 H5 多日账本、exit fillability、size/industry neutral、复权/退市审计仍未过。
- 验证：`python -m py_compile alpha-stage/scripts/alpha_backtest.py agent/*.py` 通过；`pytest -q tests/test_alpha_backtest_cache.py -q` 为 `3 passed`；`pytest -q tests/test_quant_schedule.py tests/test_quant_entrypoint.py tests/test_quant_daily_pipeline.py tests/test_quant_self_audit.py tests/test_alpha_backtest_cache.py` 为 `108 passed`；`bash -n run_daily.sh scripts/submit_alpha_gpu_backtest.sh scripts/alpha_gpu_backtest.sbatch scripts/alpha_gpu_probe.sbatch` 通过。

## 2026-06-05 — Research log evolution skipped summary must match current next-generation output

- 收紧 readiness gate：`latest_research_log_matches_current_outputs` 现在不仅核对 evolution 的 `next_generation_count` / `next_factor_ids`，还要求 `skipped_failed_count` 和 `skipped_factor_ids` 与当前 `next_generation_factors.json.skipped_evolution_factors` 完全一致。
- 目的：长期研究日志不能虚构或遗漏“因失败记忆而跳过”的 evolution 因子；否则会污染禁止重复研究失败方案的证据链。
- Regression：新增 `test_readiness_blocks_research_log_evolution_skipped_summary_mismatch`，当前 next-generation 没有 skipped 时，把 `research_log_latest.json.evolution.skipped_failed_count=1` 且 `skipped_factor_ids=['STALE_SKIPPED_EVOLUTION']`，readiness 必须阻断 `latest_research_log_matches_current_outputs`。
- 验证：`python -m py_compile agent/*.py` 通过；定向测试 `1 passed`；`pytest -q tests/test_quant_self_audit.py -q` 通过；`pytest -q tests/test_quant_schedule.py tests/test_quant_entrypoint.py tests/test_quant_daily_pipeline.py tests/test_quant_self_audit.py` 为 `106 passed`；入口和 Slurm 脚本 `bash -n` 通过。
- 入口 smoke：临时目录 `QUANT_OFFLINE=1 QUANT_RUN_DATE=20260605 ... bash run_daily.sh` 输出 `SMOKE not_production_ready True True True True None` 且 stderr 为空，证明当前 research log、knowledge pointers、daily report、run history 均匹配当前输出，但单日仍不会误过 365 天生产门槛。

## 2026-06-05 — Next-generation per-factor files must match payload formulas

- 收紧 readiness gate：`latest_next_generation_files_match_payload` 现在不仅要求 `next_generation_factors/` 文件集合等于 `next_generation_factors.json.next_generation_factors[].factor_id`，还要求每个 per-factor JSON 的 `name`、`formula`、`formula_key`、`expression`、`horizon_days`、`status`、`rationale`、`parent_decision`、`failed_issues`、`parent_metrics` 和 `provenance` 与 payload 完全一致。
- 目的：Evolution Agent 的下一代因子不能用同 id / 同 formula_key 的旧 per-factor 文件冒充当前输出；日报、artifact manifest 和长期研究日志必须可回放真实 next-generation 公式。
- Regression：新增 `test_readiness_blocks_next_generation_file_formula_mismatch`，只把 `next_generation_factors/F1_PIVOT_DEF.json.formula` 改成 stale 值、保持 id 与 formula_key 不变，readiness 必须阻断 `latest_next_generation_files_match_payload`。
- 验证：`python -m py_compile agent/*.py` 通过；定向测试 `1 passed`；`pytest -q tests/test_quant_self_audit.py -q` 通过；`pytest -q tests/test_quant_schedule.py tests/test_quant_entrypoint.py tests/test_quant_daily_pipeline.py tests/test_quant_self_audit.py` 为 `107 passed`；入口和 Slurm 脚本 `bash -n` 通过。
- 入口 smoke：临时目录 `QUANT_OFFLINE=1 QUANT_RUN_DATE=20260605 ... bash run_daily.sh` 输出 `SMOKE not_production_ready True True True True 10` 且 stderr 为空，证明真实 next-generation per-factor 文件与 payload 匹配；单日仍不满足 365 天生产门槛。

## 2026-06-05 — Candidate and factor-library files must match payload formulas

- 收紧 readiness gate：`latest_candidate_factor_files_match_payload` 和 `latest_factor_library_matches_candidates` 现在要求 per-factor JSON 的 `name`、`formula`、`formula_key`、`expression`、`source_idea_id`、`created_at_run`、`provenance` 和 `status` 与当前 `candidate_factors.json` 完全一致。
- 目的：Factor Design Agent 的候选因子和长期 `factor_library/` 不能用同 id/formula_key 的旧文件冒充当前生成结果；自动生成新因子的证据必须能回放真实公式和 provenance。
- Regression：新增 `test_readiness_blocks_factor_library_formula_mismatch` 和 `test_readiness_blocks_candidate_factor_file_formula_mismatch`，分别只篡改 library / run-dir per-factor 文件的 `formula`，readiness 必须阻断对应 gate。
- 验证：`python -m py_compile agent/*.py` 通过；定向测试 `2 passed`；`pytest -q tests/test_quant_self_audit.py -q` 通过；`pytest -q tests/test_quant_schedule.py tests/test_quant_entrypoint.py tests/test_quant_daily_pipeline.py tests/test_quant_self_audit.py` 为 `109 passed`；入口和 Slurm 脚本 `bash -n` 通过。
- 入口 smoke：临时目录 `QUANT_OFFLINE=1 QUANT_RUN_DATE=20260605 ... bash run_daily.sh` 输出 `SMOKE not_production_ready True True True 5 True` 且 stderr 为空，证明真实 candidate per-file、factor_library 和 research log 均匹配当前输出；单日仍不满足 365 天生产门槛。

## 2026-06-05 — Daily pipeline records Slurm GPU alpha submission

- 新增 `agent.gpu_alpha_submission` 并接入 `daily_pipeline`：`run_daily.sh` 现在会生成 `reports/daily_logs/<run_date>/gpu_alpha_submission.json` 与 `reports/gpu_alpha_submission_latest.json`。
- 行为：生产/在线环境通过 `scripts/submit_alpha_gpu_backtest.sh` 调用 `sbatch`，解析并记录 Slurm job id、提交参数、stdout/stderr；`QUANT_OFFLINE=1` 或无 `sbatch` 时只记录 skip reason，不在登录节点启 CUDA。
- 验证：`python -m py_compile agent/*.py` 通过；新增/受影响定向测试 `2 passed`；`pytest -q tests/test_quant_schedule.py tests/test_quant_entrypoint.py tests/test_quant_daily_pipeline.py tests/test_quant_self_audit.py` 为 `110 passed`；`bash -n run_daily.sh scripts/submit_alpha_gpu_backtest.sh scripts/alpha_gpu_backtest.sbatch scripts/alpha_gpu_probe.sbatch` 通过。
- 入口 smoke：临时目录 `QUANT_OFFLINE=1 QUANT_RUN_DATE=20260605 ... bash run_daily.sh` 输出 `SMOKE not_production_ready skipped offline_run True True`，证明 GPU 提交记录被 artifact manifest 收录且离线运行不会尝试申请 GPU。

## 2026-06-05 — Readiness now audits GPU Slurm submission evidence

- 收紧 readiness gate：`gpu_alpha_submission` 已纳入 required agent、daily report snippets 和 artifact manifest required paths；`latest_gpu_alpha_submission_is_current_evidence` 要求 run-dir `gpu_alpha_submission.json` 与 `reports/gpu_alpha_submission_latest.json` 完全一致。
- 语义：离线运行只接受 `status=skipped` 且 `skip_reason=offline_run`；非离线运行必须通过 `scripts/submit_alpha_gpu_backtest.sh` 走 `sbatch` 提交，记录 command、sbatch path、returncode 和 job id/提交状态，不允许隐式本地 CUDA 回退。
- Regression：新增 `test_readiness_blocks_stale_gpu_alpha_submission_latest`，把 latest GPU submission 指针改成旧 run_date 后，readiness 必须阻断该 gate。
- 验证：`python -m py_compile agent/*.py` 通过；新增/相关定向测试 `2 passed`；`pytest -q tests/test_quant_self_audit.py -q` 通过；`pytest -q tests/test_quant_schedule.py tests/test_quant_entrypoint.py tests/test_quant_daily_pipeline.py tests/test_quant_self_audit.py` 为 `111 passed`；Slurm/入口脚本 `bash -n` 通过。
- 入口 smoke：`QUANT_OFFLINE=1 QUANT_RUN_DATE=20260605 ... bash run_daily.sh` 输出 `SMOKE not_production_ready True skipped offline_run True True`，证明 final readiness 已看到 GPU submission current evidence。

## 2026-06-05 — README deliverable now documents GPU submission artifacts

- 收紧 repository deliverable contract：`REQUIRED_README_SNIPPETS` 现在要求 README 说明 `gpu_alpha_submission_latest.json` 和 `Slurm`，防止交付文档只描述 CPU daily pipeline 而遗漏 GPU/sbatch 申请证据。
- README 输出清单新增 `gpu_alpha_submission.json` 与 `reports/gpu_alpha_submission_latest.json`，Long-Run Reliability 说明 daily GPU alpha acceleration 是 Slurm-only，并由 readiness 审计 current-run GPU submission/skip 语义。
- Regression：`test_readiness_blocks_readme_without_audited_readiness_docs` 现在确认弱 README 会缺失 `gpu_alpha_submission_latest.json` snippet 并阻断 repository deliverables。
- 验证：`python -m py_compile agent/*.py` 通过；README snippet 定向测试 `2 passed`；`pytest -q tests/test_quant_self_audit.py -q` 通过；聚合测试 `111 passed`；离线 smoke 输出 `SMOKE not_production_ready True [] True`。

## 2026-06-05 — Repository deliverables require all daily support modules

- 收紧 repository deliverables：`REQUIRED_AGENT_MODULE_FILES` 现在覆盖 daily workflow 实际依赖的 support modules，包括 `preflight.py`、`schedule.py`、`self_audit.py`、`artifact_manifest.py`、`artifact_verifier.py`、`gpu_alpha_submission.py`、`source_cache.py`、`config.py`、`io_utils.py` 和 `daily_simulation.py`。
- 目的：长期运行系统不能只要求 7 个核心 agent；缺少 artifact/readiness/schedule/GPU/source-cache 等支持模块时，`bash run_daily.sh` 的无人值守审计链同样不完整。
- Regression：新增 `test_readiness_blocks_missing_required_support_module`，在 fake repo 中删除 `agent/gpu_alpha_submission.py` 后，readiness 必须阻断 repository deliverables。
- 验证：`python -m py_compile agent/*.py` 通过；定向测试 `2 passed`；`pytest -q tests/test_quant_self_audit.py -q` 通过；聚合测试 `112 passed`；离线 smoke 输出 `SMOKE not_production_ready True True []`。

## 2026-06-05 — Repository deliverables require Slurm GPU scripts

- 收紧 repository deliverables：新增 `REQUIRED_SCRIPT_FILES`，要求 `scripts/submit_alpha_gpu_backtest.sh`、`scripts/alpha_gpu_backtest.sbatch` 和 `scripts/alpha_gpu_probe.sbatch` 存在，同时要求 `scripts/` 目录存在。
- 目的：daily GPU submission/readiness 已依赖 launcher 和 sbatch 文件；这些脚本缺失时不应只在运行后才暴露，交付物审计阶段就应阻断。
- Regression：新增 `test_readiness_blocks_missing_required_slurm_script`，在 fake repo 删除 `scripts/submit_alpha_gpu_backtest.sh` 后，readiness 必须阻断 repository deliverables 并暴露 `script_files_present=False`。
- 验证：`python -m py_compile agent/*.py` 通过；定向测试 `2 passed`；`pytest -q tests/test_quant_self_audit.py -q` 通过；聚合测试 `113 passed`；`bash -n` 校验入口和 Slurm 脚本通过；离线 smoke 输出 `SMOKE not_production_ready True True []`。

## 2026-06-05 — Artifact manifest now hashes GPU latest submission evidence

- 收紧 artifact manifest：`agent.artifact_manifest` 现在把 `reports/gpu_alpha_submission_latest.json` 纳入文件清单，`READINESS_REPORT` 的 required manifest paths 同步要求该 latest 指针存在并带 SHA256。
- 目的：GPU submission 已经要求 run-dir 记录与 latest 指针一致；manifest/verifier 也必须覆盖 latest 指针，避免长期审计只保护 `gpu_alpha_submission.json` 而不保护 `reports/gpu_alpha_submission_latest.json`。
- Regression：`test_daily_pipeline_runs_all_agents` 现在断言 manifest 同时包含 `gpu_alpha_submission.json` 和 `gpu_alpha_submission_latest.json`。
- 验证：`python -m py_compile agent/*.py` 通过；`pytest -q tests/test_quant_daily_pipeline.py tests/test_quant_self_audit.py` 为 `104 passed`；`pytest -q tests/test_quant_schedule.py tests/test_quant_entrypoint.py` 为 `9 passed`；入口和 Slurm 脚本 `bash -n` 通过；离线 smoke 输出 `SMOKE not_production_ready pass True True True True`。

## 2026-06-05 — Daily report exposes GPU submission outcome detail

- 收紧日报证据：`daily_report.md` 的 GPU 行现在显示 `status` 加具体原因或 job id，例如离线运行写 `gpu alpha submission: skipped (offline_run)`，Slurm 成功提交时写 `submitted (job <id>)`。
- Readiness：`latest_daily_report_is_current_evidence` 现在按当前 `gpu_alpha_submission.json` 精确核对日报 GPU 行，防止日报只写模糊 `skipped/submitted` 而无法区分离线跳过、缺 sbatch、提交失败或真实作业 id。
- Regression：`test_daily_pipeline_runs_all_agents` 和 production-ready fixture 的手写日报同步要求 `skipped (offline_run)`。
- 验证：`python -m py_compile agent/*.py` 通过；`pytest -q tests/test_quant_daily_pipeline.py tests/test_quant_self_audit.py` 为 `104 passed`；`pytest -q tests/test_quant_schedule.py tests/test_quant_entrypoint.py` 为 `9 passed`；入口和 Slurm 脚本 `bash -n` 通过；离线 smoke 输出 `SMOKE not_production_ready pass True True True`。

## 2026-06-05 — Schedule evidence must match current run date

- 收紧 schedule readiness gate：`latest_schedule_is_daily_run_daily` 现在要求 `schedule.json.run_date` 等于当前 `cfg.run_date`，不仅检查 cron 是每日 `bash run_daily.sh`。
- 目的：防止把旧 run 的 `schedule.json` 复制到当前 run directory 后，因 cron 语义仍正确而通过无人值守调度证据。
- Regression：新增 `test_readiness_blocks_stale_schedule_run_date`，真实离线 pipeline 生成完整 run 后只把 `schedule.json.run_date` 改为旧日期，readiness 必须阻断 schedule gate。
- 验证：`python -m py_compile agent/*.py` 通过；新增/相关 schedule 定向测试 `3 passed`；`pytest -q tests/test_quant_daily_pipeline.py tests/test_quant_self_audit.py` 为 `105 passed`；`pytest -q tests/test_quant_entrypoint.py tests/test_quant_schedule.py` 为 `9 passed`；入口和 Slurm 脚本 `bash -n` 通过；离线 smoke 输出 `SMOKE not_production_ready pass 20260605 True 20260605`。

## 2026-06-05 — Self-audit Markdown must match self-audit JSON

- 收紧 self-audit 人读报告证据：`READINESS_REPORT` 新增 `latest_self_audit_markdown_matches_json`，要求 `self_audit.md` 包含当前 run date、status、score、source mode、所有 check 结果、preflight 和 data freshness 摘要。
- 目的：`self_audit.json` 已经严格核对当前输出，但 `self_audit.md` 之前主要只要求存在并被 manifest hash；旧 Markdown 重新 hash 后仍可能作为人读报告混入当前 run。
- Regression：新增 `test_readiness_blocks_stale_self_audit_markdown`，真实离线 pipeline 生成完整 run 后篡改 `self_audit.md` 为旧 run date，readiness 必须阻断该 gate。
- 验证：`python -m py_compile agent/*.py` 通过；self-audit 定向测试 `3 passed`；`pytest -q tests/test_quant_daily_pipeline.py tests/test_quant_self_audit.py` 为 `106 passed`；`pytest -q tests/test_quant_entrypoint.py tests/test_quant_schedule.py` 为 `9 passed`；入口和 Slurm 脚本 `bash -n` 通过；离线 smoke 输出 `SMOKE not_production_ready pass True True`。

## 2026-06-05 — Source snapshot latest pointer must match current outputs

- 收紧 source snapshot latest 证据：`READINESS_REPORT` 新增 `latest_source_snapshots_latest_matches_current_outputs`，要求 `knowledge_base/source_snapshots_latest.json` 的 agent、timestamp、source_status、source_quality、item_count 和 items 与当前 market/research 输出一致。
- 目的：此前 readiness 会核 run-dir snapshot 和 JSONL same-day records，但 latest pointer 只要求 run_date 和 agent 合法；同日错误 latest pointer 可能绕过内容级审计。
- Regression：新增 `test_readiness_blocks_source_snapshots_latest_mismatch`，production-ready fixture 中只把 `source_snapshots_latest.json.item_count` 改为 `999`，readiness 必须阻断 latest pointer gate，同时 run-dir/JSONL snapshot gate 仍为 true。
- 验证：`python -m py_compile agent/*.py` 通过；source latest 定向正负例 `2 passed`；`pytest -q tests/test_quant_daily_pipeline.py tests/test_quant_self_audit.py` 为 `107 passed`；`pytest -q tests/test_quant_entrypoint.py tests/test_quant_schedule.py` 为 `9 passed`；入口和 Slurm 脚本 `bash -n` 通过；离线 smoke 输出 `SMOKE not_production_ready pass True True research_agent`。

## 2026-06-05 — GPU Slurm scripts are cwd-independent

- 稳定性修复：`agent.gpu_alpha_submission` 现在从模块位置推导项目根目录，用绝对路径调用 `scripts/submit_alpha_gpu_backtest.sh`，并在 subprocess 中显式设置 `cwd`；从非 repo 当前目录调用时不再误判提交脚本缺失。
- Slurm 脚本修复：`scripts/submit_alpha_gpu_backtest.sh`、`scripts/alpha_gpu_backtest.sbatch`、`scripts/alpha_gpu_probe.sbatch` 不再硬编码 `cd /home/lcc17/dl`，改为根据脚本自身位置进入 repo root。
- Regression：`test_gpu_alpha_submission_uses_sbatch_and_records_job_id` 现在先 `chdir(tmp_path)`，仍能通过 fake `sbatch` 提交并记录 job id、绝对脚本路径和 `script_exists=True`。
- 验证：`python -m py_compile agent/*.py` 通过；入口/调度/GPU 定向测试 `10 passed`；`pytest -q tests/test_quant_daily_pipeline.py tests/test_quant_self_audit.py` 为 `107 passed`；入口和 Slurm 脚本 `bash -n` 通过；离线入口 smoke 输出 `SMOKE complete not_production_ready skipped offline_run True True`。

## 2026-06-05 — Config failures now produce fallback artifacts

- 入口可靠性修复：`agent.run_entrypoint` 在 `load_config()` 失败时不再只写 `run_daily_invocation_latest.json`；现在会创建 `reports/daily_logs/invalid_config_<timestamp>/entrypoint_error.json`，并生成 `artifact_manifest.json`、`artifact_manifest_latest.json`、`artifact_verification.json`、`artifact_verification_latest.json`。
- 目的：无人值守运行中即使 `QUANT_DATE` / `QUANT_RUN_DATE` 配置错误，也能留下可哈希校验的失败包，方便排查 cron/env 配置问题。
- Regression：`test_run_entrypoint_records_config_error_invocation` 现在断言非法 `QUANT_DATE=20260631` 时 invocation 带 `failure_artifact_run_date` / `failure_artifact_run_dir`，fallback manifest 覆盖 `entrypoint_error.json` 和最新 invocation，verifier 状态为 `pass`。
- 验证：`python -m py_compile agent/*.py` 通过；`pytest -q tests/test_quant_entrypoint.py` 为 `9 passed`；`pytest -q tests/test_quant_schedule.py tests/test_quant_entrypoint.py` 为 `9 passed`；`pytest -q tests/test_quant_daily_pipeline.py tests/test_quant_self_audit.py` 为 `107 passed`；入口和 Slurm 脚本 `bash -n` 通过；正常离线入口 smoke 输出 `SMOKE complete not_production_ready success True`。

## 2026-06-05 — Same-day knowledge base reruns replace stale factor records

- 长期记忆修复：`agent.knowledge_base` 在完整/standalone 写入时，将当前 `run_date` 的旧 `factor_database.factors` 记录先移除，再按当前 `backtest_results.json` 与 `critique.json` 写入新记录。
- 目的：同一天重跑 pipeline 或修复回测/审稿后，`factor_database/factors.json` 不再因为 `(factor_id, run_date)` 已存在而保留旧 RankIC、旧 decision 或旧 issues。
- Research log：`factor_database_write` 新增 `replaced_same_day_factor_count`，用于解释同日重跑替换了多少旧因子记录；首次运行通常为 0。
- Regression：新增 `test_knowledge_base_replaces_same_day_factor_records`，先写同日 `F_STABLE` 的旧 `rankic_mean=0.01/decision=kill`，再写新 `rankic_mean=0.25/decision=promote`，因子库必须只保留新记录。
- 验证：`python -m py_compile agent/*.py` 通过；知识库/回测/审稿定向测试 `11 passed`；daily pipeline 定向测试 `2 passed`；`pytest -q tests/test_quant_daily_pipeline.py tests/test_quant_self_audit.py` 为 `107 passed`；`pytest -q tests/test_quant_entrypoint.py tests/test_quant_schedule.py` 为 `9 passed`；离线入口 smoke 输出 `SMOKE complete not_production_ready updated 0`。
