"""Setup A signals (strategy.md): Daily levels + H1 SFP -> market orders.

One signal per level at most: the first H1 bar that prints a clean SFP
(sweep + close back inside + clean origin shelf) with R >= min_reward_risk.
A non-SFP close beyond the break tolerance kills the level. No touch counts,
no confluence gates, no MACD — those belong to the parked Setup B.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from sfp_reversion.config import get_config
from sfp_reversion.confirmation.sfp import detect_sfp
from sfp_reversion.levels.detection import atr_series, detect_levels, filter_levels


@dataclass
class SfpParams:
    swing_lookback: int = 5
    cluster_ticks: int = 10
    tick_size: float = 0.0001
    min_swing_magnitude_atr: float = 0.3
    touch_tolerance_atr: float = 0.1
    min_swings_per_level: int = 1
    extreme_lookback: int = 0
    extreme_proximity_atr: float = 0.25
    min_level_spacing_atr: float = 0.0
    atr_period: int = 14
    wick_atr: float = 0.1
    close_inside_atr: float = 0.05
    max_origin_wick_atr: float = 1.0
    stop_buffer_atr: float = 0.1
    fta_fallback_atr: float = 2.0
    min_reward_risk: float = 1.0
    min_stop_atr: float = 0.25
    refine_entry: bool = False
    refine_expiry_bars: int = 12

    @classmethod
    def from_config(cls) -> SfpParams:
        cfg = get_config()
        lvl = cfg.section("levels")
        sfp = cfg.section("sfp")
        return cls(
            swing_lookback=int(lvl.get("swing_lookback", 5)),
            cluster_ticks=int(lvl.get("cluster_ticks", 10)),
            tick_size=float(lvl.get("tick_size", 0.0001)),
            min_swing_magnitude_atr=float(lvl.get("min_swing_magnitude_atr", 0.3)),
            touch_tolerance_atr=float(lvl.get("touch_tolerance_atr", 0.1)),
            min_swings_per_level=int(lvl.get("min_swings_per_level", 1)),
            extreme_lookback=int(lvl.get("extreme_lookback", 0)),
            extreme_proximity_atr=float(lvl.get("extreme_proximity_atr", 0.25)),
            min_level_spacing_atr=float(lvl.get("min_level_spacing_atr", 0.0)),
            atr_period=int(cfg.get("atr.period", 14)),
            wick_atr=float(sfp.get("wick_atr", 0.1)),
            close_inside_atr=float(sfp.get("close_inside_atr", 0.05)),
            max_origin_wick_atr=float(sfp.get("max_origin_wick_atr", 1.0)),
            stop_buffer_atr=float(sfp.get("stop_buffer_atr", 0.1)),
            fta_fallback_atr=float(sfp.get("fta_fallback_atr", 2.0)),
            min_reward_risk=float(sfp.get("min_reward_risk", 1.0)),
            min_stop_atr=float(sfp.get("min_stop_atr", 0.25)),
            refine_entry=bool(sfp.get("refine_entry", False)),
            refine_expiry_bars=int(sfp.get("refine_expiry_bars", 12)),
        )


SIGNAL_COLUMNS = [
    "timestamp",
    "direction",
    "entry_price",
    "stop_price",
    "target_price",
    "level_price",
    "sweep_extreme",
    "wick_atr_mult",
    "close_atr_mult",
    "origin_wick_mult",
    "expected_r",
    "entry_mode",
    "expiry_bars",
]


def generate_sfp_signals(
    hourly: pd.DataFrame,
    daily: pd.DataFrame,
    params: SfpParams | None = None,
    levels: list | None = None,
) -> pd.DataFrame:
    """Scan each daily level for its first clean H1 SFP. One row per signal."""
    params = params or SfpParams.from_config()
    if levels is None:
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
    levels = filter_levels(
        levels,
        daily,
        min_swings=params.min_swings_per_level,
        extreme_lookback=params.extreme_lookback,
        extreme_proximity_atr=params.extreme_proximity_atr,
        min_spacing_atr=params.min_level_spacing_atr,
        atr_period=params.atr_period,
    )
    if not levels:
        return _empty_signals()
    resistances = sorted(lv.price for lv in levels if lv.kind == "resistance")
    supports = sorted(lv.price for lv in levels if lv.kind == "support")

    atr_h = atr_series(hourly, params.atr_period).shift(1)
    closes = hourly["close"].to_numpy()
    highs = hourly["high"].to_numpy()
    lows = hourly["low"].to_numpy()

    rows: list[dict[str, Any]] = []
    for level in levels:
        start = _available_from(daily, level.formed_at, params.swing_lookback)
        if start is None or hourly.index[-1] < start:
            continue
        i0 = int(hourly.index.searchsorted(start))
        direction = "long" if level.kind == "support" else "short"
        sfp = detect_sfp(
            hourly,
            level.price,
            direction,
            params.wick_atr,
            params.close_inside_atr,
            params.atr_period,
        )
        tol = params.touch_tolerance_atr * atr_h
        for p in range(i0, len(hourly)):
            a = float(atr_h.iloc[p])
            if not a > 0:
                continue
            if bool(sfp.iloc[p]):
                sig = _try_signal(
                    level,
                    direction,
                    hourly.index[p],
                    float(closes[p]),
                    float(highs[p]),
                    float(lows[p]),
                    a,
                    resistances,
                    supports,
                    params,
                )
                if sig is not None:
                    rows.append(sig)
                    break  # first clean failure per level; level consumed
                continue  # SFP that fails filters never kills the level
            if _broke(level.price, direction, float(closes[p]), float(tol.iloc[p])):
                break  # genuine break: level dead for Setup A
    if not rows:
        return _empty_signals()
    out = pd.DataFrame(rows)
    return out.sort_values("timestamp").reset_index(drop=True)[SIGNAL_COLUMNS]


def _try_signal(
    level: Any,
    direction: str,
    ts: pd.Timestamp,
    close: float,
    high: float,
    low: float,
    atr: float,
    resistances: list[float],
    supports: list[float],
    params: SfpParams,
) -> dict[str, Any] | None:
    origin_mult = level.origin_wick_mult
    if params.max_origin_wick_atr > 0 and origin_mult > params.max_origin_wick_atr:
        return None  # messy shelf (origin wick in daily ATR at formation)
    buf = params.stop_buffer_atr * atr
    if direction == "long":
        wick_mult = (level.price - low) / atr
        close_mult = (close - level.price) / atr
        stop = low - buf
        # refined: limit buy at the level (better than the rejection close);
        # unrefined: market at the close.
        entry = level.price if params.refine_entry else close
        above = [r for r in resistances if r > entry]
        target = above[0] if above else entry + params.fta_fallback_atr * atr
        risk, reward = entry - stop, target - entry
        extreme = low
    else:
        wick_mult = (high - level.price) / atr
        close_mult = (level.price - close) / atr
        stop = high + buf
        entry = level.price if params.refine_entry else close
        below = [s for s in supports if s < entry]
        target = below[-1] if below else entry - params.fta_fallback_atr * atr
        risk, reward = stop - entry, entry - target
        extreme = high
    if not risk > 0 or reward < params.min_reward_risk * risk:
        return None
    if params.min_stop_atr > 0 and risk < params.min_stop_atr * atr:
        return None  # stop inside noise: leverage fantasy, skip
    return {
        "timestamp": ts,
        "direction": direction,
        "entry_price": float(entry),
        "stop_price": float(stop),
        "target_price": float(target),
        "level_price": level.price,
        "sweep_extreme": float(extreme),
        "wick_atr_mult": float(wick_mult),
        "close_atr_mult": float(close_mult),
        "origin_wick_mult": float(origin_mult),
        "expected_r": float(reward / risk),
        "entry_mode": "limit" if params.refine_entry else "market",
        "expiry_bars": float(params.refine_expiry_bars) if params.refine_entry else 0.0,
    }


def _broke(level_price: float, direction: str, close: float, tol: float) -> bool:
    if not tol > 0:
        return False
    if direction == "long":
        return close < level_price - tol
    return close > level_price + tol


def _available_from(
    daily: pd.DataFrame, formed_at: pd.Timestamp, lookback: int
) -> pd.Timestamp | None:
    """First hourly-usable timestamp: the daily bar confirming the level."""
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
            "wick_atr_mult": pd.Series(dtype=float),
            "close_atr_mult": pd.Series(dtype=float),
            "origin_wick_mult": pd.Series(dtype=float),
            "expected_r": pd.Series(dtype=float),
            "entry_mode": pd.Series(dtype=object),
            "expiry_bars": pd.Series(dtype=float),
        }
    )
    return out[SIGNAL_COLUMNS]
