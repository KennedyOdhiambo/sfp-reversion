"""Portfolio tests: pooling math on hand-made trades (no network)."""

import pandas as pd

from sfp_reversion.portfolio import combine_trades, portfolio_equity, run_portfolio


def _trades(pnls: list[float], start: str, direction: str = "long") -> pd.DataFrame:
    idx = pd.date_range(start, periods=len(pnls), freq="D", tz="UTC")
    return pd.DataFrame(
        {
            "signal_ts": idx,
            "entry_ts": idx,
            "exit_ts": idx,
            "direction": direction,
            "entry_price": 1.10,
            "exit_price": [1.10 + (0.01 if p > 0 else -0.01) for p in pnls],
            "stop_price": 1.09,
            "target_price": 1.12,
            "units": 10000.0,
            "pnl": pnls,
            "exit_reason": "target",
        }
    )


def test_combine_adds_r_and_sorts() -> None:
    out = combine_trades(
        {"A": _trades([100.0, -50.0], "2024-01-01"), "B": _trades([200.0], "2024-01-03")}
    )
    assert list(out["symbol"][:2]) == ["A", "A"]
    assert out["symbol"].iloc[2] == "B"
    # risk_dist = |1.10-1.09| = 0.01; signed move 0.01 -> R = +1, -1
    assert out["r_multiple"].round(6).tolist() == [1.0, -1.0, 1.0]


def test_portfolio_equity_cumsum() -> None:
    out = combine_trades({"A": _trades([100.0, -50.0], "2024-01-01")})
    curve = portfolio_equity(out, 10000.0)
    assert curve.tolist() == [10100.0, 10050.0]
    assert portfolio_equity(pd.DataFrame(), 10000.0).tolist() == [10000.0]


def test_run_portfolio_empty_frames() -> None:
    res = run_portfolio({})
    assert res.trades_df.empty
    assert res.portfolio_metrics.set_index("metric").loc["n_trades", "value"] == 0.0
