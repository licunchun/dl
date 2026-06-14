# A股 Alpha Discovery Ledger

## 2026-06-05 — A029 H5 GPU sbatch allocation rerun 29573

- alpha id: `A029`
- alpha 公式/逻辑: `rank(rank(ret_20_skip5)*(1-rank(ret_5))*rank(liq_inv)*rank(low_vol)*(1-rank(turn)))`；中期动量 + 短回撤 + 高流动低波 + 低换手。
- 使用字段: `ret_20_skip5`, `ret_5`, `amihud_20`/`liq_inv`, `std_20`/`low_vol`, `turnover_rate`/`turn`；收益由 open 重新计算。
- 样本区间: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28。
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买。
- 是否行业/市值中性: 未做行业/市值中性；既有 reviewer 记录的 test size_corr 约 0.43 仍是 promote blocker。
- 回测指标: Slurm GPU job `29573`，A800 `gpu2`，`ALPHA_BACKEND=torch_cuda`，H5，cost 5/10/20/30bps。Test RankIC 0.044898；long-short annual net 0.036556 / 0.022270 / -0.006300 / -0.034871；long-only annual net 0.181849 / 0.174633 / 0.160203 / 0.145772；long-only Sharpe 1.256 / 1.206 / 1.106 / 1.007。
- 成本后表现: long-only 多成本为正；long-short 在 20/30bps 转负，不能满足成本敏感性 promote 要求。
- reviewer score: 5/10。
- leakage/bias 审查结论: sbatch 日志确认 CUDA/Torch 生效且 stderr 为 0；已有审稿问题仍未修复，包括 delayed-exit、H>1 真账本、size/industry neutral diagnostics、复权/退市审计缺口。
- decision: repair
- next action: 不再把 CPU/GPU 当 blocker；继续实现 sell-limit/suspension delayed-exit、true H5 sub-book ledger 和 size/industry neutral diagnostics 后重审。

## 2026-06-05 — A029 H5 GPU sbatch multi-cost rerun

- alpha id: `A029`
- alpha 公式/逻辑: `rank(rank(ret_20_skip5)*(1-rank(ret_5))*rank(liq_inv)*rank(low_vol)*(1-rank(turn)))`；中期动量 + 短回撤 + 高流动低波 + 低换手。
- 使用字段: `ret_20_skip5`, `ret_5`, `amihud_20`/`liq_inv`, `std_20`/`low_vol`, `turnover_rate`/`turn`；收益由 open 重新计算。
- 样本区间: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28。
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买。
- 是否行业/市值中性: 未做行业/市值中性；test size_corr 约 0.43，是 promote blocker。
- 回测指标: Slurm GPU job `29557`，A800 `gpu2`，`ALPHA_BACKEND=torch_cuda`，H5，cost 5/10/20/30bps。Test RankIC 0.044898；long-short annual net 0.036556 / 0.022270 / -0.006300 / -0.034871；long-only annual net 0.181849 / 0.174633 / 0.160203 / 0.145772；long-only Sharpe 1.256 / 1.206 / 1.106 / 1.007。
- 成本后表现: long-only 多成本为正；long-short 诊断在 20/30bps 转负，且 H5 账本仍为诊断而非真实多日 sub-book ledger。
- reviewer score: 5/10。
- leakage/bias 审查结论: GPU sbatch 与多成本验证通过；仍存在 delayed-exit、H>1 真账本、size/industry neutral diagnostics、复权/退市审计缺口。
- decision: repair
- next action: 先实现 sell-limit/suspension delayed-exit 和 true H5/H10/H20 sub-book ledger，再做 size/industry neutral diagnostics；当前不 promote。
- 复现补充: Slurm job `29572` 再次用同一 launcher 在 A800 `gpu2` 完成，CUDA/Torch 可用、stderr 为 0，指标与 `29557` 一致；GPU 不是当前 blocker。

## 2026-06-05 — A022/A024/A025 GPU sbatch rerun

- alpha id: `A022/A024/A025`
- alpha 公式/逻辑: 继续 A020 方向内 repair；A022 低换手高流动低波中期动量，A024 低换手长周期防御动量，A025 价值流动低波中期动量。
- 使用字段: `ret_20_skip5`, `ret_60_skip20`, `turn`, `pb_inv`, `amihud_20`/`liq_inv`, `std_20`/`low_vol`, `score_liq_lowvol_lowturn_mid_mom`, `score_liq_lowvol_lowturn_long_mom`, `score_value_liq_lowvol_mid_mom`。
- 样本区间: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28。
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买。
- 是否行业/市值中性: none；当前只是流动性、低波动、低换手、价值暴露约束，尚未行业/市值中性。
- 回测指标: Slurm GPU job `29516`，A800 `gpu4`，`ALPHA_BACKEND=torch_cuda`，H1/H5/H10/H20。A022 Test RankIC 0.03148 / 0.03658 / 0.03395 / 0.02893；long-short 年化 -0.1787 / -0.0634 / -0.0899 / -0.1088；long-only 年化 0.0964 / 0.1417 / 0.1551 / 0.1582；long-only Sharpe 0.749 / 1.124 / 1.366 / 1.485。A024 H5 RankIC 0.03445，long-only 年化 0.1169，long-short 年化 -0.0951。A025 H5 RankIC 0.01696，long-only 年化 0.1588，long-short 年化 -0.1829。
- 成本后表现: 默认 10bps/side 后 long-only 为正，但所有候选 long-short 诊断仍为负；最大回撤仍偏大，容量和行业/市值暴露未过审。
- reviewer score: pending formal Codex reviewer；不能 promote。
- leakage/bias 审查结论: sbatch 日志确认 GPU 节点 CUDA/Torch 生效；当前信号路径仍为 t close 到 t+1 open，但复权、退市/幸存者偏差、行业/市值暴露、多档成本仍需 reviewer 审查。
- decision: repair
- next action: 把 A022/A024/A025 改造成明确 long-only/容量约束版本，增加成本敏感性、行业/市值中性和分行业稳定性；不要因 GPU 复跑正 long-only 直接 promote。

## 2026-06-05 — A022-A026 GPU repair/pivot batch completed

- alpha id: `A022/A023/A024/A025/A026`
- alpha 公式/逻辑: A020 方向内改进；A022 低换手高流动低波中期动量，A023/A024 长周期跳短反转动量，A025 价值流动低波中期动量，A026 中长周期动量共振防御。
- 使用字段: `ret_20_skip5`, `ret_60_skip20`, `turn`, `pb_inv`, `amihud_20`/`liq_inv`, `std_20`/`low_vol`, `score_liq_lowvol_lowturn_mid_mom`, `score_liq_lowvol_long_mom`, `score_liq_lowvol_lowturn_long_mom`, `score_value_liq_lowvol_mid_mom`, `score_mid_long_def_mom`。
- 样本区间: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28。
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买。
- 是否行业/市值中性: none；低波动/高流动/低换手/价值只是暴露约束，尚未做行业/市值中性。
- 回测指标: Slurm GPU job `29491`，A800 `gpu5`，`ALPHA_BACKEND=torch_cuda`，H1/H5/H10/H20。A022 Test RankIC 0.03148 / 0.03658 / 0.03395 / 0.02893；long-short 年化 -0.1787 / -0.0634 / -0.0899 / -0.1088；long-only 年化 0.0964 / 0.1417 / 0.1551 / 0.1582；long-only Sharpe 0.749 / 1.124 / 1.366 / 1.485。A024 H5 RankIC 0.03445，long-only 年化 0.1169，long-short 年化 -0.0951。A025 H5 RankIC 0.01696，long-only 年化 0.1588，long-short 年化 -0.1829。A023/A026 长持仓出现 RankIC 转负。
- 成本后表现: 默认 10bps/side 后 long-only 多数为正，但本批所有候选 long-short 诊断均为负，且未做多档成本/行业中性/容量审查。
- reviewer score: pending formal Codex reviewer；当前证据不足以 promote。
- leakage/bias 审查结论: 框架路径为 t close 信号到 t+1 open 交易，GPU 作业未发现 CUDA 环境问题；仍需 reviewer 检查复权基准、退市/幸存者偏差、行业/市值暴露和多成本档。
- decision: repair
- next action: 优先复审 A022 的 long-only/容量约束版本，增加成本敏感性、行业/市值中性和分年/分行业稳定性；A023/A026 暂不扩大搜索。

## 2026-06-04 — A022-A026 GPU repair/pivot batch submitted

- alpha id: `A022/A023/A024/A025/A026`
- alpha 公式/逻辑: A020 方向内改进；加入低换手约束、`ret_60_skip20` 长周期跳短反转动量、价值/流动性/低波动交互和中长周期动量共振。
- 使用字段: `ret_20_skip5`, `ret_60_skip20`, `turn`, `pb_inv`, `amihud_20`, `std_20`, `score_liq_lowvol_lowturn_mid_mom`, `score_liq_lowvol_long_mom`, `score_liq_lowvol_lowturn_long_mom`, `score_value_liq_lowvol_mid_mom`, `score_mid_long_def_mom`。
- 样本区间: 计划 train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28。
- 股票池: 日频面板内股票，剔除 ST/次日 ST、IPO 初期、低成交额、无成交/疑似停牌、疑似涨停不可买。
- 是否行业/市值中性: 尚未行业中性；低波动、高流动、低换手/价值交互为暴露约束，后续需检查市值/成交额暴露。
- 回测指标: pending；已提交 Slurm GPU job `29491`，A800，`ALPHA_BACKEND=torch_cuda`，H1/H5/H10/H20，`ALPHA_FAST=0`。
- 成本后表现: pending；默认 10bps/side proxy，正式 promote 前仍需成本敏感性。
- reviewer score: pending。
- leakage/bias 审查结论: pending；新增字段均由 t 日及之前 close/metric/moneyflow 滚动计算，仍需 reviewer 检查复权和可交易约束。
- decision: repair
- next action: 等待 job `29491` 完成后解析 `reports/slurm/alpha_gpu_backtest-29491.out` 与 `alpha-stage/artifacts/alpha_results.json`，只允许通过 reviewer 的候选进入 promote。

## 2026-06-04 — A020 GPU multi-horizon repair check

- alpha id: `A020`
- alpha 公式/逻辑: `rank(rank(ret_20_skip5)*rank(liq_inv)*rank(low_vol))`，高流动、低波动约束下的跳短反转中期动量。
- 使用字段: `ret_20_skip5`, `amihud_20`/`liq_inv`, `std_20`/`low_vol`, `open`, `next_open`, limit/ST/suspension proxy fields, `amount`, `vol`, `total_mv`。
- 样本区间: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28。
- 股票池: 日频面板内股票，信号池使用 t 日 point-in-time eligibility；次日涨停/ST/停牌/成交额等只作为选后成交仿真。
- 是否行业/市值中性: none；当前只记录市值/成交额暴露，未通过行业/市值中性审查。
- 回测指标: Slurm GPU job `29464`，A800 `torch_cuda`，H1/H5/H10/H20。Test RankIC 分别为 0.010715 / 0.008193 / 0.002126 / -0.011087；long-short 年化分别为 -0.2596 / -0.1676 / -0.1611 / -0.1767；long-only 年化分别为 0.1545 / 0.1866 / 0.1949 / 0.1848；long-only Sharpe 分别为 1.018 / 1.314 / 1.524 / 1.493。
- 成本后表现: 默认 10bps/side 后 long-only 为正，但 long-short 诊断全为负；H10 long-only 收益/Sharpe 最好但 MDD -0.4613，H20 RankIC 转负且 MDD -0.6643。
- reviewer score: pending updated reviewer；按现有 Codex reviewer 标准暂不 promote。
- leakage/bias 审查结论: GPU 作业验证了修复后的 point-in-time 排名池路径；仍需进一步审查 raw/adjusted price basis、delisting/survivorship、行业/市值暴露和多成本档。
- decision: repair
- next action: 把 A020 转成明确 long-only/容量约束候选，做成本敏感性、行业/市值中性、分年/分行业稳定性和 reviewer 复审；不要用当前 long-short 结果宣称可交易 alpha。

## 2026-06-04 — Post-review continuation rule

- alpha id: `A003/A005-family`
- alpha 公式/逻辑: previous killed formulas were `rank(ret_20)` and `-rank(amihud_20)`; continuation targets direction-level variants, not re-promoting the same failed formulas.
- 使用字段: `ret_20`, `amihud_20`, plus future repair candidates such as industry, market cap, liquidity, limit/suspension, and tradable raw price fields when point-in-time availability is proven.
- 样本区间: must rerun with non-empty train/validation/test after protocol repair.
- 股票池: point-in-time signal universe; next-day tradability fields only for fill simulation.
- 是否行业/市值中性: required for continuation variants or explicitly measured with neutralized diagnostics.
- 回测指标: current killed A003/A005 post-fix 2025-2026 H5 remained negative; no promote.
- 成本后表现: current implementations negative after costs in official reviewer window.
- reviewer score: current implementation score 1/10.
- leakage/bias 审查结论: kill applies to the current implementations and flawed/negative validation, not to the whole momentum or liquidity research direction.
- decision: repair/pivot
- next action: repair backtest protocol, then test neutralized momentum/liquidity variants before archiving the factor families.

