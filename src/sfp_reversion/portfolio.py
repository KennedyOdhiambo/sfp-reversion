"""Multi-asset portfolio: one universe, pooled trades, shared equity.

Each instrument is signaled and backtested standalone at fixed fractional risk
(1% of ``starting_equity`` per trade, so every trade risks the same dollars and
R multiples stay comparable). Portfolio equity = starting equity + cumulative
realized PnL by exit time. No cross-asset capital allocation yet — that is an
explicit v2 item, not a hidden assumption.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from sfp_reversion.backtest.engine import BacktestParams, run_backtest
from sfp_reversion.report.metrics_table import metrics_table
from sfp_reversion.signals.decision_tree import DecisionTreeParams, generate_signals
from sfp_reversion.validation.significance import significance_report


@dataclass
class PortfolioResult:
    trades_df: pd.DataFrame  # all trades, with symbol + r_multiple
    equity_curve: pd.Series
    symbol_metrics: pd.DataFrame
    portfolio_metrics: pd.DataFrame
    significance: dict


def run_portfolio(
    frames: dict[str, tuple[pd.DataFrame, pd.DataFrame]],
    signal_params: DecisionTreeParams | None = None,
    backtest_params: BacktestParams | None = None,
    starting_equity: float = 10000.0,
) -> PortfolioResult:
    signal_params = signal_params or DecisionTreeParams.from_config()
    backtest_params = backtest_params or BacktestParams.from_config()
    per_symbol: dict[str, pd.DataFrame] = {}
    for symbol, (hourly, daily) in frames.items():
        sig = generate_signals(hourly, daily, signal_params)
        res = run_backtest(hourly, sig, backtest_params)
        trades = res.trades_df.copy()
        trades["symbol"] = symbol
        per_symbol[symbol] = trades
    trades_df = combine_trades(per_symbol)
    equity_curve = portfolio_equity(trades_df, starting_equity)
    sym_rows = []
    for symbol, trades in per_symbol.items():
        curve = portfolio_equity(trades, starting_equity)
        m = metrics_table(trades, curve, starting_equity).set_index("metric")["value"]
        sym_rows.append({"symbol": symbol, **m.to_dict()})
    symbol_metrics = pd.DataFrame(sym_rows)
    portfolio_metrics = metrics_table(trades_df, equity_curve, starting_equity)
    if trades_df.empty:
        significance: dict = {
            "n": 0.0,
            "sharpe": 0.0,
            "ci_low": 0.0,
            "ci_high": 0.0,
            "deflated_psr": 0.0,
            "enough_data": False,
        }
    else:
        daily_returns = equity_curve.resample("D").last().ffill().pct_change().dropna()
        significance = significance_report(daily_returns)
    return PortfolioResult(trades_df, equity_curve, symbol_metrics, portfolio_metrics, significance)


def combine_trades(per_symbol: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Pool per-symbol trades: R multiple per trade, sorted by exit time."""
    parts = []
    for symbol, trades in per_symbol.items():
        if trades.empty:
            continue
        t = trades.copy()
        t["symbol"] = symbol
        risk = (t["entry_price"] - t["stop_price"]).abs()
        signed = t.apply(
            lambda r: (
                (r["exit_price"] - r["entry_price"]) * (1.0 if r["direction"] == "long" else -1.0)
            ),
            axis=1,
        )
        t["r_multiple"] = (signed / risk.replace(0.0, float("nan"))).fillna(0.0)
        parts.append(t)
    if not parts:
        return pd.DataFrame()
    out = pd.concat(parts, ignore_index=True)
    return out.sort_values("exit_ts").reset_index(drop=True)


def portfolio_equity(trades_df: pd.DataFrame, starting_equity: float) -> pd.Series:
    """Step equity curve from realized PnL ordered by exit time."""
    if trades_df.empty:
        return pd.Series([starting_equity])
    ordered = trades_df.sort_values("exit_ts")
    curve = pd.Series(
        starting_equity + ordered["pnl"].to_numpy().cumsum(),
        index=pd.DatetimeIndex(ordered["exit_ts"]),
    )
    curve.name = "equity"
    return curve
