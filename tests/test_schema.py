"""Phase 1 tests: the schema accepts good frames and rejects bad ones."""

import pandas as pd
import pytest

from sfp_reversion.data.schema import concat_ohlc, empty_ohlc, validate_ohlc


def _frame(**overrides) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=3, freq="D", tz="UTC")
    data = {
        "open": [1.0, 1.1, 1.2],
        "high": [1.2, 1.3, 1.4],
        "low": [0.9, 1.0, 1.1],
        "close": [1.1, 1.2, 1.3],
        "volume": [100.0, 200.0, 300.0],
    }
    data.update(overrides)
    return pd.DataFrame(data, index=idx)


def test_valid_frame_passes() -> None:
    out = validate_ohlc(_frame())
    assert list(out.columns) == ["open", "high", "low", "close", "volume"]
    assert str(out.index.tz) == "UTC"
    assert out.index.name == "timestamp"


def test_naive_index_is_localized_to_utc() -> None:
    df = _frame()
    df.index = df.index.tz_localize(None)
    assert str(validate_ohlc(df).index.tz) == "UTC"


def test_rejects_non_datetime_index() -> None:
    with pytest.raises(ValueError, match="DatetimeIndex"):
        validate_ohlc(_frame().reset_index(drop=True))


def test_rejects_duplicate_timestamps() -> None:
    df = pd.concat([_frame(), _frame().iloc[[0]]])
    with pytest.raises(ValueError, match="duplicate"):
        validate_ohlc(df)


def test_rejects_missing_columns() -> None:
    with pytest.raises(ValueError, match="missing required"):
        validate_ohlc(_frame().drop(columns=["volume"]))


def test_rejects_high_below_low() -> None:
    with pytest.raises(ValueError, match="high < low"):
        validate_ohlc(_frame(high=[0.5, 0.5, 0.5]))


def test_concat_dedupes_first_wins() -> None:
    a, b = _frame(), _frame(close=[9.9, 9.9, 9.9])
    out = concat_ohlc([a, b])
    assert len(out) == 3
    assert out["close"].iloc[0] == 1.1


def test_empty_roundtrip() -> None:
    assert validate_ohlc(empty_ohlc()).empty
    assert concat_ohlc([]).empty