## 2026-06-03T02:45:23 — A003 20日动量 H5

- alpha id: `A003`
- alpha 公式/逻辑: rank(ret_20)
- 使用字段: `ret_20`；收益字段由 panel open 重新计算
- 样本区间: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.102489, ICIR=17.261, Long-short Sharpe=27.344, MDD=-0.004, turnover=0.188
- 成本后表现: cost=10.0bps/side proxy, annual net=8.973265
- reviewer score: pending Codex reviewer; pilot heuristic score=7
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: positive but requires Codex reviewer before promote

## 2026-06-05T12:07:00 — A029 delayed-exit GPU rerun formal review

- alpha id: `A029`
- alpha 公式/逻辑: rank(rank(ret_20_skip5)*(1-rank(ret_5))*rank(liq_inv)*rank(low_vol)*(1-rank(turn)))
- 使用字段: `score_mid_mom_short_pullback_liq`；收益字段由 panel open 重新计算；计划退出日不可卖时最多顺延 `ALPHA_MAX_EXIT_DELAY_DAYS=10`
- 样本区间: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 股票池: 日频面板内股票，剔除 ST/次日 ST、IPO 初期 proxy、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；test size_corr=0.430367, amount_corr=0.018081
- 回测指标: Slurm job `29601` on A800, Test RankIC=0.045370, ICIR=4.943, 2025 RankIC=0.051405, 2026 RankIC=0.028708
- 成本后表现: long-short annual net at 5/10/20/30bps = 0.049197 / 0.034964 / 0.006497 / -0.021969；long-only annual net = 0.180551 / 0.173339 / 0.158914 / 0.144489
- reviewer score: 5/10
- leakage/bias 审查结论: delayed-exit 修复改善了未来退出可成交性 drop 问题，但 unresolved exits after max delay 仍为 NaN 并被后续丢弃；exit fillability 未完整覆盖停牌、成交额、ST、退市；H5 仍非真实多日账本；size exposure 高；原始 close 复权风险未审完
- decision: repair
- next action: 实现真实 staggered long-only portfolio ledger、forced/adverse unresolved exit 处理、完整 exit fillability、size/industry neutral diagnostics、复权审计后再用 sbatch 重跑

## 2026-06-03T02:45:23 — A005 Amihud流动性 H5

- alpha id: `A005`
- alpha 公式/逻辑: -rank(amihud_20)
- 使用字段: `amihud_20`；收益字段由 panel open 重新计算
- 样本区间: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.029177, ICIR=4.987, Long-short Sharpe=11.052, MDD=-0.031, turnover=0.060
- 成本后表现: cost=10.0bps/side proxy, annual net=3.242344
- reviewer score: pending Codex reviewer; pilot heuristic score=7
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: positive but requires Codex reviewer before promote

## 2026-06-03T02:45:23 — A003 20日动量 H1

- alpha id: `A003`
- alpha 公式/逻辑: rank(ret_20)
- 使用字段: `ret_20`；收益字段由 panel open 重新计算
- 样本区间: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.027201, ICIR=3.925, Long-short Sharpe=8.654, MDD=-0.017, turnover=0.187
- 成本后表现: cost=10.0bps/side proxy, annual net=1.545565
- reviewer score: pending Codex reviewer; pilot heuristic score=7
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: positive but requires Codex reviewer before promote

## 2026-06-03T02:45:23 — A005 Amihud流动性 H1

- alpha id: `A005`
- alpha 公式/逻辑: -rank(amihud_20)
- 使用字段: `amihud_20`；收益字段由 panel open 重新计算
- 样本区间: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.017463, ICIR=2.018, Long-short Sharpe=5.013, MDD=-0.031, turnover=0.061
- 成本后表现: cost=10.0bps/side proxy, annual net=0.889019
- reviewer score: pending Codex reviewer; pilot heuristic score=7
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: positive but requires Codex reviewer before promote

## 2026-06-03T02:45:23 — A001 1日反转 H1

- alpha id: `A001`
- alpha 公式/逻辑: -rank(ret_1)
- 使用字段: `ret_1`；收益字段由 panel open 重新计算
- 样本区间: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=-0.004341, ICIR=-0.603, Long-short Sharpe=-6.735, MDD=-0.106, turnover=0.805
- 成本后表现: cost=10.0bps/side proxy, annual net=-1.066627
- reviewer score: pending Codex reviewer; pilot heuristic score=1
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: kill
- next action: negative or inconclusive pilot

## 2026-06-03T02:45:23 — A004 低波动 H1

- alpha id: `A004`
- alpha 公式/逻辑: -rank(std_20)
- 使用字段: `std_20`；收益字段由 panel open 重新计算
- 样本区间: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=-0.014281, ICIR=-1.429, Long-short Sharpe=-5.761, MDD=-0.180, turnover=0.085
- 成本后表现: cost=10.0bps/side proxy, annual net=-1.354087
- reviewer score: pending Codex reviewer; pilot heuristic score=1
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: kill
- next action: negative or inconclusive pilot

## 2026-06-03T02:45:23 — A006 小市值 H1

- alpha id: `A006`
- alpha 公式/逻辑: -rank(mv_log)
- 使用字段: `mv_log`；收益字段由 panel open 重新计算
- 样本区间: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=-0.022867, ICIR=-2.525, Long-short Sharpe=-4.919, MDD=-0.093, turnover=0.036
- 成本后表现: cost=10.0bps/side proxy, annual net=-0.886074
- reviewer score: pending Codex reviewer; pilot heuristic score=1
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: kill
- next action: negative or inconclusive pilot

## 2026-06-03T02:45:23 — A002 5日反转 H1

- alpha id: `A002`
- alpha 公式/逻辑: -rank(ret_5)
- 使用字段: `ret_5`；收益字段由 panel open 重新计算
- 样本区间: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=-0.024652, ICIR=-3.198, Long-short Sharpe=-8.709, MDD=-0.148, turnover=0.373
- 成本后表现: cost=10.0bps/side proxy, annual net=-1.371717
- reviewer score: pending Codex reviewer; pilot heuristic score=1
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: kill
- next action: negative or inconclusive pilot

## 2026-06-03T02:45:23 — A006 小市值 H5

- alpha id: `A006`
- alpha 公式/逻辑: -rank(mv_log)
- 使用字段: `mv_log`；收益字段由 panel open 重新计算
- 样本区间: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=-0.037137, ICIR=-5.254, Long-short Sharpe=-6.991, MDD=-0.240, turnover=0.036
- 成本后表现: cost=10.0bps/side proxy, annual net=-2.724288
- reviewer score: pending Codex reviewer; pilot heuristic score=1
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: kill
- next action: negative or inconclusive pilot

## 2026-06-03T02:45:23 — A001 1日反转 H5

- alpha id: `A001`
- alpha 公式/逻辑: -rank(ret_1)
- 使用字段: `ret_1`；收益字段由 panel open 重新计算
- 样本区间: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=-0.030674, ICIR=-4.516, Long-short Sharpe=-9.042, MDD=-0.266, turnover=0.800
- 成本后表现: cost=10.0bps/side proxy, annual net=-3.117451
- reviewer score: pending Codex reviewer; pilot heuristic score=0
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: kill
- next action: negative or inconclusive pilot

## 2026-06-03T02:45:23 — A002 5日反转 H5

- alpha id: `A002`
- alpha 公式/逻辑: -rank(ret_5)
- 使用字段: `ret_5`；收益字段由 panel open 重新计算
- 样本区间: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=-0.065496, ICIR=-9.288, Long-short Sharpe=-14.865, MDD=-0.419, turnover=0.370
- 成本后表现: cost=10.0bps/side proxy, annual net=-5.055350
- reviewer score: pending Codex reviewer; pilot heuristic score=0
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: kill
- next action: negative or inconclusive pilot

## 2026-06-03T02:45:23 — A004 低波动 H5

- alpha id: `A004`
- alpha 公式/逻辑: -rank(std_20)
- 使用字段: `std_20`；收益字段由 panel open 重新计算
- 样本区间: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=-0.081803, ICIR=-11.008, Long-short Sharpe=-15.715, MDD=-0.561, turnover=0.084
- 成本后表现: cost=10.0bps/side proxy, annual net=-7.243939
- reviewer score: pending Codex reviewer; pilot heuristic score=0
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: kill
- next action: negative or inconclusive pilot

## 2026-06-03T02:51:23 — A003 20日动量 H5

- alpha id: `A003`
- alpha 公式/逻辑: rank(ret_20)
- 使用字段: `ret_20`；收益字段由 panel open 重新计算
- 样本区间: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=-0.055622, ICIR=-6.427, Long-short Sharpe=-2.019, MDD=-0.908, turnover=0.217
- 成本后表现: cost=10.0bps/side proxy, annual net=-0.931534
- reviewer score: pending Codex reviewer; pilot heuristic score=1
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: kill
- next action: negative or inconclusive pilot

## 2026-06-03T02:51:23 — A003 20日动量 H10

- alpha id: `A003`
- alpha 公式/逻辑: rank(ret_20)
- 使用字段: `ret_20`；收益字段由 panel open 重新计算
- 样本区间: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=-0.058732, ICIR=-6.551, Long-short Sharpe=-1.224, MDD=-0.949, turnover=0.217
- 成本后表现: cost=10.0bps/side proxy, annual net=-0.807639
- reviewer score: pending Codex reviewer; pilot heuristic score=1
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: kill
- next action: negative or inconclusive pilot

## 2026-06-03T02:51:23 — A005 Amihud流动性 H1

- alpha id: `A005`
- alpha 公式/逻辑: -rank(amihud_20)
- 使用字段: `amihud_20`；收益字段由 panel open 重新计算
- 样本区间: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=-0.016936, ICIR=-1.919, Long-short Sharpe=-1.701, MDD=-0.411, turnover=0.070
- 成本后表现: cost=10.0bps/side proxy, annual net=-0.288752
- reviewer score: pending Codex reviewer; pilot heuristic score=0
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: kill
- next action: negative or inconclusive pilot

## 2026-06-03T02:51:23 — A005 Amihud流动性 H5

- alpha id: `A005`
- alpha 公式/逻辑: -rank(amihud_20)
- 使用字段: `amihud_20`；收益字段由 panel open 重新计算
- 样本区间: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=-0.034542, ICIR=-4.395, Long-short Sharpe=-2.969, MDD=-0.883, turnover=0.070
- 成本后表现: cost=10.0bps/side proxy, annual net=-1.070797
- reviewer score: pending Codex reviewer; pilot heuristic score=0
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: kill
- next action: negative or inconclusive pilot

## 2026-06-03T02:51:23 — A003 20日动量 H1

- alpha id: `A003`
- alpha 公式/逻辑: rank(ret_20)
- 使用字段: `ret_20`；收益字段由 panel open 重新计算
- 样本区间: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=-0.043119, ICIR=-4.617, Long-short Sharpe=-1.866, MDD=-0.558, turnover=0.216
- 成本后表现: cost=10.0bps/side proxy, annual net=-0.436467
- reviewer score: pending Codex reviewer; pilot heuristic score=0
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: kill
- next action: negative or inconclusive pilot

## 2026-06-03T02:51:23 — A005 Amihud流动性 H10

- alpha id: `A005`
- alpha 公式/逻辑: -rank(amihud_20)
- 使用字段: `amihud_20`；收益字段由 panel open 重新计算
- 样本区间: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=-0.049606, ICIR=-6.449, Long-short Sharpe=-4.145, MDD=-0.983, turnover=0.070
- 成本后表现: cost=10.0bps/side proxy, annual net=-2.109901
- reviewer score: pending Codex reviewer; pilot heuristic score=0
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: kill
- next action: negative or inconclusive pilot

## 2026-06-03T02:51:23 — A005 Amihud流动性 H20

- alpha id: `A005`
- alpha 公式/逻辑: -rank(amihud_20)
- 使用字段: `amihud_20`；收益字段由 panel open 重新计算
- 样本区间: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=-0.069150, ICIR=-8.922, Long-short Sharpe=-6.199, MDD=-1.000, turnover=0.070
- 成本后表现: cost=10.0bps/side proxy, annual net=-4.661906
- reviewer score: pending Codex reviewer; pilot heuristic score=0
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: kill
- next action: negative or inconclusive pilot

## 2026-06-03T02:51:23 — A003 20日动量 H20

- alpha id: `A003`
- alpha 公式/逻辑: rank(ret_20)
- 使用字段: `ret_20`；收益字段由 panel open 重新计算
- 样本区间: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=-0.070761, ICIR=-8.326, Long-short Sharpe=-1.546, MDD=-0.986, turnover=0.218
- 成本后表现: cost=10.0bps/side proxy, annual net=-1.280163
- reviewer score: pending Codex reviewer; pilot heuristic score=0
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: kill
- next action: negative or inconclusive pilot

