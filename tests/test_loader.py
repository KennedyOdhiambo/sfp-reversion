"""Phase 2 tests: loader caching/slicing plus TradingView parsing — no network."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from sfp_reversion.data.loader import _parse_tradingview, cache_path, load_ohlc, tv_symbol
from sfp_reversion.data.schema import empty_ohlc


def _bars(start: str, n: int, price: float = 1.1) -> pd.DataFrame:
    idx = pd.date_range(start, periods=n, freq="D", tz="UTC")
    return pd.DataFrame(
        {
            "open": price,
            "high": price + 0.01,
            "low": price - 0.01,
            "close": price,
            "volume": 0.0,
        },
        index=idx,
    )


def _stub(
    frame: pd.DataFrame,
) -> Any:
    def fetch(symbol: str, granularity: str, start: Any, end: Any) -> pd.DataFrame:
        return frame

    return fetch


def _failing(symbol: str, granularity: str, start: Any, end: Any) -> pd.DataFrame:
    raise ConnectionError("network down")


def _dt(day: int) -> datetime:
    return datetime(2024, 1, day, tzinfo=UTC)


def test_fetch_caches_and_reloads(tmp_path: Path) -> None:
    first = load_ohlc(
        "EUR_USD", _dt(1), _dt(5), fetcher=_stub(_bars("2024-01-01", 5)), cache_dir=tmp_path
    )
    assert len(first) == 5
    assert cache_path(tmp_path, "EUR_USD", "D").exists()

    second = load_ohlc("EUR_USD", _dt(1), _dt(5), fetcher=_failing, cache_dir=tmp_path)
    pd.testing.assert_frame_equal(first, second)


def test_slices_to_requested_window(tmp_path: Path) -> None:
    out = load_ohlc(
        "EUR_USD", _dt(2), _dt(4), fetcher=_stub(_bars("2024-01-01", 5)), cache_dir=tmp_path
    )
    assert out.index.min() == pd.Timestamp("2024-01-02", tz="UTC")
    assert out.index.max() == pd.Timestamp("2024-01-04", tz="UTC")


def test_merges_new_bars_into_cache(tmp_path: Path) -> None:
    load_ohlc("EUR_USD", _dt(1), _dt(3), fetcher=_stub(_bars("2024-01-01", 3)), cache_dir=tmp_path)
    out = load_ohlc(
        "EUR_USD",
        _dt(1),
        _dt(5),
        fetcher=_stub(_bars("2024-01-04", 2, price=1.2)),
        cache_dir=tmp_path,
    )
    assert len(out) == 5
    assert out["close"].iloc[-1] == 1.2


def test_no_cache_and_failed_fetch_raises(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="no cache"):
        load_ohlc("EUR_USD", _dt(1), _dt(5), fetcher=_failing, cache_dir=tmp_path)


def test_corrupt_cache_is_rebuilt(tmp_path: Path) -> None:
    bad = cache_path(tmp_path, "EUR_USD", "D")
    bad.parent.mkdir(parents=True, exist_ok=True)
    bad.write_text("not a parquet file")
    out = load_ohlc(
        "EUR_USD", _dt(1), _dt(3), fetcher=_stub(_bars("2024-01-01", 3)), cache_dir=tmp_path
    )
    assert len(out) == 3


def test_symbol_mapping_defaults_and_overrides() -> None:
    assert tv_symbol("EUR_USD") == ("EURUSD", "OANDA")
    assert tv_symbol("USD_JPY") == ("USDJPY", "OANDA")
    with pytest.raises(ValueError, match="EUR_USD"):
        tv_symbol("EURUSD")


def test_parse_tradingview_frame() -> None:
    raw = pd.DataFrame(
        {
            "symbol": ["OANDA:EURUSD"] * 3,
            "open": [1.10, 1.11, None],
            "high": [1.11, 1.12, 1.13],
            "low": [1.09, 1.10, 1.11],
            "close": [1.105, 1.115, 1.12],
            "volume": [100.0, 200.0, 300.0],
        },
        index=pd.DatetimeIndex(["2024-01-01", "2024-01-02", "2024-01-03"]),
    )
    out = _parse_tradingview(raw)
    assert len(out) == 2  # null-OHLC row dropped
    assert str(out.index.tz) == "UTC"
    assert out["volume"].iloc[0] == 100.0


def test_granularity_override_uses_separate_cache(tmp_path: Path) -> None:
    out = load_ohlc(
        "EUR_USD",
        _dt(1),
        _dt(3),
        fetcher=_stub(_bars("2024-01-01", 3)),
        cache_dir=tmp_path,
        granularity="H1",
    )
    assert len(out) == 3
    assert cache_path(tmp_path, "EUR_USD", "H1").exists()
    assert not cache_path(tmp_path, "EUR_USD", "D").exists()


def test_empty_frame_helper() -> None:
    assert empty_ohlc().empty
