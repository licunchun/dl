# A股 Alpha Discovery Narrative

## Current Status

The first discovery cycle completed data profiling, candidate generation, sanity pilots, narrowed validation, and Codex secondary review. No alpha is promoted.

## Data Foundation

Local data root: `/home/lcc17/pan_sync_20260528`.

The scanned dataset contains 12,915 files and about 15.321 GB. Raw CSV directories cover daily OHLCV, market metrics, moneyflow, ST status, index weights, market index data, and news. The usable first-pass path is raw CSV, because multiple parquet files fail column reads with pyarrow `OSError: Repetition level histogram size mismatch`.

Key first-pass data risks:

- No explicit suspension, delisting, listing-date, corporate-action adjustment, or limit-up/limit-down table was found.
- ST status exists and is used.
- Limit and suspension handling is approximated from price moves and volume/amount.
- Precomputed label parquet files are not used for backtest returns.

## Alpha Cycle 1

Initial candidates covered reversal, momentum, volatility, liquidity, turnover, size, and moneyflow. A 2026 sanity pilot showed positive short-window signals for:

- A003 20 日动量.
- A005 Amihud 流动性.

A narrowed 2025-2026 H5 check overturned the short-window result:

- A003: RankIC -0.05216, cost-adjusted annual return proxy -0.5691, Sharpe proxy -1.268, max drawdown proxy -0.814.
- A005: RankIC -0.02938, cost-adjusted annual return proxy -0.4258, Sharpe proxy -1.180, max drawdown proxy -0.669.

## Review Outcome

Codex secondary reviewer score: 1/10.

Decision:

- A003 H5: kill.
- A005 H5: kill.

The reviewer found that the negative conclusion is supported for these implementations, but current evidence does not rule out momentum or liquidity alphas in A 股 generally.

## Repairs Applied

After review, the backtest script was repaired to:

- Separate point-in-time signal eligibility from next-day fill simulation.
- Correct H>1 annualization scale.
- Mark long-short output as a diagnostic spread, not a directly tradable A 股 strategy.
- Use exit fillability to avoid counting returns from limit-down blocked exits.

## Next Alpha Directions

The next cycle should pivot away from raw 20-day momentum and raw low-Amihud selection. Stronger candidates should use:

- Long-only tradable portfolio metrics.
- Cost and turnover penalties during candidate selection.
- Capacity filters based on amount and turnover.
- Market-state conditioning, especially avoiding single-window 2026 overfit.
- Signals that do not require future eligibility filters for IC calculation.

Priority ideas:

1. Liquidity-adjusted reversal after high turnover/volume shock, with low turnover holding filter.
2. Moneyflow exhaustion: large/extra-large net inflow reversal after price extension.
3. Industry/index-relative momentum using only point-in-time index-weight data if membership timing can be proven.
4. Long-only low turnover quality/liquidity blend with explicit capacity cap.
