"""Setup B tests: break-then-return grading, confirmations, expiry."""

from dataclasses import replace

import pandas as pd

from sfp_reversion.data.schema import validate_ohlc
from sfp_reversion.signals.retest import (
    RetestParams,
    engulfing,
    fib_grid,
    generate_retest_signals,
    pin_bar,
)

LB = 2


def _daily(peak_high: float = 1.15, pin: bool = False) -> pd.DataFrame:
    idx = pd.date_range("2023-12-01", periods=15, freq="D", tz="UTC")
    df = pd.DataFrame(
        {"open": 1.10, "high": 1.12, "low": 1.10, "close": 1.10, "volume": 0.0}, index=idx
    )
    df.index.name = "timestamp"
    df.loc[idx[7], ["open", "high", "low", "close"]] = [1.12, peak_high, 1.12, 1.12]
    df.loc[idx[6], ["high"]] = 1.121
    df.loc[idx[8], ["high"]] = 1.121
    if pin:
        df.loc[idx[14], ["open", "high", "low", "close"]] = [1.112, 1.116, 1.09, 1.115]
    return validate_ohlc(df)


def _hourly(n: int = 100, special: dict[int, tuple] | None = None) -> pd.DataFrame:
    """Flat 1.14 H1 bars (ATR ~= 0.004, tolerance 0.0004 vs level 1.15)."""
    idx = pd.date_range("2024-01-01", periods=n, freq="h", tz="UTC")
    df = pd.DataFrame(
        {"open": 1.14, "high": 1.1420, "low": 1.1380, "close": 1.14, "volume": 0.0},
        index=idx,
    )
    df.index.name = "timestamp"
    for i, (o, h, lo, c) in (special or {}).items():
        df.iloc[i] = [o, h, lo, c, 0.0]
    return validate_ohlc(df)


def _params(**kw) -> RetestParams:
    return replace(
        RetestParams(),
        swing_lookback=LB,
        tick_size=0.001,
        min_swing_magnitude_atr=0.0,
        atr_period=3,  # short frame: keep ATR warmed up
        atr_stretch_period=3,
        **kw,
    )


def test_pin_and_engulfing() -> None:
    idx = pd.date_range("2024-01-01", periods=3, freq="D", tz="UTC")
    df = pd.DataFrame(
        {
            "open": [1.10, 1.10, 1.112],
            "high": [1.11, 1.11, 1.116],
            "low": [1.09, 1.09, 1.09],
            "close": [1.095, 1.095, 1.115],
            "volume": 0.0,
        },
        index=idx,
    )
    assert pin_bar(df, 2, "long")
    assert not pin_bar(df, 2, "short")
    assert not pin_bar(df, 0, "long")
    eng = pd.DataFrame(
        {
            "open": [1.10, 1.09],
            "high": [1.11, 1.12],
            "low": [1.09, 1.085],
            "close": [1.09, 1.11],
            "volume": 0.0,
        },
        index=idx[:2],
    )
    assert engulfing(eng, 1, "long")
    assert not engulfing(eng, 1, "short")


def test_fib_grid_marks_deep_legs() -> None:
    grid = fib_grid(_daily(), 14, 20, (0.5,))
    assert grid == [1.15 - 0.5 * (1.15 - 1.10)]


def test_three_touch_break_return_trades_clean() -> None:
    hourly = _hourly(
        special={
            10: (1.14, 1.1498, 1.1380, 1.1480),  # touch episode 1
            11: (1.1480, 1.1498, 1.1380, 1.1480),
            30: (1.14, 1.1498, 1.1380, 1.1480),  # touch episode 2
            50: (1.14, 1.1510, 1.1380, 1.1505),  # break up
            55: (1.1490, 1.1510, 1.1498, 1.1500),  # return within window
        }
    )
    sig = generate_retest_signals(hourly, _daily(), _params())
    assert len(sig) == 1
    row = sig.iloc[0]
    assert row["direction"] == "long"
    assert row["entry_price"] == 1.15
    assert row["entry_mode"] == "limit"
    assert row["touches"] == 3
    assert row["timestamp"] == hourly.index[55]


def test_two_touch_needs_confirmation() -> None:
    hourly = _hourly(
        special={
            10: (1.14, 1.1498, 1.1380, 1.1480),
            50: (1.14, 1.1510, 1.1380, 1.1505),
            55: (1.1490, 1.1510, 1.1498, 1.1500),
        }
    )
    # stretch gate disabled to isolate the daily-pattern confirmation
    assert generate_retest_signals(
        hourly, _daily(), _params(atr_stretch_multiple=1e9)
    ).empty  # no pin on daily
    sig = generate_retest_signals(hourly, _daily(pin=True), _params(atr_stretch_multiple=1e9))
    assert len(sig) == 1
    assert sig.iloc[0]["touches"] == 2
    assert "d1_pattern" in sig.iloc[0]["confirmations"]


def test_late_return_expires() -> None:
    hourly = _hourly(
        n=120,
        special={
            10: (1.14, 1.1498, 1.1380, 1.1480),
            30: (1.14, 1.1498, 1.1380, 1.1480),
            50: (1.14, 1.1510, 1.1380, 1.1505),
            90: (1.1490, 1.1510, 1.1498, 1.1500),  # 40 bars after break > 24
        },
    )
    assert generate_retest_signals(hourly, _daily(), _params()).empty


def test_no_break_no_signal() -> None:
    assert generate_retest_signals(_hourly(), _daily(), _params()).empty
