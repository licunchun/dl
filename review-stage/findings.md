# Findings

- [Round 1] Positive: documented `dl` environment runs leakage/training tests cleanly (`6 passed`).
- [Round 1] Risk: default Python lacks torch, so validation must use `/home/lcc17/.conda/envs/dl/bin/python` or A100 Slurm env.
- [Round 1] Risk: generic `predict_daily` was one day stale for pre-market deployment and default panel cache ended at 2026-04-30; fixed by synthetic target-day scoring plus `--data-dir/--cache-dir` support.
- [Round 1] Negative: May 2026 validation is hostile to all long-history LSTM variants; best May policy grid remains negative even after n/k search.
- [Round 2] Negative: leakage-free May labels make long-history LSTM IC more negative (`lstm_ic_large`: -0.0552).
- [Round 2] Mixed: inverse scores improve May IC but legal `n=10,k=2` inverse remains loss-making.
- [Round 3] Negative: pre-May monthly direction check rejects inverse as a robust rule; main LSTM variants are forward-positive and inverse-negative across 2025-01..2026-04.
