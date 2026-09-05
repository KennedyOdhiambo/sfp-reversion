"""SFP detector (§2.6): wick beyond the level, close back inside.

Long (support): bar wicks below the level by >= ``wick_atr`` × ATR and closes
back above it by >= ``close_inside_atr`` × ATR (mirror for shorts). Per-bar and
vectorized; each verdict uses only that bar's OHLC and ATR up to it.
"""

from __future__ import annotations

import pandas as pd

from sfp_reversion.levels.detection import atr_series


def detect_sfp(
    df: pd.DataFrame,
    level_price: float,
    direction: str,
    wick_atr: float = 0.1,
    close_inside_atr: float = 0.05,
    atr_period: int = 14,
) -> pd.Series:
    if direction not in ("long", "short"):
        raise ValueError(f"direction must be long/short, got {direction!r}")
    # regime through the prior bar: the signal bar must not set its own hurdle
    atr = atr_series(df, atr_period).shift(1)
    wick = wick_atr * atr
    inside = close_inside_atr * atr
    if direction == "long":
        hit = (df["low"] <= level_price - wick) & (df["close"] >= level_price + inside)
    else:
        hit = (df["high"] >= level_price + wick) & (df["close"] <= level_price - inside)
    return hit.fillna(False)
