"""Setup A signal tests: first clean SFP per level, exact orders, all rejects."""

from dataclasses import replace

import pandas as pd
import pytest

from sfp_reversion.data.schema import validate_ohlc
from sfp_reversion.signals.sfp import SfpParams, generate_sfp_signals

LEVEL = 1.09
LB = 2


def _daily(valley_low: float = LEVEL, valley_wick: float = 0.0) -> pd.DataFrame:
    """15 flat daily bars with one valley at idx 7 (support LEVEL)."""
    idx = pd.date_range("2023-12-01", periods=15, freq="D", tz="UTC")
    df = pd.DataFrame(
        {"open": 1.10, "high": 1.12, "low": 1.10, "close": 1.10, "volume": 0.0}, index=idx
    )
    df.index.name = "timestamp"
    df.loc[idx[7], ["open", "high", "low", "close"]] = [
        valley_low + valley_wick,
        1.11,
        valley_low,
        valley_low + valley_wick,
    ]
    df.loc[idx[6], ["low"]] = 1.095
    df.loc[idx[8], ["low"]] = 1.095
    return validate_ohlc(df)


def _hourly(n: int = 100, special: dict[int, tuple] | None = None) -> pd.DataFrame:
    """Flat 1.0950 H1 bars (ATR ~= 0.004); special[i] = (open, high, low, close)."""
    idx = pd.date_range("2024-01-01", periods=n, freq="h", tz="UTC")
    df = pd.DataFrame(
        {"open": 1.0950, "high": 1.0970, "low": 1.0930, "close": 1.0950, "volume": 0.0},
        index=idx,
    )
    df.index.name = "timestamp"
    for i, (o, h, lo, c) in (special or {}).items():
        df.iloc[i] = [o, h, lo, c, 0.0]
    return validate_ohlc(df)


def _params(**kw) -> SfpParams:
    return replace(
        SfpParams(),
        swing_lookback=LB,
        tick_size=0.001,
        min_swing_magnitude_atr=0.0,
        atr_period=3,  # short frame: keep ATR warmed up
        **kw,
    )


def test_long_sfp_signal_with_exact_orders() -> None:
    hourly = _hourly(special={60: (1.0950, 1.0970, 1.0890, 1.0905)})
    sig = generate_sfp_signals(hourly, _daily(), _params())
    assert len(sig) == 1
    row = sig.iloc[0]
    assert row["direction"] == "long"
    assert row["timestamp"] == hourly.index[60]
    assert row["entry_price"] == 1.0905
    assert row["stop_price"] == 1.0890 - 0.0004  # sweep low - 0.1 x ATR(0.004)
    assert row["target_price"] == 1.0905 + 2.0 * 0.004  # no resistance: fallback
    assert row["expected_r"] > 1.0
    assert row["wick_atr_mult"] == pytest.approx(0.25)
    assert row["close_atr_mult"] == pytest.approx(0.125)


def test_one_signal_per_level_first_sfp_wins() -> None:
    hourly = _hourly(
        special={
            60: (1.0950, 1.0970, 1.0890, 1.0905),
            80: (1.0950, 1.0970, 1.0888, 1.0906),
        }
    )
    sig = generate_sfp_signals(hourly, _daily(), _params())
    assert len(sig) == 1
    assert sig.iloc[0]["timestamp"] == hourly.index[60]


def test_shallow_wick_no_signal() -> None:
    hourly = _hourly(special={60: (1.0950, 1.0970, 1.0899, 1.0905)})  # wick 0.0001
    assert generate_sfp_signals(hourly, _daily(), _params()).empty


def test_genuine_break_kills_level() -> None:
    hourly = _hourly(
        special={
            60: (1.0950, 1.0970, 1.0890, 1.0895),  # sweeps but closes through: break
            80: (1.0950, 1.0970, 1.0888, 1.0906),  # valid SFP, but level is dead
        }
    )
    assert generate_sfp_signals(hourly, _daily(), _params()).empty


def test_messy_origin_shelf_skipped() -> None:
    hourly = _hourly(special={60: (1.0950, 1.0970, 1.0890, 1.0905)})
    daily = _daily(valley_wick=0.01)  # origin wick 2.5 x ATR(0.004) > 1.0
    assert generate_sfp_signals(hourly, daily, _params()).empty


def test_min_reward_risk_filter_skips() -> None:
    hourly = _hourly(special={60: (1.0950, 1.0970, 1.0890, 1.0905)})
    sig = generate_sfp_signals(hourly, _daily(), _params(min_reward_risk=10.0))
    assert sig.empty
