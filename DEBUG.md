# Debug Log

## 2026-06-03 — A股 alpha discovery 数据读取

- 现象：多个 parquet 文件 metadata 可读，但用 pandas/pyarrow 读取列数据时报 `OSError: Repetition level histogram size mismatch`。
- 复现命令：`python - <<'PY' ... pd.read_parquet('/home/lcc17/pan_sync_20260528/shortterm_cache/panel_2019-01-01_2026-05-28.parquet', columns=['ts_code','trade_date','open','close']) ... PY`
- 受影响文件：`shortterm_cache/panel_*.parquet`、`daily_predict_cache/panel_2019-01-01_2026-05-28.parquet`、`shortterm_cache/features_wq_2024-01-01_2026-05-28.parquet` 等抽测文件均触发同类错误。
- 已尝试：先读取 parquet schema/metadata 成功；读取数据列失败。环境未安装 `fastparquet`，不能用替代 parquet engine 交叉验证。
- 修复/绕行：`profile_data.py` 对 parquet sample read error 容错并继续；`alpha_backtest.py` 改用原始 CSV 目录 `A股数据/daily`、`metric`、`moneyflow`、`stock_st` 重新拼接日频面板和现场计算特征。
- 风险：CSV 全量拼接较慢；首轮若超时，使用 `ALPHA_START`/`ALPHA_END` 降级到较短时间窗完成最小可验证回测。

## 2026-06-03 — Reviewer 后回测框架修复

- Reviewer 发现：原脚本把 `next_amount`、`next_vol`、`next_is_st`、`next_open`、次日涨停等未来状态用于信号 universe 过滤，会污染 RankIC/组合构造。
- 修复：拆分 `signal_eligible` 与 `buy_fillable`。`signal_eligible` 只使用 t 日已知的 ST、成交额、成交量、IPO 冷却期；`buy_fillable` 只在组合选出后模拟 t+1 开盘买入是否可成交。
- Reviewer 发现：H5 return 被按日收益用 `252` 年化，数值夸大。
- 修复：`decile_portfolio` 按 `252 / horizon` 年化，并在输出中记录 `annualization_periods`。
- Reviewer 发现：A 股 long-short 不可直接交易。
- 修复：portfolio 输出增加 `portfolio_type=long_short_diagnostic_not_directly_tradable`，后续 promote 必须增加 long-only 或 hedge-aware 指标。
- Reviewer 发现：`sell_blocked_limit` 未使用。
- 修复：增加 `exit_fillable_{h}d`，若退出开盘疑似跌停不可卖，则该持仓收益记为无效，避免把不可退出收益当成可实现收益。
- 验证：`python -m py_compile alpha-stage/scripts/alpha_backtest.py` 通过；修复后 `ALPHA_FAST=1 ALPHA_START=20260101 ALPHA_END=20260528 ALPHA_CANDIDATES=A003,A005 ALPHA_HORIZONS=5 python alpha-stage/scripts/alpha_backtest.py` 完成。

## 2026-06-04 — Multi-agent backtest long-short smoke

- 现象：新增 long-short 诊断后，`tests/test_quant_agents_backtest_critic.py::test_backtest_agent_writes_results` 失败，`payload["results"][0]["long_short"]` 为空。
- 根因：synthetic fallback 数据只有 4 只股票，初始 long-short 诊断要求每日横截面至少 5 只，导致 smoke 数据无法形成 spread。
- 修复：将 long-short 诊断最低横截面样本从 5 放宽到 4，同时仍要求 long/short 两端都非空；输出继续标记为 `long_short_diagnostic_not_directly_tradable`。
- 验证：目标测试 `8 passed`；完整 MVP 测试集合 `20 passed`；端到端 smoke 通过并确认 `long_short` 与 `cost_sensitivity` 写入。

## 2026-06-04 — Full pytest collection blocked by missing torch

- 现象：`pytest -q tests` 在 collection 阶段失败。
- 根因：当前 Python 环境未安装 `torch`；失败来自 `tests/test_no_leakage.py` 导入 `src.dataset.WindowDataset` 和 `tests/test_training_pipeline.py` 直接导入 `torch`。
- 影响：这不是量化 agent pipeline 本次修改的功能失败，但会阻止仓库全量测试在当前环境完成。
- 绕行：使用量化 MVP 子集 `pytest -q tests/test_quant_*.py tests/test_backtest_engine_package.py` 验证本系统，结果 `27 passed`。
- 修复方向：若要恢复全量测试，需要安装与项目匹配的 PyTorch 环境，或给训练相关测试加依赖可用性 skip。

## 2026-06-04 — Stale daily lock can block unattended operation

- 现象：旧版 `reports/.quant_daily.lock` 只要存在就会让后续 `daily_pipeline.run` 抛出 `daily pipeline lock exists`。
- 根因：崩溃、断电或 kill -9 后 lock 文件可能残留；原逻辑没有 stale 判定和恢复路径，会让 365 天无人值守运行永久卡住。
- 修复：新增 `QUANT_LOCK_STALE_MINUTES`，默认 180 分钟；lock 写入 JSON metadata；fresh lock 继续阻止并发，stale lock 自动清理并重试获取；恢复情况写入 `pipeline_state.json` 和 `run_audit.json`。
- 验证：Pipeline lock 目标测试 `8 passed`；量化 MVP 子集 `30 passed`；端到端 stale-lock smoke 输出 `complete True True False`。

## 2026-06-04 — Corrupt JSONL lines should not poison latest-run readiness

- 现象：长期运行时 `run_history.jsonl`、`research_log.jsonl` 或 `failure_memory.jsonl` 可能因为中断留下半行。若把坏行当作普通 record，readiness 的 latest run 判断可能误用坏行。
- 根因：旧 readiness JSONL reader 把 parse error 包装成一条 record，最后一行坏掉时会污染 `latest`。
- 修复：新增 `read_jsonl_records`，分离 valid records 与 parse errors；坏行写入 `knowledge_base/jsonl_quarantine/*.corrupt.jsonl`；readiness 继续用最后一条 valid run 做 latest 判断，但 `no_jsonl_parse_errors` 失败并阻止 production-ready。
- 验证：新增 corruption 测试确认 365 条有效记录加 1 条坏行时，`has_365_successful_runs` 仍为 true，但整体状态为 `not_production_ready`，且 quarantine 文件生成。

## 2026-06-04 — Early crash left weak pipeline state evidence

- 现象：如果 pipeline 在早期 agent 运行中遭遇 `KeyboardInterrupt`、进程信号或未捕获异常，旧逻辑可能只释放 lock，缺少能说明运行卡在哪个 agent 的 `pipeline_state.json`。
- 根因：`pipeline_state.json` 主要在 core agents 全部跑完后写入，缺少启动时和 agent 级增量 checkpoint。
- 修复：启动后立即写 `status=running`；每个 agent 前后更新 `current_agent` 和 `completed_agents`；未捕获中断写 `status=interrupted`、当前 agent、已完成 agent 和 traceback，再释放 lock。
- 验证：新增测试模拟 `fatal_agent` 抛 `KeyboardInterrupt`，确认 state 记录 `interrupted`、`current_agent=fatal_agent`、`completed_agents=["market_intelligence"]` 且 lock 被释放。

## 2026-06-04 — Self-audit conflicted with running checkpoint

- 现象：新增增量 checkpoint 后，`test_self_audit_passes_after_full_pipeline` 一度失败，`self_audit.status` 从 `pass` 变为 `warning`。
- 根因：self-audit 执行时 `pipeline_state.json` 正处于 `status=running,current_agent=self_audit`。旧 self-audit 只接受 `complete/complete_with_errors`，没有识别“core agents 和 schedule 已完成，正在审计阶段”的合法状态。
- 修复：新增 `_pipeline_reached_audit_phase`，当 core agents 与 schedule 已完成且 current agent 是 `self_audit` 或 `readiness_report` 时，允许 self-audit 通过 pipeline completion 检查。
- 验证：失败测试重跑通过；Pipeline checkpoint/self-audit 定向测试 `10 passed`；量化 MVP 子集 `32 passed`。

## 2026-06-04 — Preflight warning must be a hard self-audit warning

- 现象：新增 preflight 后，`test_daily_pipeline_records_preflight_warning_without_stopping` 发现 `preflight.status=warning` 时 `self_audit.status` 仍为 `pass`。
- 根因：self-audit 的总分阈值允许一个检查失败后仍达到 0.9，导致磁盘不足这类资源风险被弱化。
- 修复：self-audit 的 pass 条件显式要求 `checks["preflight_ok"]` 为 true；preflight warning 仍不阻塞 pipeline，但会让健康状态保持 warning。
- 验证：Pipeline/Self-audit 定向测试 `14 passed`；量化 MVP 子集 `33 passed`。

## 2026-06-04 — Readiness manifest gate had a sequencing loop

- 现象：首次加入 artifact manifest gate 后，端到端 smoke 显示 `artifact_manifest_present=False`，但同一运行结束后 manifest 文件实际存在。
- 根因：`readiness_report` 在 `artifact_manifest` 生成前运行；如果只跑一次 readiness，manifest gate 会永久看到旧状态。
- 修复：每日流程先生成初版 readiness，再写 final state/日报和 manifest；随后重跑 readiness，让它读取 manifest gate；最后重生成 manifest，记录最终 readiness 内容。
- 验证：readiness-manifest smoke 输出 `True True True True`；量化 MVP 子集 `34 passed`。

## 2026-06-04 — Alpha continuation full-run too slow without panel cache

- 现象：`ALPHA_CANDIDATES=A019,A020,A021 ALPHA_HORIZONS=5 ALPHA_START=20190101 ALPHA_END=20260528 python alpha-stage/scripts/alpha_backtest.py` 和 `ALPHA_FAST=1` 版本均长时间停留在全量 CSV 拼接、特征构造和日期循环评估阶段，交互迭代超时后被手动结束。
- 根因：当前 `alpha_backtest.py` 每次从 `~/pan_sync_20260528/A股数据/{daily,metric,moneyflow,stock_st}` 重新读取并合并多年份 CSV，没有 parquet panel/cache；全量 2019-2026 对每个候选重复做按日期 RankIC/组合循环，不适合持续 alpha 挖掘。
- 修复/绕行：先用 `ALPHA_START=20250101 ALPHA_END=20260528 ALPHA_FAST=1` smoke 验证 A019/A020/A021 变体和排序池修复能跑通；正式 promote 前必须新增 panel 缓存或预聚合后重跑全量非空 train/validation/test。
- 复现信息：短窗命令 `ALPHA_FAST=1 ALPHA_CANDIDATES=A019,A020,A021 ALPHA_HORIZONS=5 ALPHA_START=20250101 ALPHA_END=20260528 python alpha-stage/scripts/alpha_backtest.py` 通过，但 train/validation rows 为 0，只能作为 smoke。

## 2026-06-04 — Alpha full-run cache and GPU availability

- 现象：首次 2019-2026 全量 A019/A020/A021 rerun 成功写入约 2.7GB panel parquet cache，但后续仍因全列 parquet 读取和 Python groupby 评估循环较慢。
- 根因：cache 初版复用了完整 panel，但每次仍读取所有字段；登录 shell 没有可见 GPU，不能自动把 pandas groupby/rank/corr 迁移到 GPU。
- 修复：`alpha_backtest.py` 新增 cache 元数据校验和按本轮 candidates/horizons 的列裁剪读取；新增 `tests/test_alpha_backtest_cache.py` 锁定 cache roundtrip、源 CSV 变更失效和列裁剪读取。
- Slurm/GPU 复现信息：登录节点 `nvidia-smi` 无输出，`/dev/nvidia*` 不存在；`cupy`、`cudf`、`torch` 未安装；`numba.cuda.is_available()` 返回 false。`scripts/alpha_gpu_probe.sbatch` 的 job `29430` 在 A800 节点 `gpu4` 验证 GPU 可用，`torch 2.12.0+cu126` 和 `numba.cuda_available=True`，但 `cudf/cupy` 仍缺失。
- GPU 修复：新增 `ALPHA_BACKEND=torch_cuda`，在 Slurm GPU 节点上用 PyTorch CUDA 实现按日 RankIC rank/corr、long-short top/bottom decile 和 long-only top decile 的核心计算；新增 `scripts/alpha_gpu_backtest.sbatch` 申请 A800 单卡运行 alpha 回测。
- 验证：本地编译、sbatch 语法和量化 MVP 子集通过；GPU job `29432` 在 A800 `gpu4` 完成 A019/A020/A021 2019-2026 H5 rerun，A020 进入 repair，A019/A021 kill。注意 parquet 读取仍是 CPU/pyarrow，若要进一步加速 I/O 和 dataframe groupby，需要安装 RAPIDS/cuDF。

## 2026-06-04 — Failed pipeline runs could pollute factor database

- 现象：`daily_pipeline` 对 agent failure 会继续运行并写 safe fallback payload；旧 `knowledge_base.run` 只读取 `backtest_results.json` 和 `critique.json`，不检查 `pipeline_state.json`，理论上可能把错误/不完整运行中的残留或不可靠 backtest 结果追加进长期 `factor_database/factors.json`。
- 根因：run quality 只在 `run_history.jsonl` 记录，Knowledge Base Agent 自身没有用 pipeline 状态作为写库门槛。
- 修复：`knowledge_base` 新增 `_run_quality`，读取 `pipeline_state.json`；完整 pipeline 中只有 `complete` 或正在执行 `knowledge_base` 且上游 agent 全 ok 时才追加 factor database。`complete_with_errors` 只写 research log，并记录 `factor_database_write.status=skipped`。
- 兼容：没有 `pipeline_state.json` 的直接 agent 调用标记为 `standalone`，仍允许测试/手动重建写库，不影响完整 pipeline 的失败运行保护。
- 验证：新增 `data_agent` failure regression，确认 research log 为 `incomplete` 且 factor database 为空；量化 MVP 子集 `39 passed`。

## 2026-06-04 — Partial live sources were too weak for production evidence

- 现象：旧 `_source_quality_is_production_evidence` 只要求 mode 非 offline/fallback、`ok_sources>0` 且未使用 fallback；如果 6 个 market source 只有 1 个成功、公告/政策/行业等 source failed，仍可能被计入 production evidence。
- 根因：readiness gate 只验证“存在 live evidence”，没有验证“全部要求的 source kind 都被覆盖”。
- 修复：production evidence 现在要求 `total_sources>0`、`ok_sources==total_sources`、`error_sources==0`、`missing_kinds=[]`、`coverage_ratio>=1.0`、`fallback_used=false`。
- 验证：新增 365 天 partial-live-source regression；Readiness/self-audit 定向测试 `10 passed`；量化 MVP 子集 `40 passed`。

## 2026-06-04 — Data production evidence lacked domain coverage

- 现象：旧 `data_health.json` 只检查少量派生列、重复键和 freshness；即使本地数据缺行业或财务/估值字段，`READINESS_REPORT` 也只要 `source_mode=local_csv` 且 freshness ok 就可能把数据计为 production evidence。
- 根因：Data Agent 没把 objective 中要求的 OHLCV、财务、行业、资金流等数据域显式映射成 health gate；`basic.csv` 的行业字段也没有并入标准数据集。
- 修复：Data Agent 合并 `basic.csv` 的 `industry/area/market/list_date`；`data_health.json` 新增 `domain_coverage` 并要求 `required_data_domains_usable`；run history 和 readiness 均纳入该 gate。
- 调试细节：新增财务域缺失测试时发现 `_add_features` 直接访问 `pb` 会抛 `KeyError`，已改为可选域缺失时补 NaN 列，再由 health gate 给出 warning。
- 验证：Data/Readiness 定向测试 `21 passed`；量化 MVP 子集 `42 passed`。

## 2026-06-04 — Backtest raw promote was too permissive

- 现象：旧 Backtest Agent 只要 RankIC 均值为正且 long-only 成本后收益为正，就把结果标为 `decision=promote`；这绕过了 Critic 对样本量、稳定性、高成本、long-short 诊断和泄漏的最终判断。
- 根因：raw backtest gate 和 reviewed promotion 使用同一个 `promote` 语义，日报和 run history 也按 backtest result 统计 promoted。
- 修复：Backtest 现在只输出 `raw_candidate` 或 `kill`；Critic 只有在 `raw_candidate` 无 issues 时才输出 `promote`。Daily report / run history 分开统计 `raw_candidates` 和 critic `promoted`。
- 新增审查：Critic 增加 `non_positive_high_cost_return`、`insufficient_backtest_dates`、`negative_long_short_diagnostic` 等 issues。
- 验证：新增 regression 确认 Backtest 不直接 promote，以及高成本/long-short 不支持时 Critic kill；量化 MVP 子集 `43 passed`。

## 2026-06-04 — run_daily lacked shell-level invocation audit

- 现象：旧 `run_daily.sh` 只执行 `python -m agent.daily_pipeline`。如果 cron 环境异常、入口层异常或 Python 进程在进入/退出 pipeline 附近失败，只有 stdout/stderr 文本日志，没有结构化 invocation exit code 和 traceback。
- 根因：运行审计集中在 `daily_pipeline` 内部，缺少 shell entrypoint 级别的 durable JSONL。
- 修复：新增 `agent.run_entrypoint` 包装 daily pipeline；成功和失败都写 `reports/run_daily_invocations.jsonl` 与 `reports/run_daily_invocation_latest.json`，记录 pid/host/cwd/argv/duration/exit_code/status/error traceback。`run_daily.sh` 改为调用该 wrapper。
- 验证：新增 entrypoint success/failure regression；真实临时目录 `bash run_daily.sh` smoke 输出 `success 0 complete True`；量化 MVP 子集 `45 passed`。

## 2026-06-04 — Readiness could not see post-pipeline invocation record

- 现象：加入 invocation readiness gate 后，真实 `bash run_daily.sh` smoke 的 `run_daily_invocation_latest.json` 为 `success/0`，但最终 `READINESS_REPORT.json` 中 `run_daily_invocation_present/success/matches_run_date` 仍为 false，artifact manifest 也没有包含 invocation latest。
- 根因：`daily_pipeline` 在 `run_entrypoint` 写 shell invocation record 之前就已生成 final readiness 和 manifest；入口层证据天然只能在 pipeline 返回后出现。
- 修复：`run_entrypoint` 成功写 invocation record 后重跑 readiness 和 artifact manifest，顺序为 readiness -> manifest -> readiness -> manifest，确保最终 readiness 看到 invocation，最终 manifest 包含 invocation 与最新 readiness。
- 验证：真实临时目录 `QUANT_OFFLINE=1 ... bash run_daily.sh` smoke 输出 `success 0 20260604 True True True not_production_ready True`；入口/readiness 定向测试 `15 passed`；量化 MVP 子集 `48 passed`。

## 2026-06-04 — Run history alone could satisfy 365-day proof

