"""Setup A backtest tests: market fills, stop-first exits, warning exit, costs."""

import pandas as pd
import pytest

from sfp_reversion.backtest.engine import BacktestParams, run_backtest
from sfp_reversion.data.schema import validate_ohlc

FREE = BacktestParams(
    spread_pips=0.0, slippage_pips=0.0, risk_per_trade_pct=1.0, min_equity=10000.0
)


def _frame(rows: list[tuple[float, float, float, float]]) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=len(rows), freq="D", tz="UTC")
    df = pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=idx)
    df["volume"] = 0.0
    df.index.name = "timestamp"
    return validate_ohlc(df)


def _sig(
    ts: pd.Timestamp,
    direction: str,
    stop: float,
    target: float,
    sweep_extreme: float | None = None,
) -> pd.DataFrame:
    row: dict = {
        "timestamp": ts,
        "direction": direction,
        "entry_price": 0.0,  # reference only: engine fills at next open
        "stop_price": stop,
        "target_price": target,
    }
    if sweep_extreme is not None:
        row["sweep_extreme"] = sweep_extreme
    return pd.DataFrame([row])


def test_market_fill_at_next_open_with_exact_pnl() -> None:
    df = _frame(
        [
            (1.1000, 1.1010, 1.0990, 1.1000),  # signal bar
            (1.1000, 1.1120, 1.0990, 1.1110),  # entry 1.10, target 1.11 hit
            (1.1110, 1.1120, 1.1100, 1.1110),
        ]
    )
    res = run_backtest(df, _sig(df.index[0], "long", 1.0950, 1.1100), FREE)
    assert len(res.trades_df) == 1
    t = res.trades_df.iloc[0]
    assert t["entry_price"] == 1.1000
    assert t["exit_reason"] == "target"
    # risk 0.005 -> 20000 units; reward 0.01 -> pnl 200
    assert t["units"] == pytest.approx(20000.0)
    assert t["pnl"] == pytest.approx(200.0)


def test_stop_wins_same_bar_ambiguity() -> None:
    df = _frame(
        [
            (1.1000, 1.1010, 1.0990, 1.1000),
            (1.1000, 1.1150, 1.0900, 1.1120),  # touches both: stop first
            (1.1120, 1.1130, 1.1110, 1.1120),
        ]
    )
    res = run_backtest(df, _sig(df.index[0], "long", 1.0950, 1.1100), FREE)
    t = res.trades_df.iloc[0]
    assert t["exit_reason"] == "stop"
    assert t["pnl"] == pytest.approx(-100.0)  # -0.005 x 20000 units


def test_warning_exit_on_close_through_extreme() -> None:
    df = _frame(
        [
            (1.1000, 1.1010, 1.0980, 1.1005),  # signal bar
            (1.1005, 1.1020, 1.0995, 1.1010),  # entry, nothing hit
            (1.1010, 1.1015, 1.0996, 1.0985),  # close < sweep extreme 1.0990? no...
            (1.0985, 1.0990, 1.0970, 1.0975),  # close 1.0975 < 1.0980 extreme
        ]
    )
    sig = _sig(df.index[0], "long", 1.0940, 1.1100, sweep_extreme=1.0980)
    res = run_backtest(df, sig, FREE)
    t = res.trades_df.iloc[0]
    assert t["exit_reason"] == "warning"
    assert t["exit_ts"] == df.index[3]


def test_no_warning_without_sweep_extreme() -> None:
    df = _frame(
        [
            (1.1000, 1.1010, 1.0980, 1.1005),
            (1.1005, 1.1020, 1.0995, 1.1010),
            (1.1010, 1.1015, 1.0996, 1.0975),  # would warn, but no extreme carried
            (1.0975, 1.0980, 1.0970, 1.0978),
        ]
    )
    sig = _sig(df.index[0], "long", 1.0940, 1.1100)
    res = run_backtest(df, sig, FREE, max_hold_bars=120)
    assert res.trades_df.iloc[0]["exit_reason"] != "warning"


def test_costs_shift_fill_against_trader() -> None:
    pricey = BacktestParams(
        spread_pips=10.0,
        slippage_pips=0.0,
        pip_size=0.0001,
        risk_per_trade_pct=1.0,
        min_equity=10000.0,
    )
    df = _frame(
        [
            (1.1000, 1.1010, 1.0990, 1.1000),
            (1.1000, 1.1120, 1.0990, 1.1110),
            (1.1110, 1.1120, 1.1100, 1.1110),
        ]
    )
    res = run_backtest(df, _sig(df.index[0], "long", 1.0950, 1.1100), pricey)
    t = res.trades_df.iloc[0]
    assert t["entry_price"] == 1.1010  # open + 10-pip cost
    assert t["pnl"] < 200.0


def test_one_position_at_a_time() -> None:
    df = _frame(
        [
            (1.1000, 1.1010, 1.0990, 1.1000),
            (1.1000, 1.1010, 1.0990, 1.1000),
            (1.1000, 1.1120, 1.0990, 1.1110),
            (1.1110, 1.1120, 1.1100, 1.1110),
        ]
    )
    sigs = pd.concat(
        [_sig(df.index[0], "long", 1.0950, 1.1100), _sig(df.index[0], "short", 1.1050, 1.0900)]
    )
    res = run_backtest(df, sigs, FREE)
    assert len(res.trades_df) == 1
    assert res.trades_df.iloc[0]["direction"] == "long"
