"""MLP baseline over flattened window features."""

from __future__ import annotations

import torch
import torch.nn as nn


class MLP(nn.Module):
    def __init__(self, window: int, n_features: int,
                 hidden: int = 128, n_layers: int = 3, dropout: float = 0.1):
        super().__init__()
        layers: list[nn.Module] = []
        in_dim = window * n_features
        for _ in range(n_layers):
            layers += [nn.Linear(in_dim, hidden), nn.GELU(), nn.Dropout(dropout)]
            in_dim = hidden
        layers.append(nn.Linear(in_dim, 1))
        self.net = nn.Sequential(*layers)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: (B, T, F)
        b = x.size(0)
        return self.net(x.reshape(b, -1)).squeeze(-1)