- 现象：readiness 只检查最新 `run_daily_invocation_latest.json`，但 365 天生产证据主要来自 `knowledge_base/run_history.jsonl`。理论上直接重建或伪造 365 条 run history，再提供一条最新成功 invocation，就可能通过生产就绪门槛。
- 根因：长期无人值守证据没有把每天的 shell entrypoint invocation JSONL 与每天的 production-evidence run date 对齐。
- 修复：`READINESS_REPORT` 现在解析 `reports/run_daily_invocations.jsonl`，要求 365 条成功 invocation、365 个唯一 invocation 日期、365 天连续 invocation streak，并要求所有 production-evidence run date 都有成功 invocation 覆盖。
- 验证：新增 regression 确认 365 条完整 production run history 但只有 1 条 successful invocation 时保持 `not_production_ready`；readiness 定向测试 `14 passed`；真实 smoke 显示单日 invocation 只计 1 条；量化 MVP 子集 `49 passed`。

## 2026-06-04 — Source quality summaries lacked replayable 365-day evidence

- 现象：`run_history.jsonl` 记录 market/research source quality，但 readiness 只要求 `source_snapshots.jsonl` 存在至少一条。理论上 365 天 run history 可以声称 live source 全成功，而缺少对应日期的逐源快照。
- 根因：source snapshot JSONL 没有按 production-evidence run date 做 coverage 对齐，也没要求每个日期同时具备 market 和 research 两类 production-grade snapshots。
- 修复：`READINESS_REPORT` 按日期聚合 `source_snapshots.jsonl`，只把同时具备 `market_intelligence` 和 `research_agent` 且 source_quality 达标的日期计为 production source snapshot date；生产就绪要求 365 天数量、连续 streak 和 production-evidence 日期覆盖。
- 验证：新增 regression 确认缺少 365 天 source snapshots 时阻止 `production_ready`；readiness 定向测试 `15 passed`；真实 smoke 写入 2 条离线 snapshot 但不计入 365 production snapshot gate；量化 MVP 子集 `50 passed`。

## 2026-06-04 — Data summaries lacked durable 365-day artifact evidence

- 现象：`run_history.jsonl` 记录 data source mode、freshness 和 domain coverage，但缺少跨日期可回放的数据健康 JSONL；旧 `data_health.json` 只在 daily run dir，长期审计时容易退化为 run_history 摘要自证。
- 根因：Data Agent 没有把每日 data health / dataset manifest 追加进 knowledge base 的长期日志，readiness 也没有按 production-evidence date 对齐数据 artifact。
- 修复：Data Agent 追加 `knowledge_base/data_health.jsonl` 并更新 `data_health_latest.json`；readiness 要求 365 天 production-grade data artifact dates、连续 streak 和 production-evidence 日期覆盖；artifact manifest 纳入 latest 数据健康证据。
- 验证：新增 regression 确认缺少 data artifacts 时阻止 `production_ready`；readiness/data 定向测试 `27 passed`；真实 smoke 写入 data health JSONL/latest 但单日不满足 365 gate；量化 MVP 子集 `51 passed`。

## 2026-06-05 — Run history could imply knowledge saves without replayable evidence

- 现象：365 天 `run_history.jsonl` 可以记录 pipeline complete 和 self-audit pass，但如果 `research_log.jsonl` 没有对应日期的 `factor_database_write.status=updated`，长期审计无法证明每天确实保存了知识库。
- 根因：readiness 过去只要求 research log 存在，缺少按 production-evidence run date 对齐的 knowledge-base save 日期门槛。
- 修复：`READINESS_REPORT` 统计完整 knowledge-save dates，并要求 365 天数量、365 天连续 streak，以及所有 production-evidence 日期都有完整 knowledge save 覆盖；新增 regression 覆盖 run/source/data/invocation 都齐但 knowledge saves 缺失的失败路径。
- 验证：`python -m py_compile agent/*.py` 通过；`tests/test_quant_self_audit.py` 为 `17 passed`；快速 smoke 必须显式设置 `QUANT_DATA_ROOT` 到缺失目录，否则会读取真实大数据导致登录节点长时间运行。

## 2026-06-05 — Current invocation could pair with stale run history

- 现象：readiness 可以有当前日期的 `run_daily_invocation_latest.json`，同时最新 `run_history.jsonl` 停在前一天；如果只看 365 天历史 run_history 和当前 invocation，可能错误通过生产就绪。
- 根因：readiness 没有要求 latest run_history record 的 `run_date` 等于当前 `RunConfig.run_date`。
- 修复：新增 `latest_run_history_matches_run_date` gate 和 blocker；production-ready happy path 改为 365 天窗口以当前 run date 收尾；新增 stale latest run history regression。
- 验证：`tests/test_quant_self_audit.py` 为 `18 passed`；快速 smoke 输出 `SMOKE 0 not_production_ready True 20260605 20260605`；量化 MVP 子集 `53 passed`。

## 2026-06-05 — Artifact manifest could be stale while hashes pass

- 现象：`artifact_manifest.json` 可以被旧运行复制到当前 run_dir；如果列出的文件仍存在且 hash 匹配，artifact verification 会通过，但 manifest 自身不一定属于当前 run date。
- 根因：readiness 检查 manifest 存在、required paths、SHA256 和 verifier status，但没有检查 manifest payload 的 `run_date`。
- 修复：新增 `artifact_manifest_matches_run_date` gate 和 blocker；新增 stale manifest run_date regression。
- 验证：`tests/test_quant_self_audit.py` 为 `19 passed`；快速 smoke 输出 `SMOKE 0 not_production_ready True True 20260605 20260605`；量化 MVP 子集 `54 passed`。

## 2026-06-04 — Run history production-evidence field missed import

- 现象：新增 `data_freshness` 写入 `run_history.jsonl` 后，`test_self_audit_passes_after_full_pipeline` 失败，`daily_pipeline._append_run_history` 抛 `NameError: name 'read_json' is not defined`。
- 根因：`daily_pipeline.py` 原来只从 `agent.io_utils` 导入 `append_jsonl` 和 `write_json`，新增读取 `data_health.json` 时漏加 `read_json`。
- 修复：补充 `from .io_utils import append_jsonl, read_json, write_json`。
- 验证：`python -m py_compile agent/*.py` 通过；`tests/test_quant_self_audit.py` 后续 `7 passed`。

## 2026-06-04 — GPU is Slurm-only for alpha backtests

- 现象：登录 shell 下看不到 GPU：`nvidia-smi` 无可用输出，`/dev/nvidia*` 不存在，登录环境缺 `torch/cupy/cudf`，`numba.cuda.is_available()` 为 false。
- 根因：集群 GPU 需要通过 Slurm 资源申请暴露给作业；登录节点不是 GPU 执行环境。
- 修复/流程：全量 alpha 回测使用 `sbatch scripts/alpha_gpu_backtest.sbatch`，脚本申请 `--partition=A800 --gres=gpu:1`，激活 conda `dl` 后设置 `ALPHA_BACKEND=torch_cuda`。环境探测使用 `sbatch scripts/alpha_gpu_probe.sbatch`。
- 复现证据：probe job `29430` 在 `gpu4` 验证 A800 + torch CUDA 可用；backtest job `29432` 完成 A019/A020/A021 H5；A020 多持仓期 repair 检查 job `29464` 完成。
- sbatch 参数坑：`sbatch --export=ALL,ALPHA_HORIZONS=1\\,5\\,10\\,20 ...` 会被 Slurm 的逗号分隔语法截断，job `29460` 实际只看到 `ALPHA_HORIZONS=1`。正确做法是先在 shell 环境设置变量再提交：`ALPHA_HORIZONS='1,5,10,20' sbatch --export=ALL scripts/alpha_gpu_backtest.sbatch`。
- 修复：`scripts/alpha_gpu_backtest.sbatch` 默认 `ALPHA_FAST=0`，全量 GPU 作业输出分年稳定性；快速 smoke 需要显式设置 `ALPHA_FAST=1`。
- 修复：新增 A022-A026 后把 `PANEL_CACHE_VERSION` 从 1 提升到 2，否则旧 parquet cache 不包含新字段，`ALPHA_CANDIDATES=A022...` 会因缺列被跳过。
- 复现信息：A022-A026 repair/pivot 作业用 `ALPHA_CANDIDATES='A022,A023,A024,A025,A026' ALPHA_HORIZONS='1,5,10,20' ALPHA_START=20190101 ALPHA_END=20260528 ALPHA_FAST=0 sbatch --export=ALL scripts/alpha_gpu_backtest.sbatch` 提交，job `29491`，提交后在 A800 分区排队 `PD (Priority)`。

## 2026-06-05 — Slurm allocation parameters should go through launcher overrides

- 现象：GPU 资源需要按集群 Slurm 规则申请；不同队列可能要求 partition/qos/account/time 参数，手动编辑 `.sbatch` 容易造成不可复现配置漂移。
- 修复：`scripts/submit_alpha_gpu_backtest.sh` 支持 `SLURM_PARTITION`、`SLURM_QOS`、`SLURM_GPUS`、`SLURM_CPUS_PER_TASK`、`SLURM_TIME` 和可选 `SLURM_ACCOUNT`，提交时显式传给 `sbatch` 覆盖脚本默认 `#SBATCH`。
- 复现提示：仍然不要用 `sbatch --export=ALL,ALPHA_HORIZONS=1,5,10,20` 传逗号变量；应先设置 shell 环境变量，再调用 launcher。
- 复现结果：job `29491` 在 `gpu5` 完成，`torch_cuda` 生效。A022/A024/A025 的 RankIC 和 long-only 指标改善，但所有候选 long-short 诊断仍为负；A023/A026 部分持仓期 RankIC 转负。结论保持 repair，不 promote。
- 修复：新增 `scripts/submit_alpha_gpu_backtest.sh`，用 shell 环境变量再 `sbatch --export=ALL` 提交，避免重复踩 Slurm 逗号解析坑；默认继续跑 A022/A024/A025 repair 队列。
- 复现信息：launcher 提交 job `29516`，`squeue` 显示在 A800 `gpu4` 运行；`reports/slurm/alpha_gpu_backtest-29516.err` 当前为空，`.out` 已生成。
- 复现结果：job `29516` 完成；stdout 显示 `CUDA_VISIBLE_DEVICES=0`、`torch.cuda_available=True`、device `NVIDIA A800-SXM4-80GB`。stderr 为空。指标与 29491 对 A022/A024/A025 一致，说明 launcher 参数传递正确。

## 2026-06-05 — schedule.json existed without machine-checked daily cadence

- 现象：`schedule_agent` 会写 `schedule.json` 和 `cron_example.txt`，但 readiness 过去只通过 artifact manifest 间接要求文件存在，没有检查它是否真的是“每天执行 bash run_daily.sh”。
- 风险：如果 schedule 退化成工作日、错误脚本或空 command，系统仍可能通过文件存在检查，和“每天自动运行”目标不一致。
- 修复：`schedule.json` 新增 `cadence`、cron 字段、`command`、`script_path`；readiness 新增 `latest_schedule_is_daily_run_daily` gate，检查 daily cadence 和 `bash run_daily.sh` 命令。
- Regression：构造 365 天生产证据齐全但 `schedule.json` 为 `cadence=weekday/day_of_week=1-5`，确认 `not_production_ready` 且 blocker 指向 schedule cadence。
- 复现证据：入口 smoke 输出 `SMOKE 0 not_production_ready True True daily * True`；MVP 子集 `65 passed`。

## 2026-06-05 — run_audit.json existed but was only presence-checked

- 现象：`run_audit.json` 已在 self-audit required files 和 artifact manifest required paths 中，但 readiness 过去只验证它存在且被哈希，没有检查内容是否匹配当前 run date/config/lock/retention。
- 风险：陈旧或占位 `run_audit.json` 可能和当前 `run_history`、`pipeline_state`、`run_daily_invocation_latest.json` 拼出看似完整的每日证据链。
- 修复：新增 `_run_audit_is_current_evidence`，检查 `run_date`、config 路径/参数、lock pid/created_at/stale_after、state run_date/status/agents/lock、retention_days；readiness 新增 `latest_run_audit_is_current_evidence` blocker 和 `run_audit_evidence` 输出。
- Regression：365 天 production evidence 齐全但最新 run_audit 的 `run_date=20260603` 且 `retention_days` 不匹配时，production-ready 被阻止。
- 复现证据：离线真实入口 smoke 输出 `latest_run_audit_is_current_evidence=True`、`artifact_manifest_verification_passed=True`、manifest 包含 `run_audit.json`。

## 2026-06-05 — failure_memory.jsonl presence did not prove same-day failure persistence

- 现象：readiness 过去只检查 `failure_memory.jsonl` 有记录，没有检查最新 `critic_agent` kill 的因子是否已经写入当天失败记忆。
- 风险：如果 `evolution_agent` 或 failure-memory append 退化，系统仍可能有旧 failure memory 文件并通过存在性检查，但当天失败因子不会进入长期去重，第二天可能重复研究。
- 修复：新增 `_killed_factors_have_failure_memory`，从最新 `critique.json` 提取 `decision=kill` 的 factor id，并要求同一 `run_date` 的 `failure_memory.jsonl` 包含这些 id；readiness 输出 killed ids 和 same-day memory ids。
- Regression：365 天 production evidence 齐全但 failure memory 只有 `run_date=20260603/F1`，当前 `20260604` critique kill `F1` 时，production-ready 被阻止。
- 复现证据：离线真实入口 smoke 输出 `latest_killed_factors_have_failure_memory=True`，当天 killed ids `F_MF_EXHAUST_5/F_VOL_REV_5/F_VWAP_REV_5` 均在 same-day failure memory 中。

## 2026-06-05 — latest knowledge pointers could become stale while JSONL looked complete

- 现象：readiness 主要基于 `run_history.jsonl`、`research_log.jsonl`、`source_snapshots.jsonl`、`data_health.jsonl` 判断长期证据，但没有检查对应 `*_latest.json` 是否指向当前 run date。
- 风险：如果 latest 文件写入失败或被旧文件覆盖，用户和 manifest 可能看到陈旧 latest 指针，而 365 天 JSONL 仍让 production evidence 看起来完整。
- 修复：新增 `latest_knowledge_pointers_match_run_date`，检查 `run_history_latest.json`、`research_log_latest.json`、`source_snapshots_latest.json`、`data_health_latest.json`；source snapshot latest 还必须来自 market/research required agent 之一。
- Regression：预写 stale `run_history_latest.json` 后运行 readiness，确认 blocker 指向 latest pointer mismatch。
- 复现证据：离线真实入口 smoke 输出 `latest_knowledge_pointers_match_run_date=True`，四个 pointer alignment 均为 true，`source_snapshots_latest.agent=research_agent`。

## 2026-06-05 — cron_example.txt was generated but not required

- 现象：`schedule.run` 会写 `cron_example.txt`，README 也把它列为输出，但 self-audit required files 和 readiness manifest required paths 过去只要求 `schedule.json`。
- 风险：调度示例文件缺失或为空时，系统仍可能通过每日产物链检查，和“用户只需 bash run_daily.sh / 可安装每日调度”的交付证据不一致。
- 修复：把 `cron_example.txt` 加入 `self_audit.REQUIRED_RUN_FILES`，从而进入 readiness required manifest paths；daily report 文件清单也同步列出该文件。
- 复现证据：离线真实入口 smoke 输出 `cron_example.txt` 的 self-audit file check 为 true、manifest 包含该路径、required manifest gate 为 true。

## 2026-06-05 — Evolution could regenerate failed repair variants

- 现象：`factor_design` 会读取 killed factor database 和 `failure_memory.jsonl` 来跳过失败模板，但 `evolution_agent` 生成 repair/pivot 子因子时没有查失败记忆。
- 风险：长期无人值守时，同一个失败过的 repair formula 可能每天被 evolution 重新写入 `next_generation_factors/`，绕过 factor design 的 skip 机制，造成重复研究。
- 修复：`evolution_agent` 复用 failed keys 读取逻辑，child 命中 `factor_id` / `formula` / `formula_key` / `expression` 时写入 `skipped_evolution_factors`，不写 child JSON；`knowledge_base` 把 skipped evolution count 写入 research log。
- Regression：构造 `failure_memory.jsonl` 含 `formula_key=\"(rank(ret_5))*(1-rank(turnover_20))\"`，确认 `BAD_VOL_PIVOT_COST` 被跳过且文件不存在。
- 复现证据：入口 smoke 输出 `SMOKE 0 not_production_ready next 10 skipped 0 log_has_skip True`；MVP 子集 `64 passed`。

## 2026-06-05 — Failure memory could be only an id list

- 现象：readiness 过去只要求最新 `critique.json` 中 killed factors 的 factor_id 出现在同日 `failure_memory.jsonl`，没有验证失败原因、检查结果或父回测指标是否保存。
- 风险：只有 factor_id 的 failure memory 可以阻止重复 id，但无法解释为什么失败，也无法支持后续 repair/pivot 或 debug 审计；公式 key 或 issue 漂移时仍可能误判为有效失败经验。
- 修复：新增 `_killed_factor_failure_memory_details_match` 和 `latest_killed_factor_failure_memory_details_match`，要求同日 failure memory 的 `formula_key`、`issues`、非空 `checks`、`parent_metrics.rankic_mean`/`ann_return_net` 与最新 backtest/critic 对齐。
- Regression：同日 failure memory 只写 `factor_id/formula_key` 时，`latest_killed_factors_have_failure_memory` 仍为 true，但 detail gate 为 false，readiness 保持 `not_production_ready`。
- 验证：self-audit 目标测试 `31 passed`、入口目标集 `49 passed`、MVP 子集 `74 passed`；离线 `run_daily.sh` smoke 证明真实 killed factors 的 failure memory 详情匹配。

## 2026-06-05 — Factor database could be nonempty but stale

- 现象：readiness 过去只要求 `knowledge_base/factor_database/factors.json` 非空，没有验证当天 backtest result 和 critic decision 是否真正写入 factor database。
- 风险：历史上有因子记录即可通过知识库存在性检查；如果当天 knowledge base 写入跳过、写旧日期或 decision 没合并 critic 结论，长期记忆会缺失当天失败/回测经验。
- 修复：新增 `_factor_database_matches_latest_results` 和 `latest_factor_database_matches_backtests`，逐个检查当天 backtest result 在 factor database 中存在同 run_date 记录，且 `formula_key`、`rankic_mean`、critic-resolved `decision` 一致。
- Regression：把 production-ready fixture 中 factor database 记录日期改成 `20260603`，确认 readiness 降为 `not_production_ready`。
- 验证：self-audit 目标测试 `30 passed`、入口目标集 `48 passed`、MVP 子集 `73 passed`；离线 `run_daily.sh` smoke 证明真实 5 个 backtest result 都有同日 factor database 记录。

## 2026-06-05 — Factor library could drift from candidate_factors.json

- 现象：Factor Design 会写 `candidate_factors.json`、run-local `candidate_factors/<id>.json` 和全局 `factor_library/<id>.json`，但 readiness 过去没有验证全局 factor library 与当天候选一致。
- 风险：候选因子生成成功但长期因子库目录漏写、旧写或字段漂移时，系统仍可能通过“自动生成新因子”证据，后续 backtest/research 复用到陈旧因子定义。
- 修复：新增 `_factor_library_matches_candidates` 和 `latest_factor_library_matches_candidates`，逐个检查 `factor_library/<factor_id>.json` 的 `factor_id`、`created_at_run`、`formula_key`、`expression` 与 `candidate_factors.json` 当前 run 一致。
- Regression：把 production-ready fixture 中 `factor_library/F1.json.created_at_run` 改成 `20260603`，确认 readiness 降为 `not_production_ready`。
- 验证：self-audit 目标测试 `29 passed`、入口目标集 `47 passed`、MVP 子集 `72 passed`；离线 `run_daily.sh` smoke 证明真实候选 5 个均匹配 factor_library。

