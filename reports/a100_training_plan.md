# A100 Quant Training Plan

## Summary

Use the A100 node to train higher-capacity in-repo neural models after fixing
daily prediction semantics and backtest leakage. The training target remains
cross-sectional IC on causal 20-day windows. No external pretrained base model
is used.

## Model Set

- `mlp_mse`: minimal baseline.
- `lstm_ic_large`: `hidden=256`, `layers=3`, `dropout=0.2`, about 1.34M parameters.
- `transformer_ic_large`: `d_model=256`, `heads=8`, `layers=4`, `dropout=0.2`, about 3.17M parameters.
- Optional `transformer_ic_mid`: `d_model=128`, `heads=8`, `layers=4`, `dropout=0.15`, about 0.8M parameters.

The planned parameter range is 1M-5M. Larger 10M+ models are avoided unless the
fixed validation and backtest results show clear underfitting.

## Commands

Enter the A100 node:

```bash
srun -p A100 -N 1 -c 4 --gres=gpu:1 --qos=normal -t 24:00:00 --pty bash
source /opt/Software/Anaconda3/etc/profile.d/conda.sh && conda activate dl
```

Rebuild cache and test:

```bash
python -m src.train --rebuild-cache --model mlp --loss mse --epochs 0
pytest -q tests/test_no_leakage.py tests/test_training_pipeline.py
```

Train:

```bash
python -m src.train --model mlp --loss mse --tag mlp_mse \
  --epochs 8 --batch-cap 8192

python -m src.train --model lstm --loss ic --tag lstm_ic_large \
  --hidden 256 --layers 3 --dropout 0.2 \
  --epochs 8 --batch-cap 8192 --amp

python -m src.train --model transformer --loss ic --tag transformer_ic_large \
  --d-model 256 --heads 8 --layers 4 --dropout 0.2 \
  --epochs 8 --batch-cap 8192 --amp
```

Evaluate:

```bash
python -m src.compare --tags mlp_mse lstm_ic_large transformer_ic_large
python -m src.backtest --preds checkpoints/lstm_ic_large_val_preds.parquet
python -m src.backtest --preds checkpoints/transformer_ic_large_val_preds.parquet
```

Daily output uses `--date` as the data cutoff date and writes targets for the
next trading day:

```bash
python -m src.predict_daily --date 2026-05-29 --model transformer \
  --tag transformer_ic_large --n 10
```

## Acceptance Criteria

- No leakage tests pass.
- Backtest tradability filtering does not use next-day movement.
- Checkpoints save and restore model capacity parameters.
- Large model predictions and backtests are generated from the fixed code.