## 2026-06-03T02:55:57 — A005 Amihud流动性 H5

- alpha id: `A005`
- alpha 公式/逻辑: -rank(amihud_20)
- 使用字段: `amihud_20`；收益字段由 panel open 重新计算
- 样本区间: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=-0.034542, ICIR=-4.395, Long-short Sharpe=-2.969, MDD=-0.883, turnover=0.070
- 成本后表现: cost=10.0bps/side proxy, annual net=-1.070797
- reviewer score: pending Codex reviewer; pilot heuristic score=0
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: kill
- next action: negative or inconclusive pilot

## 2026-06-03T02:55:57 — A003 20日动量 H5

- alpha id: `A003`
- alpha 公式/逻辑: rank(ret_20)
- 使用字段: `ret_20`；收益字段由 panel open 重新计算
- 样本区间: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=-0.055622, ICIR=-6.427, Long-short Sharpe=-2.019, MDD=-0.908, turnover=0.217
- 成本后表现: cost=10.0bps/side proxy, annual net=-0.931534
- reviewer score: pending Codex reviewer; pilot heuristic score=0
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: kill
- next action: negative or inconclusive pilot

## 2026-06-03T02:56:56 — A005 Amihud流动性 H5

- alpha id: `A005`
- alpha 公式/逻辑: -rank(amihud_20)
- 使用字段: `amihud_20`；收益字段由 panel open 重新计算
- 样本区间: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=-0.029378, ICIR=-3.540, Long-short Sharpe=-1.180, MDD=-0.669, turnover=0.066
- 成本后表现: cost=10.0bps/side proxy, annual net=-0.425822
- reviewer score: pending Codex reviewer; pilot heuristic score=0
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: kill
- next action: negative or inconclusive pilot

## 2026-06-03T02:56:56 — A003 20日动量 H5

- alpha id: `A003`
- alpha 公式/逻辑: rank(ret_20)
- 使用字段: `ret_20`；收益字段由 panel open 重新计算
- 样本区间: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=-0.052161, ICIR=-6.452, Long-short Sharpe=-1.268, MDD=-0.814, turnover=0.214
- 成本后表现: cost=10.0bps/side proxy, annual net=-0.569114
- reviewer score: pending Codex reviewer; pilot heuristic score=0
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: kill
- next action: negative or inconclusive pilot

## 2026-06-03T03:02:15 — A003 20日动量 H5

- alpha id: `A003`
- alpha 公式/逻辑: rank(ret_20)
- 使用字段: `ret_20`；收益字段由 panel open 重新计算
- 样本区间: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.100344, ICIR=16.493, Long-short Sharpe=11.655, MDD=-0.008, turnover=0.190
- 成本后表现: cost=10.0bps/side proxy, annual net=1.738199
- reviewer score: pending Codex reviewer; pilot heuristic score=6
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: positive but requires Codex reviewer before promote

## 2026-06-03T03:02:15 — A005 Amihud流动性 H5

- alpha id: `A005`
- alpha 公式/逻辑: -rank(amihud_20)
- 使用字段: `amihud_20`；收益字段由 panel open 重新计算
- 样本区间: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.030910, ICIR=5.284, Long-short Sharpe=4.989, MDD=-0.029, turnover=0.065
- 成本后表现: cost=10.0bps/side proxy, annual net=0.665367
- reviewer score: pending Codex reviewer; pilot heuristic score=6
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: positive but requires Codex reviewer before promote

## 2026-06-03T03:04:00 — A005 Amihud流动性 H5

- alpha id: `A005`
- alpha 公式/逻辑: -rank(amihud_20)
- 使用字段: `amihud_20`；收益字段由 panel open 重新计算
- 样本区间: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=-0.028352, ICIR=-3.419, Long-short Sharpe=-0.485, MDD=-0.673, turnover=0.069
- 成本后表现: cost=10.0bps/side proxy, annual net=-0.078622
- reviewer score: pending Codex reviewer; pilot heuristic score=0
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: kill
- next action: negative or inconclusive pilot

### Reviewer update

- reviewer score: 1/10
- leakage/bias 审查结论: Codex reviewer found prior framework issues; after repairs, post-fix 2025-2026 run remains negative. No promote.
- decision: kill
- next action: pivot to next alpha family after keeping point-in-time universe and corrected H>1 accounting.

## 2026-06-03T03:04:00 — A003 20日动量 H5

- alpha id: `A003`
- alpha 公式/逻辑: rank(ret_20)
- 使用字段: `ret_20`；收益字段由 panel open 重新计算
- 样本区间: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=-0.052497, ICIR=-6.482, Long-short Sharpe=-0.631, MDD=-0.822, turnover=0.215
- 成本后表现: cost=10.0bps/side proxy, annual net=-0.127069
- reviewer score: pending Codex reviewer; pilot heuristic score=0
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: kill
- next action: negative or inconclusive pilot

### Reviewer update

- reviewer score: 1/10
- leakage/bias 审查结论: Codex reviewer found prior framework issues; after repairs, post-fix 2025-2026 run remains negative. No promote.
- decision: kill
- next action: pivot to next alpha family after keeping point-in-time universe and corrected H>1 accounting.
## 2026-06-04T21:45:02 — A020 高流动低波中期动量 H5

- alpha id: `A020`
- alpha 公式/逻辑: rank(rank(ret_20_skip5)*rank(liq_inv)*rank(low_vol))
- 使用字段: `score_liq_lowvol_mid_mom`；收益字段由 panel open 重新计算
- 样本区间: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.010150, ICIR=1.211, Long-short Sharpe=-0.778, MDD=-0.620, turnover=0.190
- 成本后表现: cost=10.0bps/side proxy, annual net=-0.134267
- reviewer score: pending Codex reviewer; pilot heuristic score=5
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: mixed positive; inspect costs/exposures/leakage

## 2026-06-04T21:45:02 — A021 流动性改善 H5

- alpha id: `A021`
- alpha 公式/逻辑: rank(amihud_20-amihud_5)
- 使用字段: `score_liq_improve`；收益字段由 panel open 重新计算
- 样本区间: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=-0.017522, ICIR=-3.671, Long-short Sharpe=-0.981, MDD=-0.499, turnover=0.355
- 成本后表现: cost=10.0bps/side proxy, annual net=-0.089391
- reviewer score: pending Codex reviewer; pilot heuristic score=3
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: kill
- next action: negative or inconclusive pilot

## 2026-06-04T21:45:02 — A019 跳过短反转的中期动量 H5

- alpha id: `A019`
- alpha 公式/逻辑: rank(ret_20_skip5)
- 使用字段: `ret_20_skip5`；收益字段由 panel open 重新计算
- 样本区间: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=-0.031045, ICIR=-3.871, Long-short Sharpe=0.141, MDD=-0.652, turnover=0.241
- 成本后表现: cost=10.0bps/side proxy, annual net=0.025841
- reviewer score: pending Codex reviewer; pilot heuristic score=3
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: kill
- next action: negative or inconclusive pilot

## 2026-06-04 — Post-kill continuation clarification

- alpha id: `A019/A020/A021`
- alpha 公式/逻辑: A019 `rank(ret_20_skip5)`；A020 `rank(rank(ret_20_skip5)*rank(liq_inv)*rank(low_vol))`；A021 `rank(amihud_20-amihud_5)`。
- 使用字段: `ret_20_skip5`, `score_liq_lowvol_mid_mom`, `score_liq_improve`；收益字段由 raw open 现场计算。
- 样本区间: 2025-01-01 到 2026-05-28 smoke；train/validation rows 为 0，因此不能 promote，只能用于验证继续改进方向和脚本补丁。
- 股票池: 当前日频面板内股票；信号排名池只用 t 日可见字段，次日买入/退出可行性只在选后成交仿真阶段过滤。
- 是否行业/市值中性: 未行业中性；A020 用高流动、低波动交互减弱原始 A003/A005 暴露。
- 回测指标: A020 Test RankIC=0.01015, long-short annual net=-0.1343, long-only annual net=0.2268；A019 Test RankIC=-0.03104, long-short annual net=0.0258, long-only annual net=0.4227；A021 Test RankIC=-0.01752, long-short annual net=-0.0894, long-only annual net=0.3117。
- 成本后表现: 当前为 10bps/side proxy；long-only 短窗为正但 long-short 诊断不稳，且无 train/validation。
- reviewer score: pending；不可用短窗结果申请 reviewer promote。
- leakage/bias 审查结论: 已修复“未来收益缺失在排名前 dropna”的排序池污染；仍需全量非空 train/validation/test、复权/退市风险确认和更快缓存后再审。
- decision: repair
- next action: 增加 panel parquet/cache 或按日期预聚合以支撑 2019-2026 全量 rerun；之后优先复测 A020 和 A019 的 long-only/hedge-aware 版本。
## 2026-06-04T22:35:38 — A020 高流动低波中期动量 H5

- alpha id: `A020`
- alpha 公式/逻辑: rank(rank(ret_20_skip5)*rank(liq_inv)*rank(low_vol))
- 使用字段: `score_liq_lowvol_mid_mom`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3059463, dates=912; validation rows=2141512, dates=484; test rows=1714832, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.008206, ICIR=0.876, Long-short Sharpe=-0.859, MDD=-0.786, turnover=0.191
- 成本后表现: cost=10.0bps/side proxy, annual net=-0.167693
- reviewer score: pending Codex reviewer; pilot heuristic score=6
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: positive but requires Codex reviewer before promote

## 2026-06-04T22:37:12 — A019 跳过短反转的中期动量 H5

- alpha id: `A019`
- alpha 公式/逻辑: rank(ret_20_skip5)
- 使用字段: `ret_20_skip5`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3059463, dates=912; validation rows=2141512, dates=484; test rows=1714832, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=-0.034180, ICIR=-3.995, Long-short Sharpe=-0.123, MDD=-0.755, turnover=0.243
- 成本后表现: cost=10.0bps/side proxy, annual net=-0.023309
- reviewer score: pending Codex reviewer; pilot heuristic score=3
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: kill
- next action: negative or inconclusive pilot

## 2026-06-04T22:38:28 — A021 流动性改善 H5

- alpha id: `A021`
- alpha 公式/逻辑: rank(amihud_20-amihud_5)
- 使用字段: `score_liq_improve`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3059463, dates=912; validation rows=2141512, dates=484; test rows=1714832, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=-0.014980, ICIR=-3.125, Long-short Sharpe=-0.811, MDD=-0.511, turnover=0.358
- 成本后表现: cost=10.0bps/side proxy, annual net=-0.075020
- reviewer score: pending Codex reviewer; pilot heuristic score=3
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: kill
- next action: negative or inconclusive pilot

## 2026-06-04T22:43:51 — A020 高流动低波中期动量 H5

- alpha id: `A020`
- alpha 公式/逻辑: rank(rank(ret_20_skip5)*rank(liq_inv)*rank(low_vol))
- 使用字段: `score_liq_lowvol_mid_mom`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3059463, dates=912; validation rows=2141512, dates=484; test rows=1714832, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.008206, ICIR=0.876, Long-short Sharpe=-0.859, MDD=-0.786, turnover=0.191
- 成本后表现: cost=10.0bps/side proxy, annual net=-0.167693
- reviewer score: pending Codex reviewer; pilot heuristic score=6
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: positive but requires Codex reviewer before promote

## 2026-06-04T22:43:51 — A021 流动性改善 H5

- alpha id: `A021`
- alpha 公式/逻辑: rank(amihud_20-amihud_5)
- 使用字段: `score_liq_improve`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3059463, dates=912; validation rows=2141512, dates=484; test rows=1714832, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=-0.014980, ICIR=-3.125, Long-short Sharpe=-0.811, MDD=-0.511, turnover=0.358
- 成本后表现: cost=10.0bps/side proxy, annual net=-0.075020
- reviewer score: pending Codex reviewer; pilot heuristic score=3
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: kill
- next action: negative or inconclusive pilot

## 2026-06-04T22:43:51 — A019 跳过短反转的中期动量 H5

- alpha id: `A019`
- alpha 公式/逻辑: rank(ret_20_skip5)
- 使用字段: `ret_20_skip5`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3059463, dates=912; validation rows=2141512, dates=484; test rows=1714832, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=-0.034180, ICIR=-3.995, Long-short Sharpe=-0.123, MDD=-0.755, turnover=0.243
- 成本后表现: cost=10.0bps/side proxy, annual net=-0.023309
- reviewer score: pending Codex reviewer; pilot heuristic score=3
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: kill
- next action: negative or inconclusive pilot

## 2026-06-04T22:49:53 — A020 高流动低波中期动量 H5