## 2026-06-05 — Daily report was only manifest-level evidence

- 现象：`daily_report.md` 已是 required artifact，但 readiness 过去只通过 manifest/非空间接覆盖它，没有解析日报是否对应当前运行、是否包含 agent 状态和关键输出摘要。
- 风险：陈旧日报或占位日报只要被 manifest 哈希记录，就可能和 365 天生产证据一起通过，用户看到的日报无法证明当天真的完成 Research/Design/Backtest/Critique/Evolve/Save。
- 修复：新增 `_daily_report_is_current_evidence` 和 `latest_daily_report_is_current_evidence`，检查当前 `Run date`、标题、Agent Status/Summary/Top Backtest Results/Files 章节、核心计数字段、关键文件引用，以及除 `artifact_manifest` 外的 required agent 状态行。
- Regression：把 production-ready fixture 的 `daily_report.md` 改成前一天且缺章节，刷新 manifest 后 readiness 降为 `not_production_ready`。
- 验证：self-audit 目标测试 `28 passed`、入口目标集 `46 passed`、MVP 子集 `71 passed`；离线 `run_daily.sh` smoke 证明真实日报 `latest_daily_report_is_current_evidence=True`。

## 2026-06-05 — Self-audit pass was not enough current evidence

- 现象：readiness 过去的 `latest_self_audit_pass` 可以由 run history 的 `self_audit_status=pass` 或一个极简 `self_audit.json` 的 `status=pass` 满足，没有要求 self-audit 文件自身带当前 `run_date`、完整 checks 和足够 score。
- 风险：365 天生产证据可能混入陈旧或空壳 `self_audit.json`，导致当前运行没有真正完成自审仍被历史摘要掩盖。
- 修复：新增 `REQUIRED_SELF_AUDIT_CHECKS` 和 `_self_audit_is_current_evidence`；production readiness 新增 `latest_self_audit_is_current_evidence`，要求当前日期、`status=pass`、`score>=0.9`、全部关键 checks 存在且为 true。
- Regression：构造 365 天生产证据齐全后把 `self_audit.json.run_date` 改成 `20260603`，确认 readiness 降为 `not_production_ready`，且 `latest_self_audit.current_complete_evidence=false`。
- 验证：self-audit 目标测试 `27 passed`、入口目标集 `45 passed`、MVP 子集 `70 passed`；离线 `run_daily.sh` smoke 证明真实产物 `latest_self_audit_is_current_evidence=True` 且 `missing_required_checks=0`。

## 2026-06-05 — Cron example could drift from schedule.json

- 现象：`schedule.json` 和 `cron_example.txt` 都已成为 required artifacts，但 readiness 过去只判断 `schedule.json` 是否 daily `bash run_daily.sh`，没有验证人工安装用的 cron 示例是否和机器可读 schedule 一致。
- 风险：如果 `cron_example.txt` 是陈旧 weekday 频率、旧 repo 路径或错误脚本，manifest/self-audit 仍可能通过，后续人工按错误 cron 安装会破坏每日无人值守目标。
- 修复：`agent.readiness_report` 新增 `_cron_example_matches_schedule` 和 `latest_cron_example_matches_schedule`，要求 cron 示例存在、非空、包含 `schedule.json.cron_line`，且文本里包含 `bash` 和 `run_daily.sh`；`schedule_evidence` 输出 presence/path/match 状态。
- Regression：构造 production-ready fixture 后把 `cron_example.txt` 改成 `1-5` weekday stale line，刷新 manifest，再确认 readiness 降为 `not_production_ready`。
- 验证：`python -m py_compile agent/*.py`、调度/self-audit/daily `37 passed`、入口目标集 `44 passed`、MVP 子集 `69 passed`；离线 `run_daily.sh` smoke 证明真实生成路径下 cron match gate 为 true。

## 2026-06-05 — Artifact manifest required paths were too narrow

- 现象：readiness 过去只要求 artifact manifest 包含 `daily_report.md`、`pipeline_state.json`、`self_audit.json`、`READINESS_REPORT.md`。
- 风险：如果 agent 输出文件缺失或没有进入 manifest，系统仍可能通过 artifact gate，长期审计无法回放每天的 market/research/factor/data/backtest/critic/evolution 产物链。
- 修复：`READINESS_REPORT.REQUIRED_MANIFEST_PATHS` 复用 `self_audit.REQUIRED_RUN_FILES`，并额外要求 `daily_report.md`、`self_audit.md`、`READINESS_REPORT.json/md` 和 `run_daily_invocation_latest.json`。
- 边界：直接调用 `daily_pipeline.run()` 不负责 shell invocation，因此对应单元测试不要求 manifest 中出现 `run_daily_invocation_latest.json`；真正的 `bash run_daily.sh` entrypoint 会写 invocation 后刷新 readiness/manifest，smoke 已验证该路径包含 invocation。
- 验证：expanded manifest shell smoke 输出 `SMOKE 0 not_production_ready True [] True`，说明核心 required paths 均存在且 manifest required files gate 为 true；MVP 子集 `63 passed`。

## 2026-06-05 — 365-day readiness could pass empty research runs

- 现象：`READINESS_REPORT` 的 production evidence 过去要求 pipeline complete、自审 pass、live sources、fresh data，但没有要求 run history 里的 `counts` 证明当天确实生成过 ideas、candidate factors 和 backtest results。
- 风险：如果 365 天每天都跑完 shell/data/source/knowledge 流程，但候选因子生成或回测为空，系统仍可能被计为 production-ready，与“每天自动发现新因子并回测”的目标不一致。
- 修复：新增 `_run_has_research_activity`，要求 `counts.ideas > 0`、`counts.candidate_factors > 0`、`counts.backtest_results > 0`；`_run_has_production_evidence` 必须同时满足该条件；readiness JSON/Markdown 输出 active research/backtest 计数、日期、连续 streak 和 blocker。
- Regression：构造 365 天 live source、fresh data、successful invocation、source snapshots、knowledge saves，但 `candidate_factors=0` / `backtest_results=0`，确认仍为 `not_production_ready`。
- 复现证据：离线 smoke 的真实 `bash run_daily.sh` 产生 `counts={'ideas': 3, 'candidate_factors': 5, 'backtest_results': 5, ...}`，`latest_run_has_research_activity=True`；MVP 子集 `63 passed`。

## 2026-06-05 — GPU alpha backtests must be submitted through sbatch

- 现象：登录节点不能直接代表 GPU 环境；alpha GPU 回测必须申请 Slurm 资源后在计算节点执行。
- 正确流程：先设置 shell 环境变量，再执行 `bash scripts/submit_alpha_gpu_backtest.sh`，launcher 内部调用 `sbatch --export=ALL scripts/alpha_gpu_backtest.sbatch`。
- 避坑：不要用 `sbatch --export=ALL,ALPHA_HORIZONS=1,5,10,20 ...` 直接传逗号列表，Slurm 会按逗号拆分导致作业只看到部分值。
- 本轮修复：新增 A027-A030 后提交 job `29532`，参数为 `ALPHA_CANDIDATES=A027,A028,A029,A030`、`ALPHA_HORIZONS=1,5,10,20`、`ALPHA_FAST=0`、`ALPHA_BACKEND=torch_cuda`；提交后 `squeue` 显示在 A800 `gpu2` 运行。
- 进一步修复：新增 `ALPHA_COSTS` 参数，避免只测 10bps。A029 H5 cost sensitivity job `29537` 使用 `ALPHA_COSTS=5,10,20,30` 完成，stderr 为空。
- Reviewer root cause：A029 不能 promote 的主因不是 GPU/速度，而是 backtest protocol blocker：未来 exit fillability 造成 `NaN` 样本丢弃，H>1 缺少真实 sub-book 持仓账本，且 size exposure 高。
- 复现补充：launcher/sbatch 默认参数已改成 A029 H5 多成本并打印 `ALPHA_COSTS`。job `29557` 在 A800 `gpu2` 完成，`torch.cuda_available=True`，stderr 为空，结果与 `29537` 一致；因此“为什么用 CPU”不是当前 blocker，正确路径是登录节点轻量检查 + `sbatch` 申请 GPU。

## 2026-06-05 — Source snapshot readiness was too summary-based

- 现象：readiness 的 365 天 source snapshot gate 只检查 `source_quality` 是否 live/full coverage，没有要求 JSONL snapshot 自身包含可回放的源条目。
- 风险：构造或异常写入的 `source_quality` 摘要可能让 `source_snapshots.jsonl` 在没有任何 source items 的情况下被计为 production-grade source evidence。
- 修复：新增 `_source_snapshot_is_production_evidence`，要求 `source_quality` 通过、`item_count > 0`、`source_status` 非空，且每个 source `status=ok` 并有正的 `items` 数；readiness 的 production source snapshot 日期改用该函数。
- 验证：新增空 snapshot regression；`tests/test_quant_self_audit.py` 为 `20 passed`，agent source 测试 `14 passed`，量化 MVP 子集 `58 passed`。离线 smoke 仍可运行，但不会把离线/空研究源 snapshot 计入 365 天 production evidence。

## 2026-06-05 — Run history missed final evidence agents

- 现象：`daily_pipeline.run` 在 `self_audit` 后立即追加 `run_history.jsonl`，此时 `readiness_report` 和 `artifact_manifest` 尚未运行；最终 `pipeline_state.json` 有这些 agent，但长期 JSONL history 没有。
- 风险：365 天审计若只看 `run_history.jsonl`，会误以为每天没有完成 readiness/report artifact 证据闭环；同时 readiness 通过合并 pipeline_state 可能掩盖 JSONL 不完整。
- 修复：新增 `_build_run_history_record` 和 `_replace_latest_run_history_record`。最终 readiness/artifact_manifest 完成后，用最终 agent status 替换当前 run_date 的最后一条 JSONL 记录，并更新 `run_history_latest.json`；保留坏 JSONL 行和其它日期记录。
- 验证：`run_daily.sh` smoke 显示 `run_history.jsonl` 仍只有 1 行，且 latest `agent_status.readiness_report/artifact_manifest` 均为 `ok`；pipeline/self-audit 目标测试 `30 passed`，量化 MVP 子集 `58 passed`。

## 2026-06-05 — Bad run dates were accepted before config validation

- 现象：`load_config` 直接接收 `QUANT_DATE` / `QUANT_RUN_DATE` 字符串，非法值会进入 run_dir、invocation、run_history 等路径和证据字段。
- 风险：错误日期会污染长期 daily_logs/JSONL；readiness 的 streak 解析虽然会失败，但问题发生太晚，且原先配置解析失败时 entrypoint 可能没有 invocation 记录。
- 修复：配置入口要求 `YYYYMMDD` 为 8 位数字且是真实日历日期；`run_entrypoint` 在 `_base_record` 失败时写 fallback invocation error record，包含 env 中的 run_date、output_root、knowledge_root 和 `config_loaded=false`。
- 验证：非法 `QUANT_DATE=20260631` 的 `bash run_daily.sh` 返回 1，并写入 `run_daily_invocation_latest.json`：`status=error`、`exit_code=1`、`run_date=20260631`、`config_loaded=false`、`error.type=ValueError`。正常 `QUANT_RUN_DATE=20260605` smoke 仍成功。

## 2026-06-05 — Factor Design skipped failures had no audit trail

- 现象：Factor Design 会读取 factor database 和 failure memory 来跳过已 kill 的公式，但输出只包含保留下来的候选；被跳过的候选、命中的 key、failure memory parse error 都没有进入日报或 research log。
- 风险：长期无人值守时某天候选数变少，无法区分是没有研究想法、模板缺失，还是失败记忆去重生效；坏的 `failure_memory.jsonl` 行会被 Factor Design 静默忽略。
- 修复：`candidate_factors.json` 新增 `skipped_factors` 和 `failed_memory_audit`；Factor Design 使用 `read_jsonl_records` 读取 failure memory 并 quarantine 坏行；日报和 research log 都记录 skipped count / audit。
- 验证：新增 regression 覆盖命中失败记忆的 skip audit 和 corrupt failure memory quarantine；目标测试 `18 passed`，量化 MVP 子集 `61 passed`。

## 2026-06-05 — Backtests lacked dataset hash provenance

- 现象：Backtest Agent 从 `dataset_manifest.json.dataset_path` 读取 parquet，但 `dataset_manifest.json` 没有 dataset hash，`backtest_results.json` 也没有记录所用 dataset 的 hash/provenance。
- 风险：`daily_dataset.parquet` 在 Data Agent 和 Backtest Agent 之间被改写或损坏时，回测仍会产出结果；长期审计只能依赖最终 artifact manifest，不能直接从 backtest result 证明其输入数据集。
- 修复：Data Agent 写 `dataset_sha256` / `dataset_size_bytes`；Backtest Agent 读取前校验 SHA256，hash mismatch 直接抛错并进入 pipeline error；Backtest output、日报和 research log 都记录 dataset provenance。
- 验证：新增篡改 parquet 后 backtest 拒绝运行的 regression；端到端 smoke 证明 manifest hash 与 backtest provenance hash 一致且 `hash_verified=true`；目标测试 `29 passed`，量化 MVP 子集 `62 passed`。

## 2026-06-05 — Evolution output could pass with stale per-factor files

- 现象：readiness 过去读取 `next_generation_factors.json`，但没有检查 `next_generation_factors/<factor_id>.json` 是否存在且内容一致。
- 风险：长期无人值守时，如果 evolution agent 汇总文件和逐因子文件不一致，后续 factor design 或人工审计可能使用过期公式、父因子或状态。
- 修复：新增 `_next_generation_files_match_payload` gate，逐个核对 `factor_id`、`parent_factor_id`、`formula_key`、`status`；readiness blocker 和 `next_generation_evidence` 会暴露 mismatch。
- 验证：新增篡改逐因子 `formula_key` 的 regression；`tests/test_quant_self_audit.py` 为 `32 passed`，组合测试 `50 passed`，量化 MVP 子集 `75 passed`；离线 `run_daily.sh` smoke 显示 next-generation 文件匹配为 true。

## 2026-06-05 — Research log latest could drift from daily artifacts

- 现象：readiness 过去要求 `research_log_latest.json` 指向当前 run date，并要求 365 天 `research_log.jsonl` 有 factor database update，但没有核对 latest 研究日志是否真的对应当天 events/ideas/factors/backtests/critique/evolution/data health。
- 风险：长期运行中如果 latest pointer 被旧内容覆盖，或 knowledge-base 汇总写入漏字段，系统可能把不一致的研究链条当作可审计长期记忆。
- 修复：`agent.knowledge_base` 在 backtest 摘要中写入 `result_factor_ids`；新增 `_research_log_matches_current_outputs`，核对事件数、想法数、候选 ids、回测 ids、critic 数、next-generation ids 和 data health 摘要。
- 验证：新增篡改 `research_log_latest.json.backtest.result_factor_ids` 的 regression；self-audit/readiness 测试 `33 passed`，组合测试 `51 passed`，量化 MVP 子集 `76 passed`；离线 `run_daily.sh` smoke 显示 research log consistency 为 true。

## 2026-06-05 — Data latest pointer could hide stale dataset evidence

- 现象：readiness 过去检查 `data_health_latest.json.run_date` 是否为当前日期，并检查 365 天 data health JSONL 数量/连续性，但没有核对 latest 文件和当天 `data_health.json` / `dataset_manifest.json` 是否一致。
- 风险：如果 latest 数据健康记录被旧 hash 或旧 row count 覆盖，长期审计可能把错误 dataset provenance 当成当天数据证据。
- 修复：新增 `_data_health_latest_matches_current_outputs`，核对 status/source mode/rows/stocks/dates/freshness/checks/domain coverage 和 dataset SHA256/size；报告输出 `data_latest_evidence`。
- 验证：新增篡改 latest dataset SHA256 regression；self-audit/readiness 测试 `34 passed`，组合测试 `52 passed`，量化 MVP 子集 `77 passed`；离线 `run_daily.sh` smoke 显示 latest/current dataset hash 一致。

## 2026-06-05 — Source snapshot latest only proved one agent wrote last

- 现象：`source_snapshots_latest.json` 只能指向最后写入的 source snapshot，通常是 `research_agent`；readiness 过去没有核对当前 run 的 market 和 research 两个 source snapshot 文件是否都与当天 agent 输出一致。
- 风险：长期运行中一个 source snapshot 文件或 JSONL 记录可能缺失/漂移，但 latest pointer 仍然为当前日期，掩盖 market/research source 证据链断裂。
- 修复：新增 `_source_snapshots_match_current_outputs`，核对 run-dir 两个 snapshot 文件和同日 JSONL 记录的 `source_status`、`source_quality`、`item_count` 是否分别匹配 `daily_events.json` 和 `research_ideas.json`。
- 验证：新增篡改 `source_snapshots/research_agent.json.item_count` regression；self-audit/readiness 测试 `35 passed`，组合测试 `53 passed`，量化 MVP 子集 `78 passed`；离线 `run_daily.sh` smoke 显示同日 snapshot agents 为 market + research。

## 2026-06-05 — Artifact manifest latest could drift from run manifest

- 现象：readiness 检查当前 run-dir `artifact_manifest.json` 和 hash verification，但没有核对 `reports/artifact_manifest_latest.json` 是否仍指向同一份 manifest。
- 风险：长期无人值守审计常会读取 latest 文件；如果 latest manifest 漂移或陈旧，外部审计可能看到与当前 run 不一致的 artifact hash 证据。
- 修复：新增 `_artifact_manifest_latest_matches_current`，核对 run date、file count、total size 和每个 `relative_path` 的 SHA256；报告输出 latest/current 匹配状态。
- 验证：新增篡改 `artifact_manifest_latest.json.file_count` regression；self-audit/readiness 测试 `36 passed`，组合测试 `54 passed`，量化 MVP 子集 `79 passed`；离线 `run_daily.sh` smoke 显示 latest/current manifest file count 都为 49。

## 2026-06-05 — Self-audit could be current but not tied to current outputs

- 现象：readiness 已要求 `self_audit.json` 当前日期、`status=pass`、`score>=0.9` 和完整 checks，但没有核对 self-audit 内的 counts/source/preflight/freshness 是否来自当前 run-dir 产物。
- 风险：陈旧或伪造的 self-audit 可以保留当前日期和 true checks，却记录错误的回测数量、知识库数量、数据 freshness 或 source quality，从而掩盖当天产物漂移。
- 修复：新增 `_self_audit_matches_current_outputs`，核对 self-audit counts、`preflight`、`data_freshness`、market/research `source_quality` 与当前 `daily_events.json`、`research_ideas.json`、`candidate_factors.json`、`backtest_results.json`、`data_health.json`、`preflight.json`、factor database 一致。
- 验证：新增篡改 `self_audit.json.counts.backtest_results=999` regression；self-audit/readiness 测试 `37 passed`，组合测试 `55 passed`，量化 MVP 子集 `80 passed`；离线 `run_daily.sh` smoke 显示 self-audit counts 与 current counts 一致且 gate 为 true。

