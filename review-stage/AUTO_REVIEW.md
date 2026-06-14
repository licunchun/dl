# Codex Auto Review — A029 Delayed-Exit GPU Rerun

Date: 2026-06-05
Reviewer backend: Codex secondary reviewer
Reviewer model: gpt-5.5
Difficulty: nightmare
Reviewed artifacts: `alpha-stage/scripts/alpha_backtest.py`, `alpha-stage/artifacts/alpha_results.json`, `reports/slurm/alpha_gpu_backtest-29601.out`, `reports/slurm/alpha_gpu_backtest-29601.err`

## Verdict

A029 H5 remains **repair**, not promote. Reviewer score: **5/10**.

The delayed-exit repair improved the result and removed the most direct future exit-fillability drop for exits found within the delay window. The rerun used Slurm GPU job `29601` on A800 with `torch_cuda` and CUDA available. However, the backtest is still not a full tradable A-share H5 ledger, and the alpha keeps material exposure and cost-sensitivity risks.

## Evidence

- Slurm/GPU: job `29601`, host `gpu2`, `CUDA_VISIBLE_DEVICES=1`, PyTorch `2.12.0+cu126`, `torch.cuda_available=True`, device `NVIDIA A800-SXM4-80GB`.
- Test RankIC: `0.04537045658113058`.
- Test yearly RankIC: 2025 `0.05140474559585928`, 2026 `0.02870759032455019`.
- Long-short annual net at 5/10/20/30 bps: `0.04919740156922802`, `0.0349640913645631`, `0.006497470955233239`, `-0.02196914945409663`.
- Long-only annual net at 5/10/20/30 bps: `0.18055127519149888`, `0.1733387907177123`, `0.15891382177013919`, `0.14448885282256604`.
- Test size correlation: about `0.43036738046027573`.

## Key Findings

1. Delayed exit is partial. Exits are searched up to `ALPHA_MAX_EXIT_DELAY_DAYS`; if no exit is found, returns remain `NaN` and are later dropped. This can still understate trapped-position losses.
2. Exit fillability is incomplete. Sell blocking uses a limit-down proxy, but does not yet require exit-day volume, amount, non-suspension, non-ST, or delisting handling.
3. H5/H10/H20 accounting remains diagnostic. The code uses overlapping holding-period returns and annualizes by horizon, without a true sub-book cash/position ledger or carried unfilled positions.
4. A-share short-side results are not directly tradable. Long-short stays diagnostic unless an index-hedged or financing/securities-lending implementation is explicitly modeled.
5. Cost sensitivity improved but remains weak. Long-short is only slightly positive at 20 bps and negative at 30 bps.
6. Size exposure remains material; no size or industry neutralization has been applied.
7. Survivorship and corporate-action risks are unresolved. IPO filtering uses a first-seen proxy, delisting status is not point-in-time audited, and momentum uses raw close without explicit adjustment-factor audit.

## Required Repair

1. Replace H5 diagnostic averaging with a real staggered long-only portfolio ledger: cash, positions, T+1, daily sub-books, delayed sells, costs, unfilled carry, and delisting handling.
2. Treat unresolved exits after max delay as explicit adverse outcomes or documented forced-liquidation assumptions, not silent dropped rows.
3. Add exit fillability checks for suspension, zero/low volume, low amount, ST transitions, and delisting.
4. Run size-neutral and industry-neutral IC/portfolio diagnostics.
5. Audit raw versus adjusted prices around corporate actions.
6. Rerun A029 after the ledger and exposure repairs; keep it in `repair` until those checks pass.
