"""Phase 11 tests: hand-worked fills, exits, costs, sizing."""

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
    ts: pd.Timestamp, direction: str, limit: float, stop: float, target: float
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "timestamp": ts,
                "direction": direction,
                "limit_price": limit,
                "stop_price": stop,
                "target_price": target,
            }
        ]
    )


def test_target_and_stop_with_exact_pnl() -> None:
    df = _frame(
        [
            (1.1000, 1.1010, 1.0990, 1.1000),  # 0: signal bar
            (1.0990, 1.1010, 1.0980, 1.1005),  # 1: fills long @ 1.0990
            (1.1010, 1.1120, 1.1000, 1.1110),  # 2: target 1.11
            (1.1090, 1.1095, 1.1070, 1.1080),  # 3: signal bar (flat after exit)
            (1.1090, 1.1095, 1.1070, 1.1080),  # 4: fills short @ 1.1090
            (1.1070, 1.1080, 1.0990, 1.1010),  # 5: target 1.10
        ]
    )
    signals = pd.concat(
        [
            _sig(df.index[0], "long", 1.1000, 1.0950, 1.1100),
            _sig(df.index[3], "short", 1.1080, 1.1120, 1.1000),
        ]
    )
    res = run_backtest(df, signals, FREE)
    assert len(res.trades_df) == 2

    long, short = res.trades_df.iloc[0], res.trades_df.iloc[1]
    assert long["entry_price"] == pytest.approx(1.0990)
    assert long["units"] == pytest.approx(100.0 / 0.004)  # 1% of 10k over 0.004 risk
    assert long["exit_price"] == pytest.approx(1.1100)
    assert long["pnl"] == pytest.approx(0.011 * 25000.0)
    assert long["exit_reason"] == "target"

    assert short["entry_price"] == pytest.approx(1.1090)
    assert short["units"] == pytest.approx(102.75 / 0.003)  # equity grew to 10275
    assert short["pnl"] == pytest.approx(0.009 * 34250.0)
    assert short["exit_reason"] == "target"
    assert res.equity_curve.iloc[-1] == pytest.approx(10000.0 + 275.0 + 308.25)


def test_costs_shift_the_fill() -> None:
    df = _frame(
        [
            (1.1000, 1.1010, 1.0990, 1.1000),
            (1.0990, 1.1010, 1.0980, 1.1005),
            (1.1010, 1.1010, 1.1010, 1.1010),
        ]
    )
    params = BacktestParams(spread_pips=2.0, slippage_pips=1.0, pip_size=0.0001)
    res = run_backtest(
        df, _sig(df.index[0], "long", 1.1000, 1.0900, 1.2000), params, max_hold_bars=1
    )
    assert res.trades_df.iloc[0]["entry_price"] == pytest.approx(1.0990 + 0.0003)


def test_stop_first_and_timeout() -> None:
    df = _frame(
        [
            (1.1000, 1.1010, 1.0990, 1.1000),  # 0: signal
            (1.0990, 1.1200, 1.0900, 1.1100),  # 1: fills; spans stop AND target
            (1.1100, 1.1110, 1.1090, 1.1100),  # 2: filler
        ]
    )
    res = run_backtest(df, _sig(df.index[0], "long", 1.1000, 1.0950, 1.1100), FREE)
    assert res.trades_df.iloc[0]["exit_reason"] == "stop"  # worst-case priority
    assert res.trades_df.iloc[0]["exit_price"] == pytest.approx(1.0950)

    res = run_backtest(df, _sig(df.index[0], "long", 1.1000, 1.0800, 1.2000), FREE, max_hold_bars=1)
    assert res.trades_df.iloc[0]["exit_reason"] == "timeout"
    assert res.trades_df.iloc[0]["exit_ts"] == df.index[2]


def test_no_fill_no_trade_and_single_position() -> None:
    df = _frame(
        [
            (1.1000, 1.1010, 1.0990, 1.1000),
            (1.1050, 1.1060, 1.1040, 1.1050),  # never touches 1.10 limit
            (1.1050, 1.1060, 1.1040, 1.1050),
        ]
    )
    res = run_backtest(df, _sig(df.index[0], "long", 1.1000, 1.0900, 1.2000), FREE)
    assert res.trades_df.empty
    assert (res.equity_curve == 10000.0).all()

    df2 = _frame(
        [
            (1.1000, 1.1010, 1.0990, 1.1000),  # 0: signal 1
            (1.0990, 1.1010, 1.0980, 1.1005),  # 1: fills; signal 2 ignored
            (1.1000, 1.1010, 1.0990, 1.1000),  # 2: still open
            (1.1000, 1.1010, 1.0990, 1.1000),  # 3: timeout close
        ]
    )
    two = pd.concat(
        [
            _sig(df2.index[0], "long", 1.1000, 1.0800, 1.2000),
            _sig(df2.index[1], "long", 1.1000, 1.0800, 1.2000),
        ]
    )
    res = run_backtest(df2, two, FREE, max_hold_bars=2)
    assert len(res.trades_df) == 1
