# Next A100 Training TODO

Goal: use one A100 GPU day to turn the current LSTM result into a better
audited final-model candidate. Priority order is best-checkpoint evaluation,
small LSTM search, then one expanded-training final candidate.

## Run Control

- [ ] Submit `scripts/a100_next_training.sbatch`.
- [ ] Monitor `squeue -u "$USER"` and `reports/slurm/a100_next_training-<jobid>.out`.
- [ ] Stop condition: job finishes within 24 hours, or at least completes
  best-checkpoint re-evaluation plus two LSTM variants.
- [ ] Do not commit `data/`, `checkpoints/`, Slurm logs, backtest parquet files,
  or generated figures.

## Phase 1: Environment and Baseline

- [ ] Confirm clean branch:
  `git status --short --branch`.
- [ ] Confirm cached inputs exist:
  `data/features.parquet`, `data/labels.parquet`,
  `checkpoints/lstm_ic_large.pt`.
- [ ] Run leakage and training smoke tests:
  `pytest -q tests/test_no_leakage.py tests/test_training_pipeline.py`.

## Phase 2: Re-evaluate Current Best Checkpoint

- [ ] Regenerate validation predictions from the saved best LSTM checkpoint:
  `python -m src.infer --model lstm --tag lstm_ic_large --batch-cap 8192 --device cuda --val-start 2025-01-01 --val-end 2026-04-30`.
- [ ] Recompute metrics:
  `python -m src.compare --tags mlp_mse lstm_ic_large transformer_ic_large transformer_ic_mid`.
- [ ] Backtest the best-checkpoint predictions:
  `python -m src.backtest --preds checkpoints/lstm_ic_large_val_preds.parquet --out reports/backtest_lstm_ic_large_best`.

## Phase 3: LSTM Search on Original Validation Split

- [ ] Train `lstm_ic_h384_l2_w20`:
  `python -m src.train --model lstm --loss ic --tag lstm_ic_h384_l2_w20 --hidden 384 --layers 2 --dropout 0.2 --window 20 --epochs 8 --batch-cap 8192 --amp`.
- [ ] Re-infer `lstm_ic_h384_l2_w20` from best checkpoint.
- [ ] Train `lstm_ic_h384_l3_w20`:
  `python -m src.train --model lstm --loss ic --tag lstm_ic_h384_l3_w20 --hidden 384 --layers 3 --dropout 0.2 --window 20 --epochs 8 --batch-cap 8192 --amp`.
- [ ] Re-infer `lstm_ic_h384_l3_w20` from best checkpoint.
- [ ] Train `lstm_ic_h256_l3_w40`:
  `python -m src.train --model lstm --loss ic --tag lstm_ic_h256_l3_w40 --hidden 256 --layers 3 --dropout 0.2 --window 40 --epochs 8 --batch-cap 8192 --amp`.
- [ ] Re-infer `lstm_ic_h256_l3_w40` from best checkpoint.

## Phase 4: Expanded-Training Final Candidate

- [ ] Train `lstm_ic_final_h384_l2_w20` with later data and a short holdout:
  `python -m src.train --model lstm --loss ic --tag lstm_ic_final_h384_l2_w20 --hidden 384 --layers 2 --dropout 0.2 --window 20 --train-start 2019-01-01 --train-end 2026-02-27 --val-start 2026-03-02 --val-end 2026-04-30 --epochs 8 --batch-cap 8192 --amp`.
- [ ] Re-infer `lstm_ic_final_h384_l2_w20` on `2026-03-02` to
  `2026-04-30`.
- [ ] Backtest `lstm_ic_final_h384_l2_w20`:
  `python -m src.backtest --preds checkpoints/lstm_ic_final_h384_l2_w20_val_preds.parquet --out reports/backtest_lstm_ic_final_h384_l2_w20`.

## Phase 5: Selection and Reporting

- [ ] Compare original-split candidates:
  `python -m src.compare --tags mlp_mse lstm_ic_large lstm_ic_h384_l2_w20 lstm_ic_h384_l3_w20 lstm_ic_h256_l3_w40 transformer_ic_large transformer_ic_mid`.
- [ ] Backtest the three original-split LSTM variants into dedicated
  `reports/backtest_<tag>/` directories.
- [ ] Select the main model:
  prefer the LSTM variant with higher IC and RankIC than `lstm_ic_large` and no
  Sharpe degradation; otherwise keep `lstm_ic_large`.
- [ ] Treat `lstm_ic_final_h384_l2_w20` as the final-training candidate only if
  its short holdout is positive and it does not show obvious instability.
- [ ] Update `RESULTS.md` after reviewing the completed Slurm output.

## Expected Artifacts

- `checkpoints/<tag>.pt`
- `checkpoints/<tag>_val_preds.parquet`
- `checkpoints/<tag>_train_log.json`
- `reports/compare_metrics.csv`
- `reports/backtest_<tag>/equity.parquet`
- `reports/figures/nav_compare_<tag>_val_preds.png`