- alpha id: `A020`
- alpha 公式/逻辑: rank(rank(ret_20_skip5)*rank(liq_inv)*rank(low_vol))
- 使用字段: `score_liq_lowvol_mid_mom`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3059463, dates=912; validation rows=2141512, dates=484; test rows=1714832, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.008193, ICIR=0.874, Long-short Sharpe=-0.858, MDD=-0.786, turnover=0.191
- 成本后表现: cost=10.0bps/side proxy, annual net=-0.167649
- reviewer score: pending Codex reviewer; pilot heuristic score=6
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: positive but requires Codex reviewer before promote

## 2026-06-04T22:49:53 — A021 流动性改善 H5

- alpha id: `A021`
- alpha 公式/逻辑: rank(amihud_20-amihud_5)
- 使用字段: `score_liq_improve`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3059463, dates=912; validation rows=2141512, dates=484; test rows=1714832, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=-0.014973, ICIR=-3.124, Long-short Sharpe=-0.814, MDD=-0.511, turnover=0.358
- 成本后表现: cost=10.0bps/side proxy, annual net=-0.075295
- reviewer score: pending Codex reviewer; pilot heuristic score=3
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: kill
- next action: negative or inconclusive pilot

## 2026-06-04T22:49:53 — A019 跳过短反转的中期动量 H5

- alpha id: `A019`
- alpha 公式/逻辑: rank(ret_20_skip5)
- 使用字段: `ret_20_skip5`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3059463, dates=912; validation rows=2141512, dates=484; test rows=1714832, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=-0.034176, ICIR=-3.995, Long-short Sharpe=-0.122, MDD=-0.755, turnover=0.243
- 成本后表现: cost=10.0bps/side proxy, annual net=-0.023153
- reviewer score: pending Codex reviewer; pilot heuristic score=3
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: kill
- next action: negative or inconclusive pilot

## 2026-06-04T23:27:08 — A020 高流动低波中期动量 H1

- alpha id: `A020`
- alpha 公式/逻辑: rank(rank(ret_20_skip5)*rank(liq_inv)*rank(low_vol))
- 使用字段: `score_liq_lowvol_mid_mom`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3059463, dates=912; validation rows=2141512, dates=484; test rows=1714832, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.010715, ICIR=1.127, Long-short Sharpe=-1.282, MDD=-0.377, turnover=0.191
- 成本后表现: cost=10.0bps/side proxy, annual net=-0.259550
- reviewer score: pending Codex reviewer; pilot heuristic score=7
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: positive but requires Codex reviewer before promote

## 2026-06-04T23:28:39 — A020 高流动低波中期动量 H1

- alpha id: `A020`
- alpha 公式/逻辑: rank(rank(ret_20_skip5)*rank(liq_inv)*rank(low_vol))
- 使用字段: `score_liq_lowvol_mid_mom`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3059463, dates=912; validation rows=2141512, dates=484; test rows=1714832, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.010715, ICIR=1.127, Long-short Sharpe=-1.282, MDD=-0.377, turnover=0.191
- 成本后表现: cost=10.0bps/side proxy, annual net=-0.259550
- reviewer score: pending Codex reviewer; pilot heuristic score=7
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: positive but requires Codex reviewer before promote

## 2026-06-04T23:28:39 — A020 高流动低波中期动量 H5

- alpha id: `A020`
- alpha 公式/逻辑: rank(rank(ret_20_skip5)*rank(liq_inv)*rank(low_vol))
- 使用字段: `score_liq_lowvol_mid_mom`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3059463, dates=912; validation rows=2141512, dates=484; test rows=1714832, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.008193, ICIR=0.874, Long-short Sharpe=-0.858, MDD=-0.786, turnover=0.191
- 成本后表现: cost=10.0bps/side proxy, annual net=-0.167649
- reviewer score: pending Codex reviewer; pilot heuristic score=6
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: positive but requires Codex reviewer before promote

## 2026-06-04T23:28:39 — A020 高流动低波中期动量 H10

- alpha id: `A020`
- alpha 公式/逻辑: rank(rank(ret_20_skip5)*rank(liq_inv)*rank(low_vol))
- 使用字段: `score_liq_lowvol_mid_mom`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3059463, dates=912; validation rows=2141512, dates=484; test rows=1714832, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.002126, ICIR=0.217, Long-short Sharpe=-0.830, MDD=-0.935, turnover=0.192
- 成本后表现: cost=10.0bps/side proxy, annual net=-0.161144
- reviewer score: pending Codex reviewer; pilot heuristic score=6
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: positive but requires Codex reviewer before promote

## 2026-06-04T23:28:39 — A020 高流动低波中期动量 H20

- alpha id: `A020`
- alpha 公式/逻辑: rank(rank(ret_20_skip5)*rank(liq_inv)*rank(low_vol))
- 使用字段: `score_liq_lowvol_mid_mom`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3059463, dates=912; validation rows=2141512, dates=484; test rows=1714832, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=-0.011087, ICIR=-1.120, Long-short Sharpe=-0.875, MDD=-0.993, turnover=0.191
- 成本后表现: cost=10.0bps/side proxy, annual net=-0.176726
- reviewer score: pending Codex reviewer; pilot heuristic score=4
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: mixed positive; inspect costs/exposures/leakage
## 2026-06-05T00:13:44 — A022 低换手高流动低波中期动量 H1

- alpha id: `A022`
- alpha 公式/逻辑: rank(rank(ret_20_skip5)*rank(liq_inv)*rank(low_vol)*(1-rank(turn)))
- 使用字段: `score_liq_lowvol_lowturn_mid_mom`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3057834, dates=912; validation rows=2141512, dates=484; test rows=1714832, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.031481, ICIR=2.848, Long-short Sharpe=-0.746, MDD=-0.308, turnover=0.200
- 成本后表现: cost=10.0bps/side proxy, annual net=-0.178715
- reviewer score: pending Codex reviewer; pilot heuristic score=8
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: positive but requires Codex reviewer before promote

## 2026-06-05T00:13:44 — A025 价值流动低波中期动量 H1

- alpha id: `A025`
- alpha 公式/逻辑: rank(rank(ret_20_skip5)*rank(pb_inv)*rank(liq_inv)*rank(low_vol))
- 使用字段: `score_value_liq_lowvol_mid_mom`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3052267, dates=912; validation rows=2138028, dates=484; test rows=1711434, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.016943, ICIR=1.593, Long-short Sharpe=-1.138, MDD=-0.362, turnover=0.145
- 成本后表现: cost=10.0bps/side proxy, annual net=-0.252787
- reviewer score: pending Codex reviewer; pilot heuristic score=8
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: positive but requires Codex reviewer before promote

## 2026-06-05T00:13:44 — A023 高流动低波长周期动量 H1

- alpha id: `A023`
- alpha 公式/逻辑: rank(rank(ret_60_skip20)*rank(liq_inv)*rank(low_vol))
- 使用字段: `score_liq_lowvol_long_mom`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3059463, dates=912; validation rows=2141512, dates=484; test rows=1714832, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.015090, ICIR=1.860, Long-short Sharpe=-1.607, MDD=-0.367, turnover=0.150
- 成本后表现: cost=10.0bps/side proxy, annual net=-0.272090
- reviewer score: pending Codex reviewer; pilot heuristic score=8
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: positive but requires Codex reviewer before promote

## 2026-06-05T00:13:44 — A026 中长周期动量共振防御 H1

- alpha id: `A026`
- alpha 公式/逻辑: rank(rank(ret_20_skip5)*rank(ret_60_skip20)*rank(liq_inv)*rank(low_vol))
- 使用字段: `score_mid_long_def_mom`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3059463, dates=912; validation rows=2141512, dates=484; test rows=1714832, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.007020, ICIR=0.855, Long-short Sharpe=-1.373, MDD=-0.335, turnover=0.195
- 成本后表现: cost=10.0bps/side proxy, annual net=-0.227981
- reviewer score: pending Codex reviewer; pilot heuristic score=8
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: positive but requires Codex reviewer before promote

## 2026-06-05T00:13:44 — A022 低换手高流动低波中期动量 H5

- alpha id: `A022`
- alpha 公式/逻辑: rank(rank(ret_20_skip5)*rank(liq_inv)*rank(low_vol)*(1-rank(turn)))
- 使用字段: `score_liq_lowvol_lowturn_mid_mom`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3057834, dates=912; validation rows=2141512, dates=484; test rows=1714832, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.036576, ICIR=3.524, Long-short Sharpe=-0.288, MDD=-0.619, turnover=0.201
- 成本后表现: cost=10.0bps/side proxy, annual net=-0.063407
- reviewer score: pending Codex reviewer; pilot heuristic score=7
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: positive but requires Codex reviewer before promote

## 2026-06-05T00:13:44 — A024 低换手长周期防御动量 H5

- alpha id: `A024`
- alpha 公式/逻辑: rank(rank(ret_60_skip20)*rank(liq_inv)*rank(low_vol)*(1-rank(turn)))
- 使用字段: `score_liq_lowvol_lowturn_long_mom`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3057834, dates=912; validation rows=2141512, dates=484; test rows=1714832, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.034446, ICIR=3.758, Long-short Sharpe=-0.463, MDD=-0.626, turnover=0.178
- 成本后表现: cost=10.0bps/side proxy, annual net=-0.095066
- reviewer score: pending Codex reviewer; pilot heuristic score=7
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: positive but requires Codex reviewer before promote

## 2026-06-05T00:13:44 — A022 低换手高流动低波中期动量 H10

- alpha id: `A022`
- alpha 公式/逻辑: rank(rank(ret_20_skip5)*rank(liq_inv)*rank(low_vol)*(1-rank(turn)))
- 使用字段: `score_liq_lowvol_lowturn_mid_mom`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3057834, dates=912; validation rows=2141512, dates=484; test rows=1714832, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.033949, ICIR=3.125, Long-short Sharpe=-0.412, MDD=-0.832, turnover=0.200
- 成本后表现: cost=10.0bps/side proxy, annual net=-0.089870
- reviewer score: pending Codex reviewer; pilot heuristic score=7
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: positive but requires Codex reviewer before promote

## 2026-06-05T00:13:44 — A024 低换手长周期防御动量 H1

- alpha id: `A024`
- alpha 公式/逻辑: rank(rank(ret_60_skip20)*rank(liq_inv)*rank(low_vol)*(1-rank(turn)))
- 使用字段: `score_liq_lowvol_lowturn_long_mom`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3057834, dates=912; validation rows=2141512, dates=484; test rows=1714832, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.033578, ICIR=3.283, Long-short Sharpe=-0.881, MDD=-0.313, turnover=0.178
- 成本后表现: cost=10.0bps/side proxy, annual net=-0.195100
- reviewer score: pending Codex reviewer; pilot heuristic score=7
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: positive but requires Codex reviewer before promote

## 2026-06-05T00:13:44 — A022 低换手高流动低波中期动量 H20

- alpha id: `A022`
- alpha 公式/逻辑: rank(rank(ret_20_skip5)*rank(liq_inv)*rank(low_vol)*(1-rank(turn)))
- 使用字段: `score_liq_lowvol_lowturn_mid_mom`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3057834, dates=912; validation rows=2141512, dates=484; test rows=1714832, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.028929, ICIR=2.593, Long-short Sharpe=-0.489, MDD=-0.967, turnover=0.199
- 成本后表现: cost=10.0bps/side proxy, annual net=-0.108803
- reviewer score: pending Codex reviewer; pilot heuristic score=7
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: positive but requires Codex reviewer before promote

## 2026-06-05T00:13:44 — A024 低换手长周期防御动量 H20

- alpha id: `A024`
- alpha 公式/逻辑: rank(rank(ret_60_skip20)*rank(liq_inv)*rank(low_vol)*(1-rank(turn)))
- 使用字段: `score_liq_lowvol_lowturn_long_mom`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3057834, dates=912; validation rows=2141512, dates=484; test rows=1714832, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.027080, ICIR=2.969, Long-short Sharpe=-0.638, MDD=-0.968, turnover=0.178
- 成本后表现: cost=10.0bps/side proxy, annual net=-0.119568
- reviewer score: pending Codex reviewer; pilot heuristic score=7
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: positive but requires Codex reviewer before promote

## 2026-06-05T00:13:44 — A024 低换手长周期防御动量 H10

- alpha id: `A024`
- alpha 公式/逻辑: rank(rank(ret_60_skip20)*rank(liq_inv)*rank(low_vol)*(1-rank(turn)))
- 使用字段: `score_liq_lowvol_lowturn_long_mom`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3057834, dates=912; validation rows=2141512, dates=484; test rows=1714832, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.026992, ICIR=2.965, Long-short Sharpe=-0.620, MDD=-0.848, turnover=0.178
- 成本后表现: cost=10.0bps/side proxy, annual net=-0.121836
- reviewer score: pending Codex reviewer; pilot heuristic score=7
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: positive but requires Codex reviewer before promote

## 2026-06-05T00:13:44 — A025 价值流动低波中期动量 H5

