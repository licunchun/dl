"""Sliding-window dataset.

Inputs:
    feats: long-form causal feature frame (rows = one (ts_code, trade_date))
    labels: output of labels.attach_labels (same keys)

The dataset emits windows of length ``T``:

    X[stock, end_date]  ∈ R^{T × F}       features over [end_date-T+1 ... end_date]
    y[stock, end_date]  ∈ R                label realised after end_date

By the causal construction in features.py, every column in X at row ``t``
only references data ≤ t-1, so the last row of X at end_date references
data up to end_date-1.  The label y is close_{end_date+1}/close_{end_date}-1
— i.e. the return realised between the close on end_date and the close on
end_date+1.  Thus X and y are fully causally aligned: given X we know nothing
about future closes.

Per-window z-score
------------------
Per the assignment's dataprocessing rule, we standardise each window using
*its own* mean / std (per stock, per window, per feature).  No global mean
or std is ever computed.  Static cross-sectional rank features (rk_*) are
left untouched since they are already in [0, 1].
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd
import torch
from torch.utils.data import Dataset


# feature columns that should NOT be z-scored per-window (already normalised)
_SKIP_ZSCORE_PREFIX = ("rk_",)


@dataclass
class SampleIndex:
    stock_idx: int        # index into ts_codes
    end_row: int          # index into the stock's row array


def _prepare_arrays(feats: pd.DataFrame, labels: pd.DataFrame,
                    feature_cols: list[str]):
    merged = feats.merge(
        labels[["ts_code", "trade_date", "y", "drop_reason"]],
        on=["ts_code", "trade_date"], how="inner",
    )
    merged = merged.sort_values(["ts_code", "trade_date"]).reset_index(drop=True)
    # Drop rows missing any feature.
    merged = merged.dropna(subset=feature_cols).reset_index(drop=True)
    return merged


class WindowDataset(Dataset):
    """Sliding-window (T) samples with per-window z-score."""

    def __init__(
        self,
        feats: pd.DataFrame,
        labels: pd.DataFrame,
        feature_cols: list[str],
        window: int = 20,
        date_range: tuple[str, str] | None = None,
        drop_missing_label: bool = True,
    ) -> None:
        self.feature_cols = list(feature_cols)
        self.window = window

        merged = _prepare_arrays(feats, labels, self.feature_cols)

        if date_range is not None:
            lo, hi = pd.Timestamp(date_range[0]), pd.Timestamp(date_range[1])
            merged = merged[(merged["trade_date"] >= lo) & (merged["trade_date"] <= hi)]
            merged = merged.reset_index(drop=True)

        # Per-stock blocks, each an (n_rows, F) numpy array.
        self.ts_codes: list[str] = []
        self.blocks_X: list[np.ndarray] = []
        self.blocks_y: list[np.ndarray] = []
        self.blocks_dates: list[np.ndarray] = []
        self.blocks_drop: list[np.ndarray] = []

        for code, g in merged.groupby("ts_code", sort=False):
            self.ts_codes.append(code)
            self.blocks_X.append(g[self.feature_cols].to_numpy(dtype=np.float32))
            self.blocks_y.append(g["y"].to_numpy(dtype=np.float32))
            self.blocks_dates.append(g["trade_date"].to_numpy(dtype="datetime64[ns]"))
            self.blocks_drop.append(g["drop_reason"].to_numpy(dtype=object))

        # Pre-compute a flat list of (stock_idx, end_row) valid samples.
        self.samples: list[SampleIndex] = []
        for si, (X, y, drop) in enumerate(zip(self.blocks_X, self.blocks_y, self.blocks_drop)):
            n = X.shape[0]
            for end in range(window - 1, n):
                if drop_missing_label and (np.isnan(y[end]) or drop[end] != ""):
                    continue
                self.samples.append(SampleIndex(si, end))

        # z-score masks
        self._zscore_mask = np.array(
            [not any(c.startswith(p) for p in _SKIP_ZSCORE_PREFIX) for c in self.feature_cols],
            dtype=bool,
        )

    # ------------------------------------------------------------------
    def __len__(self) -> int:
        return len(self.samples)

    def _get_window(self, si: int, end: int) -> np.ndarray:
        start = end - self.window + 1
        return self.blocks_X[si][start : end + 1].copy()

    def _zscore(self, window: np.ndarray) -> np.ndarray:
        """In-place z-score for columns in self._zscore_mask. Computed in
        float64 to avoid mean-drift when feature magnitudes differ by 1e6."""
        cols = self._zscore_mask
        sub = window[:, cols].astype(np.float64, copy=False)
        mu = sub.mean(axis=0, keepdims=True)
        sd = sub.std(axis=0, keepdims=True)
        sd = np.where(sd < 1e-8, 1.0, sd)
        window[:, cols] = ((sub - mu) / sd).astype(window.dtype, copy=False)
        return window

    def __getitem__(self, idx: int):
        s = self.samples[idx]
        X = self._get_window(s.stock_idx, s.end_row)
        X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
        X = self._zscore(X)
        y = float(self.blocks_y[s.stock_idx][s.end_row])
        ts = self.blocks_dates[s.stock_idx][s.end_row]
        return (
            torch.from_numpy(X),
            torch.tensor(y, dtype=torch.float32),
            s.stock_idx,
            np.datetime64(ts, "D").astype("int64"),
        )

    # ------------------------------------------------------------------
    def by_date(self) -> dict[np.datetime64, list[int]]:
        """Indices grouped by end_date. Useful for IC-style batching."""
        out: dict[np.datetime64, list[int]] = {}
        for i, s in enumerate(self.samples):
            d = self.blocks_dates[s.stock_idx][s.end_row]
            out.setdefault(d, []).append(i)
        return out


class DayBatchSampler(torch.utils.data.Sampler):
    """Yields index lists where each batch = all samples from one trading day.

    This is the natural batching scheme for IC loss, and it also mirrors the
    competition: the model ranks the whole cross-section on a given day.
    """

    def __init__(self, dataset: WindowDataset, shuffle: bool = True,
                 min_stocks: int = 100):
        self.dataset = dataset
        self.shuffle = shuffle
        by_date = dataset.by_date()
        self.day_indices = [idxs for idxs in by_date.values() if len(idxs) >= min_stocks]

    def __iter__(self):
        order = list(range(len(self.day_indices)))
        if self.shuffle:
            np.random.shuffle(order)
        for i in order:
            yield self.day_indices[i]

    def __len__(self) -> int:
        return len(self.day_indices)
