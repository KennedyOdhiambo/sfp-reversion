"""ATR extension (§2.5): is the level stretched far from the last turning point?

True where the level price sits at least ``multiple`` × ATR away from the
reference — either the most recent confirmed swing (either kind) or the prior
bar's close. Stretched = reactive territory where reversals happen.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from sfp_reversion.levels.detection import atr_series, swing_points


def atr_extension(
    df: pd.DataFrame,
    price_levels: pd.Series,
    multiple: float = 1.0,
    reference: str = "recent_swing",
    atr_period: int = 14,
    swing_lookback: int = 5,
) -> pd.Series:
    atr = atr_series(df, atr_period).shift(1)
    price = price_levels.reindex(df.index).to_numpy(dtype=float)
    limit = multiple * atr.to_numpy(dtype=float)
    if reference == "prior_close":
        ref = df["close"].shift(1).to_numpy(dtype=float)
        return pd.Series((np.abs(price - ref) >= limit).tolist(), index=df.index).fillna(False)
    if reference != "recent_swing":
        raise ValueError(f"Unknown ATR extension reference: {reference!r}")
    ref = _last_confirmed_swing(df, atr_period, swing_lookback)
    return pd.Series((np.abs(price - ref) >= limit).tolist(), index=df.index).fillna(False)


def _last_confirmed_swing(df: pd.DataFrame, atr_period: int, swing_lookback: int) -> np.ndarray:
    """Per-bar price of the most recent confirmed swing (NaN before the first)."""
    n = len(df)
    swings = swing_points(df, swing_lookback, atr_period, min_magnitude_atr=0.0)
    if swings.empty:
        return np.full(n, np.nan)
    pos = df.index.get_indexer(swings.index) + swing_lookback
    keep = pos < n
    cpos = pos[keep]
    sprices = swings["price"].to_numpy(dtype=float)[keep]
    order = np.argsort(cpos, kind="stable")
    cpos, sprices = cpos[order], sprices[order]
    idx = np.searchsorted(cpos, np.arange(n), side="right") - 1
    return np.where(idx >= 0, sprices[np.clip(idx, 0, len(sprices) - 1)], np.nan)