## 2026-06-05 — Candidate factor directory was not part of readiness consistency

- 现象：Agent 3 输出目录是 `candidate_factors/`，但 readiness 过去只核对汇总 `candidate_factors.json` 和全局 `factor_library/`，没有检查 run-local 逐因子文件是否仍与当天 payload 一致。
- 风险：长期运行中 `candidate_factors/<factor_id>.json` 可能缺失或被旧公式覆盖；artifact manifest 会记录文件存在和 hash，但 production readiness 不知道它是否语义上匹配当天候选。
- 修复：新增 `_candidate_factor_files_match_payload`，逐个核对 run-local candidate 文件的 `factor_id`、`created_at_run`、`formula_key`、`expression`、`status`；readiness 新增 blocker 和 evidence。
- 验证：新增只篡改 run-local `candidate_factors/F1.json.formula_key` 的 regression；self-audit/readiness 测试 `38 passed`，组合测试 `56 passed`，量化 MVP 子集 `81 passed`；离线 `run_daily.sh` smoke 显示 5 个真实候选文件均匹配 payload。

## 2026-06-05 — Failure analysis could be a stale placeholder

- 现象：`failure_analysis.md` 是 Critic Agent 的用户可读核心输出，但 readiness 过去只通过 manifest 检查它存在并有 hash，没有核对它是否对应当前 `critique.json`。
- 风险：长期运行中 failure analysis 可能停留在旧日期、旧 factor 或占位文本；`critique.json` 与 failure memory 仍可能正确，导致日报/人工审计看到的失败原因文本失真。
- 修复：新增 `_failure_analysis_matches_critique`，要求 markdown 包含当前 run date，以及每个 critique 的 factor id、decision、issues、leakage_check、stability score、collinearity score；readiness 新增 blocker 和 `failure_analysis_evidence`。
- 验证：新增篡改 `failure_analysis.md` 为旧日期/旧 factor 的 regression；self-audit/readiness 测试 `39 passed`，组合测试 `57 passed`，量化 MVP 子集 `82 passed`；离线 `run_daily.sh` smoke 显示真实 failure analysis 与 critique payload 匹配。

## 2026-06-05 — Backtest result directory was not semantically checked

- 现象：Backtest Agent 输出目录是 `backtest_results/`，但 readiness 过去只核对汇总 `backtest_results.json` 与 factor database，没有检查 run-local 逐因子 backtest 文件是否仍与汇总一致。
- 风险：长期运行中 `backtest_results/<factor_id>.json` 可能缺失、损坏或保留旧 RankIC/portfolio 指标；artifact manifest 会记录文件 hash，但 production readiness 不知道它是否语义上匹配当天回测汇总。
- 修复：新增 `_backtest_result_files_match_payload`，逐个核对 `factor_id`、`formula_key`、`expression`、`rankic_mean`、`decision`、`portfolio`；readiness 新增 blocker 和 evidence。
- 验证：新增只篡改 run-local `backtest_results/F1.json.rankic_mean` 的 regression；self-audit/readiness 测试 `40 passed`，组合测试 `58 passed`，量化 MVP 子集 `83 passed`；离线 `run_daily.sh` smoke 显示 5 个真实 backtest 逐文件均匹配汇总 payload。

## 2026-06-05 — Backtest summary could carry stale dataset provenance

- 现象：Backtest Agent 已在 `backtest_results.json.dataset_provenance` 写入 dataset hash，但 readiness 只核对 `data_health_latest.json` 与 `dataset_manifest.json`，以及 backtest 逐因子文件与 summary，没有直接核对 backtest summary 声称使用的数据集是否就是当前 run 的 manifest。
- 风险：旧 `backtest_results.json` 或手工拼接的 summary 可能保留正确信号指标，却对应另一个 `daily_dataset.parquet`；长期审计会误以为当天回测基于当前数据集。
- 修复：新增 `_backtest_dataset_provenance_matches_manifest`，要求 `hash_verified=true`，并核对 dataset SHA256、size、rows、stocks、dates、source mode、health status；新增 blocker `latest backtest dataset provenance does not match current dataset_manifest.json` 和 hash evidence。
- Regression：只篡改 `backtest_results.json.dataset_provenance.dataset_sha256` 为 stale 值，确认 readiness 降为 `not_production_ready`，而 `latest_backtest_result_files_match_payload` 与 `latest_factor_database_matches_backtests` 仍为 true，说明新 gate 覆盖的是独立盲点。
- 验证：`python -m py_compile agent/*.py` 通过；self-audit/readiness 测试 `41 passed`，组合测试 `59 passed`，量化 MVP 子集 `84 passed`；离线 `bash run_daily.sh` smoke 显示 backtest/current dataset hash 完全一致。

## 2026-06-05 — Research log could preserve stale backtest provenance

- 现象：`knowledge_base.py` 已把 `backtest_results.json.dataset_provenance` 写入 `research_log_latest.json.backtest.dataset_provenance`，但 readiness 过去只核对 research log 的 result ids 和数据健康摘要，没有核对这份长期日志里的回测输入数据来源。
- 风险：backtest summary 可以正确匹配当前 manifest，但长期 knowledge-base research log 仍保存旧 dataset hash；365 天审计会留下不可复现的研究链条。
- 修复：`_research_log_matches_current_outputs` 现在要求 research log 的 `backtest.dataset_provenance` 与当前 `backtest_results.json.dataset_provenance` 完全一致；`research_log_evidence` 输出两侧 dataset SHA256。
- Regression：只篡改 `research_log_latest.json.backtest.dataset_provenance.dataset_sha256`，确认 `latest_research_log_matches_current_outputs=false`，同时 backtest-vs-manifest gate 仍为 true，说明 failure 属于 knowledge-base provenance 漂移。
- 验证：`python -m py_compile agent/*.py` 通过；self-audit/readiness 测试 `42 passed`，组合测试 `60 passed`，量化 MVP 子集 `85 passed`；离线 `bash run_daily.sh` smoke 显示 research log/current backtest dataset hash 一致。

## 2026-06-05 — Factor database could keep stale portfolio metrics

- 现象：`latest_factor_database_matches_backtests` 过去只核对 factor database 同日记录的 `formula_key`、`rankic_mean` 和 critic-resolved `decision`。
- 风险：长期 `factor_database/factors.json` 可能保存旧 portfolio、旧公式文本、旧 expression 或旧 critic issues；readiness 仍会认为 knowledge base 已更新，后续 factor design 和人工审计会基于错误历史结果。
- 修复：收紧 `_factor_database_matches_latest_results`，逐因子核对 `decision`、`issues`、`name`、`formula`、`formula_key`、`expression`、`rankic_mean`、`portfolio`；`factor_database_evidence.matched_fields` 输出覆盖字段。
- Regression：只篡改同日 factor database 记录的 `portfolio.ann_return_net`，确认 `latest_factor_database_matches_backtests=false`，而 current backtest 逐文件一致和 dataset provenance gate 仍为 true，说明 failure 是长期因子库漂移。
- 验证：`python -m py_compile agent/*.py` 通过；self-audit/readiness 测试 `43 passed`，组合测试 `61 passed`，量化 MVP 子集 `86 passed`；离线 `bash run_daily.sh` smoke 显示 5 条同日 factor database 记录与当前 backtest/critic 完整匹配。

## 2026-06-05 — Run history latest could have current date but stale contents

- 现象：readiness 过去要求最新 `run_history.jsonl` 记录日期等于当前 run date，并用其中 counts/source/data 判断 365 天 production evidence，但没有核对这条主历史记录是否真的来自当前 run-dir 产物。
- 风险：`run_history.jsonl` 最新行可以保留当前日期和非零 counts，却记录错误 backtest 数量、source quality、data health、自审分数或 agent status；365 天主账本会被污染。
- 修复：新增 `_run_history_matches_current_outputs` 和 `latest_run_history_matches_current_outputs` gate，核对 pipeline status、self-audit status/score、agent status、counts、market/research source quality、data health/source/freshness/checks/domain coverage。
- Regression：只篡改最新 run history 的 `counts.backtest_results=999` 并保持 run date 当前，确认 readiness 降为 `not_production_ready`，blocker 指向 run history 与当前 daily outputs 不匹配。
- 验证：`python -m py_compile agent/*.py` 通过；self-audit/readiness 测试 `44 passed`，组合测试 `62 passed`，量化 MVP 子集 `87 passed`；离线 `bash run_daily.sh` smoke 显示 latest/current counts 完全一致。

## 2026-06-05 — Daily report could be complete but numerically stale

- 现象：`_daily_report_is_current_evidence` 过去只检查 run date、固定章节、required agent 行和文件引用；fixture 中 `daily_report.md` 写着 events=3/ideas=2/backtests=2，但当前 JSON 产物实际是 1/1/1，readiness 仍可通过。
- 风险：用户最常看的日报可能展示旧 counts 或旧 dataset hash；机器 JSON 证据正确但人工审计被误导。
- 修复：`_daily_report_is_current_evidence` 现在核对事件数、market/research source mode、研究想法数、候选数、回测数、backtest dataset SHA 前缀、raw candidate 数、critic promote 数、data health、preflight 和 self-audit 状态。
- Regression：只把 `daily_report.md` 的 `backtested factors` 改成 `999`，保持日期和章节完整，确认 `latest_daily_report_is_current_evidence=false`。
- 验证：`python -m py_compile agent/*.py` 通过；self-audit/readiness 测试 `45 passed`，组合测试 `63 passed`，量化 MVP 子集 `88 passed`；离线 `bash run_daily.sh` smoke 显示日报关键 counts 与当前产物一致。

## 2026-06-05 — run_audit final state was a stale mixed snapshot

- 现象：新增 `run_audit.state` vs `pipeline_state.json` 一致性检查后，离线 `bash run_daily.sh` smoke 显示 `latest_run_audit_is_current_evidence=false`；`run_audit.state.agents` 有 13 个 agent，但 `completed_agents` 只有 12 个，且缺 `artifact_manifest_path`。
- 根因：`run_audit.json` 最初写在核心 agent 后，后续又更新 `pipeline_state.json`；修复时第一次传入的是较早的 `final_state` 变量。同时 `_write_pipeline_state` 直接保存 `statuses` 列表引用，后续追加 artifact agent 后让 audit 变成半新半旧的浅拷贝快照。
- 修复：抽出 `_write_run_audit`；最终 `_write_pipeline_state` 的返回值赋回 `final_state` 后再写 audit；`pipeline_state.agents`、`pipeline_state.lock`、`run_audit.lock`、`run_audit.state` 均用 `copy.deepcopy` 固化快照。
- Regression：`test_readiness_blocks_run_audit_state_that_does_not_match_pipeline_state` 覆盖 run_audit agent 列表少于 pipeline state 的情况。
- 复现证据：修复后离线入口 smoke 输出 `run_audit_current=True`、`state_matches_pipeline_state=True`、`manifest_verified=True`、`daily_report_current=True`；`python -m py_compile agent/*.py`、self-audit/readiness `46 passed`、聚合 `64 passed`、量化全集 `89 passed`。
- GPU 相关坑同步：不要在登录 shell 直接判断 GPU 或跑 CUDA 回测；需要通过 `bash scripts/submit_alpha_gpu_backtest.sh` 提交 Slurm/sbatch，且逗号列表参数必须先放进 shell 环境变量。

## 2026-06-05 — artifact_manifest latest check had self-referential readiness drift

- 现象：离线 `bash run_daily.sh` smoke 后，`READINESS_REPORT.json.artifact_manifest.latest_total_size_bytes=308272`，但最终 `artifact_manifest_latest.json.total_size_bytes=306837`；同时 readiness gate 仍显示 `artifact_manifest_latest_matches_current_manifest=true`。
- 根因：入口成功后会刷新 readiness/manifest 多轮。`artifact_manifest` 记录 `READINESS_REPORT.json` / `.md` 的 hash 和 size，但 readiness 写完自身后，最终 manifest 总会比 readiness payload 晚；若把 readiness 自身文件纳入 latest/current 总量比较，会形成不可消除的自引用循环。
- 修复：`_artifact_manifest_latest_matches_current` 改为比较 stable manifest records，跳过 `artifact_verifier.MUTABLE_READINESS_PATHS`；evidence 输出 stable/raw totals，便于审计真实产物一致性。
- Regression：`backtest_results.json` 这类稳定文件 hash 被篡改仍会阻塞；`READINESS_REPORT.json` hash/size 被篡改不会误报 latest manifest stale。
- 复现证据：修复后离线入口 smoke 输出 `manifest_gate=True`、`manifest_verified=True`、raw total `308521` vs `307086`、stable total `269445` vs `269445`、`run_audit_current=True`。
- 验证：`python -m py_compile agent/*.py`、self-audit/readiness `47 passed`、聚合 `65 passed`、量化全集 `90 passed`、sbatch 脚本 `bash -n` 均通过。

## 2026-06-05 — failed run_daily entrypoints did not refresh latest readiness evidence

- 现象：`agent.run_entrypoint` 成功路径会写 invocation 后刷新 readiness/manifest；失败路径只写 `run_daily_invocation_latest.json`，不会刷新 `READINESS_REPORT.json` 和 `artifact_manifest_latest.json`。
- 风险：无人值守运行失败后，用户打开最新 readiness 可能仍看到上一轮审计结果；失败证据只在 invocation JSONL 中，未进入最新报告/manifest 证据链。
- 修复：新增 `_refresh_failure_evidence(record)`，当 `config_loaded=true` 时在异常路径 best-effort 运行 readiness/manifest 双轮刷新；若刷新本身失败，把 `failure_evidence_refresh_error` 写回 invocation，不覆盖原始失败类型和退出码。
- Regression：`test_run_entrypoint_records_failed_invocation` 现在要求失败入口生成 `READINESS_REPORT.json`、`artifact_manifest_latest.json`，且 readiness 中 `run_daily_invocation_success=false`。
- 复现证据：用 fresh `.quant_daily.lock` 触发真实入口失败，`python -m agent.run_entrypoint` 返回 1；latest invocation 为 `error`/`RuntimeError`；readiness 为 `not_production_ready` 且 invocation present=true/success=false；manifest 包含 `run_daily_invocation_latest.json`。
- 验证：`python -m py_compile agent/*.py`、entrypoint `7 passed`、聚合 `65 passed`、量化全集 `90 passed`、sbatch 脚本 `bash -n` 均通过。

## 2026-06-05 — interrupted daily_pipeline only wrote pipeline_state, not run_audit

- 现象：`daily_pipeline.run` 的 `except BaseException` 分支只写 `pipeline_state.json(status=interrupted)`，没有更新 `run_audit.json`。
- 风险：无人值守运行被中断时，长期审计文件 `run_audit.json` 可能缺失或保留核心 agent 后的旧状态；用户需要同时查 pipeline_state 才能复盘 active agent/traceback。
- 修复：异常分支保存 `_write_pipeline_state(..., status=\"interrupted\", error=...)` 的返回值，并立即 `_write_run_audit(cfg, lock_info, interrupted_state)`。
- Regression：`test_daily_pipeline_writes_interrupted_checkpoint_on_uncaught_exception` 现在断言 `run_audit.state == pipeline_state`，包含 `KeyboardInterrupt`、`fatal_agent` 和 completed agents。
- 复现证据：正常离线 `bash run_daily.sh` smoke 仍输出 `run_audit_current=True`、`state_matches_pipeline_state=True`、`audit_state_status complete True`；异常路径由测试覆盖。
- 验证：`python -m py_compile agent/*.py`、daily pipeline + entrypoint `17 passed`、聚合 `65 passed`、量化全集 `90 passed`、sbatch 脚本 `bash -n` 均通过。

## 2026-06-05 — transient retry failures were hidden after successful retry

- 现象：agent 首次失败但后续 retry 成功时，最终 `pipeline_state.json` 只显示 `attempt=2` 和 `status=ok`，没有记录第一轮失败原因。
- 风险：365 天无人值守运行中，网络/API/数据源间歇性失败会被成功 retry 掩盖；后续只能看到 attempt 数字，无法判断是哪类故障、是否集中在某个 agent 或数据源。
- 修复：`_run_agent_with_retries` 新增 `failed_attempts`，每次异常记录 attempt、duration、error 和 traceback 摘要；成功状态若发生过 retry，会带 `retries`；最终失败写入 `errors/<agent>.json` 时也带完整 retries。
- Regression：瞬时 `market_intelligence` 失败后成功时，断言 `state.agents[0].retries[0].error` 包含 `transient` 且没有 error 文件；永久 `data_agent` 失败时，断言 `errors/data_agent.json.retries[0].error` 包含模拟失败。
- 复现证据：正常离线 `bash run_daily.sh` smoke 输出 `state complete 13 []`，说明无失败时不会污染状态；run_audit 和 manifest gate 仍为 true。
- 验证：`python -m py_compile agent/*.py`、daily pipeline `10 passed`、聚合 `65 passed`、量化全集 `90 passed`、sbatch 脚本 `bash -n` 均通过。

## 2026-06-05 — daily_simulation could be mistaken for production proof

- 现象：`agent.daily_simulation` 直接调用 `daily_pipeline.run`，但 payload 使用 `status=pass`，容易被误读为 365 天生产就绪证据。
- 风险：本地多日仿真没有走 shell-level `bash run_daily.sh` invocation 记录，也通常是 offline/synthetic 数据；如果和 readiness 证据混用，会削弱“真实连续 365 天无人值守”的证明边界。
- 修复：simulation payload 改为 `simulation_pass` / `simulation_warning`，显式输出 `uses_shell_entrypoint=false`、`production_ready_evidence=false`、`evidence_scope=local_simulation_only` 和说明文字。
- 同步修复：simulation 每日 `RunConfig` 继承 `lock_stale_minutes` 和 `min_free_disk_mb`，避免压测环境与真实 daily 配置不一致。
- Regression/复现：测试检查 local-only 标记和 run audit 配置继承；smoke 输出 `SIM_SMOKE simulation_pass False False local_simulation_only`、history 2、latest `20260606`、config `77 1`。
- 验证：`python -m py_compile agent/*.py`、daily pipeline `10 passed`、聚合 `65 passed`、量化全集 `90 passed`、sbatch 脚本 `bash -n` 均通过。

## 2026-06-05 — alpha GPU rerun must use sbatch allocation

- 根因/约束：登录节点不能作为 GPU 可用性判断，也不应直接运行 CUDA alpha 回测；正式 GPU 回测必须用 Slurm `sbatch` 申请资源。
- 正确命令：`ALPHA_CANDIDATES='A029' ALPHA_HORIZONS='5' ALPHA_COSTS='5,10,20,30' ALPHA_FAST=0 ALPHA_BACKEND=torch_cuda bash scripts/submit_alpha_gpu_backtest.sh`。launcher 内部使用 `sbatch --export=ALL scripts/alpha_gpu_backtest.sbatch`，逗号列表先进入 shell 环境，避免 Slurm `--export=ALL,VAR=1,5` 解析截断。
- 复现证据：job `29571` 在 A800 `gpu2` 完成；stdout 记录 `CUDA_VISIBLE_DEVICES=0`、`torch.cuda_available=True`、device `NVIDIA A800-SXM4-80GB`、`ALPHA_COSTS=5,10,20,30`；stderr 为空。
- 结果解释：A029 H5 GPU 后端给出 RankIC `0.04490`，但 long-short 成本后年化在 20/30bps 下为负，因此资源问题已排除，剩余问题是 alpha/组合构造需要继续 repair。
- 验证：`bash -n scripts/submit_alpha_gpu_backtest.sh scripts/alpha_gpu_backtest.sbatch scripts/alpha_gpu_probe.sbatch` 通过；量化测试全集 `91 passed`。

