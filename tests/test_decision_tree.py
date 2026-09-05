"""Phase 10 tests: scripted end-to-end signal + real-data properties and probe."""

import pandas as pd

from sfp_reversion.data.schema import validate_ohlc
from sfp_reversion.signals.decision_tree import DecisionTreeParams, generate_signals


def _daily_three_valleys() -> pd.DataFrame:
    """70 bars, base 1.10/1.12, three 1.05 valleys at 15/30/45 -> one 3-touch level."""
    n = 70
    lows = [1.10] * n
    highs = [1.12] * n
    for c in (15, 30, 45):
        lows[c - 2 : c + 3] = [1.09, 1.08, 1.05, 1.08, 1.09]
        highs[c] = 1.07
    idx = pd.date_range("2024-01-01", periods=n, freq="D", tz="UTC")
    df = pd.DataFrame(
        {"open": lows, "high": highs, "low": lows, "close": lows, "volume": 0.0}, index=idx
    )
    df.index.name = "timestamp"
    return validate_ohlc(df)


def _hourly_with_dip() -> pd.DataFrame:
    """120 flat hours from 2024-02-20 with one SFP dip at position 60."""
    n = 120
    idx = pd.date_range("2024-02-20", periods=n, freq="h", tz="UTC")
    df = pd.DataFrame(
        {"open": 1.10, "high": 1.11, "low": 1.09, "close": 1.10, "volume": 0.0}, index=idx
    )
    i = 60
    df.iloc[i, df.columns.get_loc("low")] = 1.045
    df.iloc[i, df.columns.get_loc("high")] = 1.10
    df.iloc[i, df.columns.get_loc("close")] = 1.056
    df.index.name = "timestamp"
    return validate_ohlc(df)


def test_scripted_three_touch_sfp_signal() -> None:
    params = DecisionTreeParams(swing_lookback=3, special_fib_rule=False)
    sig = generate_signals(_hourly_with_dip(), _daily_three_valleys(), params)
    assert len(sig) == 1
    row = sig.iloc[0]
    assert row["direction"] == "long"
    assert row["level_price"] == 1.05
    assert row["touches"] == 4  # 3 daily swings + 1 hourly episode
    assert row["retests"] == 1
    assert row["sfp"]
    assert row["stop_price"] < row["limit_price"] < row["target_price"]
    assert (row["target_price"] - row["limit_price"]) >= (row["limit_price"] - row["stop_price"])


def _real_frames() -> tuple[pd.DataFrame, pd.DataFrame] | None:
    try:
        daily = validate_ohlc(pd.read_parquet("data/cache/EUR_USD_D.parquet"))
        hourly = validate_ohlc(pd.read_parquet("data/cache/EUR_USD_H1.parquet"))
    except FileNotFoundError:
        return None
    return hourly, daily


def test_real_data_signal_properties() -> None:
    frames = _real_frames()
    if frames is None:
        return
    hourly, daily = frames
    sig = generate_signals(hourly, daily)
    assert list(sig.columns) == [
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
    for _, r in sig.iterrows():
        assert r["timestamp"] in hourly.index
        if r["direction"] == "long":
            assert r["stop_price"] < r["limit_price"] < r["target_price"]
        else:
            assert r["stop_price"] > r["limit_price"] > r["target_price"]
        assert r["retests"] <= 2
        assert r["confluence_count"] == len(r["confluence_factors"])


def test_truncation_invariance_probe() -> None:
    """Same bars in -> same signals out, regardless of how much future exists."""
    frames = _real_frames()
    if frames is None:
        return
    hourly, daily = frames
    cut = len(hourly) // 2
    safe_ts = hourly.index[cut - 50]
    full = generate_signals(hourly, daily)
    trunc = generate_signals(hourly.iloc[:cut], daily)
    f = full[full["timestamp"] < safe_ts].reset_index(drop=True)
    t = trunc[trunc["timestamp"] < safe_ts].reset_index(drop=True)
    f = f.assign(confluence_factors=f["confluence_factors"].map(tuple))
    t = t.assign(confluence_factors=t["confluence_factors"].map(tuple))
    pd.testing.assert_frame_equal(f, t)
