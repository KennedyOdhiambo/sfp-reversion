"""Touch / retest event timeline (§2.3, §2.4).

The forming swing is touch #1 by definition. Every later bar whose extreme comes
within ``tolerance_atr`` × ATR of the level is a retest; a bar that *closes*
beyond the level by more than the tolerance is a break, after which the level
is dead and the timeline stops.

Timeframe-agnostic: feed it hourly bars against daily levels, or anything else.
"""

from __future__ import annotations

from dataclasses import dataclass

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
    atr = atr_series(df).shift(1).to_numpy()
    n = 0
    for i in range(len(df)):
        if df.index[i] < level.formed_at or not atr[i] > 0:
            continue
        tol = tolerance_atr * atr[i]
        close = float(df["close"].iloc[i])
        if _broke(level, close, tol):
            break
        if _approached(level, float(df["high"].iloc[i]), float(df["low"].iloc[i]), tol):
            n += 1
    return max(n, 1)


def retest_events(
    level: Level,
    df: pd.DataFrame,
    tolerance_atr: float,
    retest_start: str = "first_touch",
) -> list[LevelEvent]:
    """Full touch/retest/break timeline for one level, oldest first."""
    atr = atr_series(df).shift(1).to_numpy()
    events: list[LevelEvent] = []
    seen_touch = retest_start == "first_touch"
    retest_count = 0
    for i in range(len(df)):
        ts = df.index[i]
        if ts < level.formed_at or not atr[i] > 0:
            continue
        close = float(df["close"].iloc[i])
        tol = tolerance_atr * atr[i]
        if _broke(level, close, tol):
            events.append(LevelEvent(ts, "break", close, retest_count))
            break
        if _approached(level, float(df["high"].iloc[i]), float(df["low"].iloc[i]), tol):
            if not seen_touch:
                events.append(LevelEvent(ts, "touch", close, retest_count))
                seen_touch = True
            else:
                retest_count += 1
                events.append(LevelEvent(ts, "retest", close, retest_count))
    return events


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
