"""Signal assembly (Phase 10): daily levels + hourly entries -> signal table.

Option A wiring: levels are detected on the daily frame; everything else runs
on the hourly (entry) frame. Daily context (bias, fib lines) is mapped onto
hourly bars with forward-fill, so a bar only ever sees confirmed daily output.

Counting: touches = daily swings forming the level + hourly approach episodes;
retests = hourly episodes (returns to an established level). At most one
signal per episode (the first bar where every gate passes).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from sfp_reversion.config import get_config
from sfp_reversion.confirmation import detect_sfp, macd_divergence
from sfp_reversion.confluence import atr_extension, d1_bias
from sfp_reversion.confluence.fib_levels import fib_grid, fib_override_price, near_fib
from sfp_reversion.levels.detection import atr_series, detect_levels
from sfp_reversion.levels.touches import approach_episodes, retest_events


@dataclass
class DecisionTreeParams:
    swing_lookback: int = 5
    cluster_ticks: int = 10
    tick_size: float = 0.0001
    min_swing_magnitude_atr: float = 0.3
    touch_tolerance_atr: float = 0.1
    atr_period: int = 14
    d1_ema_fast: int = 20
    d1_ema_slow: int = 50
    d1_lookback: int = 10
    fib_swing_lookback: int = 20
    fib_ratios: tuple[float, ...] = (0.382, 0.5, 0.618, 0.786)
    fib_proximity_atr: float = 0.2
    atr_ext_multiple: float = 1.0
    atr_ext_reference: str = "recent_swing"
    sfp_wick_atr: float = 0.1
    sfp_close_inside_atr: float = 0.05
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    macd_use_histogram: bool = True
    macd_swing_lookback: int = 5
    macd_n_swings: int = 3
    touch_confluence: dict[int, int] = field(default_factory=lambda: {3: 0, 2: 1, 1: 2})
    retest_gate: dict[int, str] = field(default_factory=lambda: {1: "sfp", 2: "sfp_macd"})
    max_retests: int = 2
    min_reward_risk: float = 1.0
    special_fib_rule: bool = True
    stop_buffer_atr: float = 0.1
    fta_fallback_atr: float = 2.0

    @classmethod
    def from_config(cls) -> DecisionTreeParams:
        cfg = get_config()
        lvl = cfg.section("levels")
        d1 = cfg.section("confluence").get("d1_bias", {})
        fib = cfg.section("confluence").get("fib", {})
        ext = cfg.section("confluence").get("atr_extension", {})
        sfp = cfg.section("confirmation").get("sfp", {})
        macd = cfg.section("confirmation").get("macd", {})
        sig = cfg.section("signal")
        return cls(
            swing_lookback=int(lvl.get("swing_lookback", 5)),
            cluster_ticks=int(lvl.get("cluster_ticks", 10)),
            tick_size=float(lvl.get("tick_size", 0.0001)),
            min_swing_magnitude_atr=float(lvl.get("min_swing_magnitude_atr", 0.3)),
            touch_tolerance_atr=float(lvl.get("touch_tolerance_atr", 0.1)),
            atr_period=int(ext.get("period", 14)),
            d1_ema_fast=int(d1.get("ema_fast", 20)),
            d1_ema_slow=int(d1.get("ema_slow", 50)),
            d1_lookback=int(d1.get("lookback", 10)),
            fib_swing_lookback=int(fib.get("swing_lookback", 20)),
            fib_ratios=tuple(float(r) for r in fib.get("ratios", [0.382, 0.5, 0.618, 0.786])),
            fib_proximity_atr=float(fib.get("proximity_atr", 0.2)),
            atr_ext_multiple=float(ext.get("multiple", 1.0)),
            atr_ext_reference=str(ext.get("reference", "recent_swing")),
            sfp_wick_atr=float(sfp.get("wick_atr", 0.1)),
            sfp_close_inside_atr=float(sfp.get("close_inside_atr", 0.05)),
            macd_fast=int(macd.get("fast", 12)),
            macd_slow=int(macd.get("slow", 26)),
            macd_signal=int(macd.get("signal", 9)),
            macd_use_histogram=bool(macd.get("use_histogram", True)),
            macd_swing_lookback=int(macd.get("swing_lookback", 5)),
            macd_n_swings=int(macd.get("n_swings", 3)),
            touch_confluence={int(k): int(v) for k, v in sig.get("touch_confluence", {}).items()},
            retest_gate={int(k): str(v) for k, v in sig.get("retest_gate", {}).items()},
            max_retests=int(lvl.get("max_retests", 2)),
            min_reward_risk=float(sig.get("min_reward_risk", 1.0)),
            special_fib_rule=bool(sig.get("special_fib_rule", True)),
            stop_buffer_atr=float(sig.get("stop_buffer_atr", 0.1)),
            fta_fallback_atr=float(sig.get("fta_fallback_atr", 2.0)),
        )


def generate_signals(
    hourly: pd.DataFrame,
    daily: pd.DataFrame,
    params: DecisionTreeParams | None = None,
) -> pd.DataFrame:
    """Full decision tree over hourly bars against daily levels. One row per signal."""
    params = params or DecisionTreeParams.from_config()
    levels = detect_levels(
        daily,
        lookback=params.swing_lookback,
        cluster_ticks=params.cluster_ticks,
        tick_size=params.tick_size,
        atr_period=params.atr_period,
        min_swing_magnitude_atr=params.min_swing_magnitude_atr,
    )
    if not levels:
        return _empty_signals()

    resistances = sorted(lv.price for lv in levels if lv.kind == "resistance")
    supports = sorted(lv.price for lv in levels if lv.kind == "support")

    # daily context, forward-filled onto hourly bars (confirmed-only by construction)
    bias_h = d1_bias(daily, params.d1_ema_fast, params.d1_ema_slow, params.d1_lookback)
    bias_h = bias_h.reindex(hourly.index, method="ffill")
    fib_h = fib_grid(daily, params.fib_swing_lookback, params.fib_ratios, params.atr_period)
    fib_h = fib_h.reindex(hourly.index, method="ffill")

    atr_h = atr_series(hourly, params.atr_period).shift(1)
    macd_long = macd_divergence(
        hourly,
        "long",
        params.macd_fast,
        params.macd_slow,
        params.macd_signal,
        params.macd_swing_lookback,
        params.macd_n_swings,
        params.macd_use_histogram,
    )
    macd_short = macd_divergence(
        hourly,
        "short",
        params.macd_fast,
        params.macd_slow,
        params.macd_signal,
        params.macd_swing_lookback,
        params.macd_n_swings,
        params.macd_use_histogram,
    )
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
        want_bias = 1.0 if direction == "long" else -1.0

        events = retest_events(level, hourly, params.touch_tolerance_atr)
        episodes, _ = approach_episodes(events, hourly)
        live = [(j, ep) for j, ep in enumerate(episodes) if hourly.index.get_loc(ep[-1].ts) >= i0]
        if not live:
            continue

        const = pd.Series(level.price, index=hourly.index)
        sfp = detect_sfp(
            hourly,
            level.price,
            direction,
            params.sfp_wick_atr,
            params.sfp_close_inside_atr,
            params.atr_period,
        )
        macd_hit = macd_long if direction == "long" else macd_short
        ext = atr_extension(
            hourly,
            const,
            params.atr_ext_multiple,
            params.atr_ext_reference,
            params.atr_period,
        )
        near = near_fib(
            hourly,
            const,
            params.fib_swing_lookback,
            params.fib_ratios,
            params.fib_proximity_atr,
            params.atr_period,
            grid=fib_h,
        )
        override = fib_override_price(
            hourly,
            const,
            params.fib_swing_lookback,
            params.fib_ratios,
            params.fib_proximity_atr,
            params.atr_period,
            grid=fib_h,
        )

        for j, ep in live:
            retests = j + 1
            if retests > params.max_retests:
                break
            touches = level.touches + j + 1
            req = params.touch_confluence.get(min(touches, 3), 0)
            gate = params.retest_gate.get(retests, "none")
            if gate == "pass":
                break
            if gate not in ("none", "sfp", "sfp_macd"):
                raise ValueError(f"Unknown retest gate: {gate}")
            for e in ep:
                p = hourly.index.get_loc(e.ts)
                if p < i0:
                    continue
                if direction == "long" and not closes[p] > level.price:
                    continue
                if direction == "short" and not closes[p] < level.price:
                    continue
                factors: list[str] = []
                if req > 0:
                    if bias_h.iloc[p] == want_bias:
                        factors.append("d1_bias")
                    if bool(near.iloc[p]):
                        factors.append("fib")
                    if bool(ext.iloc[p]):
                        factors.append("atr_extension")
                if len(factors) < req:
                    continue
                sfp_hit = bool(sfp.iloc[p])
                div_hit = bool(macd_hit.iloc[p])
                if gate == "sfp" and not sfp_hit:
                    continue
                if gate == "sfp_macd" and not (sfp_hit and div_hit):
                    continue
                limit = level.price
                special = False
                if params.special_fib_rule and pd.notna(override.iloc[p]):
                    limit = float(override.iloc[p])
                    special = limit != level.price
                buf = params.stop_buffer_atr * atr_h.iloc[p]
                if not atr_h.iloc[p] > 0:
                    continue
                if direction == "long":
                    stop = float(lows[p] - buf)
                    above = [r for r in resistances if r > limit]
                    target = above[0] if above else limit + params.fta_fallback_atr * atr_h.iloc[p]
                    risk, reward = limit - stop, target - limit
                else:
                    stop = float(highs[p] + buf)
                    below = [s for s in supports if s < limit]
                    target = below[-1] if below else limit - params.fta_fallback_atr * atr_h.iloc[p]
                    risk, reward = stop - limit, limit - target
                if not risk > 0 or reward < params.min_reward_risk * risk:
                    continue
                rows.append(
                    {
                        "timestamp": hourly.index[p],
                        "direction": direction,
                        "level_price": level.price,
                        "limit_price": limit,
                        "stop_price": stop,
                        "target_price": float(target),
                        "touches": touches,
                        "retests": retests,
                        "confluence_count": len(factors),
                        "sfp": sfp_hit,
                        "macd_divergence": div_hit,
                        "confluence_factors": factors,
                        "special_fib": special,
                    }
                )
                break  # one signal per episode
    if not rows:
        return _empty_signals()
    out = pd.DataFrame(rows).drop_duplicates(subset=["timestamp", "direction", "level_price"])
    return out.sort_values("timestamp").reset_index(drop=True)


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
    return pd.DataFrame(
        columns=[
            "timestamp",
            "direction",
            "level_price",
            "limit_price",
            "stop_price",
            "target_price",
            "touches",
            "retests",
            "confluence_count",
            "sfp",
            "macd_divergence",
            "confluence_factors",
            "special_fib",
        ]
    )
