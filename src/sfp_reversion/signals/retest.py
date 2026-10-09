"""Setup B signals (philosophy.md): breakout-then-return off daily levels.

A level breaks (H1 close beyond tolerance), then price comes straight back
within ``max_break_return_bars``. Buy the return to broken resistance, sell
the return to broken support — but only the *first* return directly after the
move. Strength is graded by pre-break touches (forming swing counts as #1):
3 touches trade clean, 2 need 1 confirmation, 1 needs 2. Confirmations come
from the daily frame: pin/engulfing/swing-failure pattern, fib proximity, or
ATR stretch. Entries are limits at the level (fib override when close to one)
so the existing limit-fill engine executes them unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from sfp_reversion.config import get_config
from sfp_reversion.confirmation.sfp import detect_sfp
from sfp_reversion.levels.detection import atr_series, detect_levels


@dataclass
class RetestParams:
    swing_lookback: int = 5
    cluster_ticks: int = 10
    tick_size: float = 0.0001
    min_swing_magnitude_atr: float = 0.3
    touch_tolerance_atr: float = 0.1
    atr_period: int = 14
    max_break_return_bars: int = 24
    touch_gates: dict[int, int] = field(default_factory=lambda: {3: 0, 2: 1, 1: 2})
    pin_wick_body_ratio: float = 2.0
    bias_sfp_wick_atr: float = 0.1
    bias_sfp_close_atr: float = 0.05
    fib_lookback: int = 20
    fib_ratios: tuple[float, ...] = (0.382, 0.5, 0.618)
    fib_proximity_atr: float = 0.2
    special_fib_rule: bool = True
    atr_stretch_period: int = 20
    atr_stretch_multiple: float = 1.0
    stop_buffer_atr: float = 0.1
    fta_fallback_atr: float = 2.0
    min_reward_risk: float = 1.0
    min_stop_atr: float = 0.25
    limit_expiry_bars: int = 24

    @classmethod
    def from_config(cls) -> RetestParams:
        cfg = get_config()
        lvl = cfg.section("levels")
        ret = cfg.section("retest")
        return cls(
            swing_lookback=int(lvl.get("swing_lookback", 5)),
            cluster_ticks=int(lvl.get("cluster_ticks", 10)),
            tick_size=float(lvl.get("tick_size", 0.0001)),
            min_swing_magnitude_atr=float(lvl.get("min_swing_magnitude_atr", 0.3)),
            touch_tolerance_atr=float(lvl.get("touch_tolerance_atr", 0.1)),
            atr_period=int(cfg.get("atr.period", 14)),
            max_break_return_bars=int(ret.get("max_break_return_bars", 24)),
            touch_gates={int(k): int(v) for k, v in ret.get("touch_gates", {}).items()}
            or {3: 0, 2: 1, 1: 2},
            pin_wick_body_ratio=float(ret.get("pin_wick_body_ratio", 2.0)),
            bias_sfp_wick_atr=float(ret.get("bias_sfp_wick_atr", 0.1)),
            bias_sfp_close_atr=float(ret.get("bias_sfp_close_atr", 0.05)),
            fib_lookback=int(ret.get("fib_lookback", 20)),
            fib_ratios=tuple(float(r) for r in ret.get("fib_ratios", [0.382, 0.5, 0.618])),
            fib_proximity_atr=float(ret.get("fib_proximity_atr", 0.2)),
            special_fib_rule=bool(ret.get("special_fib_rule", True)),
            atr_stretch_period=int(ret.get("atr_stretch_period", 20)),
            atr_stretch_multiple=float(ret.get("atr_stretch_multiple", 1.0)),
            stop_buffer_atr=float(ret.get("stop_buffer_atr", 0.1)),
            fta_fallback_atr=float(ret.get("fta_fallback_atr", 2.0)),
            min_reward_risk=float(ret.get("min_reward_risk", 1.0)),
            min_stop_atr=float(ret.get("min_stop_atr", 0.25)),
            limit_expiry_bars=int(ret.get("limit_expiry_bars", 24)),
        )


SIGNAL_COLUMNS = [
    "timestamp",
    "direction",
    "entry_price",
    "stop_price",
    "target_price",
    "level_price",
    "sweep_extreme",
    "touches",
    "confirmations",
    "expected_r",
    "entry_mode",
    "expiry_bars",
]


def pin_bar(df: pd.DataFrame, pos: int, direction: str, ratio: float = 2.0) -> bool:
    """Pin bar at row ``pos``: dominant wick >= ``ratio`` x body, against it."""
    if pos < 0 or pos >= len(df):
        return False
    o, h, lo, c = (float(df.iloc[pos][k]) for k in ("open", "high", "low", "close"))
    body = abs(o - c)
    if not body > 0:
        return False
    if direction == "long":
        return (min(o, c) - lo) >= ratio * body and (h - max(o, c)) <= (min(o, c) - lo)
    return (h - max(o, c)) >= ratio * body and (min(o, c) - lo) <= (h - max(o, c))


def engulfing(df: pd.DataFrame, pos: int, direction: str) -> bool:
    """Two-bar engulfing at row ``pos`` in ``direction``."""
    if pos < 1 or pos >= len(df):
        return False
    po, pc = float(df.iloc[pos - 1]["open"]), float(df.iloc[pos - 1]["close"])
    o, c = float(df.iloc[pos]["open"]), float(df.iloc[pos]["close"])
    if direction == "long":
        return pc < po and c > o and o <= pc and c >= po
    return pc > po and c < o and o >= pc and c <= po


def fib_grid(daily: pd.DataFrame, end_pos: int, lookback: int, ratios: tuple) -> list[float]:
    """Retracement levels of the deep high->low over ``lookback`` bars ending at ``end_pos``."""
    window = daily.iloc[max(0, end_pos - lookback + 1) : end_pos + 1]
    if window.empty:
        return []
    hi, lo = float(window["high"].max()), float(window["low"].min())
    if not hi > lo:
        return []
    return [hi - r * (hi - lo) for r in ratios]


def daily_confirmations(
    daily: pd.DataFrame,
    level_price: float,
    direction: str,
    ret_ts: pd.Timestamp,
    params: RetestParams,
) -> list[str]:
    """Daily-context confirmations known before the H1 return bar (completed days only)."""
    pos = int(daily.index.searchsorted(ret_ts, side="left") - 1)
    if pos < 1:
        return []
    out: list[str] = []
    if (
        pin_bar(daily, pos, direction, params.pin_wick_body_ratio)
        or engulfing(daily, pos, direction)
        or bool(
            detect_sfp(
                daily.iloc[: pos + 1],
                level_price,
                direction,
                params.bias_sfp_wick_atr,
                params.bias_sfp_close_atr,
                params.atr_period,
            ).iloc[-1]
        )
    ):
        out.append("d1_pattern")
    atr_d = atr_series(daily, params.atr_period)
    a = float(atr_d.iloc[pos])
    if a > 0:
        grid = fib_grid(daily, pos, params.fib_lookback, params.fib_ratios)
        if grid and min(abs(level_price - f) for f in grid) <= params.fib_proximity_atr * a:
            out.append("fib")
    sma = daily["close"].rolling(params.atr_stretch_period).mean()
    atr_s = atr_series(daily, params.atr_stretch_period)
    if pos >= params.atr_stretch_period and float(atr_s.iloc[pos]) > 0:
        if abs(level_price - float(sma.iloc[pos])) >= params.atr_stretch_multiple * float(
            atr_s.iloc[pos]
        ):
            out.append("atr_stretch")
    return out


def fib_override(
    daily: pd.DataFrame,
    level_price: float,
    ret_ts: pd.Timestamp,
    params: RetestParams,
) -> float | None:
    """Nearest fib within proximity, else None."""
    pos = int(daily.index.searchsorted(ret_ts, side="left") - 1)
    if pos < 1:
        return None
    a = float(atr_series(daily, params.atr_period).iloc[pos])
    if not a > 0:
        return None
    grid = fib_grid(daily, pos, params.fib_lookback, params.fib_ratios)
    near = [f for f in grid if abs(level_price - f) <= params.fib_proximity_atr * a]
    return min(near, key=lambda f: abs(level_price - f)) if near else None


def _return_episodes(
    level: Any,
    hourly: pd.DataFrame,
    bpos: int,
    deadline: int,
    direction: str,
    params: RetestParams,
) -> list[tuple[int, pd.Timestamp]]:
    """First bar of each return to the broken level: the bar must overlap the
    tolerance band around the level AND close on the broken side (a bar that
    closes back through has re-broken, not returned)."""
    atr = atr_series(hourly, params.atr_period).shift(1).to_numpy()
    highs = hourly["high"].to_numpy()
    lows = hourly["low"].to_numpy()
    closes = hourly["close"].to_numpy()
    out: list[tuple[int, pd.Timestamp]] = []
    prev = -2
    for p in range(bpos + 1, deadline + 1):
        tol = params.touch_tolerance_atr * atr[p]
        if not tol > 0:
            prev = -2
            continue
        overlap = lows[p] <= level.price + tol and highs[p] >= level.price - tol
        if direction == "long":
            held = closes[p] >= level.price - tol
        else:
            held = closes[p] <= level.price + tol
        if overlap and held and p > prev + 1:
            out.append((p, hourly.index[p]))
        prev = p if (overlap and held) else -2
    return out


def touch_episodes(
    level: Any, hourly: pd.DataFrame, i0: int, tolerance_atr: float, atr_period: int
) -> tuple[list[list[int]], int | None]:
    """Approach episodes from ``i0`` and the first break-bar position (or None).

    Returns (episodes, break_pos): episodes are lists of consecutive bar
    positions touching the level; the break bar ends the timeline. The forming
    swing counts as touch #1, so touches = 1 + episodes before the break.
    """
    atr = atr_series(hourly, atr_period).shift(1).to_numpy()
    highs = hourly["high"].to_numpy()
    lows = hourly["low"].to_numpy()
    closes = hourly["close"].to_numpy()
    touch_kind = "resistance" if level.kind == "resistance" else "support"
    episodes: list[list[int]] = []
    current: list[int] = []
    for p in range(i0, len(hourly)):
        tol = tolerance_atr * atr[p]
        if not tol > 0:
            if current:
                episodes.append(current)
                current = []
            continue
        if touch_kind == "resistance":
            touched = highs[p] >= level.price - tol
            broke = closes[p] > level.price + tol
        else:
            touched = lows[p] <= level.price + tol
            broke = closes[p] < level.price - tol
        if broke:
            if current:
                episodes.append(current)
            return episodes, p
        if touched:
            if current and p > current[-1] + 1:
                episodes.append(current)
                current = []
            current.append(p)
        elif current:
            episodes.append(current)
            current = []
    if current:
        episodes.append(current)
    return episodes, None


def generate_retest_signals(
    hourly: pd.DataFrame,
    daily: pd.DataFrame,
    params: RetestParams | None = None,
) -> pd.DataFrame:
    """Breakout-then-return signals, one per level at most."""
    params = params or RetestParams.from_config()
    levels = detect_levels(
        daily,
        lookback=params.swing_lookback,
        cluster_ticks=params.cluster_ticks,
        tick_size=params.tick_size,
        atr_period=params.atr_period,
        min_swing_magnitude_atr=params.min_swing_magnitude_atr,
    )
    if not levels or hourly.empty:
        return _empty_signals()
    resistances = sorted(lv.price for lv in levels if lv.kind == "resistance")
    supports = sorted(lv.price for lv in levels if lv.kind == "support")
    atr_h = atr_series(hourly, params.atr_period).shift(1)
    highs = hourly["high"].to_numpy()
    lows = hourly["low"].to_numpy()

    rows: list[dict[str, Any]] = []
    for level in levels:
        start = _available_from(daily, level.formed_at, params.swing_lookback)
        if start is None or hourly.index[-1] < start:
            continue
        i0 = int(hourly.index.searchsorted(start))
        episodes, bpos = touch_episodes(
            level, hourly, i0, params.touch_tolerance_atr, params.atr_period
        )
        if bpos is None:
            continue  # never broke: not a Setup B level
        # break direction decides the trade (resistance broken up -> long)
        if level.kind == "resistance":
            direction = "long"
        else:
            direction = "short"
        touches = 1 + sum(1 for ep in episodes if ep[-1] < bpos)
        required = params.touch_gates.get(min(touches, 3), 0)
        # first return episode strictly after the break, within the window
        deadline = min(bpos + params.max_break_return_bars, len(hourly) - 1)
        returns = _return_episodes(level, hourly, bpos, deadline, direction, params)
        for p, ret_ts in returns:
            factors = daily_confirmations(daily, level.price, direction, ret_ts, params)
            if len(factors) < required:
                continue
            a = float(atr_h.iloc[p])
            if not a > 0:
                continue
            limit = level.price
            if params.special_fib_rule:
                override = fib_override(daily, level.price, ret_ts, params)
                if override is not None:
                    limit = float(override)
            buf = params.stop_buffer_atr * a
            if direction == "long":
                stop = float(lows[p] - buf)
                above = [r for r in resistances if r > limit]
                target = above[0] if above else limit + params.fta_fallback_atr * a
                risk, reward = limit - stop, target - limit
                extreme = float(lows[p])
            else:
                stop = float(highs[p] + buf)
                below = [s for s in supports if s < limit]
                target = below[-1] if below else limit - params.fta_fallback_atr * a
                risk, reward = stop - limit, limit - target
                extreme = float(highs[p])
            if not risk > 0 or reward < params.min_reward_risk * risk:
                continue
            if params.min_stop_atr > 0 and risk < params.min_stop_atr * a:
                continue  # stop inside noise: leverage fantasy, skip
            rows.append(
                {
                    "timestamp": ret_ts,
                    "direction": direction,
                    "entry_price": float(limit),
                    "stop_price": float(stop),
                    "target_price": float(target),
                    "level_price": level.price,
                    "sweep_extreme": extreme,
                    "touches": touches,
                    "confirmations": factors,
                    "expected_r": float(reward / risk),
                    "entry_mode": "limit",
                    "expiry_bars": float(params.limit_expiry_bars),
                }
            )
            break  # one signal per level
        # next level (a level whose first return fails gates keeps no second chance
        # once the window lapses; loop above already tries every return in-window)
    if not rows:
        return _empty_signals()
    out = pd.DataFrame(rows)
    return out.sort_values("timestamp").reset_index(drop=True)[SIGNAL_COLUMNS]


def _available_from(
    daily: pd.DataFrame, formed_at: pd.Timestamp, lookback: int
) -> pd.Timestamp | None:
    if formed_at not in daily.index:
        return None
    pos = daily.index.get_loc(formed_at) + lookback
    if pos >= len(daily):
        return None
    return daily.index[pos]


def _empty_signals() -> pd.DataFrame:
    out = pd.DataFrame(
        {
            "timestamp": pd.Series(dtype="datetime64[ns, UTC]"),
            "direction": pd.Series(dtype=object),
            "entry_price": pd.Series(dtype=float),
            "stop_price": pd.Series(dtype=float),
            "target_price": pd.Series(dtype=float),
            "level_price": pd.Series(dtype=float),
            "sweep_extreme": pd.Series(dtype=float),
            "touches": pd.Series(dtype=float),
            "confirmations": pd.Series(dtype=object),
            "expected_r": pd.Series(dtype=float),
            "entry_mode": pd.Series(dtype=object),
            "expiry_bars": pd.Series(dtype=float),
        }
    )
    return out[SIGNAL_COLUMNS]