## 2026-06-05 — schedule could prove cadence without proving cron logs were writable

- 现象：`schedule.json` 已证明 daily `bash run_daily.sh`，但 cron 重定向只写相对 `reports/daily_cron.log`，readiness 没有检查日志目录是否存在可写。
- 风险：crontab 安装后如果工作目录或 reports 目录异常，长期无人值守失败可能没有 cron 日志，后续只能从缺失产物推断问题。
- 修复：`agent.schedule` 生成绝对 cron log path，并创建/记录 log parent；`READINESS_REPORT` 的 schedule gate 要求 `log_parent_exists=true` 且 `log_parent_writable=true`；新增不可用日志目录 regression。
- 复现证据：离线 `bash run_daily.sh` smoke 输出 `schedule_gate=True`、`cron_example_gate=True`、`log_path=/home/lcc17/dl/reports/daily_cron.log`、`log_parent=True True`、manifest/invocation gate 均为 true。
- 验证：`python -m py_compile agent/*.py`、schedule/readiness `50 passed`、聚合 `67 passed`、量化测试全集 `92 passed` 均通过。

## 2026-06-05 — source snapshots lacked per-source replay metadata

- 现象：Market/Research source snapshots 记录了 `source_status` 和 items，但成功源没有响应大小/hash，失败源没有 `error_type`，离线/失败/成功状态都缺少统一 URL 证据；snapshot 文件本身也没有写入时间。
- 风险：365 天后只能看到某个 source 被计为 ok/error，难以复盘当天访问的是哪个 URL、内容是否变化、失败类型是否集中在网络/解析/站点响应。
- 修复：Market/Research agents 在 source status 中记录 URL；live 成功记录 `response_bytes`、`content_sha256`、`fetched_at`；失败记录 `error_type` 和 `fetched_at`；`source_cache.write_source_snapshot` 写入 `snapshot_written_at`。
- 复现证据：离线 `bash run_daily.sh` smoke 输出 `snapshot_written_at=True True`、`source_status_urls=True True`、`source_match=True`、manifest gate 为 true。
- 验证：`python -m py_compile agent/*.py`、source/readiness `64 passed`、聚合 `67 passed`、量化测试全集 `92 passed` 均通过。

## 2026-06-05 — stored formula_key formatting could bypass failed-factor memory

- 现象：`factor_design._failed_factor_keys` 直接信任历史记录中的 `formula_key` 字段；如果旧 `factor_database` 或 `failure_memory.jsonl` 写入了带空格/大小写差异的 formula key，当前候选的标准化 key 可能匹配不上。
- 风险：长期无人值守运行中，旧版本或人工导入的失败记录会因格式不同失效，导致系统重复研究已经 kill 的公式或重复生成相同 repair 子因子。
- 修复：新增 `factor_identity_keys`，对 `formula` 和 `formula_key` 同时加入 raw 与 normalized identity；`factor_design` 和 `evolution_agent` 共用该逻辑。
- Regression：格式化 `formula_key` 的旧 factor database 记录会阻止 `F_VOL_REV_5`；格式化成本修复 formula key 的 failure memory 会阻止 `BAD_VOL_PIVOT_COST`。
- 验证：`python -m py_compile agent/*.py`、factor/evolution/readiness `71 passed`、聚合 `67 passed`、量化测试全集 `94 passed` 均通过。

## 2026-06-05 — synthetic fallback did not explain which local data source failed

- 现象：`dataset_manifest.json` 记录 `source_mode=synthetic_fallback`，但没有记录 Data Agent 检查了哪些目录、窗口内找到多少 CSV、为什么 fallback。
- 风险：无人值守运行中如果某天数据同步失败，后续只能知道用了合成数据，无法判断是 `daily` 目录不存在、窗口内无文件、还是辅助数据域缺失。
- 修复：新增 `data_source_detail`，写入 manifest、data health 和 data health latest；记录 daily/metric/moneyflow/ST/basic 路径、存在性、CSV 数、选中文件数和 fallback reason。
- 复现证据：离线 `bash run_daily.sh` smoke 输出 `source_mode synthetic_fallback`、`fallback_reason daily_csv_missing_or_empty`、`daily_exists_selected False 0`、`production_data False`、manifest gate 为 true。
- 验证：`python -m py_compile agent/*.py`、data/readiness `62 passed`、聚合 `67 passed`、量化测试全集 `94 passed` 均通过。

## 2026-06-05 — factor database saved too little backtest evidence

- 现象：`knowledge_base.run()` 只保存 `rankic_mean`、`portfolio`、`decision` 和 `issues`，没有保存 `rankic_ir`、`rankic_positive_frac`、`long_short`、`cost_sensitivity`、样本 `rows/dates`、`horizon_days` 或 `decision_note`。
- 风险：长期运行后 factor database 可审计性不足；尤其 A 股 alpha promotion 依赖成本敏感性和 long-short 诊断，若这些字段没有持久化，review/readiness 无法证明结论来自同一份 backtest。
- 修复：knowledge base 持久化完整 backtest audit fields；readiness 使用同一组字段比对 factor database 与 `backtest_results.json`；新增 cost sensitivity mismatch regression。
- 复现证据：离线 `bash run_daily.sh` smoke 输出 factor database 5 条记录，增强字段全部为 true，`latest_factor_database_matches_backtests=True`。
- 验证：`python -m py_compile agent/*.py`、backtest/critic+self-audit `59 passed`、聚合 `68 passed`、量化测试全集 `95 passed` 均通过。

## 2026-06-05 — source snapshot production evidence was too weak

- 现象：source snapshots 已记录 URL、响应 hash、响应 bytes、fetch 时间和 snapshot 写入时间，但 `_source_snapshot_is_production_evidence` 只检查 source quality、`status=ok` 和 `items>0`。
- 风险：伪造或不完整的 live source 记录可能缺少可回放证据，却仍被计入 365 天生产级 source snapshot 日期。
- 修复：production source snapshot gate 要求 `snapshot_written_at`，且每个 ok source status 必须包含 URL、`fetched_at`、`content_sha256` 和正数 `response_bytes`。
- 复现证据：删掉 365 天 fixture 中第一天 market source 的 `content_sha256` 后，readiness 输出 `production_source_snapshot_dates=364`，并阻断 `has_365_source_snapshot_dates`。
- 离线 smoke：`bash run_daily.sh` 输出 `source_match=True`、`snapshot_written=[True, True]`，但离线 `skipped_offline` 无 content hash，`production_source_snapshot_dates=0`，符合生产证据边界。
- 验证：`python -m py_compile agent/*.py`、self-audit/readiness `51 passed`、聚合 `69 passed`、量化测试全集 `96 passed`、sbatch 脚本 `bash -n` 均通过。

## 2026-06-05 — data artifact production evidence was too weak

- 现象：`production_data_artifact_dates` 只通过 `source_mode`、freshness 和 domain usable 判断；缺少 dataset hash、size、rows/stocks/dates 一致性和 `data_source_detail` 的真实 CSV 来源要求。
- 风险：长期运行中，手写或损坏的 `data_health.jsonl` 记录可能被计入 365 天真实数据产物，即使没有可校验的数据集哈希或无法说明来自哪个本地 CSV 窗口。
- 修复：新增 `_data_artifact_is_production_evidence`，要求 manifest/health 一致、dataset SHA256 和 size 存在、rows/stocks/dates 为正、非 synthetic、无 fallback reason，且 daily CSV 目录存在并有窗口内选中文件。
- 复现证据：删掉 365 天 fixture 中第一天 `dataset_manifest.dataset_sha256` 后，readiness 输出 `production_data_artifact_dates=364`，并阻断 `has_365_data_artifact_dates`。
- 离线 smoke：`bash run_daily.sh` 输出 `dataset_hash=True` 但 `source_mode=synthetic_fallback`、`fallback_reason=daily_csv_missing_or_empty`，因此 `latest_data_artifact_is_production=False`、`production_data_artifact_dates=0`。
- 验证：`python -m py_compile agent/*.py`、self-audit/readiness `52 passed`、聚合 `70 passed`、量化测试全集 `97 passed`、sbatch 脚本 `bash -n` 均通过。

## 2026-06-05 — successful invocation did not prove bash run_daily.sh

- 现象：`run_daily_invocations.jsonl` 中 `status=success`、`exit_code=0` 的记录会被计入 successful run_daily invocation，即使它可能来自直接 `python -m agent.run_entrypoint` 调用。
- 风险：365 天 production readiness 目标要求用户只需执行 `bash run_daily.sh`；如果直接 Python 调用也计入 shell-level invocation，长期无人值守证据会混淆实际入口。
- 修复：`run_daily.sh` 设置 shell provenance 环境变量；`run_entrypoint` 写入 shell provenance；readiness 只把带 `shell_entrypoint=True`、存在的 `run_daily.sh` 脚本路径和 `bash run_daily.sh` 命令的成功记录计入 run_daily invocation。
- 复现证据：直接调用 `run_entrypoint.main()` 的单测中 `shell_entrypoint=False`；设置 run_daily shell provenance 时记录为 true；readiness regression 中成功但无 shell provenance 的 latest invocation 被阻断。
- 离线 smoke：真实 `bash run_daily.sh` 输出 `shell_entrypoint=True`、`entrypoint_script=/home/lcc17/dl/run_daily.sh`、`script_exists=True`、`entrypoint_command=bash run_daily.sh`、`readiness_invocation_success=True`。
- 验证：`python -m py_compile agent/*.py`、entrypoint+self-audit `61 passed`、聚合 `72 passed`、量化测试全集 `99 passed`、`bash -n run_daily.sh` 和 sbatch 脚本检查均通过。

## 2026-06-05 — knowledge save evidence did not prove factor ids were persisted

- 现象：`knowledge_save_dates` 只检查 `pipeline.run_quality=complete` 和 `factor_database_write.status=updated`，无法证明当天 backtest 结果对应的 factor ids 已经写入 factor database。
- 风险：research log 可以声称已更新知识库，但 saved factors 缺失、数量不符或 ids 不符时仍被计入 365 天 production knowledge-save evidence。
- 修复：`knowledge_base.run()` 在 complete pipeline 中写入 `saved_factor_count` 和 `saved_factor_ids`；`READINESS_REPORT` 要求 saved count 等于 backtest result id 数，saved ids 与 backtest ids 精确一致。
- 测试坑：`test_critic_evolution_and_knowledge_base_update` 原来没有写 `pipeline_state.json`，触发 standalone 分支；standalone 会落 DB 但不作为 production knowledge-save 证据。测试已改为完整 pipeline state 后断言 saved ids/count。
- 复现证据：365 天 fixture 中把第一天 `factor_database_write.saved_factor_ids` 改为空，readiness 输出 `knowledge_save_dates=364` 并阻断 365 天 knowledge-save gates。
- GPU 运行注意：A 股 alpha GPU 回测不能在登录节点直接用 CUDA，需通过 `scripts/submit_alpha_gpu_backtest.sh` 调 `sbatch` 申请 GPU；`.sbatch` 内部检查 `nvidia-smi` 和 `torch.cuda.is_available()`。
- 验证：`python -m py_compile agent/*.py`、backtest/critic+self-audit `63 passed`、schedule/self-audit/daily/entrypoint `73 passed`、量化测试全集 `100 passed`、Slurm 脚本 `bash -n` 均通过。

## 2026-06-05 — source snapshot metadata accepted weak replay evidence

- 现象：`_source_snapshot_is_production_evidence` 检查 URL、fetch time、content hash 和 response bytes 是否存在，但没有验证 ISO 时间格式、SHA256 hex 格式、HTTPS URL，也没有核对 snapshot `item_count` 与 source status 的 `items` 总数。
- 风险：365 天 live source 证据可能包含不可解析时间、假 hash、非安全 URL 或统计不一致的 snapshot，后续无法可靠复盘当天到底抓取了多少外部源内容。
- 修复：production source snapshot gate 现在要求可解析 `snapshot_written_at`/`fetched_at`、64 位 hex `content_sha256`、`https://` URL、正数 bytes，以及 `item_count == sum(source_status[].items)`。
- 复现证据：365 天 fixture 中只篡改第一天 market snapshot 的 `item_count`，readiness 输出 `production_source_snapshot_dates=364` 并阻断 source snapshot 365 天 gate。
- 离线 smoke：`bash run_daily.sh` 正常完成，offline snapshots 有写入时间但不计入 production source evidence，避免把离线 fallback 当作联网证据。
- 验证：`python -m py_compile agent/*.py`、source/readiness `71 passed`、聚合 `74 passed`、量化测试全集 `101 passed`、入口和 Slurm 脚本 `bash -n` 均通过。

## 2026-06-05 — successful run_daily invocation lacked complete timing proof

- 现象：`_invocation_is_successful_run_daily` 检查 status/exit code/shell provenance/config loaded，但不要求 `started_at`、`finished_at` 或正 `duration_sec`。
- 风险：手写或截断的 invocation 记录可以被计入 365 天 shell-level production invocation，即使无法证明当日运行何时开始、何时结束、持续多久。
- 修复：successful invocation gate 要求 started/finished 时间可解析且 duration 为正数；测试 fixture 中的 latest invocation 和 365 天 invocation history 同步补齐完整时间字段。
- 复现证据：365 天 fixture 中删掉第一天 invocation 的 `finished_at` 后，readiness 输出 `successful_invocations=364` 并阻断 365 天 run_daily invocation gates。
- 离线 smoke：真实 `bash run_daily.sh` 输出 `run_daily_invocation_success=True`，latest invocation 含 started/finished/duration 和 shell command。
- 验证：`python -m py_compile agent/*.py`、entrypoint+self-audit `64 passed`、聚合 `75 passed`、量化测试全集 `102 passed`、入口和 Slurm 脚本 `bash -n` 均通过。

## 2026-06-05 — failure memory did not prove repair actions were generated

- 现象：failure memory detail gate 已核对 issues/checks/formula/parent metrics，但 `next_actions` 只要存在于日志中即可，没有验证它们是否对应当前 `next_generation_factors.json` 的真实子因子。
- 风险：长期运行中可能出现 kill 记录写了 stale 或空 next actions，但 Evolution Agent 实际没有生成相应 repair/pivot；这会让系统看起来在迭代，实际没有可执行下一代候选。
- 修复：`_killed_factor_failure_memory_details_match` 增加 `latest_next_generation` 输入，要求每个被 kill 父因子的 failure memory `next_actions` 与当前 next-generation 子因子 id 集合精确一致且非空。
- 复现证据：365 天 fixture 中把同日 failure memory 的 `next_actions` 改为 `STALE_PIVOT`，readiness 阻断 `latest_killed_factor_failure_memory_details_match`。
- 离线 smoke：真实 `bash run_daily.sh` 中 failure memory detail match 为 true，3 条 failure memory 对应 10 个 generated next factors。
- 验证：`python -m py_compile agent/*.py`、self-audit `57 passed`、聚合 `76 passed`、量化测试全集 `103 passed`、入口和 Slurm 脚本 `bash -n` 均通过。

## 2026-06-05 — per-factor backtest files could drop audit fields

- 现象：`_backtest_result_files_match_payload` 只核对 `factor_id`、`formula_key`、`expression`、`rankic_mean`、`decision` 和 `portfolio`；单因子 JSON 可以丢失 `rankic_by_date`、`long_short`、`cost_sensitivity`、rows/dates 等关键审计字段。
- 风险：长期运行后，聚合 `backtest_results.json` 可能仍完整，但单因子文件不可复盘成本敏感性、long-short 诊断或稳定性，artifact manifest 也无法证明每个因子文件本身完整。
- 修复：per-factor backtest 文件现在必须与聚合 payload 的完整字段一致；测试 fixture 补齐 `rankic_by_date`，使 production-ready fixture 代表真实 backtest 输出形态。
- 复现证据：删除 `backtest_results/F1.json.cost_sensitivity` 后，readiness 阻断 `latest_backtest_result_files_match_payload`，而 factor database 与聚合 backtest 仍可保持匹配。
- 离线 smoke：真实 `bash run_daily.sh` 的 per-factor 文件含 `rankic_by_date`、`cost_sensitivity`、`long_short`，并通过 backtest file match gate。
- 验证：`python -m py_compile agent/*.py`、self-audit `58 passed`、backtest/critic `9 passed`、聚合 `77 passed`、量化测试全集 `104 passed`、入口和 Slurm 脚本 `bash -n` 均通过。

## 2026-06-05 — alpha GPU rerun used Slurm allocation, not login-node CUDA

- 根因/约束：登录节点不能作为 GPU 可用性判断；正式 alpha CUDA backtest 需要 `sbatch` 分配 GPU 后执行。
- 正确命令：`ALPHA_CANDIDATES='A029' ALPHA_HORIZONS='5' ALPHA_COSTS='5,10,20,30' ALPHA_FAST=0 ALPHA_BACKEND=torch_cuda bash scripts/submit_alpha_gpu_backtest.sh`。launcher 内部用 shell 环境变量加 `sbatch --export=ALL scripts/alpha_gpu_backtest.sbatch`，避免 Slurm 逗号列表截断。
- 复现证据：job `29572` 在 A800 `gpu2` 完成，日志显示 `CUDA_VISIBLE_DEVICES=0`、`torch.cuda_available=True`、`NVIDIA A800-SXM4-80GB`，stderr 为 0 字节。
- 结果解释：A029 H5 RankIC 为正，但 20/30bps long-short annual net 为负；因此当前 blocker 是 alpha/组合构造和 A 股交易账本约束，不是 GPU 资源。

## 2026-06-05 — daily report could omit final readiness state

- 现象：`daily_report.md` 只列出 `reports/READINESS_REPORT.md` 文件路径，没有在报告正文里写 readiness status、score 或 blocker count。
- 风险：长期无人值守时，日报可读性不足；即使 readiness 发现 365 天证据、live source、真实数据或 invocation blocker，人工扫日报时也可能看不到生产状态。
- 修复：日报新增 `## Readiness` 区块；readiness gate 把 readiness 摘要字段纳入 `latest_daily_report_is_current_evidence`；pipeline 尾部在最终 readiness 后重写日报并刷新 artifact manifest。
- 复现证据：删除日报 readiness 区块后，`test_readiness_blocks_daily_report_without_readiness_summary` 阻断 `latest_daily_report_is_current_evidence`。
- 离线 smoke：真实 `bash run_daily.sh` 生成日报 readiness 区块，`latest_daily_report_is_current_evidence=True`，manifest 中 `daily_report.md` 有 SHA256；整体仍保持 `not_production_ready`，因为只有 1/365 天生产证据。
- 验证：`python -m py_compile agent/*.py`、self-audit/readiness `59 passed`、daily pipeline `10 passed`、聚合 `78 passed`、量化全集 `105 passed`、入口和 Slurm 脚本 `bash -n` 均通过。

