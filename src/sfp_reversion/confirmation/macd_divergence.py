"""MACD divergence (§2.7) over the prior swing lows/highs.

Bullish (long): price prints a lower low while the MACD histogram prints a
higher low, across the window of prior confirmed swings. Mirror for bearish.
A swing only enters the window once confirmed (``swing_lookback`` bars later),
so no verdict can peek at an unformed extreme.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from sfp_reversion.levels.detection import swing_points


def macd(
    df: pd.DataFrame,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> pd.DataFrame:
    ema_fast = df["close"].ewm(span=fast, adjust=False).mean()
    ema_slow = df["close"].ewm(span=slow, adjust=False).mean()
    line = ema_fast - ema_slow
    signal_line = line.ewm(span=signal, adjust=False).mean()
    return pd.DataFrame({"macd": line, "signal": signal_line, "hist": line - signal_line})


def macd_divergence(
    df: pd.DataFrame,
    direction: str,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
    swing_lookback: int = 5,
    n_swings: int = 3,
    use_histogram: bool = True,
) -> pd.Series:
    if direction not in ("long", "short"):
        raise ValueError(f"direction must be long/short, got {direction!r}")
    kind = "low" if direction == "long" else "high"
    values = macd(df, fast, slow, signal)["hist" if use_histogram else "macd"]
    swings = swing_points(df, swing_lookback, min_magnitude_atr=0.0)
    out = pd.Series(False, index=df.index)
    subset = swings[swings["kind"] == kind]
    if len(subset) < 2:
        return out
    pos = df.index.get_indexer(subset.index) + swing_lookback
    keep = pos < len(df)
    cpos = pos[keep]
    sprices = subset["price"].to_numpy(dtype=float)[keep]
    svals = values.reindex(subset.index).to_numpy(dtype=float)[keep]
    order = np.argsort(cpos, kind="stable")
    cpos, sprices, svals = cpos[order], sprices[order], svals[order]
    flags = np.zeros(len(df), dtype=bool)
    for i in range(len(df)):
        j = int(np.searchsorted(cpos, i, side="right"))
        if j < 2:
            continue
        prices = sprices[max(0, j - n_swings) : j]
        vals = svals[max(0, j - n_swings) : j]
        if not np.isfinite(vals).all():
            continue
        if kind == "low":
            flags[i] = prices[-1] < prices[:-1].min() and vals[-1] > vals[:-1].max()
        else:
            flags[i] = prices[-1] > prices[:-1].max() and vals[-1] < vals[:-1].min()
    return pd.Series(flags, index=df.index)