- alpha id: `A025`
- alpha 公式/逻辑: rank(rank(ret_20_skip5)*rank(pb_inv)*rank(liq_inv)*rank(low_vol))
- 使用字段: `score_value_liq_lowvol_mid_mom`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3052267, dates=912; validation rows=2138028, dates=484; test rows=1711434, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.016958, ICIR=1.643, Long-short Sharpe=-0.867, MDD=-0.754, turnover=0.145
- 成本后表现: cost=10.0bps/side proxy, annual net=-0.182876
- reviewer score: pending Codex reviewer; pilot heuristic score=7
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: positive but requires Codex reviewer before promote

## 2026-06-05T00:13:44 — A025 价值流动低波中期动量 H10

- alpha id: `A025`
- alpha 公式/逻辑: rank(rank(ret_20_skip5)*rank(pb_inv)*rank(liq_inv)*rank(low_vol))
- 使用字段: `score_value_liq_lowvol_mid_mom`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3052267, dates=912; validation rows=2138028, dates=484; test rows=1711434, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.013929, ICIR=1.312, Long-short Sharpe=-0.837, MDD=-0.922, turnover=0.145
- 成本后表现: cost=10.0bps/side proxy, annual net=-0.173855
- reviewer score: pending Codex reviewer; pilot heuristic score=7
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: positive but requires Codex reviewer before promote

## 2026-06-05T00:13:44 — A025 价值流动低波中期动量 H20

- alpha id: `A025`
- alpha 公式/逻辑: rank(rank(ret_20_skip5)*rank(pb_inv)*rank(liq_inv)*rank(low_vol))
- 使用字段: `score_value_liq_lowvol_mid_mom`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3052267, dates=912; validation rows=2138028, dates=484; test rows=1711434, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.009322, ICIR=0.851, Long-short Sharpe=-0.755, MDD=-0.991, turnover=0.144
- 成本后表现: cost=10.0bps/side proxy, annual net=-0.163830
- reviewer score: pending Codex reviewer; pilot heuristic score=7
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: positive but requires Codex reviewer before promote

## 2026-06-05T00:13:44 — A023 高流动低波长周期动量 H5

- alpha id: `A023`
- alpha 公式/逻辑: rank(rank(ret_60_skip20)*rank(liq_inv)*rank(low_vol))
- 使用字段: `score_liq_lowvol_long_mom`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3059463, dates=912; validation rows=2141512, dates=484; test rows=1714832, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.007990, ICIR=1.117, Long-short Sharpe=-1.187, MDD=-0.792, turnover=0.150
- 成本后表现: cost=10.0bps/side proxy, annual net=-0.197583
- reviewer score: pending Codex reviewer; pilot heuristic score=7
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: positive but requires Codex reviewer before promote

## 2026-06-05T00:13:44 — A026 中长周期动量共振防御 H5

- alpha id: `A026`
- alpha 公式/逻辑: rank(rank(ret_20_skip5)*rank(ret_60_skip20)*rank(liq_inv)*rank(low_vol))
- 使用字段: `score_mid_long_def_mom`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3059463, dates=912; validation rows=2141512, dates=484; test rows=1714832, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=-0.001644, ICIR=-0.206, Long-short Sharpe=-0.922, MDD=-0.773, turnover=0.195
- 成本后表现: cost=10.0bps/side proxy, annual net=-0.160628
- reviewer score: pending Codex reviewer; pilot heuristic score=5
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: mixed positive; inspect costs/exposures/leakage

## 2026-06-05T00:13:44 — A023 高流动低波长周期动量 H20

- alpha id: `A023`
- alpha 公式/逻辑: rank(rank(ret_60_skip20)*rank(liq_inv)*rank(low_vol))
- 使用字段: `score_liq_lowvol_long_mom`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3059463, dates=912; validation rows=2141512, dates=484; test rows=1714832, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=-0.008387, ICIR=-1.207, Long-short Sharpe=-1.077, MDD=-0.987, turnover=0.150
- 成本后表现: cost=10.0bps/side proxy, annual net=-0.161062
- reviewer score: pending Codex reviewer; pilot heuristic score=5
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: mixed positive; inspect costs/exposures/leakage

## 2026-06-05T00:13:44 — A026 中长周期动量共振防御 H10

- alpha id: `A026`
- alpha 公式/逻辑: rank(rank(ret_20_skip5)*rank(ret_60_skip20)*rank(liq_inv)*rank(low_vol))
- 使用字段: `score_mid_long_def_mom`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3059463, dates=912; validation rows=2141512, dates=484; test rows=1714832, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=-0.012195, ICIR=-1.579, Long-short Sharpe=-0.893, MDD=-0.919, turnover=0.196
- 成本后表现: cost=10.0bps/side proxy, annual net=-0.148887
- reviewer score: pending Codex reviewer; pilot heuristic score=5
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: mixed positive; inspect costs/exposures/leakage

## 2026-06-05T00:13:44 — A026 中长周期动量共振防御 H20

- alpha id: `A026`
- alpha 公式/逻辑: rank(rank(ret_20_skip5)*rank(ret_60_skip20)*rank(liq_inv)*rank(low_vol))
- 使用字段: `score_mid_long_def_mom`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3059463, dates=912; validation rows=2141512, dates=484; test rows=1714832, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=-0.022491, ICIR=-3.027, Long-short Sharpe=-0.895, MDD=-0.988, turnover=0.195
- 成本后表现: cost=10.0bps/side proxy, annual net=-0.141426
- reviewer score: pending Codex reviewer; pilot heuristic score=5
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: mixed positive; inspect costs/exposures/leakage

## 2026-06-05T00:13:44 — A023 高流动低波长周期动量 H10

- alpha id: `A023`
- alpha 公式/逻辑: rank(rank(ret_60_skip20)*rank(liq_inv)*rank(low_vol))
- 使用字段: `score_liq_lowvol_long_mom`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3059463, dates=912; validation rows=2141512, dates=484; test rows=1714832, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=-0.003820, ICIR=-0.546, Long-short Sharpe=-1.203, MDD=-0.934, turnover=0.150
- 成本后表现: cost=10.0bps/side proxy, annual net=-0.190002
- reviewer score: pending Codex reviewer; pilot heuristic score=4
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: mixed positive; inspect costs/exposures/leakage
## 2026-06-05T00:32:08 — A022 低换手高流动低波中期动量 H1

- alpha id: `A022`
- alpha 公式/逻辑: rank(rank(ret_20_skip5)*rank(liq_inv)*rank(low_vol)*(1-rank(turn)))
- 使用字段: `score_liq_lowvol_lowturn_mid_mom`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3057834, dates=912; validation rows=2141512, dates=484; test rows=1714832, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.031481, ICIR=2.848, Long-short Sharpe=-0.746, MDD=-0.308, turnover=0.200
- 成本后表现: cost=10.0bps/side proxy, annual net=-0.178715
- reviewer score: pending Codex reviewer; pilot heuristic score=8
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: positive but requires Codex reviewer before promote

## 2026-06-05T00:32:08 — A025 价值流动低波中期动量 H1

- alpha id: `A025`
- alpha 公式/逻辑: rank(rank(ret_20_skip5)*rank(pb_inv)*rank(liq_inv)*rank(low_vol))
- 使用字段: `score_value_liq_lowvol_mid_mom`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3052267, dates=912; validation rows=2138028, dates=484; test rows=1711434, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.016943, ICIR=1.593, Long-short Sharpe=-1.138, MDD=-0.362, turnover=0.145
- 成本后表现: cost=10.0bps/side proxy, annual net=-0.252787
- reviewer score: pending Codex reviewer; pilot heuristic score=8
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: positive but requires Codex reviewer before promote

## 2026-06-05T00:32:08 — A022 低换手高流动低波中期动量 H5

- alpha id: `A022`
- alpha 公式/逻辑: rank(rank(ret_20_skip5)*rank(liq_inv)*rank(low_vol)*(1-rank(turn)))
- 使用字段: `score_liq_lowvol_lowturn_mid_mom`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3057834, dates=912; validation rows=2141512, dates=484; test rows=1714832, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.036576, ICIR=3.524, Long-short Sharpe=-0.288, MDD=-0.619, turnover=0.201
- 成本后表现: cost=10.0bps/side proxy, annual net=-0.063407
- reviewer score: pending Codex reviewer; pilot heuristic score=7
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: positive but requires Codex reviewer before promote

## 2026-06-05T00:32:08 — A024 低换手长周期防御动量 H5

- alpha id: `A024`
- alpha 公式/逻辑: rank(rank(ret_60_skip20)*rank(liq_inv)*rank(low_vol)*(1-rank(turn)))
- 使用字段: `score_liq_lowvol_lowturn_long_mom`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3057834, dates=912; validation rows=2141512, dates=484; test rows=1714832, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.034446, ICIR=3.758, Long-short Sharpe=-0.463, MDD=-0.626, turnover=0.178
- 成本后表现: cost=10.0bps/side proxy, annual net=-0.095066
- reviewer score: pending Codex reviewer; pilot heuristic score=7
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: positive but requires Codex reviewer before promote

## 2026-06-05T00:32:08 — A022 低换手高流动低波中期动量 H10

- alpha id: `A022`
- alpha 公式/逻辑: rank(rank(ret_20_skip5)*rank(liq_inv)*rank(low_vol)*(1-rank(turn)))
- 使用字段: `score_liq_lowvol_lowturn_mid_mom`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3057834, dates=912; validation rows=2141512, dates=484; test rows=1714832, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.033949, ICIR=3.125, Long-short Sharpe=-0.412, MDD=-0.832, turnover=0.200
- 成本后表现: cost=10.0bps/side proxy, annual net=-0.089870
- reviewer score: pending Codex reviewer; pilot heuristic score=7
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: positive but requires Codex reviewer before promote

## 2026-06-05T00:32:08 — A024 低换手长周期防御动量 H1

- alpha id: `A024`
- alpha 公式/逻辑: rank(rank(ret_60_skip20)*rank(liq_inv)*rank(low_vol)*(1-rank(turn)))
- 使用字段: `score_liq_lowvol_lowturn_long_mom`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3057834, dates=912; validation rows=2141512, dates=484; test rows=1714832, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.033578, ICIR=3.283, Long-short Sharpe=-0.881, MDD=-0.313, turnover=0.178
- 成本后表现: cost=10.0bps/side proxy, annual net=-0.195100
- reviewer score: pending Codex reviewer; pilot heuristic score=7
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: positive but requires Codex reviewer before promote

## 2026-06-05T00:32:08 — A022 低换手高流动低波中期动量 H20

- alpha id: `A022`
- alpha 公式/逻辑: rank(rank(ret_20_skip5)*rank(liq_inv)*rank(low_vol)*(1-rank(turn)))
- 使用字段: `score_liq_lowvol_lowturn_mid_mom`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3057834, dates=912; validation rows=2141512, dates=484; test rows=1714832, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.028929, ICIR=2.593, Long-short Sharpe=-0.489, MDD=-0.967, turnover=0.199
- 成本后表现: cost=10.0bps/side proxy, annual net=-0.108803
- reviewer score: pending Codex reviewer; pilot heuristic score=7
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: positive but requires Codex reviewer before promote

## 2026-06-05T00:32:08 — A024 低换手长周期防御动量 H20

- alpha id: `A024`
- alpha 公式/逻辑: rank(rank(ret_60_skip20)*rank(liq_inv)*rank(low_vol)*(1-rank(turn)))
- 使用字段: `score_liq_lowvol_lowturn_long_mom`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3057834, dates=912; validation rows=2141512, dates=484; test rows=1714832, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.027080, ICIR=2.969, Long-short Sharpe=-0.638, MDD=-0.968, turnover=0.178
- 成本后表现: cost=10.0bps/side proxy, annual net=-0.119568
- reviewer score: pending Codex reviewer; pilot heuristic score=7
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: positive but requires Codex reviewer before promote

## 2026-06-05T00:32:08 — A024 低换手长周期防御动量 H10

- alpha id: `A024`
- alpha 公式/逻辑: rank(rank(ret_60_skip20)*rank(liq_inv)*rank(low_vol)*(1-rank(turn)))
- 使用字段: `score_liq_lowvol_lowturn_long_mom`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3057834, dates=912; validation rows=2141512, dates=484; test rows=1714832, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.026992, ICIR=2.965, Long-short Sharpe=-0.620, MDD=-0.848, turnover=0.178
- 成本后表现: cost=10.0bps/side proxy, annual net=-0.121836
- reviewer score: pending Codex reviewer; pilot heuristic score=7
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: positive but requires Codex reviewer before promote

## 2026-06-05T00:32:08 — A025 价值流动低波中期动量 H5