## 2026-06-05 — run_daily shell refresh made daily readiness summary stale

- 现象：真实 `bash run_daily.sh` smoke 中，`daily_report.md` 显示 readiness score `0.6029`、blockers `25`，但最终 `reports/READINESS_REPORT.json` 显示 score `0.6618`、blockers `23`；旧 gate 仍返回 true。
- 根因：`run_entrypoint` 在 pipeline 完成后才写入 shell invocation 记录，然后刷新 readiness/manifest；这个 shell provenance 会改变 readiness，但日报 readiness 区块没有同步刷新。
- 修复：`READINESS_REPORT` 要求日报 readiness 摘要与最新 `READINESS_REPORT.json` 精确一致；`daily_pipeline` 和 `run_entrypoint` 都循环刷新 readiness、日报 readiness 区块、artifact manifest 直到摘要稳定。
- 复现证据：新增 `test_readiness_blocks_daily_report_readiness_summary_mismatch`，把日报 `readiness blockers` 从 `0` 改成 `7` 会阻断 `latest_daily_report_is_current_evidence`。
- 离线 smoke：真实 `bash run_daily.sh` 后，日报 readiness 行与 final JSON 完全一致：status `not_production_ready`、score `0.6765`、blockers `22`，daily gate 为 true。
- 验证：`python -m py_compile agent/*.py`、entrypoint+daily `18 passed`、self-audit/readiness `60 passed`、聚合 `79 passed`、量化全集 `106 passed`、入口和 Slurm 脚本 `bash -n` 均通过。

## 2026-06-05 — final run_audit was written after artifact manifest

- 现象：直接执行 `python -m agent.daily_pipeline` 后，`artifact_manifest.json` 中 `run_audit.json` 的 SHA256 与最终 `run_audit.json` 文件不一致；而当时 `READINESS_REPORT.json` 仍显示 artifact manifest verification pass。
- 根因：pipeline 尾部先刷新 readiness 和 artifact manifest，再写最终 `run_audit.json`；verification 检查的是写 run_audit 之前的 manifest 状态。
- 修复：最终 `run_audit.json` 写入提前到最终 readiness/manifest 收敛刷新之前，确保 manifest 记录最终 run audit。
- 复现证据：修复前 direct pipeline smoke 输出 `run_audit.json False`；修复后输出 `RUN_AUDIT_HASH_MATCH True`、`MANIFEST_VERIFICATION True pass 0`。
- Regression：`test_daily_pipeline_runs_all_agents` 直接重算 `run_audit.json` SHA256，要求与 manifest 中记录一致。
- 验证：`python -m py_compile agent/*.py`、daily pipeline `10 passed`、entrypoint+self-audit `68 passed`、聚合 `79 passed`、量化全集 `106 passed`、真实 `bash run_daily.sh` smoke 和脚本 `bash -n` 均通过。

## 2026-06-05 — artifact verification checked the previous manifest

- 现象：direct pipeline smoke 显示 `artifact_verification.json.manifest_generated_at` 不等于最终 `artifact_manifest.json.generated_at`；readiness 内嵌 verification 也没有暴露 manifest timestamp，无法证明 final readiness 检查了最终 manifest。
- 根因：刷新循环每轮执行顺序是 readiness -> 更新日报 -> 重写 manifest。最后一次 readiness 生成的 verification 指向旧 manifest，随后又写了新 manifest。
- 修复：刷新循环在 readiness 摘要与上一轮一致时停止，不再重写 manifest；同时 `READINESS_REPORT` 的 artifact verification 摘要暴露 `generated_at` 和 `manifest_generated_at`。
- 复现证据：修复前 `VERIFICATION_FRESH False`；修复后 direct pipeline smoke 为 `VERIFICATION_FRESH True`、`READINESS_VERIFICATION_FRESH True`。
- Regression：daily pipeline 测试同时检查 run-local `artifact_verification.json` 和 readiness 内嵌 verification 的 `manifest_generated_at` 与最终 manifest 一致。
- 验证：`python -m py_compile agent/*.py`、daily+entrypoint `18 passed`、daily pipeline `10 passed`、entrypoint+self-audit `68 passed`、聚合 `79 passed`、量化全集 `106 passed`、真实 `bash run_daily.sh` smoke 和脚本 `bash -n` 均通过。

## 2026-06-05 — agent failure artifact audit needed stronger regression

- 现象：`test_daily_pipeline_records_agent_error_and_continues` 已覆盖 `data_agent` 失败时写出 error JSON 和 incomplete research log，但没有验证失败 run 的 error artifact、daily report、run audit 是否被最终 manifest/verifier 覆盖。
- 风险：长期无人值守中，失败日最需要可审计产物；如果后续改动让 `errors/<agent>.json` 或最终 `run_audit.json` 落在 manifest 之外，readiness 证据会变弱。
- 修复：失败路径测试直接重算 `daily_report.md`、`run_audit.json`、`errors/data_agent.json` 的 SHA256，并要求 manifest 记录一致；同时要求 artifact verification fresh/pass 和 daily report gate true。
- 复现证据：手动失败路径 smoke 显示 `daily_report.md True True`、`run_audit.json True True`、`errors/data_agent.json True True`、`verification fresh True pass 0`。
- 验证：`python -m py_compile agent/*.py`、daily pipeline `10 passed`、entrypoint+self-audit `68 passed`、聚合 `79 passed`、量化全集 `106 passed`、真实 `bash run_daily.sh` smoke 和脚本 `bash -n` 均通过。

## 2026-06-05 — README alpha GPU example was stale

- 现象：GPU launcher 和 sbatch 默认已切到 A029 H5 多成本 repair 验证，但 README 仍展示旧的 A022/A024/A025 多 horizon 命令。
- 风险：后续人工或自动流程按 README 示例提交时，会重复旧 repair 队列，而不是当前需要继续修复的 A029。
- 修复：README 示例更新为 `ALPHA_CANDIDATES='A029' ALPHA_HORIZONS='5' ALPHA_COSTS='5,10,20,30' ALPHA_FAST=0 ALPHA_BACKEND=torch_cuda bash scripts/submit_alpha_gpu_backtest.sh`。
- 复现/约束：GPU alpha 回测需要 Slurm 申请；正确入口是 launcher 内部调用 `sbatch --export=ALL scripts/alpha_gpu_backtest.sbatch`，不要在登录节点直接运行 CUDA 回测，也不要用 `sbatch --export=ALL,VAR=1,5` 传逗号列表。
- 验证：`bash -n scripts/submit_alpha_gpu_backtest.sh scripts/alpha_gpu_backtest.sbatch scripts/alpha_gpu_probe.sbatch` 通过；`squeue -u "$USER"` 当前无未完成 alpha GPU 作业。

## 2026-06-05 — artifact_verification_latest could drift from current verification

- 现象：readiness 已检查 `artifact_manifest_latest.json` 是否匹配当前 manifest，也会运行 verifier，但没有显式检查 `artifact_verification_latest.json` 是否与当前 run-local `artifact_verification.json` 同步。
- 风险：如果 latest pointer 写入失败、被旧 run 覆盖或外部流程留下 stale latest，日报/readiness 可能只证明 run-local verification pass，不能证明 latest pointer 也可审计。
- 修复：新增 `_artifact_verification_latest_matches_current`，比较 verification 稳定摘要；readiness 新增 check 和 blocker：`artifact_verification_latest.json does not match current run artifact_verification.json`。
- Regression：`test_readiness_blocks_stale_artifact_verification_latest` 用 monkeypatch 模拟 verifier 返回当前 pass 结果但 latest file 仍是旧 manifest timestamp，确认 readiness 被阻断。
- 验证：`python -m py_compile agent/*.py`、self-audit/readiness `61 passed`、聚合 `80 passed`、量化全集 `107 passed`、入口和 Slurm 脚本 `bash -n` 均通过。

## 2026-06-05 — failed run_daily entrypoint needed hash-level evidence

- 现象：失败入口测试已确认 `run_daily_invocation_latest.json`、readiness 和 manifest 存在，但没有直接证明 manifest 记录的是失败后最终 invocation 文件的 hash，也没有证明 latest verification 与 run-local verification 对齐。
- 风险：长期无人值守时，失败日最依赖 error invocation；如果 manifest 或 verification latest 指向失败前的旧文件，审计者可能误判失败路径证据完整。
- 修复/验证：增强 `test_run_entrypoint_records_failed_invocation`，重算 `run_daily_invocation_latest.json` SHA256，要求 manifest 记录一致；同时要求 run-local/latest verification 均验证最终 manifest，readiness 的 latest verification check 为 true。
- 结果：现有 `run_entrypoint._refresh_failure_evidence` 已满足该更严格断言，无需业务代码变更。
- 验证：`python -m py_compile agent/*.py`、entrypoint `8 passed`、entrypoint+daily+self-audit `79 passed`、量化全集 `107 passed`、入口和 Slurm 脚本 `bash -n` 均通过。

## 2026-06-05 — artifact verification output must be manifested but not self-verified

- 现象：`artifact_verification.json` 是关键审计产物，但此前 readiness required manifest paths 没有强制它出现在 `artifact_manifest.json`。
- 风险：如果 verifier 输出缺失或不被 manifest/latest manifest 覆盖，长期审计只能知道 manifest 被检查过，不能证明 verifier 输出本身作为每日 artifact 留存。
- 修复：把 `artifact_verification.json` 加入 `READINESS_REPORT.REQUIRED_MANIFEST_PATHS`；测试 fixture 改为先生成 manifest，再生成 verification，再重写 manifest，使 manifest 覆盖 verifier 输出。
- 重要契约：verifier 校验 manifest 时会把 `artifact_verification.json` 标记为 `verification_output` 并跳过 hash 复算，避免“文件写完自己后 hash 立刻变化”的自引用循环。
- 验证：`python -m py_compile agent/*.py`、daily+self-audit `71 passed`、聚合 `80 passed`、量化全集 `107 passed`、入口和 Slurm 脚本 `bash -n` 均通过。

## 2026-06-05 — verifier pass status alone did not prove final manifest freshness

- 现象：readiness 检查 `artifact_manifest_verification_passed` 只看 verifier `status=pass`；虽然正常路径会即时运行 verifier，但 gate 本身没有显式要求 `manifest_generated_at` 等于当前 manifest 的 `generated_at`。
- 风险：如果 verifier 返回或 latest pointer 意外复用旧 pass payload，readiness 可能误把旧 manifest 的 pass 结果当成最终 manifest 证据。
- 修复：新增 `artifact_manifest_verification_matches_current_manifest`，同时检查 run_date、manifest_path 和 manifest timestamp；报告中暴露 `matches_current_manifest`。
- Regression：`test_readiness_blocks_stale_artifact_verification_current_manifest` 用 monkeypatch 返回旧 timestamp 的 pass verifier，确认 readiness 阻断。
- 验证：`python -m py_compile agent/*.py`、self-audit/readiness `62 passed`、聚合 `81 passed`、量化全集 `108 passed`、入口和 Slurm 脚本 `bash -n` 均通过。

## 2026-06-05 — README-style readiness markdown hid verifier freshness

- 现象：`READINESS_REPORT.json` 已暴露 verifier freshness，但 `READINESS_REPORT.md` 的 Evidence 只显示 verification status、hash mismatch 和 missing files。
- 风险：长期无人值守巡检通常先看 Markdown；如果 Markdown 不展示 `matches_current_manifest` 和 latest pointer alignment，人工可能误把 `status=pass` 当成足够证据。
- 修复：Markdown Evidence 增加 `artifact manifest verification matches current manifest`、`artifact verification latest matches current verification` 和 `artifact verification manifest generated at`。
- Regression：production-ready readiness 测试直接读取 `READINESS_REPORT.md`，要求这些行存在且布尔值为 `True`。
- 验证：`python -m py_compile agent/*.py`、self-audit/readiness `62 passed`、聚合 `81 passed`、量化全集 `108 passed`、入口和 Slurm 脚本 `bash -n` 均通过。

## 2026-06-05 — readiness markdown/json consistency can self-reference

- 现象/风险：直接检查“已有 `READINESS_REPORT.md` 是否匹配当前 JSON”会和 readiness 自己写 JSON/Markdown 的顺序形成 fixed-point 问题；旧 Markdown 可能只是上一轮输出，而不是当前 run 的真实失败。
- 修复策略：不把旧文件作为输入门禁；`readiness_report.run()` 先基于当前 payload 渲染 Markdown，写盘后立刻读取文件并核对当前 payload 的关键行。不匹配时将 `readiness_markdown_matches_current_json=False`、重算 score/status、追加 blocker，再重写 JSON/Markdown。
- 复现测试：`test_readiness_blocks_mismatched_markdown_renderer` 用 monkeypatch 让 renderer 输出 `Run date: 20260603`/`Status: stale`，验证 readiness 被阻断。
- 验证：`python -m py_compile agent/*.py`、self-audit/readiness `63 passed`、schedule+entrypoint+daily+self-audit `82 passed`、agent/backtest 子集 `27 passed`、入口和 Slurm 脚本 `bash -n` 均通过。

## 2026-06-05 — production-ready also needs static repository deliverables

- 现象/风险：readiness 已严格验证每日运行产物、manifest、shell invocation 和 365 天证据，但没有集中证明目标交付物本身仍存在；理论上 `README.md`、`agent/` 或 `backtest_engine/` 被误删后，旧的每日证据仍可能掩盖仓库不可交付状态。
- 修复：新增 `_repository_deliverables_evidence`，检查静态 repo 文件和当前配置目录；`run_daily.sh` 必须是文件且有 executable bit，`reports`/`knowledge_base`/`factor_library` 必须存在且可写。
- 复现测试：`test_readiness_blocks_missing_repository_deliverable` monkeypatch repo root 到一个缺少 `README.md` 的临时目录，确认 `repository_deliverables_present=False` 和 blocker 生效。
- 验证：`python -m py_compile agent/*.py`、self-audit/readiness `64 passed`、schedule+entrypoint+daily+self-audit `83 passed`、agent/backtest 子集 `27 passed`、入口和 Slurm 脚本 `bash -n` 均通过。

## 2026-06-05 — source_quality missing_kinds alone was forgeable

- 现象/风险：旧 production source gate 信任 `missing_kinds=[]`，但没有用系统要求的来源种类反查 `covered_kinds`；如果上游或 fixture 错误地只写 `covered_kinds=["news"]` 且 `missing_kinds=[]`，readiness 可能把不完整联网覆盖当成生产证据。
- 修复：新增 `REQUIRED_MARKET_SOURCE_KINDS` 和 `REQUIRED_RESEARCH_SOURCE_KINDS`，market/research production evidence 和 source snapshot production evidence 都必须显式覆盖这些 kind。
- 调试点：同步测试 fixture 后，production-ready fixture 仍失败一次，根因是 `run_history.counts.events` 仍硬编码为 1，而当前 market payload 按 5 类来源生成 5 个 events；修复为按 required kind 数动态计数。
- 复现测试：`test_readiness_blocks_live_sources_without_required_kind_coverage` 覆盖 “missing_kinds 为空但 covered_kinds 不完整” 的伪完整证据。
- 验证：`python -m py_compile agent/*.py`、self-audit/readiness `65 passed`、schedule+entrypoint+daily+self-audit `84 passed`、agent/source/backtest 子集 `27 passed`、入口和 Slurm 脚本 `bash -n` 均通过。

## 2026-06-05 — executable run_daily.sh was not enough

- 现象/风险：`repository_deliverables_present` 只检查 `run_daily.sh` 存在且可执行时，脚本仍可能被改成直接调用 `agent.daily_pipeline`；这样 daily pipeline 会跑，但不会写 shell-level invocation、失败入口 traceback 或最终入口证据刷新。
- 修复：`_repository_deliverables_evidence` 读取 `run_daily.sh` 内容，要求包含 `QUANT_RUN_DAILY_SH=1`、`QUANT_RUN_DAILY_SCRIPT`、`QUANT_RUN_DAILY_COMMAND` 和 `python -m agent.run_entrypoint`。
- 复现测试：`test_readiness_blocks_run_daily_without_audited_entrypoint` 使用可执行但绕过 `agent.run_entrypoint` 的临时脚本，确认 readiness 阻断且 blocker 暴露 `run_daily_uses_audited_entrypoint=False`。
- 验证：`python -m py_compile agent/*.py`、self-audit/readiness `66 passed`、schedule+entrypoint+daily+self-audit `85 passed`、entrypoint/agent/backtest 子集 `35 passed`、入口和 Slurm 脚本 `bash -n` 均通过。

## 2026-06-05 — alpha GPU rerun must be submitted with sbatch allocation

- 约束确认：登录节点不是 GPU 执行环境；正式 alpha CUDA 回测必须通过 Slurm `sbatch` 申请 GPU。
- 正确入口：`ALPHA_CANDIDATES='A029' ALPHA_HORIZONS='5' ALPHA_COSTS='5,10,20,30' ALPHA_FAST=0 ALPHA_BACKEND=torch_cuda bash scripts/submit_alpha_gpu_backtest.sh`。launcher 内部调用 `sbatch --export=ALL scripts/alpha_gpu_backtest.sbatch`，逗号列表先放入 shell 环境变量，避免 Slurm `--export` 按逗号截断。
- 复现证据：job `29573` 在 A800 `gpu2` 完成；stdout 记录 `CUDA_VISIBLE_DEVICES=0`、`torch.cuda_available=True`、`NVIDIA A800-SXM4-80GB`，stderr 为 0 字节。
- 结果解释：A029 H5 GPU 结果与前次一致，RankIC 为正但 20/30bps long-short annual net 为负；因此被 `repair` 不是 CPU/GPU 问题，而是 alpha 组合构造和 A 股交易账本约束仍未过审。

## 2026-06-05 — README can exist while missing production-readiness semantics

- 现象/风险：`repository_deliverables_present` 只检查 `README.md` 存在时，弱 README 也能通过静态交付物门禁；长期无人值守系统可能代码证据链正确，但运维文档没有说明必须使用 `bash run_daily.sh`、shell invocation JSONL 和真实 365 连续生产日证据。
- 修复：新增 `REQUIRED_README_SNIPPETS`，要求 README 包含 `bash run_daily.sh`、`reports/run_daily_invocations.jsonl`、`365 consecutive unique dates` 和 `not_production_ready`。缺失时 `repository_deliverables_present=False`，blocker 暴露 `missing_readme_snippets` 和 `readme_documents_audited_readiness=False`。
- Regression：`test_readiness_blocks_readme_without_audited_readiness_docs` 构造 365 天其它证据齐全但 README 缺少审计/365 语义的 repo，确认 readiness 仍阻断。
- 验证：`python -m py_compile agent/*.py`、self-audit/readiness `67 passed`、schedule+entrypoint+daily+self-audit 聚合 `86 passed`、入口和 Slurm 脚本 `bash -n` 均通过；临时目录 `bash run_daily.sh` smoke 成功且保持 `not_production_ready`。

