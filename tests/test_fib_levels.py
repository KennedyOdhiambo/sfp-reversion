"""Phase 6 tests: fib grid math, confirmation gating, proximity, override."""

import pandas as pd

from sfp_reversion.confluence.fib_levels import fib_grid, fib_override_price, near_fib
from sfp_reversion.data.schema import validate_ohlc

LB = 3


def _frame() -> pd.DataFrame:
    """50 bars: peak (high 1.20) at 10, valley (low 1.00) at 30, flat 1.10/1.12 base."""
    n = 50
    lows = [1.10] * n
    highs = [1.12] * n
    lows[10], highs[10] = 1.18, 1.20
    lows[30], highs[30] = 1.00, 1.02
    idx = pd.date_range("2024-01-01", periods=n, freq="D", tz="UTC")
    df = pd.DataFrame(
        {"open": lows, "high": highs, "low": lows, "close": lows, "volume": 0.0}, index=idx
    )
    df.index.name = "timestamp"
    return validate_ohlc(df)


def test_grid_nan_until_pair_confirms_then_correct() -> None:
    grid = fib_grid(_frame(), swing_lookback=LB, atr_period=3)
    assert grid.iloc[20].isna().all()  # only the peak confirmed: no pair yet
    row = grid.iloc[40]  # valley confirmed at 33: down-leg fibs of 1.20 -> 1.00
    assert row["fib_0.618"] == 1.20 - 0.618 * 0.20
    assert row["fib_0.382"] == 1.20 - 0.382 * 0.20
    assert row["fib_0.500"] == 1.10


def test_up_leg_draws_from_low() -> None:
    df = _frame()
    # swap: valley first (10), peak last (30) -> up-leg fibs of 1.00 -> 1.20
    df.iloc[10, df.columns.get_loc("low")] = 1.00
    df.iloc[10, df.columns.get_loc("high")] = 1.02
    df.iloc[30, df.columns.get_loc("low")] = 1.18
    df.iloc[30, df.columns.get_loc("high")] = 1.20
    row = fib_grid(df, swing_lookback=LB, atr_period=3).iloc[40]
    assert row["fib_0.618"] == 1.00 + 0.618 * 0.20


def test_near_fib_proximity_and_gating() -> None:
    df = _frame()
    near = near_fib(df, pd.Series(1.0764, index=df.index), swing_lookback=LB, atr_period=3)
    assert not near.iloc[20]  # no fibs live yet
    assert near.iloc[40]  # |1.0764 - 1.0764| = 0
    far = near_fib(df, pd.Series(1.15, index=df.index), swing_lookback=LB, atr_period=3)
    assert not far.iloc[40]


def test_override_picks_nearest_live_fib() -> None:
    df = _frame()
    out = fib_override_price(df, pd.Series(1.077, index=df.index), swing_lookback=LB, atr_period=3)
    assert pd.isna(out.iloc[20])
    assert out.iloc[40] == 1.20 - 0.618 * 0.20
    far = fib_override_price(df, pd.Series(1.15, index=df.index), swing_lookback=LB, atr_period=3)
    assert pd.isna(far.iloc[40])
