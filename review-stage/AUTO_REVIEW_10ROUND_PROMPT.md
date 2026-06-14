# Auto Review Loop Prompt — Short-Term May Backtest Rescue

Created: 2026-05-29T23:18:35+08:00

## Persistent Operating Constraint

- Run up to 10 autonomous review/improvement rounds.
- Submission time is short. Prefer experiments that finish quickly and give
  feedback fast.
- Do not poll too frequently. Poll running experiments no more often than once
  every 10 minutes; a 15-30 minute cadence is acceptable for Slurm jobs.
- Keep each candidate small: small data slice, few epochs, and lightweight
  model architecture. Do not launch long full-history 8-10 epoch jobs unless a
  faster pilot already looks promising.
- Primary success target: produce a short-term model/strategy whose May 2026
  holdout backtest is a materially positive value, with defensible no-leakage
  evaluation.
- Stop early only if a candidate is clearly better than existing May baselines
  and produces usable target holdings plus documented caveats.

## Prompt

You are running an autonomous 10-round review-and-improvement loop for an
A-share daily stock-selection coursework project under a tight deadline. The
loop must optimize for iteration speed first: small experiments, short feedback
cycles, and explicit evidence.

The project predicts next-day returns and constructs a Top-N long-only portfolio. Existing long-validation LSTM models performed well on 2025-01-01 to 2026-04-30, but all existing LSTM variants failed on the May 2026 holdout:

- `lstm_ic_large`: May IC about -0.055, RankIC about -0.037, Sharpe about -6.64.
- Larger/deeper/window-40 LSTM variants also have negative May IC and negative May backtest.
- A same-checkpoint default-censor May sanity check weakens the IC failure but does not fix the backtest, so both evaluation-censor differences and actual regime/strategy failure are plausible.

Existing urgent training job:

- Slurm job `27558`, script `scripts/a100_short_term_training.sbatch`, running on A100 node `gpu18`.
- It trains `lstm_ic_short_mf_decay_h256_l2_w10` using data through 2026-05-28.
- Training range: 2019-01-01 to 2026-04-30.
- Validation/holdout: 2026-05-06 to 2026-05-27.
- Target output date: 2026-06-01 from as-of 2026-05-28.
- Log files: `reports/slurm/a100_short_term-27558.out` and `.err`.

Review objective:

1. Every round, inspect current result artifacts and logs before proposing changes.
2. Prioritize cheap, high-impact changes that can finish before the deadline.
3. The three required optimization levers are:
   - hyperparameters,
   - data selection / train-validation ratio,
   - model architecture.
4. Do not chase larger LSTM capacity as the first lever; May failure
   synchronized across capacity variants.
5. Prefer short-horizon and regime-adaptive fixes:
   - shorter window,
   - recency weighting,
   - train-start moved to recent history such as 2024-01-01 or 2025-01-01,
   - validation on 2026-05-06 to 2026-05-27,
   - very small epoch counts such as 2-4 for pilots,
   - moneyflow features,
   - altered portfolio direction only if validated,
   - smaller Top-N / inverse / blended candidate only with explicit May evidence,
   - sklearn/linear baseline if it gives robust positive May behavior.
6. Required evidence for any recommended model:
   - May 2026 IC and RankIC,
   - May Top10 spread,
   - May backtest annualized return, Sharpe, max drawdown, n_days,
   - generated 2026-06-01 target list,
   - no-leakage caveat about the exact label/censor setting used.
7. If May positivity is obtained by optimizing directly on May, mark it clearly
   as short-term contest tuning, not a generalizable research claim.
8. If no candidate gets positive May backtest after feasible attempts, produce
   the best available fallback:
   - most stable May drawdown/least negative Sharpe,
   - target list,
   - concise explanation for report.

Experiment design rules:

- Default pilot budget:
  - train-start: 2024-01-01 or 2025-01-01,
  - train-end: 2026-04-30,
  - val-start: 2026-05-06,
  - val-end: 2026-05-27,
  - epochs: 2-4,
  - batch-cap: full day cross-section unless memory forces sampling.
- Only expand to longer data or more epochs after a pilot shows positive May
  direction or positive May backtest.
- Prefer one-factor changes per round when possible, so the result explains
  something:
  - hyperparameter round: half-life, dropout, learning rate, hidden size,
    window length;
  - data round: 2025-only vs 2024+2025+2026, recent weighting floor, holdout
    split;
  - architecture round: shallow LSTM, GRU/simple RNN if implemented, MLP/linear
    baseline, or small ensemble/blend.
- Avoid slow candidates:
  - full 2019-2026 data with 10 epochs,
  - hidden > 256,
  - layers > 2 for pilots,
  - Transformer retraining unless a cheap baseline suggests it is worth it.

Monitoring protocol:

- Check `squeue` and tail Slurm logs at an interval greater than 10 minutes
  while jobs are running. Do not busy-poll every few minutes.
- After the job exits, immediately parse:
  - `checkpoints/lstm_ic_short_mf_decay_h256_l2_w10_train_log.json`
  - `reports/backtest_lstm_ic_short_mf_decay_h256_l2_w10/stats.json`
  - `reports/daily_logs/20260601_short_term_targets.csv`
- If results are poor and time remains, launch the next cheapest candidate
  rather than waiting:
  - same short-term script with `window=5`, `hidden=128`, `layers=1-2`,
    `dropout=0.25-0.35`, `epochs=2-4`, `train-start=2024-01-01` or
    `2025-01-01`, `half-life-days=60-120`;
  - or train/evaluate `scripts/train_sklearn_baseline.py` plus `scripts/evaluate_sklearn_may_2026.py`;
  - or generate inverse/top-N variants from saved predictions and backtest them explicitly.

Round output format:

For each round, append to `review-stage/AUTO_REVIEW.md`:

- Round number out of 10.
- Current job status and last poll time.
- Evidence inspected.
- Reviewer score for submission readiness.
- Top weaknesses.
- Concrete next action.
- Whether a positive May short-term backtest exists.

Do not claim success without file-backed metrics.
