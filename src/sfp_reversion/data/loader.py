"""Real OHLC ingestion: TradingView feed + local parquet cache.

The cache is the source of truth after the first fetch: cached ranges are never
re-fetched, and a failed fetch degrades to cache.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from sfp_reversion.config import get_config
from sfp_reversion.data.schema import concat_ohlc, empty_ohlc, validate_ohlc

log = logging.getLogger(__name__)

_TVWS_INTERVALS = {"D": "1D", "W": "1W", "M": "1M", "H4": "4H", "H1": "1H", "M5": "5"}

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
    """Paged websocket history (own scraper): ~15mo H1 anonymously, Daily to 2007.

    Dates before the feed's reach simply return what's available; the cache
    merge keeps everything ever fetched.
    """
    if granularity not in _TVWS_INTERVALS:
        raise ValueError(f"Unsupported granularity for TradingView: {granularity}")
    from sfp_reversion.data.tvws import fetch_history, to_utc

    symbol, exchange = tv_symbol(pair)
    try:
        df = fetch_history(
            f"{exchange}:{symbol}", _TVWS_INTERVALS[granularity], start=start, delay=1.0
        )
    except Exception as exc:
        raise RuntimeError(f"TradingView fetch failed for {exchange}:{symbol}: {exc}") from exc
    if df.empty:
        return empty_ohlc()
    return validate_ohlc(to_utc(df))


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
