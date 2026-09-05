"""Phase 9 tests: divergence flags on textbook shapes, silent otherwise."""

import numpy as np
import pandas as pd

from sfp_reversion.confirmation.macd_divergence import macd, macd_divergence
from sfp_reversion.data.schema import validate_ohlc

LB = 3


def _frame(close: np.ndarray) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=len(close), freq="D", tz="UTC")
    df = pd.DataFrame(
        {
            "open": close,
            "high": close + 0.005,
            "low": close - 0.005,
            "close": close,
            "volume": 0.0,
        },
        index=idx,
    )
    df.index.name = "timestamp"
    return validate_ohlc(df)


def _decelerating_drop() -> np.ndarray:
    segs: list[float] = []
    segs += list(np.linspace(1.20, 1.10, 10))
    segs += list(np.linspace(1.10, 1.14, 5))[1:]
    segs += list(np.linspace(1.14, 1.08, 12))[1:]
    segs += list(np.linspace(1.08, 1.11, 5))[1:]
    segs += list(np.linspace(1.11, 1.06, 14))[1:]
    segs += list(np.linspace(1.06, 1.09, 5))[1:]
    return np.array(segs)


def test_bullish_divergence_from_third_low_confirmation() -> None:
    df = _frame(_decelerating_drop())
    out = macd_divergence(df, "long", swing_lookback=LB)
    assert not out.iloc[:-2].any()  # silent until the 3rd low confirms
    assert out.iloc[-1]


def test_bearish_mirror() -> None:
    df = _frame(2.20 - _decelerating_drop())
    out = macd_divergence(df, "short", swing_lookback=LB)
    assert not out.iloc[:-2].any()
    assert out.iloc[-1]


def test_wrong_direction_silent() -> None:
    df = _frame(_decelerating_drop())
    assert not macd_divergence(df, "short", swing_lookback=LB).any()


def test_accelerating_drop_has_no_divergence() -> None:
    segs: list[float] = []
    segs += list(np.linspace(1.20, 1.16, 10))
    segs += list(np.linspace(1.16, 1.18, 4))[1:]
    segs += list(np.linspace(1.18, 1.10, 8))[1:]
    segs += list(np.linspace(1.10, 1.13, 4))[1:]
    segs += list(np.linspace(1.13, 1.02, 6))[1:]
    segs += list(np.linspace(1.02, 1.05, 4))[1:]
    df = _frame(np.array(segs))
    assert not macd_divergence(df, "long", swing_lookback=LB).any()


def test_macd_frame_columns() -> None:
    m = macd(_frame(_decelerating_drop()))
    assert list(m.columns) == ["macd", "signal", "hist"]
    assert len(m) == len(_decelerating_drop())
