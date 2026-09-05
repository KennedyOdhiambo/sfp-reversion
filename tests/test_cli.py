"""Phase 15 tests: CLI commands on stubbed data (no network)."""

import pandas as pd
import pytest

import sfp_reversion.cli as cli
from sfp_reversion.cli import main
from sfp_reversion.data.schema import validate_ohlc


def _frame(n: int = 60, start: str = "2024-01-01", freq: str = "h") -> pd.DataFrame:
    idx = pd.date_range(start, periods=n, freq=freq, tz="UTC")
    close = 1.10 + 0.0005 * pd.Series(range(n)).to_numpy()
    df = pd.DataFrame(
        {"open": close, "high": close + 0.002, "low": close - 0.002, "close": close, "volume": 0.0},
        index=idx,
    )
    df.index.name = "timestamp"
    return validate_ohlc(df)


@pytest.fixture
def stubbed(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    def fake_load(pair: str, start=None, end=None, fetcher=None, cache_dir=None, granularity=None):
        return _frame(60) if granularity == "H1" else _frame(60, freq="D")

    monkeypatch.setattr(cli, "load_ohlc", fake_load)
    monkeypatch.chdir(tmp_path)


def test_fetch(stubbed: None, capsys: pytest.CaptureFixture) -> None:
    assert main(["fetch", "EUR_USD"]) == 0
    assert "60 bars" in capsys.readouterr().out


def test_signals(stubbed: None, capsys: pytest.CaptureFixture) -> None:
    assert main(["signals", "EUR_USD", "--out", "sig.csv"]) == 0
    assert "signals" in capsys.readouterr().out


def test_backtest(stubbed: None, capsys: pytest.CaptureFixture) -> None:
    assert main(["backtest", "EUR_USD", "--n-baseline", "2", "--out-dir", "rep"]) == 0
    out = capsys.readouterr().out
    assert "n_trades" in out and ("PASS" in out or "FAIL" in out)


def test_validate_sweep(stubbed: None, capsys: pytest.CaptureFixture) -> None:
    assert (
        main(
            ["validate", "EUR_USD", "--parameter", "touch_tolerance_atr", "--values", "0.1", "0.2"]
        )
        == 0
    )
    assert "touch_tolerance_atr=" in capsys.readouterr().out


def test_validate_windows(stubbed: None, capsys: pytest.CaptureFixture) -> None:
    rc = main(["validate", "EUR_USD", "--is-years", "0.05", "--oos-years", "0.02"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "pnl=" in out or "no walk-forward" in out
