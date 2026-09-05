"""D1 bias (§2.5): daily trend verdict in {-1, 0, +1}.

Bullish (+1) when the fast EMA sits above the slow EMA *and* price made higher
highs over the last ``lookback`` bars (mirror for bearish). Anything else is
neutral (0). Allow ~2× ``ema_slow`` bars of warmup before trusting values.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def d1_bias(
    df: pd.DataFrame,
    ema_fast: int = 20,
    ema_slow: int = 50,
    lookback: int = 10,
) -> pd.Series:
    fast = df["close"].ewm(span=ema_fast, adjust=False).mean()
    slow = df["close"].ewm(span=ema_slow, adjust=False).mean()
    trend = np.sign(fast - slow)
    higher_highs = df["high"].diff(lookback) > 0
    lower_lows = df["low"].diff(lookback) < 0
    bias = pd.Series(0.0, index=df.index)
    bias[(trend > 0) & higher_highs.fillna(False)] = 1.0
    bias[(trend < 0) & lower_lows.fillna(False)] = -1.0
    return bias


def d1_bias_matches(bias: pd.Series, direction: str) -> pd.Series:
    """True where the bias agrees with the trade direction (long/short)."""
    if direction not in ("long", "short"):
        raise ValueError(f"direction must be long/short, got {direction!r}")
    return bias == (1.0 if direction == "long" else -1.0)
