"""Real OHLC ingestion: TradingView feed + local parquet cache.

The cache is the source of truth after the first fetch: cached ranges are never
re-fetched, and a failed fetch degrades to cache.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from sfp_reversion.config import get_config
from sfp_reversion.data.schema import concat_ohlc, empty_ohlc, validate_ohlc

log = logging.getLogger(__name__)

_TV_INTERVALS = {"D": "in_daily", "W": "in_weekly", "M": "in_monthly", "H4": "in_4_hour", "H1": "in_1_hour"}

Fetcher = Callable[[str, str, datetime | None, datetime | None], pd.DataFrame]


def tv_symbol(pair: str) -> tuple[str, str]:
    """Map our pair (EUR_USD) to a (TradingView symbol, exchange) tuple."""
    overrides = get_config().get("data.tradingview.symbols", {})
    if pair in overrides:
        sym, exch = overrides[pair]
        return str(sym), str(exch)
    base, sep, quote = pair.upper().partition("_")
    if not sep or not quote:
        raise ValueError(f"Pair must look like EUR_USD, got {pair!r}")
    return f"{base}{quote}", str(get_config().get("data.tradingview.exchange", "OANDA"))


def cache_path(cache_dir: Path, pair: str, granularity: str) -> Path:
    return cache_dir / f"{pair}_{granularity}.parquet"


def load_ohlc(
    pair: str,
    start: datetime | None = None,
    end: datetime | None = None,
    fetcher: Fetcher | None = None,
    cache_dir: Path | None = None,
    granularity: str | None = None,
) -> pd.DataFrame:
    """Load OHLC for ``pair`` within ``[start, end]`` (UTC) via cache-first fetch."""
    granularity = granularity or str(get_config().get("data.tradingview.granularity", "D"))
    cache_dir = cache_dir or Path(get_config().get("data.cache_dir", "data/cache"))
    path = cache_path(cache_dir, pair, granularity)

    cached = _read_cache(path) if path.exists() else empty_ohlc()
    try:
        fetched = (fetcher or fetch_tradingview)(pair, granularity, start, end)
    except Exception as exc:
        if cached.empty:
            raise RuntimeError(f"Fetch failed and no cache at {path}: {exc}") from exc
        log.warning("Fetch failed (%s); using cached data only", exc)
        fetched = empty_ohlc()

    if not fetched.empty:
        cache_dir.mkdir(parents=True, exist_ok=True)
        cached = concat_ohlc([cached, fetched])
        cached.to_parquet(path)

    out = validate_ohlc(cached)
    if start is not None:
        out = out[out.index >= _as_utc(start)]
    if end is not None:
        out = out[out.index <= _as_utc(end)]
    return out


def fetch_tradingview(
    pair: str,
    granularity: str,
    start: datetime | None,
    end: datetime | None,
) -> pd.DataFrame:
    """Newest 5000 bars per pull (D -> 2007, H4 -> 2023, H1 -> ~7mo), merged into cache.

    Unofficial websocket client; keyless for light use, or set TV_USERNAME /
    TV_PASSWORD for an authenticated session.
    """
    if granularity not in _TV_INTERVALS:
        raise ValueError(f"Unsupported granularity for TradingView: {granularity}")
    from tvDatafeed import Interval, TvDatafeed  # lazy: keeps imports light

    symbol, exchange = tv_symbol(pair)
    username, password = os.environ.get("TV_USERNAME"), os.environ.get("TV_PASSWORD")
    tv = TvDatafeed(username=username, password=password) if username else TvDatafeed()
    interval = getattr(Interval, _TV_INTERVALS[granularity])
    try:
        raw = tv.get_hist(symbol=symbol, exchange=exchange, interval=interval, n_bars=5000)
    except Exception as exc:
        raise RuntimeError(f"TradingView fetch failed for {exchange}:{symbol}: {exc}") from exc
    if raw is None or raw.empty:
        return empty_ohlc()
    return _parse_tradingview(raw)


def _parse_tradingview(raw: pd.DataFrame) -> pd.DataFrame:
    frame = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(raw.index, utc=True),
            "open": pd.to_numeric(raw["open"], errors="coerce"),
            "high": pd.to_numeric(raw["high"], errors="coerce"),
            "low": pd.to_numeric(raw["low"], errors="coerce"),
            "close": pd.to_numeric(raw["close"], errors="coerce"),
            "volume": pd.to_numeric(raw["volume"], errors="coerce").fillna(0.0),
        }
    )
    frame = frame.dropna(subset=["open", "high", "low", "close"])
    out = frame.set_index("timestamp").sort_index()[["open", "high", "low", "close", "volume"]]
    out.index.name = "timestamp"
    return validate_ohlc(out)


def _read_cache(path: Path) -> pd.DataFrame:
    try:
        return pd.read_parquet(path)
    except Exception:
        log.warning("Corrupt cache %s; refetching", path)
        path.unlink(missing_ok=True)
        return empty_ohlc()


def _as_utc(ts: datetime) -> pd.Timestamp:
    t = pd.Timestamp(ts)
    return t.tz_localize("UTC") if t.tz is None else t.tz_convert("UTC")
