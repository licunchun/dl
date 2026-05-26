"""Small Transformer encoder over the window, with a learned [CLS] token."""

from __future__ import annotations

import math
import torch
import torch.nn as nn


class TransformerModel(nn.Module):
    def __init__(
        self,
        n_features: int,
        d_model: int = 64,
        n_heads: int = 4,
        n_layers: int = 2,
        window: int = 20,
        dropout: float = 0.1,
    ):
        super().__init__()
        self.input_proj = nn.Linear(n_features, d_model)
        self.cls = nn.Parameter(torch.zeros(1, 1, d_model))
        # learned positional embedding of size window+1 (for the [CLS] prepend)
        self.pos = nn.Parameter(torch.zeros(1, window + 1, d_model))
        nn.init.trunc_normal_(self.cls, std=0.02)
        nn.init.trunc_normal_(self.pos, std=0.02)

        layer = nn.TransformerEncoderLayer(
            d_model=d_model, nhead=n_heads,
            dim_feedforward=d_model * 4, dropout=dropout,
            batch_first=True, activation="gelu",
        )
        self.encoder = nn.TransformerEncoder(layer, num_layers=n_layers)
        self.head = nn.Sequential(
            nn.LayerNorm(d_model), nn.Linear(d_model, 1),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: (B, T, F)
        b, t, _ = x.shape
        h = self.input_proj(x)
        cls = self.cls.expand(b, -1, -1)
        h = torch.cat([cls, h], dim=1)
        h = h + self.pos[:, : t + 1, :]
        h = self.encoder(h)
        return self.head(h[:, 0, :]).squeeze(-1)
