"""Phase 8 tests: textbook SFPs detected, near-misses rejected."""

import pandas as pd

from sfp_reversion.confirmation.sfp import detect_sfp
from sfp_reversion.data.schema import validate_ohlc

LEVEL = 1.05


def _frame() -> pd.DataFrame:
    """30 flat bars (range 0.02 -> ATR ~= 0.02); tests overwrite bar 20."""
    idx = pd.date_range("2024-01-01", periods=30, freq="D", tz="UTC")
    df = pd.DataFrame(
        {"open": 1.10, "high": 1.11, "low": 1.09, "close": 1.10, "volume": 0.0}, index=idx
    )
    df.index.name = "timestamp"
    return validate_ohlc(df)


def _set(df: pd.DataFrame, low: float, high: float, close: float, i: int = 20) -> None:
    df.iloc[i, df.columns.get_loc("low")] = low
    df.iloc[i, df.columns.get_loc("high")] = high
    df.iloc[i, df.columns.get_loc("close")] = close


def test_textbook_long_sfp() -> None:
    df = _frame()
    _set(df, low=1.047, high=1.06, close=1.052)
    out = detect_sfp(df, LEVEL, "long", atr_period=3)
    assert out.iloc[20]
    assert out.sum() == 1


def test_textbook_short_sfp() -> None:
    df = _frame()
    _set(df, low=1.04, high=1.053, close=1.048)
    out = detect_sfp(df, 1.05, "short", atr_period=3)
    assert out.iloc[20]
    assert out.sum() == 1


def test_short_wick_rejected() -> None:
    df = _frame()
    _set(df, low=1.0495, high=1.06, close=1.052)  # wick 0.0005 < 0.1 x ATR
    assert not detect_sfp(df, LEVEL, "long", atr_period=3).iloc[20]


def test_shallow_close_rejected() -> None:
    df = _frame()
    _set(df, low=1.047, high=1.06, close=1.0505)  # inside by 0.0005 < 0.05 x ATR
    assert not detect_sfp(df, LEVEL, "long", atr_period=3).iloc[20]


def test_wrong_side_rejected() -> None:
    df = _frame()
    _set(df, low=1.04, high=1.053, close=1.048)  # a short SFP is not a long SFP
    assert not detect_sfp(df, LEVEL, "long", atr_period=3).iloc[20]


def test_invalid_direction_raises() -> None:
    try:
        detect_sfp(_frame(), LEVEL, "sideways")
    except ValueError as exc:
        assert "long/short" in str(exc)
    else:
        raise AssertionError("expected ValueError")
