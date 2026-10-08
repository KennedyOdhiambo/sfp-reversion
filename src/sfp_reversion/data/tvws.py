"""TradingView websocket feed, scraped directly (no third-party client).

Same feed the charts use, same keyless access — but with history paging:
after the first window, ``request_more_data`` walks further back until the
server sends nothing new. One 5000-bar chunk per request; a 3y H1 pull is a
handful of requests.
"""

from __future__ import annotations

import json
import logging
import random
import string
import time
from datetime import UTC, datetime

import pandas as pd
from websocket import create_connection

log = logging.getLogger(__name__)

WS_URL = "wss://data.tradingview.com/socket.io/websocket?from=chart%2F&type=chart"
WS_HEADERS = json.dumps(
    {
        "Origin": "https://www.tradingview.com",
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
        ),
    }
)
CHUNK = 5000


def _session(prefix: str) -> str:
    return prefix + "".join(random.choice(string.ascii_lowercase) for _ in range(12))


def _frame(func: str, params: list) -> str:
    body = json.dumps({"m": func, "p": params}, separators=(",", ":"))
    return f"~m~{len(body)}~m~{body}"


def _split_frames(raw: str) -> list[dict]:
    """Split a concatenated ~m~ payload into parsed messages."""
    out = []
    for part in raw.split("~m~"):
        part = part.strip()
        if not part or part[0].isdigit():
            continue
        try:
            out.append(json.loads(part))
        except json.JSONDecodeError:
            continue
    return out


def _series_bars(msg: dict) -> list[list]:
    """Pull [[ts, o, h, l, c, v], ...] out of a timescale_update message."""
    try:
        series = msg["p"][1]
        block = series.get("s1", series.get("sds_1", {}))
        return [e["v"] for e in block["s"]]
    except (KeyError, IndexError, TypeError, AttributeError):
        return []


def _is_done(msg: dict) -> bool:
    return msg.get("m") == "series_completed"


class ChartSession:
    """One websocket chart session: open, page back, close."""

    def __init__(self, timeout: int = 10) -> None:
        self.timeout = timeout
        self.ws = None
        self.cs = _session("cs_")

    def connect(self) -> None:
        self.ws = create_connection(WS_URL, headers=WS_HEADERS, timeout=self.timeout)

    def close(self) -> None:
        try:
            if self.ws:
                self.ws.close()
        except Exception:
            pass
        self.ws = None

    def _send(self, func: str, params: list) -> None:
        assert self.ws is not None
        self.ws.send(_frame(func, params))

    def open_series(self, symbol: str, interval: str, n_bars: int = CHUNK) -> None:
        self._send("set_auth_token", ["unauthorized_user_token"])
        self._send("chart_create_session", [self.cs, ""])
        self._send(
            "resolve_symbol",
            [self.cs, "symbol_1", f'={{"symbol":"{symbol}","adjustment":"splits"}}'],
        )
        self._send("create_series", [self.cs, "s1", "s1", "symbol_1", interval, n_bars])
        self._send("switch_timezone", [self.cs, "exchange"])

    def request_more(self, n_bars: int = CHUNK) -> None:
        self._send("request_more_data", [self.cs, "s1", n_bars])

    def recv_batch(self) -> tuple[list[list], bool]:
        """Next batch of bars; True when the server completed this window."""
        bars: list[list] = []
        assert self.ws is not None
        while True:
            try:
                raw = self.ws.recv()
            except Exception as exc:
                log.warning("TV websocket recv failed: %s", exc)
                return bars, True
            for msg in _split_frames(raw):
                bars.extend(_series_bars(msg))
                if _is_done(msg):
                    return bars, True


def fetch_history(
    symbol: str,
    interval: str,
    start: datetime | None = None,
    chunk: int = CHUNK,
    max_chunks: int = 12,
    delay: float = 0.5,
    session_factory=ChartSession,
) -> pd.DataFrame:
    """Newest-first paging back to ``start`` (or exhaustion). UTC-naive index."""
    start_ts = start.timestamp() if start is not None else None
    seen: dict[int, list] = {}
    session = session_factory()
    try:
        session.connect()
        session.open_series(symbol, interval, chunk)
        for _ in range(max_chunks):
            bars, _ = session.recv_batch()
            new = 0
            for b in bars:
                ts = int(b[0])
                if ts not in seen:
                    seen[ts] = b
                    new += 1
            if not seen:
                break
            earliest = min(seen)
            if new == 0 or (start_ts is not None and earliest <= start_ts):
                break
            if delay > 0:
                time.sleep(delay)
            session.request_more(chunk)
    finally:
        session.close()
    if not seen:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    rows = [seen[ts] for ts in sorted(seen)]
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"])
    df["ts"] = pd.to_datetime(df["ts"], unit="s")
    out = df.set_index("ts").sort_index()[["open", "high", "low", "close", "volume"]]
    out.index.name = "timestamp"
    if start_ts is not None:
        out = out[out.index >= pd.Timestamp(start_ts, unit="s")]
    return out


def to_utc(df: pd.DataFrame) -> pd.DataFrame:
    """TV sends UTC seconds: stamp the index as UTC."""
    out = df.copy()
    out.index = pd.DatetimeIndex(out.index, tz="UTC")
    out.index.name = "timestamp"
    return out
