from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def candles() -> pd.DataFrame:
    """Deterministic synthetic 1h candles with a trend and a pullback."""
    rng = np.random.default_rng(11)
    n = 600
    idx = pd.date_range("2024-01-01", periods=n, freq="h")
    drift = np.concatenate([np.full(300, 0.15), np.full(200, -0.25), np.full(100, 0.3)])
    close = 30_000 + np.cumsum(drift * 20 + rng.normal(0, 8, n))
    spread = rng.random(n) * 15 + 2
    volume = rng.lognormal(3, 0.4, n)
    open_ = close + rng.normal(0, 3, n)
    return pd.DataFrame(
        {
            "Open": open_,
            "High": np.maximum(close, open_) + spread,
            "Low": np.minimum(close, open_) - spread,
            "Close": close,
            "Volume": volume,
            "TakerBuyBase": volume * rng.uniform(0.3, 0.7, n),
            "Trades": (volume * 10).astype(int),
        },
        index=idx,
    ).rename_axis("Time")
