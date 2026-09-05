"""Real OHLC ingestion: Yahoo Finance chart API + local parquet cache.

Keyless and global. The cache is the source of truth after the first fetch:
cached ranges are never re-fetched, and a failed fetch degrades to cache.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from sfp_reversion.config import get_config
from sfp_reversion.data.schema import concat_ohlc, empty_ohlc, validate_ohlc

log = logging.getLogger(__name__)

_UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
_INTERVALS = {"D": "1d", "W": "1wk", "M": "1mo", "H1": "1h"}

Fetcher = Callable[[str, str, datetime | None, datetime | None], pd.DataFrame]


def yahoo_symbol(pair: str) -> str:
    """Map our pair (EUR_USD) to a Yahoo symbol (EURUSD=X)."""
    overrides = get_config().get("data.yahoo.symbols", {})
    if pair in overrides:
        return str(overrides[pair])
    base, sep, quote = pair.upper().partition("_")
    if not sep or not quote:
        raise ValueError(f"Pair must look like EUR_USD, got {pair!r}")
    return f"{base}{quote}=X"


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
    granularity = granularity or str(get_config().get("data.yahoo.granularity", "D"))
    cache_dir = cache_dir or Path(get_config().get("data.cache_dir", "data/cache"))
    path = cache_path(cache_dir, pair, granularity)

    cached = _read_cache(path) if path.exists() else empty_ohlc()
    try:
        fetched = (fetcher or fetch_yahoo)(yahoo_symbol(pair), granularity, start, end)
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


def fetch_yahoo(
    symbol: str,
    granularity: str,
    start: datetime | None,
    end: datetime | None,
) -> pd.DataFrame:
    """One bulk request for the full range (daily history goes back to ~2003)."""
    if granularity not in _INTERVALS:
        raise ValueError(f"Unsupported granularity: {granularity}")
    end_ts = (end or datetime.now(UTC)).astimezone(UTC)
    start_ts = (start or datetime(1970, 1, 1, tzinfo=UTC)).astimezone(UTC)
    resp = requests.get(
        f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
        params={
            "interval": _INTERVALS[granularity],
            "period1": int(start_ts.timestamp()),
            "period2": int(end_ts.timestamp()),
        },
        headers=_UA,
        timeout=30,
    )
    resp.raise_for_status()
    return _parse_yahoo(resp.json())


def _parse_yahoo(payload: dict[str, Any]) -> pd.DataFrame:
    results = (payload.get("chart") or {}).get("result") or []
    if not results:
        raise RuntimeError(f"Yahoo returned no data: {(payload.get('chart') or {}).get('error')}")
    res = results[0]
    quote = ((res.get("indicators") or {}).get("quote") or [{}])[0]
    frame = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(res.get("timestamp") or [], unit="s", utc=True),
            "open": quote.get("open"),
            "high": quote.get("high"),
            "low": quote.get("low"),
            "close": quote.get("close"),
            "volume": quote.get("volume"),
        }
    )
    frame = frame.dropna(subset=["open", "high", "low", "close"])
    frame["volume"] = pd.to_numeric(frame["volume"], errors="coerce").fillna(0.0)
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