## 2026-06-05 — invocation script basename was forgeable

- 现象/风险：旧 `_invocation_is_successful_run_daily` 只要求 `entrypoint_script.endswith("run_daily.sh")`。如果另一个目录下有同名脚本，伪造的 `run_daily_invocations.jsonl` 可能被算作当前仓库的 365 天 shell-level 调用证据。
- 修复：successful invocation 判定现在接收 `expected_script_path=_repository_root()/run_daily.sh`，并用 `Path(...).resolve(strict=False)` 比较 `entrypoint_script`。`READINESS_REPORT` 暴露 `expected_entrypoint_script`。
- Regression：`test_readiness_blocks_invocation_from_different_run_daily_script` 覆盖同名异目录脚本；该记录不再计入 `has_365_successful_run_daily_invocations`，latest invocation 也不再通过 success gate。
- 验证：`python -m py_compile agent/*.py`、self-audit/readiness `68 passed`、schedule+entrypoint+daily+self-audit 聚合 `87 passed`、入口和 Slurm 脚本 `bash -n` 均通过；临时目录 shell smoke 显示 actual/expected 都为 `/home/lcc17/dl/run_daily.sh`，状态仍为 `not_production_ready`。

## 2026-06-05 — 365 successful run gate did not require every agent

- 现象/风险：旧 `successful_runs` 只看 `pipeline_status=complete` 和 `self_audit_status=pass`。历史 JSONL 若缺少某个 agent 的 `agent_status`，仍可能计入 365 天 unattended proof；这会削弱“每天自动启动全部 Agent”的 Definition of Done。
- 修复：新增 `_run_has_successful_audited_evidence`，要求 `self_audit_score>=0.9`，并要求 `agent_status` 覆盖全部 `REQUIRED_AGENT_NAMES` 且均为 `ok`。`_run_has_production_evidence` 也复用该判定。
- Regression：`test_readiness_blocks_365_successful_runs_with_missing_agent_roster` 覆盖 365 条缺少 `artifact_manifest` 的 complete/pass 历史记录；即使 latest run 完整，365 successful/production gates 也必须失败。
- 调试点：旧 offline/synthetic 365 测试没有写 `self_audit_score`，新门禁正确把它排除；该测试本意是“audited 但非生产源/数据”，因此补齐 `self_audit_score=1.0`，保持测试语义。
- 验证：`python -m py_compile agent/*.py`、self-audit/readiness `69 passed`、schedule+entrypoint+daily+self-audit 聚合 `88 passed`、入口和 Slurm 脚本 `bash -n` 均通过；临时目录 shell smoke 成功且仍为 `not_production_ready`。

## 2026-06-05 — run_history records without recorded_at were too weak

- 现象/风险：365 天 run_history 记录即使没有 `recorded_at` 写入时间，也可能在旧 audited-run 判定下被当作 successful run；这让历史 JSONL 更容易被离线拼接，缺少长期无人值守运行的时间证据。
- 修复：`_run_has_successful_audited_evidence` 现在要求 `run_date` 可解析为 `YYYYMMDD`，且 `recorded_at` 是 ISO datetime。`_build_run_history_record` 已天然写入 `recorded_at`，测试 production fixture 同步补齐。
- Regression：`test_readiness_blocks_365_successful_runs_without_recorded_at` 覆盖缺时间戳的 365 条完整记录；这些记录不再计入 365 successful/production evidence。
- 调试点：offline/synthetic 365 fixture 是手写 run_history，不走 `_production_run_record`，需同步补 `recorded_at` 才能继续表达“audited 但非 production data/source”的测试意图。
- 验证：`python -m py_compile agent/*.py`、self-audit/readiness `70 passed`、schedule+entrypoint+daily+self-audit 聚合 `89 passed`、入口和 Slurm 脚本 `bash -n` 均通过；临时目录 shell smoke 显示 latest `recorded_at` 正常写入。

## 2026-06-05 — alpha GPU work requires Slurm allocation

- 环境坑：登录节点不能作为正式 CUDA 回测证据；即使代码支持 `torch_cuda`，也必须先通过 Slurm `sbatch` 分配 GPU，否则容易被误判为只能跑 CPU。
- 正确入口：`ALPHA_CANDIDATES='A029' ALPHA_HORIZONS='5' ALPHA_COSTS='5,10,20,30' ALPHA_FAST=0 ALPHA_BACKEND=torch_cuda bash scripts/submit_alpha_gpu_backtest.sh`。该 launcher 内部调用 `sbatch --export=ALL scripts/alpha_gpu_backtest.sbatch`。
- 复现证据：job `29576` 在 A800 `gpu2` 完成；stdout 记录 `CUDA_VISIBLE_DEVICES=0`、`torch.cuda_available=True`、`NVIDIA A800-SXM4-80GB`，stderr 为 0 字节。
- 根因说明：A029 未 promote 不是 CPU/GPU 问题；GPU 结果与前次一致，高成本 long-short annual net 在 20/30bps 为负，且交易账本/暴露诊断仍未满足 reviewer 要求。

## 2026-06-05 — run/invocation timestamps were valid ISO but not date-bound

- 现象/风险：之前的 365-day proof 只要求 `run_history.recorded_at`、invocation `started_at`、`finished_at` 是合法 ISO datetime；如果这些时间戳合法但落在别的日期，记录仍可能被当作对应 `run_date` 的无人值守证据。
- 修复：新增 `_run_record_timestamp_matches_run_date` 和 `_invocation_timestamps_match_run_date`，并把它们纳入 successful run / successful invocation 判定，同时在 readiness checks、JSON evidence 和 Markdown evidence 中显式展示。
- 测试调整：旧的 invocation run_date mismatch 测试现在同步把 started/finished 设为 `20260603`，确保它只测试“invocation 自身成功但不等于当前 cfg.run_date”，而不是被新时间绑定门禁提前拦截。
- 验证：`python -m py_compile agent/*.py`、self-audit/readiness 测试、schedule+entrypoint+daily+self-audit 聚合 `91 passed`、入口和 Slurm 脚本 `bash -n`、临时目录 `bash run_daily.sh` smoke 均通过。

## 2026-06-05 — source snapshot item_count was not enough replay evidence

- 现象/风险：旧 `_source_snapshot_is_production_evidence` 校验 `item_count == sum(source_status.items)`，但没有检查 `items` 缓存本身。伪造记录可声明抓到 N 条，同时把 `items=[]`，仍可能计入 365 天 source snapshot evidence。
- 修复：production snapshot 现在要求 cached `items` 数量等于 `min(item_count, 50)`，item URL 必须为 HTTPS，item kind 必须来自 source_status；market snapshot 需要 `title`，research snapshot 需要 `text`。
- 调试点：离线 smoke 中 research snapshot 的 `item_count=0` 是预期，因为离线 fallback 不作为 production-grade source evidence；新门禁只影响 `_source_snapshot_is_production_evidence` 的生产级计数，不阻止离线 MVP 可运行性。
- 验证：`python -m py_compile agent/*.py`、self-audit/readiness 测试、schedule+entrypoint+daily+self-audit 聚合 `92 passed`、入口和 Slurm 脚本 `bash -n`、临时目录 `bash run_daily.sh` smoke 均通过。

## 2026-06-05 — candidate skip logic needed independent readiness audit

- 现象/风险：`factor_design` 已会读取 failed memory 并跳过历史失败公式，但 `READINESS_REPORT` 没有独立审计最新候选是否真的避开历史 failed keys；如果生成器被改坏，365 天 evidence 仍可能只看到候选/回测/知识库存在。
- 修复：readiness 新增历史 failed key 构造与候选 identity match 检查。历史定义为 `run_date != cfg.run_date` 或无日期的 kill/failure memory；same-day failure memory 不阻断当天候选，避免把当天研究闭环误判成重复研究。
- 测试点：负例同时写入同日完整 failure memory 和 `20260603` 历史 duplicate formula key，确认同日记忆不误拦、历史记忆会拦。
- 验证：`python -m py_compile agent/*.py`、self-audit/readiness 测试、schedule+entrypoint+daily+self-audit 聚合 `93 passed`、入口和 Slurm 脚本 `bash -n`、临时目录 `bash run_daily.sh` smoke 均通过。

## 2026-06-05 — data artifact fixture exposed missing dataset path date binding

- 现象/风险：旧 `_data_artifact_is_production_evidence` 没有要求 `dataset_manifest.run_date`、`data_health.run_date`、外层 row run_date 和 `dataset_path` 日期一致；历史 JSONL 可复用当前 run_dir manifest 冒充多日数据 artifact。
- 修复：production data artifact 现在检查三处 run_date 一致、dataset path 包含 `daily_logs/<run_date>/`，并要求 health date_min/date_max 可解析且顺序有效。
- 调试点：新增门禁后 production-ready fixture 初次失败，因为测试 helper `_data_health_latest_payload` 为历史 run_date 改了 manifest run_date，但 dataset_path 仍指向当前 `cfg.run_dir`。修复 helper 让历史 fixture 的 dataset_path 指向对应 `daily_logs/<run_date>/daily_dataset.parquet`，匹配真实 pipeline 行为。
- 验证：`python -m py_compile agent/*.py`、self-audit/readiness 测试、schedule+entrypoint+daily+self-audit 聚合 `94 passed`、入口和 Slurm 脚本 `bash -n`、临时目录 `bash run_daily.sh` smoke 均通过。

## 2026-06-05 — research_log knowledge saves lacked write-time evidence

- 现象/风险：`research_log.jsonl` 的 complete knowledge-save 判定只需要 run_date 和 factor_database_write 内容；手写历史日志可声明 365 天保存完成但没有写入时间。
- 修复：`agent.knowledge_base.run` 在 research_log record 中写入 UTC `recorded_at`；readiness 的 `_knowledge_save_is_complete` 复用 run record 时间绑定检查，要求 recorded_at 日期等于 run_date。
- 测试点：fixture `_research_log_payload` 和 `_write_complete_knowledge_saves` 同步补 recorded_at；新增负例删除第一天 recorded_at 后，knowledge_save_dates 从 365 降到 364。
- 验证：`python -m py_compile agent/*.py`、self-audit/readiness 测试、schedule+entrypoint+daily+self-audit 聚合 `95 passed`、入口和 Slurm 脚本 `bash -n`、临时目录 `bash run_daily.sh` smoke 均通过。

## 2026-06-05 — data_health artifact records lacked write-time evidence

- 现象/风险：`data_health.jsonl` 的 production-grade data artifact 判定已经校验 outer run_date、dataset manifest run_date、health run_date 和 daily log path，但没有要求该 JSONL 记录有写入时间；旧记录仍可能被离线复制拼接成 365 天数据证据。
- 修复：`agent.data_agent.run` 在 data artifact record 中写入 UTC `recorded_at`；readiness 的 `_data_artifact_is_production_evidence` 复用 run record 时间绑定检查，要求 recorded_at 日期等于 run_date。
- 测试点：fixture `_data_health_latest_payload` 同步补 recorded_at；新增负例删除第一天 data artifact recorded_at 后，production-grade data artifact dates 从 365 降到 364。
- 验证：`python -m py_compile agent/*.py`、self-audit/readiness 测试、schedule+entrypoint+daily+self-audit 聚合 `96 passed`、入口和 Slurm 脚本 `bash -n`、临时目录 `bash run_daily.sh` smoke 均通过。

## 2026-06-05 — source snapshots had ISO timestamps but no run-date binding

- 现象/风险：`source_snapshots.jsonl` 的 production evidence 只要求 `snapshot_written_at` 和 `source_status[].fetched_at` 是合法 ISO datetime；历史 fixture 暴露出所有 run_date 可以共用同一个 `2026-06-04` timestamp，仍可能被计入 365 天 source evidence。
- 修复：`_source_snapshot_is_production_evidence` 现在要求 `snapshot_written_at.date() == run_date`，并要求每个 source status 的 `fetched_at.date() == run_date`。
- 测试点：production source snapshot fixture 改为按 run_date 写 `snapshot_written_at` 和 `fetched_at`；新增负例把第一天 market snapshot 的 `snapshot_written_at` 改成次日后，source snapshot dates 从 365 降到 364。
- 验证：`python -m py_compile agent/*.py`、self-audit/readiness 测试、schedule+entrypoint+daily+self-audit 聚合 `97 passed`、入口和 Slurm 脚本 `bash -n`、临时目录 `bash run_daily.sh` smoke 均通过。

## 2026-06-05 — current source snapshot match ignored cached item content

- 现象/风险：`latest_source_snapshots_match_current_outputs` 只比较 source status、source quality 和 item_count；如果 run-dir snapshot 或 JSONL 同日记录保留相同计数但替换了 `items` 内容，readiness 仍可能认为当前 source snapshot 与当前 market/research 输出一致。
- 修复：current-output match 现在比较 `items` 与当前 `daily_events.json.events[:50]` / `research_ideas.json.research_context[:50]`，并要求 `snapshot_written_at` 日期等于当前 run date。
- 测试点：新增负例只改当前 run-dir market snapshot 第一条 title，不改 item_count，确认 `latest_source_snapshots_match_current_outputs` 变 false。
- 验证：`python -m py_compile agent/*.py`、self-audit/readiness 测试、schedule+entrypoint+daily+self-audit 聚合 `98 passed`、入口和 Slurm 脚本 `bash -n`、临时目录 `bash run_daily.sh` smoke 均通过。

## 2026-06-05 — backtest result directory allowed stale extra files

- 现象/风险：`latest_backtest_result_files_match_payload` 会逐个验证 `backtest_results.json.results` 中列出的 per-factor 文件，但没有检查 `backtest_results/` 目录是否存在额外旧 JSON。旧因子文件可能被 manifest/hash 纳入当前运行输出，削弱“当前自动回测结果”证据。
- 修复：backtest result file gate 现在要求目录下 `*.json` 文件名集合等于当前 result factor ids 集合。
- 测试点：新增负例在当前 payload 只有 `F1` 时额外写入 `backtest_results/STALE.json`，确认 readiness 阻断 `latest_backtest_result_files_match_payload`。
- 验证：`python -m py_compile agent/*.py`、self-audit/readiness 测试、schedule+entrypoint+daily+self-audit 聚合 `99 passed`、入口和 Slurm 脚本 `bash -n`、临时目录 `bash run_daily.sh` smoke 均通过。

## 2026-06-05 — candidate/next-generation directories allowed stale extra files

- 现象/风险：`latest_candidate_factor_files_match_payload` 和 `latest_next_generation_files_match_payload` 会逐个验证 payload 中列出的 per-factor 文件，但没有检查对应目录是否存在额外旧 JSON。旧候选或旧修复候选可能被 manifest/hash 纳入当前运行输出，削弱“当前自动生成因子”的证据。
- 修复：candidate 与 next-generation file gate 现在先构造 payload factor id 对应的 expected filename set，再要求目录下 `*.json` 文件名集合完全相等。
- 测试点：新增 stale extra file 负例，分别在当前 payload 不包含旧 id 时写入 `candidate_factors/STALE.json` 与 `next_generation_factors/STALE_NEXT.json`，确认 readiness 阻断对应 check。
- GPU 调试约束：GPU 需要走 Slurm 申请；登录节点只做 CPU smoke、脚本语法和本地测试，实际 alpha GPU backtest 通过 sbatch launcher 提交。
- 验证：`python -m py_compile agent/*.py`、self-audit/readiness 测试、schedule+entrypoint+daily+self-audit 聚合 `101 passed`、入口和 Slurm 脚本 `bash -n`、临时目录 `bash run_daily.sh` smoke 均通过。

## 2026-06-05 — GPU acceleration must be submitted through sbatch

- 根因/约束：GPU 资源不是登录节点默认可用资源，必须通过 Slurm 申请。直接在本地日常流水线里启 CUDA 会把 `run_daily.sh` 变成依赖调度资源的入口，破坏 CPU/离线 smoke 和无人值守 readiness。
- 修复/操作：用 `scripts/submit_alpha_gpu_backtest.sh` 提交 A029 fast rerun，传入 `SLURM_PARTITION=A800`、`SLURM_GPUS=1`、`SLURM_TIME=00:30:00`，实际作业 `29596` 跑在 `gpu2`。
- 复现信息：日志 `reports/slurm/alpha_gpu_backtest-29596.out` 显示 `cuda_available True`、device `NVIDIA A800-SXM4-80GB`，并输出 A029 cost sensitivity 结果；`.err` 为空。
- 调试结论：以后重型 alpha 搜索/回测走 sbatch launcher；登录节点只跑测试、smoke、artifact 检查和轻量 CPU pilot。

## 2026-06-05 — factor_database allowed extra same-day records

- 现象/风险：`latest_factor_database_matches_backtests` 原先只逐个检查当前 backtest result 是否存在对应当天 factor database 记录；如果 `factor_database/factors.json` 额外混入同一 `run_date` 的旧因子，readiness 仍可能通过，导致当天知识库保存证据被污染。
- 修复：factor database gate 先计算当前 backtest result ids，再要求当天 factor database record ids 集合完全相等；报告 evidence 新增 `same_day_factor_ids`。
- 测试点：新增负例在当前 payload 只有 `F1` 时追加 `STALE_SAME_DAY` same-day record，确认 readiness 阻断 `latest_factor_database_matches_backtests`，同时 backtest per-factor 文件 gate 仍为 true。
- 验证：`python -m py_compile agent/*.py`、定向测试、self-audit/readiness 测试、schedule+entrypoint+daily+self-audit 聚合 `102 passed`、入口和 Slurm 脚本 `bash -n`、临时目录 `bash run_daily.sh` smoke 均通过。

## 2026-06-05 — failure_memory allowed extra same-day records

- 现象/风险：`latest_killed_factors_have_failure_memory` 原先用 subset 语义，只要求当前 killed factor ids 被 same-day failure memory 覆盖；如果 `failure_memory.jsonl` 额外混入同日未被 critic kill 的因子，readiness 仍可能通过，污染“禁止重复研究已失败方案”的长期记忆。
- 修复：failure-memory gate 改为 exact set 语义：当前 `critique.json` 的 killed ids 必须等于同日 `failure_memory.jsonl` factor ids。无 killed 时也不允许有同日 failure memory 残留。
- 测试点：新增负例先写正常 F1 failure memory，再追加 `STALE_FAILURE` same-day record，确认 readiness 阻断 `latest_killed_factors_have_failure_memory`；缺失、详情缺失、next_actions stale 的旧负例继续通过。
- 验证：`python -m py_compile agent/*.py`、定向测试 `4 passed`、self-audit/readiness 测试、schedule+entrypoint+daily+self-audit 聚合 `103 passed`、入口和 Slurm 脚本 `bash -n`、临时目录 `bash run_daily.sh` smoke 均通过。

## 2026-06-05 — research_log critic summary only checked count

