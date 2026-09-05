"""Phase 2 tests: loader paging, caching, slicing — all against a stub client."""

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from sfp_reversion.data.loader import cache_path, load_ohlc
from sfp_reversion.data.schema import empty_ohlc


def _bars(start: str, n: int, price: float = 1.1) -> pd.DataFrame:
    idx = pd.date_range(start, periods=n, freq="D", tz="UTC")
    return pd.DataFrame(
        {
            "open": price,
            "high": price + 0.01,
            "low": price - 0.01,
            "close": price,
            "volume": 100.0,
        },
        index=idx,
    )


class StubClient:
    """Canned pages of candles; records calls so tests can assert paging."""

    def __init__(self, pages: list[pd.DataFrame]) -> None:
        self._pages = list(pages)
        self.calls = 0

    def candles(
        self, pair: str, granularity: str, price: str, start: str, end: str
    ) -> pd.DataFrame:
        self.calls += 1
        if self._pages:
            return self._pages.pop(0)
        return empty_ohlc()


class FailingClient:
    def candles(
        self, pair: str, granularity: str, price: str, start: str, end: str
    ) -> pd.DataFrame:
        raise ConnectionError("network down")


def _dt(day: int) -> datetime:
    return datetime(2024, 1, day, tzinfo=UTC)


def test_fetch_caches_and_reloads(tmp_path: Path) -> None:
    client = StubClient([_bars("2024-01-01", 5)])
    first = load_ohlc("EUR_USD", _dt(1), _dt(5), client=client, cache_dir=tmp_path)
    assert len(first) == 5
    assert cache_path(tmp_path, "EUR_USD", "D").exists()

    # second call hits cache only: failing network still returns data
    second = load_ohlc("EUR_USD", _dt(1), _dt(5), client=FailingClient(), cache_dir=tmp_path)
    pd.testing.assert_frame_equal(first, second)


def test_slices_to_requested_window(tmp_path: Path) -> None:
    out = load_ohlc(
        "EUR_USD", _dt(2), _dt(4), client=StubClient([_bars("2024-01-01", 5)]), cache_dir=tmp_path
    )
    assert out.index.min() == pd.Timestamp("2024-01-02", tz="UTC")
    assert out.index.max() == pd.Timestamp("2024-01-04", tz="UTC")


def test_merges_new_bars_into_cache(tmp_path: Path) -> None:
    load_ohlc(
        "EUR_USD", _dt(1), _dt(3), client=StubClient([_bars("2024-01-01", 3)]), cache_dir=tmp_path
    )
    out = load_ohlc(
        "EUR_USD",
        _dt(1),
        _dt(5),
        client=StubClient([_bars("2024-01-04", 2, price=1.2)]),
        cache_dir=tmp_path,
    )
    assert len(out) == 5
    assert out["close"].iloc[-1] == 1.2


def test_no_cache_and_failed_fetch_raises(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="no cache"):
        load_ohlc("EUR_USD", _dt(1), _dt(5), client=FailingClient(), cache_dir=tmp_path)


def test_corrupt_cache_is_rebuilt(tmp_path: Path) -> None:
    bad = cache_path(tmp_path, "EUR_USD", "D")
    bad.parent.mkdir(parents=True, exist_ok=True)
    bad.write_text("not a parquet file")
    out = load_ohlc(
        "EUR_USD", _dt(1), _dt(3), client=StubClient([_bars("2024-01-01", 3)]), cache_dir=tmp_path
    )
    assert len(out) == 3


def test_missing_token_gives_actionable_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("SFP_OANDA_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="SFP_OANDA_TOKEN"):
        load_ohlc("EUR_USD", _dt(1), _dt(5), client=None, cache_dir=tmp_path)
