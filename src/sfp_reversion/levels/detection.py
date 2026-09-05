"""Level detection (§2.1): fractal swings clustered into horizontal levels.

A bar ``i`` is a swing high iff its high is strictly greater than the highs of
``lookback`` bars on each side (mirror for lows). Swings smaller than
``min_magnitude_atr`` × ATR are noise. Same-kind swings within ``cluster_ticks``
merge into one level at their mean price.

A level's ``formed_at`` is its swing bar; it is only *usable* from
``formed_at + lookback`` bars onward (confirmation lag — no lookahead).
Consumers must enforce that; see Phase 10.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd


def atr_series(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Wilder ATR over the canonical frame."""
    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()


def swing_points(
    df: pd.DataFrame,
    lookback: int = 5,
    atr_period: int = 14,
    min_magnitude_atr: float = 0.3,
) -> pd.DataFrame:
    """All qualifying swings: index ``timestamp``, columns ``price`` and ``kind``."""
    atr = atr_series(df, atr_period)
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    rows: list[tuple[Any, float, str]] = []
    for i in range(lookback, len(df) - lookback):
        window_h = highs[i - lookback : i + lookback + 1]
        window_l = lows[i - lookback : i + lookback + 1]
        # unique extremum: ties (plateau edges) are not swings
        is_high = bool(highs[i] == window_h.max() and (window_h == highs[i]).sum() == 1)
        is_low = bool(lows[i] == window_l.min() and (window_l == lows[i]).sum() == 1)
        if is_high and is_low:  # overlapping extremes: keep the stronger side
            is_low = abs(lows[i] - window_l.max()) > abs(highs[i] - window_h.min())
            is_high = not is_low
        if not (is_high or is_low) or not atr.iloc[i] > 0:
            continue
        magnitude = abs(highs[i] - lows[i]) / atr.iloc[i]
        if magnitude < min_magnitude_atr:
            continue
        kind = "high" if is_high else "low"
        price = float(highs[i] if is_high else lows[i])
        rows.append((df.index[i], price, kind))
    out = pd.DataFrame(rows, columns=["timestamp", "price", "kind"])
    return out.set_index("timestamp") if rows else out


@dataclass
class Level:
    price: float
    kind: str  # "support" | "resistance"
    formed_at: pd.Timestamp
    swing_prices: list[float] = field(default_factory=list)

    @property
    def touches(self) -> int:
        return len(self.swing_prices)

    def add_swing(self, price: float) -> None:
        self.swing_prices.append(price)
        self.price = float(np.mean(self.swing_prices))


def detect_levels(
    df: pd.DataFrame,
    lookback: int = 5,
    cluster_ticks: int = 10,
    tick_size: float = 0.0001,
    atr_period: int = 14,
    min_swing_magnitude_atr: float = 0.3,
) -> list[Level]:
    """Cluster same-kind swings within ``cluster_ticks`` ticks into levels, oldest first."""
    swings = swing_points(df, lookback, atr_period, min_swing_magnitude_atr)
    levels: list[Level] = []
    for ts, row in swings.iterrows():
        price = float(row["price"])
        kind = "resistance" if row["kind"] == "high" else "support"
        best: Level | None = None
        best_dist = float("inf")
        for level in levels:
            if level.kind != kind:
                continue
            dist = abs(level.price - price)
            if dist <= cluster_ticks * tick_size and dist < best_dist:
                best, best_dist = level, dist
        if best is None:
            levels.append(Level(price=price, kind=kind, formed_at=ts, swing_prices=[price]))
        else:
            best.add_swing(price)
    return levels
