"""tvws tests: framing, parsing, paging — no network."""

import pandas as pd

from sfp_reversion.data.tvws import _frame, _series_bars, _split_frames, fetch_history


def _update(bars: list[list]) -> str:
    return _frame(
        "timescale_update",
        ["s1", {"s1": {"s": [{"i": i, "v": b} for i, b in enumerate(bars)]}}],
    )


def _done() -> str:
    return _frame("series_completed", ["cs_x", "s1", "update"])


def test_frame_roundtrip() -> None:
    raw = _update([[100, 1.0, 1.1, 0.9, 1.05, 10.0]]) + _done()
    msgs = _split_frames(raw)
    assert [m["m"] for m in msgs] == ["timescale_update", "series_completed"]
    assert _series_bars(msgs[0]) == [[100, 1.0, 1.1, 0.9, 1.05, 10.0]]


class _FakeSession:
    def __init__(self, batches: list[list[list]]) -> None:
        self.batches = batches
        self.requests = 0

    def connect(self) -> None:
        pass

    def close(self) -> None:
        pass

    def open_series(self, *args) -> None:
        pass

    def request_more(self, n: int) -> None:
        self.requests += 1

    def recv_batch(self):
        if self.requests < len(self.batches):
            return self.batches[self.requests], True
        return [], True


def test_paging_merges_dedupes_and_filters() -> None:
    recent = [[300, 1.3, 1.4, 1.2, 1.35, 5.0], [200, 1.2, 1.3, 1.1, 1.25, 4.0]]
    older = [[200, 1.2, 1.3, 1.1, 1.25, 4.0], [100, 1.1, 1.2, 1.0, 1.15, 3.0]]
    sess = _FakeSession([recent, older, []])
    out = fetch_history(
        "OANDA:EURUSD",
        "60",
        start=pd.Timestamp("1970-01-01 00:02:30"),
        delay=0.0,
        session_factory=lambda: sess,
    )
    assert out["close"].tolist() == [1.25, 1.35]  # ts 100 filtered, dup 200 merged
    assert sess.requests == 1  # stopped once start was covered


def test_empty_feed_gives_empty_frame() -> None:
    out = fetch_history("X", "60", delay=0.0, session_factory=lambda: _FakeSession([[]]))
    assert out.empty
    assert list(out.columns) == ["open", "high", "low", "close", "volume"]
