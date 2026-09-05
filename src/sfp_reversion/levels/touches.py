"""Touch / retest event timeline (§2.3, §2.4).

The forming swing is touch #1 by definition. Every later bar whose extreme comes
within ``tolerance_atr`` × ATR of the level is a retest; a bar that *closes*
beyond the level by more than the tolerance is a break, after which the level
is dead and the timeline stops.

Timeframe-agnostic: feed it hourly bars against daily levels, or anything else.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from sfp_reversion.levels.detection import Level, atr_series


@dataclass
class LevelEvent:
    ts: pd.Timestamp
    event: str  # "touch" | "retest" | "break"
    close: float
    retest_count: int = 0  # retests seen up to and including this event


def count_touches(level: Level, df: pd.DataFrame, tolerance_atr: float) -> int:
    """Approach bars from formation until a break, minimum 1 (the forming swing)."""
    approached, _, _, _ = _classify(level, df, tolerance_atr)
    return max(int(approached.sum()), 1)


def retest_events(
    level: Level,
    df: pd.DataFrame,
    tolerance_atr: float,
    retest_start: str = "first_touch",
) -> list[LevelEvent]:
    """Full touch/retest/break timeline for one level, oldest first."""
    approached, broke, base, closes = _classify(level, df, tolerance_atr)
    events: list[LevelEvent] = []
    seen_touch = retest_start == "first_touch"
    retest_count = 0
    for rel in np.where(approached)[0]:
        if not seen_touch:
            events.append(
                LevelEvent(
                    df.index[base + int(rel)], "touch", float(closes[int(rel)]), retest_count
                )
            )
            seen_touch = True
        else:
            retest_count += 1
            events.append(
                LevelEvent(
                    df.index[base + int(rel)], "retest", float(closes[int(rel)]), retest_count
                )
            )
    if broke.any():
        rel = int(np.where(broke)[0][0])
        events.append(LevelEvent(df.index[base + rel], "break", float(closes[rel]), retest_count))
    return events


def _classify(
    level: Level, df: pd.DataFrame, tolerance_atr: float
) -> tuple[np.ndarray, np.ndarray, int, np.ndarray]:
    """Vectorized verdicts from formation onward.

    ``approached`` is True only before the first break; a break bar counts as
    break, never as approach. Identical outcomes to the old per-bar loop.
    """
    n = len(df)
    base = int(df.index.searchsorted(level.formed_at))
    if base >= n:
        empty = np.zeros(0, dtype=bool)
        return empty, empty, base, np.zeros(0)
    avals = atr_series(df).shift(1).to_numpy(dtype=float)[base:]
    tol = tolerance_atr * avals
    valid = np.isfinite(tol) & (tol > 0)
    highs = df["high"].to_numpy(dtype=float)[base:]
    lows = df["low"].to_numpy(dtype=float)[base:]
    closes = df["close"].to_numpy(dtype=float)[base:]
    if level.kind == "resistance":
        approached = valid & (highs >= level.price - tol)
        broke = valid & (closes > level.price + tol)
    else:
        approached = valid & (lows <= level.price + tol)
        broke = valid & (closes < level.price - tol)
    if broke.any():
        approached = approached.copy()
        approached[int(np.where(broke)[0][0]) :] = False
    return approached, broke, base, closes


def _approached(level: Level, high: float, low: float, tol: float) -> bool:
    if level.kind == "resistance":
        return high >= level.price - tol
    return low <= level.price + tol


def _broke(level: Level, close: float, tol: float) -> bool:
    if level.kind == "resistance":
        return close > level.price + tol
    return close < level.price - tol


def approach_episodes(
    events: list[LevelEvent], df: pd.DataFrame
) -> tuple[list[list[LevelEvent]], bool]:
    """Collapse same-approach bars into episodes; flag a terminal break.

    Returns (episodes, broke): each episode is the events of one continuous
    visit (bars on consecutive positions), oldest first. A break ends the
    timeline and is not an episode.
    """
    episodes: list[list[LevelEvent]] = []
    current: list[LevelEvent] = []
    prev_pos = -2
    broke = False
    for e in events:
        if e.event == "break":
            broke = True
            break
        pos = df.index.get_loc(e.ts)
        if current and pos > prev_pos + 1:
            episodes.append(current)
            current = []
        current.append(e)
        prev_pos = int(pos)
    if current:
        episodes.append(current)
    return episodes, broke
