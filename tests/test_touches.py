"""Phase 4 tests: touch/retest/break timelines on scripted frames."""

import pandas as pd

from sfp_reversion.data.schema import validate_ohlc
from sfp_reversion.levels.detection import Level
from sfp_reversion.levels.touches import count_touches, retest_events

TOL = 0.1  # × ATR; filler range 0.02 -> ATR ~= 0.02 -> tol ~= 0.002


def _frame() -> pd.DataFrame:
    """30 filler bars around 1.10; tests overwrite scripted indices."""
    idx = pd.date_range("2024-01-01", periods=30, freq="D", tz="UTC")
    df = pd.DataFrame(
        {"open": 1.10, "high": 1.11, "low": 1.09, "close": 1.10, "volume": 0.0}, index=idx
    )
    df.index.name = "timestamp"
    return validate_ohlc(df)


def _support() -> Level:
    df = _frame()
    return Level(price=1.05, kind="support", formed_at=df.index[14], swing_prices=[1.05])


def _set(df: pd.DataFrame, i: int, low: float, high: float, close: float) -> None:
    df.iloc[i, df.columns.get_loc("low")] = low
    df.iloc[i, df.columns.get_loc("high")] = high
    df.iloc[i, df.columns.get_loc("close")] = close


def test_retest_then_break_timeline() -> None:
    df, level = _frame(), _support()
    _set(df, 16, low=1.051, high=1.07, close=1.06)  # retest #1
    _set(df, 18, low=1.053, high=1.07, close=1.06)  # just outside tol -> nothing
    _set(df, 20, low=1.0505, high=1.07, close=1.06)  # retest #2
    _set(df, 22, low=1.039, high=1.06, close=1.04)  # break
    _set(df, 24, low=1.05, high=1.07, close=1.06)  # after break -> ignored

    events = retest_events(level, df, TOL)
    assert [(e.event, e.retest_count) for e in events] == [
        ("retest", 1),
        ("retest", 2),
        ("break", 2),
    ]
    assert count_touches(level, df, TOL) == 2


def test_first_touch_mode_counts_establishing_touch() -> None:
    df, level = _frame(), _support()
    _set(df, 16, low=1.051, high=1.07, close=1.06)
    _set(df, 20, low=1.0505, high=1.07, close=1.06)

    events = retest_events(level, df, TOL, retest_start="after_first_touch")
    assert [(e.event, e.retest_count) for e in events] == [("touch", 0), ("retest", 1)]


def test_resistance_mirrors() -> None:
    df = _frame()
    level = Level(price=1.15, kind="resistance", formed_at=df.index[14], swing_prices=[1.15])
    _set(df, 16, low=1.13, high=1.149, close=1.14)  # retest #1
    _set(df, 20, low=1.13, high=1.16, close=1.155)  # break (close > 1.152)

    events = retest_events(level, df, TOL)
    assert [(e.event, e.retest_count) for e in events] == [("retest", 1), ("break", 1)]


def test_untouched_level_counts_one_no_events() -> None:
    df, level = _frame(), _support()
    assert count_touches(level, df, TOL) == 1
    assert retest_events(level, df, TOL) == []
