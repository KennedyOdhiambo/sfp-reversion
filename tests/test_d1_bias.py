"""Phase 5 tests: bias reads trend, range, and flips correctly."""

import numpy as np
import pandas as pd
import pytest

from sfp_reversion.confluence.d1_bias import d1_bias, d1_bias_matches
from sfp_reversion.data.schema import validate_ohlc


def _trend(n: int, start: float, step: float) -> pd.DataFrame:
    close = start + step * np.arange(n)
    idx = pd.date_range("2024-01-01", periods=n, freq="D", tz="UTC")
    df = pd.DataFrame(
        {
            "open": close,
            "high": close + 0.002,
            "low": close - 0.002,
            "close": close,
            "volume": 0.0,
        },
        index=idx,
    )
    df.index.name = "timestamp"
    return validate_ohlc(df)


def test_uptrend_is_bullish_after_warmup() -> None:
    bias = d1_bias(_trend(150, 1.0, 0.001))
    assert (bias.iloc[-20:] == 1.0).all()


def test_downtrend_is_bearish_after_warmup() -> None:
    bias = d1_bias(_trend(150, 1.2, -0.001))
    assert (bias.iloc[-20:] == -1.0).all()


def test_flat_market_is_neutral() -> None:
    bias = d1_bias(_trend(150, 1.1, 0.0))
    assert (bias == 0.0).all()


def test_flip_changes_sides() -> None:
    up = _trend(100, 1.0, 0.001)
    down = _trend(100, 1.1, -0.001)
    down.index = up.index + pd.Timedelta(days=100)
    df = validate_ohlc(pd.concat([up, down]))
    bias = d1_bias(df)
    assert bias.iloc[99] == 1.0
    assert bias.iloc[-1] == -1.0


def test_matcher() -> None:
    bias = pd.Series([1.0, 0.0, -1.0])
    assert d1_bias_matches(bias, "long").tolist() == [True, False, False]
    assert d1_bias_matches(bias, "short").tolist() == [False, False, True]
    with pytest.raises(ValueError, match="long/short"):
        d1_bias_matches(bias, "sideways")
