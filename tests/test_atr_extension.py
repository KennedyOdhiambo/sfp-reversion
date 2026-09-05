"""Phase 7 tests: stretched vs nearby levels, both references, gating."""

import pandas as pd
import pytest

from sfp_reversion.confluence.atr_extension import atr_extension
from sfp_reversion.data.schema import validate_ohlc


def _frame() -> pd.DataFrame:
    """40 bars, range ~0.02; valley (low 1.00) at 10, rallied flat (~1.10) from 20."""
    n = 40
    lows = [1.09] * n
    highs = [1.11] * n
    lows[10] = 1.00
    highs[10] = 1.02
    for i in range(20, n):
        lows[i], highs[i] = 1.10, 1.12
    idx = pd.date_range("2024-01-01", periods=n, freq="D", tz="UTC")
    df = pd.DataFrame(
        {"open": lows, "high": highs, "low": lows, "close": lows, "volume": 0.0}, index=idx
    )
    df.index.name = "timestamp"
    return validate_ohlc(df)


def _level(price: float, n: int = 40) -> pd.Series:
    idx = pd.date_range("2024-01-01", periods=n, freq="D", tz="UTC")
    return pd.Series(price, index=idx)


def test_stretched_level_true_after_confirmation() -> None:
    df = _frame()
    out = atr_extension(df, _level(1.10), swing_lookback=2, atr_period=3)
    assert not out.iloc[11]  # swing at 10 confirms at 12
    assert out.iloc[15]  # |1.10 - 1.00| = 0.10 >> ATR
    assert out.iloc[39]


def test_nearby_level_false() -> None:
    df = _frame()
    out = atr_extension(df, _level(1.005), swing_lookback=2, atr_period=3)
    assert not out.iloc[15]
    assert not out.iloc[39]


def test_nan_level_never_fires() -> None:
    df = _frame()
    out = atr_extension(df, pd.Series(float("nan"), index=df.index), swing_lookback=2, atr_period=3)
    assert not out.any()


def test_prior_close_reference() -> None:
    df = _frame()
    far = atr_extension(df, _level(1.50), reference="prior_close", atr_period=3)
    assert far.iloc[25]
    same = atr_extension(df, df["close"], reference="prior_close", atr_period=3)
    assert not same.iloc[25]


def test_unknown_reference_raises() -> None:
    with pytest.raises(ValueError, match="Unknown ATR extension reference"):
        atr_extension(_frame(), _level(1.10), reference="vibes")
