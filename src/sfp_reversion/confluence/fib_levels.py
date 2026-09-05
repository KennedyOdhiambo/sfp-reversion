"""Fib confluence (§2.5 + special limit rule): retracements of the last confirmed leg.

``fib_grid`` returns one row per bar with the active retracement levels — NaN
until a full swing high+low pair has confirmed, so early bars can never see
future fibs. The grid always describes the most recent *leg*: after a down-leg
(levels = high − r·span), after an up-leg (levels = low + r·span).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from sfp_reversion.levels.detection import atr_series, swing_points


def fib_grid(
    df: pd.DataFrame,
    swing_lookback: int = 20,
    ratios: tuple[float, ...] = (0.382, 0.5, 0.618, 0.786),
    atr_period: int = 14,
    min_magnitude_atr: float = 0.0,
) -> pd.DataFrame:
    cols = [f"fib_{r:.3f}" for r in ratios]
    grid = pd.DataFrame(np.nan, index=df.index, columns=cols)
    swings = swing_points(df, swing_lookback, atr_period, min_magnitude_atr)
    if swings.empty:
        return grid
    n = len(df)
    pos = df.index.get_indexer(swings.index)
    events = sorted(
        (int(c), float(p), str(k))
        for c, p, k in zip(pos + swing_lookback, swings["price"], swings["kind"], strict=True)
        if c < n
    )
    state_high: float | None = None
    state_low: float | None = None
    last_kind = ""
    prev = 0
    for c, price, kind in events:
        if state_high is not None and state_low is not None:
            _fill(grid, ratios, prev, c, state_high, state_low, last_kind)
        if kind == "high":
            state_high = price
        else:
            state_low = price
        last_kind = kind
        prev = c
    if state_high is not None and state_low is not None:
        _fill(grid, ratios, prev, n, state_high, state_low, last_kind)
    return grid


def _fill(
    grid: pd.DataFrame,
    ratios: tuple[float, ...],
    start: int,
    stop: int,
    high: float,
    low: float,
    last_kind: str,
) -> None:
    span = high - low
    if span <= 0 or start >= stop:
        return
    for r in ratios:
        level = high - r * span if last_kind == "low" else low + r * span
        grid.iloc[start:stop, grid.columns.get_loc(f"fib_{r:.3f}")] = level


def near_fib(
    df: pd.DataFrame,
    price_levels: pd.Series,
    swing_lookback: int = 20,
    ratios: tuple[float, ...] = (0.382, 0.5, 0.618, 0.786),
    proximity_atr: float = 0.2,
    atr_period: int = 14,
    grid: pd.DataFrame | None = None,
) -> pd.Series:
    """True where the level price sits within ``proximity_atr``×ATR of a live fib."""
    grid = fib_grid(df, swing_lookback, ratios, atr_period) if grid is None else grid
    prox = proximity_atr * atr_series(df, atr_period).shift(1)
    hit = pd.Series(False, index=df.index)
    for col in grid.columns:
        diff = (price_levels - grid[col]).abs()
        hit = hit | (diff <= prox).fillna(False)
    return hit


def fib_override_price(
    df: pd.DataFrame,
    price_levels: pd.Series,
    swing_lookback: int = 20,
    ratios: tuple[float, ...] = (0.382, 0.5, 0.618, 0.786),
    proximity_atr: float = 0.2,
    atr_period: int = 14,
    grid: pd.DataFrame | None = None,
) -> pd.Series:
    """Nearest live fib within proximity, else NaN (the special limit rule)."""
    grid = fib_grid(df, swing_lookback, ratios, atr_period) if grid is None else grid
    prox = (proximity_atr * atr_series(df, atr_period).shift(1)).to_numpy(dtype=float)[:, None]
    dist = np.abs(
        grid.to_numpy(dtype=float) - price_levels.reindex(df.index).to_numpy(dtype=float)[:, None]
    )
    ok = np.isfinite(dist) & np.isfinite(prox) & (dist <= prox)
    has = ok.any(axis=1)
    best = np.argmin(np.where(ok, dist, np.inf), axis=1)
    out = pd.Series(np.nan, index=df.index)
    rows = np.arange(len(df))[has]
    out.iloc[rows] = grid.to_numpy(dtype=float)[rows, best[has]]
    return out
