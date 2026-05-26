"""Stacked LSTM."""

from __future__ import annotations

import torch
import torch.nn as nn


class LSTMModel(nn.Module):
    def __init__(self, n_features: int, hidden: int = 64, n_layers: int = 2,
                 dropout: float = 0.1):
        super().__init__()
        self.lstm = nn.LSTM(
            input_size=n_features, hidden_size=hidden,
            num_layers=n_layers, batch_first=True,
            dropout=dropout if n_layers > 1 else 0.0,
        )
        self.head = nn.Sequential(
            nn.LayerNorm(hidden), nn.Linear(hidden, 1),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: (B, T, F) -> take last step
        out, _ = self.lstm(x)
        return self.head(out[:, -1, :]).squeeze(-1)
