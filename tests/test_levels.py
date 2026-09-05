"""Phase 3 tests: swings and levels on hand-labeled frames + real-data smoke."""

from pathlib import Path

import pandas as pd
import pytest

from sfp_reversion.data.schema import validate_ohlc
from sfp_reversion.levels.detection import atr_series, detect_levels, swing_points

LB = 2  # compact lookback for hand-labeled frames


def _frame(lows: list[float], spread: float = 0.02) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=len(lows), freq="D", tz="UTC")
    df = pd.DataFrame(
        {
            "open": lows,
            "high": [x + spread for x in lows],
            "low": lows,
            "close": lows,
            "volume": 0.0,
        },
        index=idx,
    )
    df.index.name = "timestamp"
    return validate_ohlc(df)


def test_finds_lone_valley() -> None:
    df = _frame([1.10] * 10 + [1.09, 1.08, 1.05, 1.08, 1.09] + [1.10] * 10)
    swings = swing_points(df, lookback=LB, atr_period=3)
    assert len(swings) == 1
    assert swings.iloc[0]["kind"] == "low"
    assert swings.iloc[0]["price"] == 1.05
    assert swings.index[0] == df.index[12]


def test_finds_lone_peak() -> None:
    df = _frame([1.10] * 10 + [1.11, 1.12, 1.15, 1.12, 1.11] + [1.10] * 10)
    swings = swing_points(df, lookback=LB, atr_period=3)
    assert len(swings) == 1
    assert swings.iloc[0]["kind"] == "high"
    assert swings.iloc[0]["price"] == 1.15 + 0.02


def test_flat_market_has_no_swings() -> None:
    df = _frame([1.10] * 30)
    assert swing_points(df, lookback=LB, atr_period=3).empty


def test_magnitude_filter_rejects_dojilike_extremum() -> None:
    lows = [1.10 + (0.05 if i % 2 == 0 else -0.05) for i in range(20)]
    df = _frame(lows)
    # pinch the middle valley bar into a doji: range ~0 vs ATR ~0.1
    i = 11
    df.iloc[i, df.columns.get_loc("high")] = df.iloc[i]["low"] + 0.0001
    swings = swing_points(df, lookback=LB, atr_period=3, min_magnitude_atr=0.3)
    assert not ((swings["kind"] == "low") & (swings.index == df.index[i])).any()


def test_close_swings_cluster_into_one_level() -> None:
    df = _frame(
        [1.10] * 6 + [1.08, 1.05, 1.08] + [1.10] * 6 + [1.0805, 1.0505, 1.0805] + [1.10] * 6
    )
    levels = detect_levels(df, lookback=LB, atr_period=3, cluster_ticks=10, tick_size=0.0001)
    supports = [lv for lv in levels if lv.kind == "support"]
    assert len(supports) == 1
    assert supports[0].touches == 2
    assert supports[0].price == pytest.approx((1.05 + 1.0505) / 2)


def test_distant_swings_stay_separate() -> None:
    df = _frame([1.10] * 6 + [1.08, 1.05, 1.08] + [1.10] * 6 + [1.08, 1.04, 1.08] + [1.10] * 6)
    levels = detect_levels(df, lookback=LB, atr_period=3, cluster_ticks=10, tick_size=0.0001)
    assert len([lv for lv in levels if lv.kind == "support"]) == 2


def test_highs_and_lows_never_merge() -> None:
    df = _frame([1.10] * 6 + [1.08, 1.05, 1.08] + [1.10] * 6 + [1.12, 1.15, 1.12] + [1.10] * 6)
    levels = detect_levels(df, lookback=LB, atr_period=3, cluster_ticks=1000, tick_size=0.0001)
    kinds = sorted(lv.kind for lv in levels)
    assert kinds == ["resistance", "support"]


def test_atr_warmup_and_positivity() -> None:
    df = _frame([1.10 + 0.01 * (i % 3) for i in range(30)])
    atr = atr_series(df, period=5)
    assert len(atr) == len(df)
    assert atr.iloc[:4].isna().all()
    assert (atr.iloc[4:] > 0).all()


def test_real_data_yields_sane_levels() -> None:
    path = Path("data/cache/EUR_USD_D.parquet")
    if not path.exists():
        pytest.skip("no cached daily data")
    df = validate_ohlc(pd.read_parquet(path))
    levels = detect_levels(df)
    assert levels, "expected levels on a year of daily EUR/USD"
    for lv in levels:
        assert lv.kind in ("support", "resistance")
        assert lv.formed_at in df.index
        assert lv.touches >= 1
