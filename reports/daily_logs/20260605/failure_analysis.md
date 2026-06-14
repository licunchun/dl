# Failure Analysis

Run date: 20260605

## F_VOL_REV_5

- decision: kill
- issues: large_drawdown
- leakage_check: pass
- stability: pass
- collinearity: pass

## F_VWAP_REV_5

- decision: promote
- issues: none
- leakage_check: pass
- stability: pass
- collinearity: pass

## F_MF_EXHAUST_5

- decision: kill
- issues: large_drawdown, negative_long_short_diagnostic
- leakage_check: pass
- stability: pass
- collinearity: pass

## F_MF_CONFIRM_5

- decision: kill
- issues: non_positive_rankic, negative_long_short_diagnostic, unstable_rankic
- leakage_check: pass
- stability: fail
- collinearity: pass

## F_VALUE_LIQ_DEF_5

- decision: kill
- issues: negative_long_short_diagnostic
- leakage_check: pass
- stability: pass
- collinearity: pass
