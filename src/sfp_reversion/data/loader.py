"""Real OHLC ingestion: OANDA REST API + local parquet cache.

The cache is the source of truth after the first fetch: cached ranges are never
re-fetched, and a failed fetch degrades to cache with a warning.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import pandas as pd

from sfp_reversion.config import get_config
from sfp_reversion.data.schema import concat_ohlc, empty_ohlc, validate_ohlc

log = logging.getLogger(__name__)

_DATE_FMT = "%Y-%m-%dT%H:%M:%S"
_PAGE_SIZE = 5000  # OANDA max candles per request

_GRANULARITY_STEP = {
    "M1": pd.Timedelta(minutes=1),
    "M5": pd.Timedelta(minutes=5),
    "M15": pd.Timedelta(minutes=15),
    "H1": pd.Timedelta(hours=1),
    "H4": pd.Timedelta(hours=4),
    "D": pd.Timedelta(days=1),
    "W": pd.Timedelta(weeks=1),
}


class CandleClient(Protocol):
    """Minimal surface the loader needs. Real and stub clients implement this."""

    def candles(
        self, pair: str, granularity: str, price: str, start: str, end: str
    ) -> pd.DataFrame: ...


def cache_path(cache_dir: Path, pair: str, granularity: str) -> Path:
    return cache_dir / f"{pair}_{granularity}.parquet"


def load_ohlc(
    pair: str,
    start: datetime | None = None,
    end: datetime | None = None,
    client: CandleClient | None = None,
    cache_dir: Path | None = None,
) -> pd.DataFrame:
    """Load OHLC for ``pair`` within ``[start, end]`` (UTC) via cache-first OANDA fetch."""
    cfg = get_config()
    granularity = cfg.get("data.oanda.granularity", "D")
    price = cfg.get("data.oanda.price", "M")
    cache_dir = cache_dir or Path(cfg.get("data.cache_dir", "data/cache"))
    path = cache_path(cache_dir, pair, granularity)

    cached = _read_cache(path) if path.exists() else empty_ohlc()
    # credential/config errors raise directly; only fetch failures fall back to cache
    resolved_client = client if client is not None else _oanda_client()
    try:
        fetched = _fetch_range(resolved_client, pair, granularity, price, start, end)
    except Exception as exc:
        if cached.empty:
            raise RuntimeError(f"OANDA fetch failed and no cache at {path}: {exc}") from exc
        log.warning("OANDA fetch failed (%s); using cached data only", exc)
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


def _as_utc(ts: datetime) -> pd.Timestamp:
    t = pd.Timestamp(ts)
    return t.tz_localize("UTC") if t.tz is None else t.tz_convert("UTC")


def _read_cache(path: Path) -> pd.DataFrame:
    try:
        return pd.read_parquet(path)
    except Exception:
        log.warning("Corrupt cache %s; refetching", path)
        path.unlink(missing_ok=True)
        return empty_ohlc()


def _oanda_client() -> CandleClient:
    from oandapyV20 import API  # lazy: unit tests with stubs need no network libs
    from oandapyV20.endpoints import instruments as instr
    from oandapyV20.exceptions import V20Error

    cfg = get_config()
    token = cfg.get("data.oanda.token", "")
    if not token:
        raise RuntimeError(
            "OANDA token not configured; export SFP_OANDA_TOKEN "
            "(and SFP_OANDA_ACCOUNT_ID for account-scoped calls)"
        )
    environment = cfg.get("data.oanda.environment", "practice")
    return _OandaClient(API(access_token=token, environment=environment), instr, V20Error)


class _OandaClient:
    def __init__(self, api: Any, instruments: Any, v20_error: type[Exception]) -> None:
        self.api = api
        self._instruments = instruments
        self._v20_error = v20_error

    def candles(
        self, pair: str, granularity: str, price: str, start: str, end: str
    ) -> pd.DataFrame:
        params = {"granularity": granularity, "price": price, "from": start, "to": end}
        req = self._instruments.InstrumentsCandles(instrument=pair, params=params)
        try:
            self.api.request(req)
        except self._v20_error as exc:
            raise RuntimeError(f"OANDA request failed: {exc}") from exc
        rows: list[dict[str, Any]] = []
        for c in req.response.get("candles", []):
            if not c.get("complete", False):
                continue
            mid = c.get("mid", {})
            rows.append(
                {
                    "timestamp": pd.Timestamp(c["time"]).tz_convert("UTC"),
                    "open": float(mid["o"]),
                    "high": float(mid["h"]),
                    "low": float(mid["l"]),
                    "close": float(mid["c"]),
                    "volume": float(c.get("volume", 0.0)),
                }
            )
        if not rows:
            return empty_ohlc()
        return pd.DataFrame(rows).set_index("timestamp")


def _fetch_range(
    client: CandleClient,
    pair: str,
    granularity: str,
    price: str,
    start: datetime | None,
    end: datetime | None,
) -> pd.DataFrame:
    """Forward-page the full range in 5000-candle requests (OANDA max)."""
    if granularity not in _GRANULARITY_STEP:
        raise ValueError(f"Unsupported granularity: {granularity}")
    step = _GRANULARITY_STEP[granularity]
    end_ts = (end or datetime.now(UTC)).astimezone(UTC)
    start_ts = (start or end_ts - pd.Timedelta(days=3650)).astimezone(UTC)
    parts: list[pd.DataFrame] = []
    cursor = start_ts
    while cursor < end_ts:
        page = client.candles(
            pair, granularity, price, cursor.strftime(_DATE_FMT), end_ts.strftime(_DATE_FMT)
        )
        if page.empty:
            break
        parts.append(page)
        latest = page.index.max().to_pydatetime().astimezone(UTC)
        if len(page) < _PAGE_SIZE or latest >= end_ts - step:
            break
        cursor = latest + step
    if not parts:
        return empty_ohlc()
    return concat_ohlc(parts)