- alpha id: `A025`
- alpha 公式/逻辑: rank(rank(ret_20_skip5)*rank(pb_inv)*rank(liq_inv)*rank(low_vol))
- 使用字段: `score_value_liq_lowvol_mid_mom`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3052267, dates=912; validation rows=2138028, dates=484; test rows=1711434, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.016958, ICIR=1.643, Long-short Sharpe=-0.867, MDD=-0.754, turnover=0.145
- 成本后表现: cost=10.0bps/side proxy, annual net=-0.182876
- reviewer score: pending Codex reviewer; pilot heuristic score=7
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: positive but requires Codex reviewer before promote

## 2026-06-05T00:32:08 — A025 价值流动低波中期动量 H10

- alpha id: `A025`
- alpha 公式/逻辑: rank(rank(ret_20_skip5)*rank(pb_inv)*rank(liq_inv)*rank(low_vol))
- 使用字段: `score_value_liq_lowvol_mid_mom`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3052267, dates=912; validation rows=2138028, dates=484; test rows=1711434, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.013929, ICIR=1.312, Long-short Sharpe=-0.837, MDD=-0.922, turnover=0.145
- 成本后表现: cost=10.0bps/side proxy, annual net=-0.173855
- reviewer score: pending Codex reviewer; pilot heuristic score=7
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: positive but requires Codex reviewer before promote

## 2026-06-05T00:32:08 — A025 价值流动低波中期动量 H20

- alpha id: `A025`
- alpha 公式/逻辑: rank(rank(ret_20_skip5)*rank(pb_inv)*rank(liq_inv)*rank(low_vol))
- 使用字段: `score_value_liq_lowvol_mid_mom`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3052267, dates=912; validation rows=2138028, dates=484; test rows=1711434, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.009322, ICIR=0.851, Long-short Sharpe=-0.755, MDD=-0.991, turnover=0.144
- 成本后表现: cost=10.0bps/side proxy, annual net=-0.163830
- reviewer score: pending Codex reviewer; pilot heuristic score=7
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: positive but requires Codex reviewer before promote
## 2026-06-05T01:16:02 — A028 长动量短回撤防御 H1

- alpha id: `A028`
- alpha 公式/逻辑: rank(rank(ret_60_skip20)*(1-rank(ret_5))*rank(liq_inv)*rank(low_vol)*(1-rank(turn)))
- 使用字段: `score_long_mom_short_pullback_def`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3057834, dates=912; validation rows=2141512, dates=484; test rows=1714832, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.042433, ICIR=4.466, Long-short Sharpe=-0.382, MDD=-0.209, turnover=0.249
- 成本后表现: cost=10.0bps/side proxy, annual net=-0.084105
- reviewer score: pending Codex reviewer; pilot heuristic score=8
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: positive but requires Codex reviewer before promote

## 2026-06-05T01:16:02 — A029 中期动量短回撤低冲击 H1

- alpha id: `A029`
- alpha 公式/逻辑: rank(rank(ret_20_skip5)*(1-rank(ret_5))*rank(liq_inv)*rank(low_vol)*(1-rank(turn)))
- 使用字段: `score_mid_mom_short_pullback_liq`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3057834, dates=912; validation rows=2141512, dates=484; test rows=1714832, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.040254, ICIR=4.055, Long-short Sharpe=-0.449, MDD=-0.231, turnover=0.284
- 成本后表现: cost=10.0bps/side proxy, annual net=-0.100049
- reviewer score: pending Codex reviewer; pilot heuristic score=8
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: positive but requires Codex reviewer before promote

## 2026-06-05T01:16:02 — A027 容量约束低换手中期动量 H1

- alpha id: `A027`
- alpha 公式/逻辑: rank(rank(ret_20_skip5)*rank(liq_inv)*rank(amount)*rank(low_vol)*(1-rank(turn)))
- 使用字段: `score_capacity_lowturn_mid_mom`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3057834, dates=912; validation rows=2141512, dates=484; test rows=1714832, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.013975, ICIR=1.423, Long-short Sharpe=-1.126, MDD=-0.361, turnover=0.181
- 成本后表现: cost=10.0bps/side proxy, annual net=-0.238406
- reviewer score: pending Codex reviewer; pilot heuristic score=8
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: positive but requires Codex reviewer before promote

## 2026-06-05T01:16:02 — A029 中期动量短回撤低冲击 H5

- alpha id: `A029`
- alpha 公式/逻辑: rank(rank(ret_20_skip5)*(1-rank(ret_5))*rank(liq_inv)*rank(low_vol)*(1-rank(turn)))
- 使用字段: `score_mid_mom_short_pullback_liq`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3057834, dates=912; validation rows=2141512, dates=484; test rows=1714832, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.044898, ICIR=4.883, Long-short Sharpe=0.111, MDD=-0.481, turnover=0.283
- 成本后表现: cost=10.0bps/side proxy, annual net=0.022270
- reviewer score: pending Codex reviewer; pilot heuristic score=7
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: positive but requires Codex reviewer before promote

## 2026-06-05T01:16:02 — A028 长动量短回撤防御 H5

- alpha id: `A028`
- alpha 公式/逻辑: rank(rank(ret_60_skip20)*(1-rank(ret_5))*rank(liq_inv)*rank(low_vol)*(1-rank(turn)))
- 使用字段: `score_long_mom_short_pullback_def`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3057834, dates=912; validation rows=2141512, dates=484; test rows=1714832, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.043869, ICIR=5.265, Long-short Sharpe=-0.029, MDD=-0.552, turnover=0.249
- 成本后表现: cost=10.0bps/side proxy, annual net=-0.005582
- reviewer score: pending Codex reviewer; pilot heuristic score=7
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: positive but requires Codex reviewer before promote

## 2026-06-05T01:16:02 — A029 中期动量短回撤低冲击 H10

- alpha id: `A029`
- alpha 公式/逻辑: rank(rank(ret_20_skip5)*(1-rank(ret_5))*rank(liq_inv)*rank(low_vol)*(1-rank(turn)))
- 使用字段: `score_mid_mom_short_pullback_liq`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3057834, dates=912; validation rows=2141512, dates=484; test rows=1714832, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.042590, ICIR=4.325, Long-short Sharpe=-0.116, MDD=-0.739, turnover=0.283
- 成本后表现: cost=10.0bps/side proxy, annual net=-0.023372
- reviewer score: pending Codex reviewer; pilot heuristic score=7
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: positive but requires Codex reviewer before promote

## 2026-06-05T01:16:02 — A028 长动量短回撤防御 H10

- alpha id: `A028`
- alpha 公式/逻辑: rank(rank(ret_60_skip20)*(1-rank(ret_5))*rank(liq_inv)*rank(low_vol)*(1-rank(turn)))
- 使用字段: `score_long_mom_short_pullback_def`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3057834, dates=912; validation rows=2141512, dates=484; test rows=1714832, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.037946, ICIR=4.444, Long-short Sharpe=-0.291, MDD=-0.777, turnover=0.249
- 成本后表现: cost=10.0bps/side proxy, annual net=-0.055399
- reviewer score: pending Codex reviewer; pilot heuristic score=7
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: positive but requires Codex reviewer before promote

## 2026-06-05T01:16:02 — A028 长动量短回撤防御 H20

- alpha id: `A028`
- alpha 公式/逻辑: rank(rank(ret_60_skip20)*(1-rank(ret_5))*rank(liq_inv)*rank(low_vol)*(1-rank(turn)))
- 使用字段: `score_long_mom_short_pullback_def`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3057834, dates=912; validation rows=2141512, dates=484; test rows=1714832, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.036156, ICIR=4.136, Long-short Sharpe=-0.419, MDD=-0.922, turnover=0.250
- 成本后表现: cost=10.0bps/side proxy, annual net=-0.079041
- reviewer score: pending Codex reviewer; pilot heuristic score=7
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: positive but requires Codex reviewer before promote

## 2026-06-05T01:16:02 — A029 中期动量短回撤低冲击 H20

- alpha id: `A029`
- alpha 公式/逻辑: rank(rank(ret_20_skip5)*(1-rank(ret_5))*rank(liq_inv)*rank(low_vol)*(1-rank(turn)))
- 使用字段: `score_mid_mom_short_pullback_liq`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3057834, dates=912; validation rows=2141512, dates=484; test rows=1714832, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.035136, ICIR=3.456, Long-short Sharpe=-0.399, MDD=-0.929, turnover=0.283
- 成本后表现: cost=10.0bps/side proxy, annual net=-0.083299
- reviewer score: pending Codex reviewer; pilot heuristic score=7
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: positive but requires Codex reviewer before promote

## 2026-06-05T01:16:02 — A030 资金确认低换手防御动量 H5

- alpha id: `A030`
- alpha 公式/逻辑: rank(rank(ret_20_skip5)*rank(mf_buy_pressure)*rank(liq_inv)*rank(low_vol)*(1-rank(turn)))
- 使用字段: `score_mf_confirm_lowturn_def_mom`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3053835, dates=912; validation rows=2105507, dates=484; test rows=1642605, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.022519, ICIR=2.382, Long-short Sharpe=-0.447, MDD=-0.571, turnover=0.407
- 成本后表现: cost=10.0bps/side proxy, annual net=-0.085596
- reviewer score: pending Codex reviewer; pilot heuristic score=7
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: positive but requires Codex reviewer before promote

## 2026-06-05T01:16:02 — A030 资金确认低换手防御动量 H1

- alpha id: `A030`
- alpha 公式/逻辑: rank(rank(ret_20_skip5)*rank(mf_buy_pressure)*rank(liq_inv)*rank(low_vol)*(1-rank(turn)))
- 使用字段: `score_mf_confirm_lowturn_def_mom`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3053835, dates=912; validation rows=2105507, dates=484; test rows=1642605, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.020543, ICIR=1.958, Long-short Sharpe=-1.177, MDD=-0.382, turnover=0.407
- 成本后表现: cost=10.0bps/side proxy, annual net=-0.261393
- reviewer score: pending Codex reviewer; pilot heuristic score=7
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: positive but requires Codex reviewer before promote

## 2026-06-05T01:16:02 — A030 资金确认低换手防御动量 H10

- alpha id: `A030`
- alpha 公式/逻辑: rank(rank(ret_20_skip5)*rank(mf_buy_pressure)*rank(liq_inv)*rank(low_vol)*(1-rank(turn)))
- 使用字段: `score_mf_confirm_lowturn_def_mom`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3053835, dates=912; validation rows=2105507, dates=484; test rows=1642605, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.019167, ICIR=1.940, Long-short Sharpe=-0.469, MDD=-0.803, turnover=0.407
- 成本后表现: cost=10.0bps/side proxy, annual net=-0.090426
- reviewer score: pending Codex reviewer; pilot heuristic score=7
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: positive but requires Codex reviewer before promote

## 2026-06-05T01:16:02 — A030 资金确认低换手防御动量 H20

- alpha id: `A030`
- alpha 公式/逻辑: rank(rank(ret_20_skip5)*rank(mf_buy_pressure)*rank(liq_inv)*rank(low_vol)*(1-rank(turn)))
- 使用字段: `score_mf_confirm_lowturn_def_mom`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3053835, dates=912; validation rows=2105507, dates=484; test rows=1642605, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.014824, ICIR=1.475, Long-short Sharpe=-0.575, MDD=-0.966, turnover=0.406
- 成本后表现: cost=10.0bps/side proxy, annual net=-0.114755
- reviewer score: pending Codex reviewer; pilot heuristic score=7
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: positive but requires Codex reviewer before promote

## 2026-06-05T01:16:02 — A027 容量约束低换手中期动量 H5

- alpha id: `A027`
- alpha 公式/逻辑: rank(rank(ret_20_skip5)*rank(liq_inv)*rank(amount)*rank(low_vol)*(1-rank(turn)))
- 使用字段: `score_capacity_lowturn_mid_mom`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3057834, dates=912; validation rows=2141512, dates=484; test rows=1714832, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.012510, ICIR=1.347, Long-short Sharpe=-0.539, MDD=-0.735, turnover=0.181
- 成本后表现: cost=10.0bps/side proxy, annual net=-0.107990
- reviewer score: pending Codex reviewer; pilot heuristic score=7
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: positive but requires Codex reviewer before promote

## 2026-06-05T01:16:02 — A027 容量约束低换手中期动量 H10

- alpha id: `A027`
- alpha 公式/逻辑: rank(rank(ret_20_skip5)*rank(liq_inv)*rank(amount)*rank(low_vol)*(1-rank(turn)))
- 使用字段: `score_capacity_lowturn_mid_mom`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3057834, dates=912; validation rows=2141512, dates=484; test rows=1714832, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.005991, ICIR=0.628, Long-short Sharpe=-0.619, MDD=-0.921, turnover=0.181
- 成本后表现: cost=10.0bps/side proxy, annual net=-0.122729
- reviewer score: pending Codex reviewer; pilot heuristic score=7
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: positive but requires Codex reviewer before promote

## 2026-06-05T01:16:02 — A027 容量约束低换手中期动量 H20