- 现象/风险：`latest_research_log_matches_current_outputs` 原先只检查 `critic.critique_count`，没有核对 promoted/killed 数和 issue_counts；同样数量的 stale 审稿摘要可能把 kill 写成 promote 或丢失失败原因，长期研究日志仍可能通过 readiness。
- 修复：research log gate 现在从当前 `critique.json` 计算 promoted、killed 和 issue_counts，并要求与 `research_log_latest.json.critic` 完全一致；同时核对 backtest summary 的 promoted_raw/killed_raw。
- 测试点：新增负例保持 critique_count=1，但把 research log 的 killed 改为 0、promoted 改为 1、issue_counts 清空，确认 readiness 阻断 `latest_research_log_matches_current_outputs`。
- 验证：`python -m py_compile agent/*.py`、定向测试 `4 passed`、self-audit/readiness 测试、schedule+entrypoint+daily+self-audit 聚合 `104 passed`、入口和 Slurm 脚本 `bash -n`、临时目录 `bash run_daily.sh` smoke 均通过。

## 2026-06-05 — A029 delayed-exit repair is useful but still not promotable

- 根因/约束：先前 A029 blocker 之一是计划退出日不可卖时 `ret_o2o_*` 变 `NaN`，后续 IC/组合 drop 掉样本，带来未来退出可成交性筛选风险。
- 修复：新增 `add_delayed_exit_returns()`，对计划退出日 sell-blocked 的样本向后寻找最多 10 个交易日的下一可卖开盘；panel cache version 从 v3 升到 v4。布尔 fill 的 pandas FutureWarning 用显式 `np.where(..., dtype=bool)` 清理，避免后续日志污染。
- GPU 复现：job `29601` 通过 `scripts/submit_alpha_gpu_backtest.sh` 申请 A800，运行在 `gpu2`，CUDA 可用。当前 job stderr 中的 warning 来自作业启动前旧代码版本；本地后续 `py_compile` 和 `test_alpha_backtest_cache` 已验证新代码无该 warning。
- 结果解释：delayed-exit 后 A029 H5 RankIC 从约 `0.04490` 到 `0.04537`，20bps long-short annual net 从 `-0.0063` 到 `0.0065`，说明不是应该 kill 的方向；但 30bps 仍为负，size_corr 约 `0.43`，且 unresolved exits after max delay 仍会被 drop，所以只能 `repair`。
- 后续修复顺序：真实 staggered long-only H5 ledger；unresolved exits forced/adverse outcome；exit-day 停牌/成交额/ST/退市 fillability；size/industry neutral diagnostics；raw vs adjusted price audit；再走 sbatch rerun。

## 2026-06-05 — research_log evolution skipped summary only checked next ids

- 现象/风险：`latest_research_log_matches_current_outputs` 之前只校验 evolution 的 next-generation 数量和 ids；如果 `research_log_latest.json` 伪造 `skipped_failed_count` 或 `skipped_factor_ids`，readiness 仍可能通过，导致失败记忆/跳过逻辑的长期日志不可信。
- 修复：readiness 现在从当前 `next_generation_factors.json.skipped_evolution_factors` 计算 skipped ids，要求 research log 的 `skipped_failed_count` 与 `skipped_factor_ids` 完全一致；evidence 暴露当前值和日志值，便于定位。
- 测试点：新增负例在 current skipped 为空时把 research log 写成跳过 `STALE_SKIPPED_EVOLUTION`，确认 `latest_research_log_matches_current_outputs` 阻断。
- 验证：`python -m py_compile agent/*.py`、定向测试、self-audit/readiness、schedule+entrypoint+daily+self-audit 聚合 `106 passed`、入口和 Slurm 脚本 `bash -n`、临时目录 `bash run_daily.sh` smoke 均通过。

## 2026-06-05 — next_generation per-factor files only checked identity fields

- 现象/风险：`_next_generation_files_match_payload` 之前检查目录集合和 `factor_id` / `parent_factor_id` / `formula_key` / `status`，但没有核对 `formula`、`expression`、`rationale`、父指标和 provenance。旧文件只要保留同 id/formula_key 就可能通过 readiness，削弱 Evolution Agent 当前输出证据。
- 修复：per-factor JSON 现在和 payload 核对完整核心字段，包括公式、表达式、持仓期、rationale、parent decision、failed issues、parent metrics 和 provenance。
- 测试点：新增负例只改 per-factor 文件的 `formula`，保持 id 和 formula_key 不变，确认 readiness 阻断 `latest_next_generation_files_match_payload`。
- 验证：`python -m py_compile agent/*.py`、定向测试、self-audit/readiness、schedule+entrypoint+daily+self-audit 聚合 `107 passed`、入口和 Slurm 脚本 `bash -n`、临时目录 `bash run_daily.sh` smoke 均通过。

## 2026-06-05 — candidate/factor_library files only checked identity fields

- 现象/风险：candidate per-factor 文件和 `factor_library/<id>.json` 之前主要核对 id、created_at_run、formula_key、expression、status；如果旧文件保留同 id/formula_key 但公式、名称或 provenance 漂移，readiness 仍可能通过，削弱 Factor Design Agent 当前输出证据。
- 修复：candidate per-factor 与 factor_library 文件现在核对完整核心字段：`factor_id`、`name`、`formula`、`formula_key`、`expression`、`source_idea_id`、`created_at_run`、`provenance`、`status`。
- 测试点：新增两个负例，分别只改 run-dir candidate 文件公式和 factor_library 文件公式，确认 readiness 阻断对应 gate。
- 验证：`python -m py_compile agent/*.py`、定向测试 `2 passed`、self-audit/readiness、schedule+entrypoint+daily+self-audit 聚合 `109 passed`、入口和 Slurm 脚本 `bash -n`、临时目录 `bash run_daily.sh` smoke 均通过。

## 2026-06-05 — daily GPU work must be submitted, not executed on login node

- 现象/风险：`run_daily.sh` 之前只跑本地 agent pipeline；重型 alpha GPU 回测需要手工运行 `scripts/submit_alpha_gpu_backtest.sh`，日常证据链没有记录“是否申请了 GPU 作业”。如果直接在 daily 入口中尝试 CUDA，登录节点无 GPU 时会失败或退回 CPU，且不可审计。
- 修复：新增 `gpu_alpha_submission` 记录型 agent，通过 launcher 调 `sbatch` 并解析 `Submitted batch job <id>`；离线运行、禁用开关或缺少 `sbatch` 时写 `skip_reason`，不回退到本地 CUDA。
- 测试点：fake `sbatch` 输出 `Submitted batch job 12345`，确认 job id、逗号型 `ALPHA_HORIZONS=1,5,10,20` 环境变量和 latest JSON 都被保留。
- 验证：编译、daily pipeline 定向测试、schedule+entrypoint+daily+self-audit 聚合 `110 passed`、sbatch 脚本 `bash -n`、离线 `run_daily.sh` smoke 均通过。

## 2026-06-05 — GPU submission record existed before readiness audited it

- 现象/风险：daily pipeline 会写 `gpu_alpha_submission.json` 和 latest JSON，但 readiness 之前只通过 manifest 间接看到文件存在；如果 latest 指针过期、run-dir 记录被替换，或在线运行缺少真实 sbatch 提交语义，系统仍可能无法暴露这个退化。
- 修复：readiness 新增 `latest_gpu_alpha_submission_is_current_evidence`，比较 run-dir 与 latest 完全一致，并检查离线 skip 或在线 sbatch command/status/job 语义。
- 测试点：production-ready fixture 中加入 GPU submission evidence；新增 stale latest 负例，确认 latest 指针 run_date 漂移会阻断 readiness。
- 验证：`tests/test_quant_self_audit.py`、schedule+entrypoint+daily+self-audit 聚合、脚本语法和离线 smoke 均通过。

## 2026-06-05 — README did not list new GPU submission artifacts

- 现象/风险：实现和 readiness 已经写入/审计 `gpu_alpha_submission.json`，但 README 的 MVP 输出清单和 Long-Run Reliability 仍未列出该产物；未来交付审查或新 agent 可能按 README 误以为 daily workflow 没有 GPU/sbatch 证据。
- 修复：README 增补 run-dir/latest GPU submission artifact 和 Slurm-only readiness 说明；readiness 的 README snippet gate 增加 `gpu_alpha_submission_latest.json` 与 `Slurm`。
- 测试点：弱 README regression 现在也要求缺失 GPU submission snippet 会出现在 `missing_readme_snippets`。
- 验证：README snippet 机器检查 `True []`，self-audit/readiness 与聚合测试通过，离线 smoke 确认 repository deliverables gate 仍为 true。

## 2026-06-05 — support modules were not part of repository deliverables

- 现象/风险：`REQUIRED_AGENT_MODULE_FILES` 只覆盖早期核心 agent 和 entrypoint；后续新增的 schedule/self-audit/artifact verifier/source cache/GPU submission 等模块如果从仓库缺失，repository deliverables gate 仍可能不报错。
- 修复：required module list 扩展到当前 `agent/` daily workflow 关键模块；fake repo fixture 自动按该列表生成文件，另加删除 `agent/gpu_alpha_submission.py` 的负例。
- 调试注意：这些文件很多在当前 worktree 仍是 untracked 状态；测试和 readiness 使用当前文件系统为准，不应把 untracked 当成可丢弃。
- 验证：真实仓库 `_repository_deliverables_evidence` 输出 `agent_module_files_present=True, missing_files=[]`；self-audit、聚合测试和离线 smoke 均通过。

## 2026-06-05 — Slurm scripts were only indirectly checked

- 现象/风险：GPU submission 记录会引用 `scripts/submit_alpha_gpu_backtest.sh`，但 repository deliverables 不要求 launcher/sbatch/probe 文件存在。脚本缺失可能只通过某次运行的 `script_exists=false` 暴露，而不是在交付物层面提前阻断。
- 修复：新增 `REQUIRED_SCRIPT_FILES` 和 `script_files_present` evidence；fake repo fixture 为这些脚本生成占位文件，缺失 launcher 的负例确认 readiness 阻断。
- 调试注意：脚本语法仍要单独用 `bash -n run_daily.sh scripts/submit_alpha_gpu_backtest.sh scripts/alpha_gpu_backtest.sbatch scripts/alpha_gpu_probe.sbatch` 验证；deliverables gate 只证明文件存在。
- 验证：真实仓库 `_repository_deliverables_evidence` 输出 `script_files_present=True`，聚合测试和离线 smoke 均通过。

## 2026-06-05 — GPU latest pointer was read but not hash-manifested

- 现象/风险：readiness 会比较 `gpu_alpha_submission.json` 与 `reports/gpu_alpha_submission_latest.json`，但 artifact manifest 的 extra report files 之前没有包含 latest GPU submission 指针。长期完整性审计能看到 run-dir GPU 记录，却不会对 latest 指针本身生成 SHA256 证据。
- 修复：`agent.artifact_manifest` 增加 `cfg.output_root / "gpu_alpha_submission_latest.json"`；`REQUIRED_MANIFEST_PATHS` 同步增加 `gpu_alpha_submission_latest.json`，daily pipeline 回归断言该文件出现在 manifest。
- 调试注意：该 latest 文件在 `gpu_alpha_submission` agent 阶段写入，早于 manifest/verifier，因此纳入 hash 不会造成最终 readiness 刷新循环的自引用漂移。
- 验证：daily+self-audit 定向测试 `104 passed`；schedule+entrypoint `9 passed`；隔离 `bash run_daily.sh` smoke 显示 `artifact_verification.status=pass` 且 manifest 同时包含 run-dir 和 latest GPU submission 文件。

## 2026-06-05 — Daily report GPU line was too coarse

- 现象/风险：日报原先只写 `gpu alpha submission: skipped` 或 `submitted`，读日报无法判断是正常离线跳过、`sbatch_not_found`、提交失败，还是已经拿到 Slurm job id；长期无人值守排查需要在日报里看到原因。
- 修复：`daily_pipeline._gpu_submission_summary()` 把 `job_id`、`skip_reason` 或 `error` 拼进日报；`readiness_report._daily_report_is_current_evidence()` 同步按当前 GPU payload 精确核对该行。
- 调试注意：`tests/test_quant_self_audit.py` 有手写 production-ready `daily_report.md` fixture，改日报格式时必须同步更新，否则 readiness fixture 会因为日报证据不匹配失败。
- 验证：daily+self-audit 定向测试 `104 passed`；schedule+entrypoint `9 passed`；隔离 smoke 确认日报包含 `gpu alpha submission: skipped (offline_run)` 且 `latest_daily_report_is_current_evidence=True`。

## 2026-06-05 — Schedule gate did not reject stale run_date

- 现象/风险：`_schedule_is_daily_run_daily()` 之前只检查 cron cadence、`run_daily.sh`、脚本存在和日志目录可写；如果旧 run 的 `schedule.json` 被复制到当前 run directory，只要 cron 行仍正确，schedule gate 仍可能通过。
- 修复：schedule gate 增加当前 run date 参数，要求 `schedule.json.run_date == cfg.run_date`；readiness 的 `schedule_evidence` 暴露 `run_date` 方便定位陈旧文件。
- 测试点：`test_readiness_blocks_stale_schedule_run_date` 用真实离线 pipeline 生成 run，再只改 `schedule.json.run_date=20260603` 并刷新 manifest，确认 readiness 阻断 schedule gate。
- 验证：定向 schedule 测试 `3 passed`；daily+self-audit 主套件 `105 passed`；entrypoint+schedule `9 passed`；隔离 smoke 显示真实 schedule run_date 和 readiness evidence 都是 `20260605`。

## 2026-06-05 — self_audit.md was only existence/hash evidence

- 现象/风险：`self_audit.json` 会核对 run_date、check results 和当前输出，但 `self_audit.md` 之前在 readiness 中没有内容级校验；如果旧 Markdown 被复制后重新生成 manifest，hash 也会匹配旧内容，用户读到的自检报告可能不是当前 run。
- 修复：新增 `_self_audit_markdown_matches_json()`，按当前 `self_audit.json` 核对 Markdown 的 run date、status、score、source mode、checks、preflight 和 freshness；payload 暴露 `latest_self_audit.markdown_matches_json`。
- 调试注意：`tests/test_quant_self_audit.py` 的 fake production-ready helper 原先只写 `# Self Audit`，新增 gate 后必须生成与 `_current_self_audit_payload()` 对齐的 Markdown，否则大量 readiness fixture 会误失败。
- 验证：新增 stale Markdown 负例通过；daily+self-audit 主套件 `106 passed`；entrypoint+schedule `9 passed`；隔离 smoke 显示 `latest_self_audit_markdown_matches_json=True`。

## 2026-06-05 — source_snapshots_latest.json was only weak pointer evidence

- 现象/风险：`source_snapshots_latest.json` 之前在 latest pointer alignment 中只要求 `run_date` 当前、`agent` 属于 market/research；如果该 latest 文件内容被改成同日错误 source_quality 或 item_count，run-dir snapshot 和 JSONL 仍正确时 readiness 可能通过。
- 修复：新增 `_source_snapshots_latest_matches_current_outputs()`，按 latest 指向的 agent 精确核对 source_status、source_quality、item_count、items 和 snapshot_written_at 日期；payload 暴露 `source_snapshot_evidence.latest_matches_current_outputs/latest_agent/latest_item_count`。
- 测试点：`test_readiness_blocks_source_snapshots_latest_mismatch` 只改 latest pointer 的 `item_count=999`，确认 `latest_source_snapshots_match_current_outputs` 仍 true，而 latest pointer gate 为 false。
- 验证：source latest 正负例 `2 passed`；daily+self-audit 主套件 `107 passed`；entrypoint+schedule `9 passed`；隔离 smoke 显示 latest pointer 指向 `research_agent` 且内容匹配。

## 2026-06-05 — GPU submission depended on caller cwd and hardcoded repo path

- 现象/风险：`agent.gpu_alpha_submission` 原先用相对路径 `scripts/submit_alpha_gpu_backtest.sh` 判断脚本存在并提交；如果被测试、调度器或 Python 入口从非 repo cwd 调用，会误报 `missing_submit_script`。Slurm shell/sbatch 文件也硬编码 `cd /home/lcc17/dl`，复制 repo 或路径迁移后会跑错目录。
- 修复：Python 模块用 `Path(__file__).resolve().parents[1]` 推导 repo root，payload 记录 `project_root`，subprocess 使用绝对 submit 脚本路径和显式 `cwd`；三个 Slurm 相关脚本用 `${BASH_SOURCE[0]}` 推导 repo root。
- 测试点：`test_gpu_alpha_submission_uses_sbatch_and_records_job_id` 在 `monkeypatch.chdir(tmp_path)` 后仍通过 fake `sbatch`，确认脚本路径为 absolute 且 `script_exists=True`。
- 验证：`python -m py_compile agent/*.py`、`bash -n run_daily.sh scripts/submit_alpha_gpu_backtest.sh scripts/alpha_gpu_backtest.sbatch scripts/alpha_gpu_probe.sbatch`、入口/调度/GPU 定向测试 `10 passed`、daily+self-audit 主套件 `107 passed`、隔离入口 smoke `SMOKE complete not_production_ready skipped offline_run True True`。

## 2026-06-05 — Invalid config failures had no artifact package

- 现象/风险：`agent.run_entrypoint` 在 `load_config()` 因非法日期等问题失败时，原先只能写 `run_daily_invocation_latest.json`；因为没有合法 `RunConfig`，不会生成 run-dir 失败包、artifact manifest 或 verifier。长期 cron 运行遇到坏 env 时，排查证据比正常失败路径弱。
- 修复：新增 config-failure fallback artifact：用 `invalid_config_<started_at>` 作为 fallback run id，写 `entrypoint_error.json`，然后基于 fallback `RunConfig` 生成 manifest 和 artifact verification。Invocation 记录新增 `failure_artifact_run_date`、`failure_artifact_run_dir` 和 `failure_artifact_manifest_path`。
- 调试注意：必须先把 fallback artifact 路径写入 invocation，再生成 manifest/verifier；如果 manifest 后再次改 invocation，会导致 manifest 中 `run_daily_invocation_latest.json` 的 SHA256 滞后。
- 验证：非法 `QUANT_DATE=20260631` regression 通过，manifest 覆盖 `entrypoint_error.json` 和最新 invocation，artifact verifier 为 `pass`；entrypoint 全套 `9 passed`，daily+self-audit 主套件 `107 passed`，正常离线入口 smoke 仍为 `SMOKE complete not_production_ready success True`。

## 2026-06-05 — Same-day factor database writes kept stale metrics

- 现象/风险：`agent.knowledge_base` 原先用 `(factor_id, run_date)` 去重；同一天重跑后，如果回测或 critic 输出变化，已有 factor record 会被跳过而不是更新，导致长期因子库保留旧 RankIC、旧 decision 或旧 issues。
- 修复：完整/standalone 写入时把当前 run_date 的旧 factor records 整体移除，再用当前 `backtest_results.json` 与 `critique.json` 重建同日记录。`research_log_latest.json.factor_database_write` 记录 `replaced_same_day_factor_count`。
- 测试点：`test_knowledge_base_replaces_same_day_factor_records` 先写同日旧 `F_STABLE`，再写同日新结果，确认 factor database 只有一条新记录且 latest research log 报告替换数量为 1。
- 验证：知识库定向测试 `11 passed`；daily pipeline 定向测试 `2 passed`；daily+self-audit 主套件 `107 passed`；entrypoint+schedule `9 passed`；离线入口 smoke `SMOKE complete not_production_ready updated 0`。
