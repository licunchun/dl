# Reviewer Memory

## Round 1
- Suspicion A: validation/backtest used future next-day limit censoring.
- Suspicion B: close-to-close backtest and pre-market order workflow were misaligned.
- Suspicion C: May regime shift invalidated long-history LSTM confidence.

## Round 2
- Leakage/window/as-of fixes appear real and targeted tests pass.
- Inverse/high-concentration May result looks post-hoc and not aligned with the documented 10-name protocol.
- Daily deployment needed explicit direction support.

## Round 3
- Explicit inverse support is implemented and tested.
- Inverse is rejected as a robust rule: it only explains May and fails pre-May monthly direction checks.
- Final deployment posture: NOT_READY_LOW_RISK_ONLY; forced fallback is the short-term moneyflow list with latest-data regeneration.