- alpha id: `A027`
- alpha 公式/逻辑: rank(rank(ret_20_skip5)*rank(liq_inv)*rank(amount)*rank(low_vol)*(1-rank(turn)))
- 使用字段: `score_capacity_lowturn_mid_mom`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3057834, dates=912; validation rows=2141512, dates=484; test rows=1714832, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=-0.003802, ICIR=-0.392, Long-short Sharpe=-0.685, MDD=-0.992, turnover=0.180
- 成本后表现: cost=10.0bps/side proxy, annual net=-0.139815
- reviewer score: pending Codex reviewer; pilot heuristic score=5
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: mixed positive; inspect costs/exposures/leakage

## 2026-06-05T01:24:00 — A029 中期动量短回撤低冲击 H5

- alpha id: `A029`
- alpha 公式/逻辑: rank(rank(ret_20_skip5)*(1-rank(ret_5))*rank(liq_inv)*rank(low_vol)*(1-rank(turn)))
- 使用字段: `score_mid_mom_short_pullback_liq`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3057834, dates=912; validation rows=2141512, dates=484; test rows=1714832, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.044898, ICIR=4.883, Long-short Sharpe=0.183, MDD=-0.476, turnover=0.283
- 成本后表现: cost=5.0bps/side proxy, annual net=0.036556
- reviewer score: pending Codex reviewer; pilot heuristic score=7
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: positive but requires Codex reviewer before promote

## 2026-06-05T01:24:00 — A029 中期动量短回撤低冲击 H5

- alpha id: `A029`
- alpha 公式/逻辑: rank(rank(ret_20_skip5)*(1-rank(ret_5))*rank(liq_inv)*rank(low_vol)*(1-rank(turn)))
- 使用字段: `score_mid_mom_short_pullback_liq`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3057834, dates=912; validation rows=2141512, dates=484; test rows=1714832, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.044898, ICIR=4.883, Long-short Sharpe=0.111, MDD=-0.481, turnover=0.283
- 成本后表现: cost=10.0bps/side proxy, annual net=0.022270
- reviewer score: pending Codex reviewer; pilot heuristic score=7
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: positive but requires Codex reviewer before promote

## 2026-06-05T01:24:00 — A029 中期动量短回撤低冲击 H5

- alpha id: `A029`
- alpha 公式/逻辑: rank(rank(ret_20_skip5)*(1-rank(ret_5))*rank(liq_inv)*rank(low_vol)*(1-rank(turn)))
- 使用字段: `score_mid_mom_short_pullback_liq`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3057834, dates=912; validation rows=2141512, dates=484; test rows=1714832, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.044898, ICIR=4.883, Long-short Sharpe=-0.031, MDD=-0.490, turnover=0.283
- 成本后表现: cost=20.0bps/side proxy, annual net=-0.006300
- reviewer score: pending Codex reviewer; pilot heuristic score=7
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: positive but requires Codex reviewer before promote

## 2026-06-05T01:24:00 — A029 中期动量短回撤低冲击 H5

- alpha id: `A029`
- alpha 公式/逻辑: rank(rank(ret_20_skip5)*(1-rank(ret_5))*rank(liq_inv)*rank(low_vol)*(1-rank(turn)))
- 使用字段: `score_mid_mom_short_pullback_liq`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3057834, dates=912; validation rows=2141512, dates=484; test rows=1714832, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.044898, ICIR=4.883, Long-short Sharpe=-0.174, MDD=-0.500, turnover=0.283
- 成本后表现: cost=30.0bps/side proxy, annual net=-0.034871
- reviewer score: pending Codex reviewer; pilot heuristic score=7
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: positive but requires Codex reviewer before promote
## 2026-06-05T01:25:00 — A029 H5 Codex reviewer decision override

- alpha id: `A029`
- alpha 公式/逻辑: rank(rank(ret_20_skip5)*(1-rank(ret_5))*rank(liq_inv)*rank(low_vol)*(1-rank(turn)))
- 使用字段: `score_mid_mom_short_pullback_liq`
- 样本区间: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；test `size_corr` 约 0.430，存在显著 size/style 暴露
- 回测指标: Test RankIC=0.044898；10bps long-short annual net=0.022270, Sharpe=0.111；10bps long-only annual net=0.174633, Sharpe=1.206
- 成本后表现: long-short annual net 5/10/20/30bps = 0.036556 / 0.022270 / -0.006300 / -0.034871；long-only annual net 5/10/20/30bps = 0.181849 / 0.174633 / 0.160203 / 0.145772
- reviewer score: 5/10
- leakage/bias 审查结论: 不通过 promote。主要 blocker 是退出受阻样本被 NaN 丢弃、H>1 不是真实多日持仓账本、size exposure 高、上市/退市/停牌/复权证据仍不足。
- decision: repair
- next action: 实现 delayed-exit carry/next-fill、真实 H5/H10/H20 sub-book portfolio ledger、size/industry neutral diagnostics 后重跑 reviewer

## 2026-06-05T01:55:58 — A029 中期动量短回撤低冲击 H5

- alpha id: `A029`
- alpha 公式/逻辑: rank(rank(ret_20_skip5)*(1-rank(ret_5))*rank(liq_inv)*rank(low_vol)*(1-rank(turn)))
- 使用字段: `score_mid_mom_short_pullback_liq`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3057834, dates=912; validation rows=2141512, dates=484; test rows=1714832, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.044898, ICIR=4.883, Long-short Sharpe=0.183, MDD=-0.476, turnover=0.283
- 成本后表现: cost=5.0bps/side proxy, annual net=0.036556
- reviewer score: pending Codex reviewer; pilot heuristic score=7
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: positive but requires Codex reviewer before promote

## 2026-06-05T01:55:58 — A029 中期动量短回撤低冲击 H5

- alpha id: `A029`
- alpha 公式/逻辑: rank(rank(ret_20_skip5)*(1-rank(ret_5))*rank(liq_inv)*rank(low_vol)*(1-rank(turn)))
- 使用字段: `score_mid_mom_short_pullback_liq`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3057834, dates=912; validation rows=2141512, dates=484; test rows=1714832, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.044898, ICIR=4.883, Long-short Sharpe=0.111, MDD=-0.481, turnover=0.283
- 成本后表现: cost=10.0bps/side proxy, annual net=0.022270
- reviewer score: pending Codex reviewer; pilot heuristic score=7
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: positive but requires Codex reviewer before promote

## 2026-06-05T01:55:58 — A029 中期动量短回撤低冲击 H5

- alpha id: `A029`
- alpha 公式/逻辑: rank(rank(ret_20_skip5)*(1-rank(ret_5))*rank(liq_inv)*rank(low_vol)*(1-rank(turn)))
- 使用字段: `score_mid_mom_short_pullback_liq`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3057834, dates=912; validation rows=2141512, dates=484; test rows=1714832, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.044898, ICIR=4.883, Long-short Sharpe=-0.031, MDD=-0.490, turnover=0.283
- 成本后表现: cost=20.0bps/side proxy, annual net=-0.006300
- reviewer score: pending Codex reviewer; pilot heuristic score=7
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: positive but requires Codex reviewer before promote

## 2026-06-05T01:55:58 — A029 中期动量短回撤低冲击 H5

- alpha id: `A029`
- alpha 公式/逻辑: rank(rank(ret_20_skip5)*(1-rank(ret_5))*rank(liq_inv)*rank(low_vol)*(1-rank(turn)))
- 使用字段: `score_mid_mom_short_pullback_liq`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3057834, dates=912; validation rows=2141512, dates=484; test rows=1714832, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.044898, ICIR=4.883, Long-short Sharpe=-0.174, MDD=-0.500, turnover=0.283
- 成本后表现: cost=30.0bps/side proxy, annual net=-0.034871
- reviewer score: pending Codex reviewer; pilot heuristic score=7
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: positive but requires Codex reviewer before promote
## 2026-06-05T05:29:46 — A029 中期动量短回撤低冲击 H5

- alpha id: `A029`
- alpha 公式/逻辑: rank(rank(ret_20_skip5)*(1-rank(ret_5))*rank(liq_inv)*rank(low_vol)*(1-rank(turn)))
- 使用字段: `score_mid_mom_short_pullback_liq`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3057834, dates=912; validation rows=2141512, dates=484; test rows=1714832, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.044898, ICIR=4.883, Long-short Sharpe=0.183, MDD=-0.476, turnover=0.283
- 成本后表现: cost=5.0bps/side proxy, annual net=0.036556
- reviewer score: pending Codex reviewer; pilot heuristic score=7
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: positive but requires Codex reviewer before promote

## 2026-06-05T05:29:46 — A029 中期动量短回撤低冲击 H5

- alpha id: `A029`
- alpha 公式/逻辑: rank(rank(ret_20_skip5)*(1-rank(ret_5))*rank(liq_inv)*rank(low_vol)*(1-rank(turn)))
- 使用字段: `score_mid_mom_short_pullback_liq`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3057834, dates=912; validation rows=2141512, dates=484; test rows=1714832, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.044898, ICIR=4.883, Long-short Sharpe=0.111, MDD=-0.481, turnover=0.283
- 成本后表现: cost=10.0bps/side proxy, annual net=0.022270
- reviewer score: pending Codex reviewer; pilot heuristic score=7
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: positive but requires Codex reviewer before promote

## 2026-06-05T05:29:46 — A029 中期动量短回撤低冲击 H5

- alpha id: `A029`
- alpha 公式/逻辑: rank(rank(ret_20_skip5)*(1-rank(ret_5))*rank(liq_inv)*rank(low_vol)*(1-rank(turn)))
- 使用字段: `score_mid_mom_short_pullback_liq`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3057834, dates=912; validation rows=2141512, dates=484; test rows=1714832, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.044898, ICIR=4.883, Long-short Sharpe=-0.031, MDD=-0.490, turnover=0.283
- 成本后表现: cost=20.0bps/side proxy, annual net=-0.006300
- reviewer score: pending Codex reviewer; pilot heuristic score=7
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: positive but requires Codex reviewer before promote

## 2026-06-05T05:29:46 — A029 中期动量短回撤低冲击 H5

- alpha id: `A029`
- alpha 公式/逻辑: rank(rank(ret_20_skip5)*(1-rank(ret_5))*rank(liq_inv)*rank(low_vol)*(1-rank(turn)))
- 使用字段: `score_mid_mom_short_pullback_liq`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3057834, dates=912; validation rows=2141512, dates=484; test rows=1714832, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.044898, ICIR=4.883, Long-short Sharpe=-0.174, MDD=-0.500, turnover=0.283
- 成本后表现: cost=30.0bps/side proxy, annual net=-0.034871
- reviewer score: pending Codex reviewer; pilot heuristic score=7
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: positive but requires Codex reviewer before promote

## 2026-06-05T07:18:59 — A029 中期动量短回撤低冲击 H5

- alpha id: `A029`
- alpha 公式/逻辑: rank(rank(ret_20_skip5)*(1-rank(ret_5))*rank(liq_inv)*rank(low_vol)*(1-rank(turn)))
- 使用字段: `score_mid_mom_short_pullback_liq`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3057834, dates=912; validation rows=2141512, dates=484; test rows=1714832, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.044898, ICIR=4.883, Long-short Sharpe=0.183, MDD=-0.476, turnover=0.283
- 成本后表现: cost=5.0bps/side proxy, annual net=0.036556
- reviewer score: pending Codex reviewer; pilot heuristic score=7
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: positive but requires Codex reviewer before promote

## 2026-06-05T07:18:59 — A029 中期动量短回撤低冲击 H5

- alpha id: `A029`
- alpha 公式/逻辑: rank(rank(ret_20_skip5)*(1-rank(ret_5))*rank(liq_inv)*rank(low_vol)*(1-rank(turn)))
- 使用字段: `score_mid_mom_short_pullback_liq`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3057834, dates=912; validation rows=2141512, dates=484; test rows=1714832, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.044898, ICIR=4.883, Long-short Sharpe=0.111, MDD=-0.481, turnover=0.283
- 成本后表现: cost=10.0bps/side proxy, annual net=0.022270
- reviewer score: pending Codex reviewer; pilot heuristic score=7
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: positive but requires Codex reviewer before promote

## 2026-06-05T07:18:59 — A029 中期动量短回撤低冲击 H5

- alpha id: `A029`
- alpha 公式/逻辑: rank(rank(ret_20_skip5)*(1-rank(ret_5))*rank(liq_inv)*rank(low_vol)*(1-rank(turn)))
- 使用字段: `score_mid_mom_short_pullback_liq`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3057834, dates=912; validation rows=2141512, dates=484; test rows=1714832, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.044898, ICIR=4.883, Long-short Sharpe=-0.031, MDD=-0.490, turnover=0.283
- 成本后表现: cost=20.0bps/side proxy, annual net=-0.006300
- reviewer score: pending Codex reviewer; pilot heuristic score=7
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: positive but requires Codex reviewer before promote

## 2026-06-05T07:18:59 — A029 中期动量短回撤低冲击 H5

- alpha id: `A029`
- alpha 公式/逻辑: rank(rank(ret_20_skip5)*(1-rank(ret_5))*rank(liq_inv)*rank(low_vol)*(1-rank(turn)))
- 使用字段: `score_mid_mom_short_pullback_liq`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3057834, dates=912; validation rows=2141512, dates=484; test rows=1714832, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.044898, ICIR=4.883, Long-short Sharpe=-0.174, MDD=-0.500, turnover=0.283
- 成本后表现: cost=30.0bps/side proxy, annual net=-0.034871
- reviewer score: pending Codex reviewer; pilot heuristic score=7
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: positive but requires Codex reviewer before promote
## 2026-06-05T09:17:01 — A029 中期动量短回撤低冲击 H5

- alpha id: `A029`
- alpha 公式/逻辑: rank(rank(ret_20_skip5)*(1-rank(ret_5))*rank(liq_inv)*rank(low_vol)*(1-rank(turn)))
- 使用字段: `score_mid_mom_short_pullback_liq`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3057834, dates=912; validation rows=2141512, dates=484; test rows=1714832, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.044898, ICIR=4.883, Long-short Sharpe=0.183, MDD=-0.476, turnover=0.283
- 成本后表现: cost=5.0bps/side proxy, annual net=0.036556
- reviewer score: pending Codex reviewer; pilot heuristic score=7
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: positive but requires Codex reviewer before promote

## 2026-06-05T09:17:01 — A029 中期动量短回撤低冲击 H5

- alpha id: `A029`
- alpha 公式/逻辑: rank(rank(ret_20_skip5)*(1-rank(ret_5))*rank(liq_inv)*rank(low_vol)*(1-rank(turn)))
- 使用字段: `score_mid_mom_short_pullback_liq`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3057834, dates=912; validation rows=2141512, dates=484; test rows=1714832, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.044898, ICIR=4.883, Long-short Sharpe=0.111, MDD=-0.481, turnover=0.283
- 成本后表现: cost=10.0bps/side proxy, annual net=0.022270
- reviewer score: pending Codex reviewer; pilot heuristic score=7
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: positive but requires Codex reviewer before promote

## 2026-06-05T09:17:01 — A029 中期动量短回撤低冲击 H5

- alpha id: `A029`
- alpha 公式/逻辑: rank(rank(ret_20_skip5)*(1-rank(ret_5))*rank(liq_inv)*rank(low_vol)*(1-rank(turn)))
- 使用字段: `score_mid_mom_short_pullback_liq`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3057834, dates=912; validation rows=2141512, dates=484; test rows=1714832, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.044898, ICIR=4.883, Long-short Sharpe=-0.031, MDD=-0.490, turnover=0.283
- 成本后表现: cost=20.0bps/side proxy, annual net=-0.006300
- reviewer score: pending Codex reviewer; pilot heuristic score=7
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: positive but requires Codex reviewer before promote

## 2026-06-05T09:17:01 — A029 中期动量短回撤低冲击 H5

- alpha id: `A029`
- alpha 公式/逻辑: rank(rank(ret_20_skip5)*(1-rank(ret_5))*rank(liq_inv)*rank(low_vol)*(1-rank(turn)))
- 使用字段: `score_mid_mom_short_pullback_liq`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3057834, dates=912; validation rows=2141512, dates=484; test rows=1714832, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.044898, ICIR=4.883, Long-short Sharpe=-0.174, MDD=-0.500, turnover=0.283
- 成本后表现: cost=30.0bps/side proxy, annual net=-0.034871
- reviewer score: pending Codex reviewer; pilot heuristic score=7
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: positive but requires Codex reviewer before promote
## 2026-06-05T09:54:22 — A029 中期动量短回撤低冲击 H5

- alpha id: `A029`
- alpha 公式/逻辑: rank(rank(ret_20_skip5)*(1-rank(ret_5))*rank(liq_inv)*rank(low_vol)*(1-rank(turn)))
- 使用字段: `score_mid_mom_short_pullback_liq`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3057834, dates=912; validation rows=2141512, dates=484; test rows=1714832, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.044898, ICIR=4.883, Long-short Sharpe=0.183, MDD=-0.476, turnover=0.283
- 成本后表现: cost=5.0bps/side proxy, annual net=0.036556
- reviewer score: pending Codex reviewer; pilot heuristic score=7
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: positive but requires Codex reviewer before promote

## 2026-06-05T09:54:22 — A029 中期动量短回撤低冲击 H5

- alpha id: `A029`
- alpha 公式/逻辑: rank(rank(ret_20_skip5)*(1-rank(ret_5))*rank(liq_inv)*rank(low_vol)*(1-rank(turn)))
- 使用字段: `score_mid_mom_short_pullback_liq`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3057834, dates=912; validation rows=2141512, dates=484; test rows=1714832, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.044898, ICIR=4.883, Long-short Sharpe=0.111, MDD=-0.481, turnover=0.283
- 成本后表现: cost=10.0bps/side proxy, annual net=0.022270
- reviewer score: pending Codex reviewer; pilot heuristic score=7
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: positive but requires Codex reviewer before promote

## 2026-06-05T09:54:22 — A029 中期动量短回撤低冲击 H5

- alpha id: `A029`
- alpha 公式/逻辑: rank(rank(ret_20_skip5)*(1-rank(ret_5))*rank(liq_inv)*rank(low_vol)*(1-rank(turn)))
- 使用字段: `score_mid_mom_short_pullback_liq`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3057834, dates=912; validation rows=2141512, dates=484; test rows=1714832, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.044898, ICIR=4.883, Long-short Sharpe=-0.031, MDD=-0.490, turnover=0.283
- 成本后表现: cost=20.0bps/side proxy, annual net=-0.006300
- reviewer score: pending Codex reviewer; pilot heuristic score=7
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: positive but requires Codex reviewer before promote

## 2026-06-05T09:54:22 — A029 中期动量短回撤低冲击 H5

- alpha id: `A029`
- alpha 公式/逻辑: rank(rank(ret_20_skip5)*(1-rank(ret_5))*rank(liq_inv)*rank(low_vol)*(1-rank(turn)))
- 使用字段: `score_mid_mom_short_pullback_liq`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3057834, dates=912; validation rows=2141512, dates=484; test rows=1714832, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.044898, ICIR=4.883, Long-short Sharpe=-0.174, MDD=-0.500, turnover=0.283
- 成本后表现: cost=30.0bps/side proxy, annual net=-0.034871
- reviewer score: pending Codex reviewer; pilot heuristic score=7
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: positive but requires Codex reviewer before promote

## 2026-06-05T11:26:59 — A029 中期动量短回撤低冲击 H5

- alpha id: `A029`
- alpha 公式/逻辑: rank(rank(ret_20_skip5)*(1-rank(ret_5))*rank(liq_inv)*rank(low_vol)*(1-rank(turn)))
- 使用字段: `score_mid_mom_short_pullback_liq`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3057834, dates=912; validation rows=2141512, dates=484; test rows=1714832, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.044898, ICIR=4.883, Long-short Sharpe=0.183, MDD=-0.476, turnover=0.283
- 成本后表现: cost=5.0bps/side proxy, annual net=0.036556
- reviewer score: pending Codex reviewer; pilot heuristic score=6
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: positive but requires Codex reviewer before promote

## 2026-06-05T11:26:59 — A029 中期动量短回撤低冲击 H5

- alpha id: `A029`
- alpha 公式/逻辑: rank(rank(ret_20_skip5)*(1-rank(ret_5))*rank(liq_inv)*rank(low_vol)*(1-rank(turn)))
- 使用字段: `score_mid_mom_short_pullback_liq`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3057834, dates=912; validation rows=2141512, dates=484; test rows=1714832, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.044898, ICIR=4.883, Long-short Sharpe=0.111, MDD=-0.481, turnover=0.283
- 成本后表现: cost=10.0bps/side proxy, annual net=0.022270
- reviewer score: pending Codex reviewer; pilot heuristic score=6
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: positive but requires Codex reviewer before promote

## 2026-06-05T11:26:59 — A029 中期动量短回撤低冲击 H5

- alpha id: `A029`
- alpha 公式/逻辑: rank(rank(ret_20_skip5)*(1-rank(ret_5))*rank(liq_inv)*rank(low_vol)*(1-rank(turn)))
- 使用字段: `score_mid_mom_short_pullback_liq`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3057834, dates=912; validation rows=2141512, dates=484; test rows=1714832, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.044898, ICIR=4.883, Long-short Sharpe=-0.031, MDD=-0.490, turnover=0.283
- 成本后表现: cost=20.0bps/side proxy, annual net=-0.006300
- reviewer score: pending Codex reviewer; pilot heuristic score=6
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: positive but requires Codex reviewer before promote

## 2026-06-05T11:26:59 — A029 中期动量短回撤低冲击 H5

- alpha id: `A029`
- alpha 公式/逻辑: rank(rank(ret_20_skip5)*(1-rank(ret_5))*rank(liq_inv)*rank(low_vol)*(1-rank(turn)))
- 使用字段: `score_mid_mom_short_pullback_liq`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3057834, dates=912; validation rows=2141512, dates=484; test rows=1714832, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.044898, ICIR=4.883, Long-short Sharpe=-0.174, MDD=-0.500, turnover=0.283
- 成本后表现: cost=30.0bps/side proxy, annual net=-0.034871
- reviewer score: pending Codex reviewer; pilot heuristic score=6
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: positive but requires Codex reviewer before promote

## 2026-06-05T12:00:27 — A029 中期动量短回撤低冲击 H5

- alpha id: `A029`
- alpha 公式/逻辑: rank(rank(ret_20_skip5)*(1-rank(ret_5))*rank(liq_inv)*rank(low_vol)*(1-rank(turn)))
- 使用字段: `score_mid_mom_short_pullback_liq`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3057834, dates=912; validation rows=2141512, dates=484; test rows=1714832, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.045370, ICIR=4.943, Long-short Sharpe=0.246, MDD=-0.460, turnover=0.282
- 成本后表现: cost=5.0bps/side proxy, annual net=0.049197
- reviewer score: pending Codex reviewer; pilot heuristic score=7
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: positive but requires Codex reviewer before promote

## 2026-06-05T12:00:27 — A029 中期动量短回撤低冲击 H5

- alpha id: `A029`
- alpha 公式/逻辑: rank(rank(ret_20_skip5)*(1-rank(ret_5))*rank(liq_inv)*rank(low_vol)*(1-rank(turn)))
- 使用字段: `score_mid_mom_short_pullback_liq`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3057834, dates=912; validation rows=2141512, dates=484; test rows=1714832, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.045370, ICIR=4.943, Long-short Sharpe=0.175, MDD=-0.465, turnover=0.282
- 成本后表现: cost=10.0bps/side proxy, annual net=0.034964
- reviewer score: pending Codex reviewer; pilot heuristic score=7
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: positive but requires Codex reviewer before promote

## 2026-06-05T12:00:27 — A029 中期动量短回撤低冲击 H5

- alpha id: `A029`
- alpha 公式/逻辑: rank(rank(ret_20_skip5)*(1-rank(ret_5))*rank(liq_inv)*rank(low_vol)*(1-rank(turn)))
- 使用字段: `score_mid_mom_short_pullback_liq`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3057834, dates=912; validation rows=2141512, dates=484; test rows=1714832, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.045370, ICIR=4.943, Long-short Sharpe=0.032, MDD=-0.475, turnover=0.282
- 成本后表现: cost=20.0bps/side proxy, annual net=0.006497
- reviewer score: pending Codex reviewer; pilot heuristic score=7
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: positive but requires Codex reviewer before promote

## 2026-06-05T12:00:27 — A029 中期动量短回撤低冲击 H5

- alpha id: `A029`
- alpha 公式/逻辑: rank(rank(ret_20_skip5)*(1-rank(ret_5))*rank(liq_inv)*rank(low_vol)*(1-rank(turn)))
- 使用字段: `score_mid_mom_short_pullback_liq`；收益字段由 panel open 重新计算
- 样本区间配置: train 2019-2022, validation 2023-2024, test 2025-01-01 到 2026-05-28
- 实际可用样本: train rows=3057834, dates=912; validation rows=2141512, dates=484; test rows=1714832, dates=337
- 股票池: 日频面板内股票，剔除 ST/次日 ST、首次出现后 60 个交易日、低成交额、无成交/疑似停牌、疑似涨停不可买
- 是否行业/市值中性: none；市值/成交额暴露以相关系数记录，未做真实行业中性除非字段本身为 `indrk`
- 回测指标: Test RankIC=0.045370, ICIR=4.943, Long-short Sharpe=-0.110, MDD=-0.484, turnover=0.282
- 成本后表现: cost=30.0bps/side proxy, annual net=-0.021969
- reviewer score: pending Codex reviewer; pilot heuristic score=7
- leakage/bias 审查结论: pending formal Codex review；框架已显式使用 t close -> t+1 open，不使用预制 label
- decision: repair
- next action: positive but requires Codex reviewer before promote
