"""Backtest engine (Phase 11): limit fills, stop/target exits, costs, sizing.

A signal at bar ``t`` executes from bar ``t+1``. Fills only if the execution
bar actually trades through the limit. Exits scan stop-first (worst-case for
same-bar ambiguity), then target, then a max-hold timeout at the close.
One position at a time; open-trade MTM is ignored in the equity curve.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from sfp_reversion.config import get_config


@dataclass
class BacktestParams:
    spread_pips: float = 1.0
    slippage_pips: float = 0.5
    pip_size: float = 0.0001
    risk_per_trade_pct: float = 1.0
    min_equity: float = 10000.0

    @classmethod
    def from_config(cls) -> BacktestParams:
        bt = get_config().section("backtest")
        return cls(
            spread_pips=float(bt.get("spread_pips", 1.0)),
            slippage_pips=float(bt.get("slippage_pips", 0.5)),
            pip_size=float(bt.get("pip_size", 0.0001)),
            risk_per_trade_pct=float(bt.get("risk_per_trade_pct", 1.0)),
            min_equity=float(bt.get("min_equity", 10000)),
        )


@dataclass
class BacktestResult:
    trades_df: pd.DataFrame
    equity_curve: pd.Series


def run_backtest(
    df: pd.DataFrame,
    signals: pd.DataFrame,
    params: BacktestParams | None = None,
    max_hold_bars: int = 120,
) -> BacktestResult:
    params = params or BacktestParams.from_config()
    empty_trades = pd.DataFrame(
        columns=[
            "signal_ts",
            "entry_ts",
            "exit_ts",
            "direction",
            "entry_price",
            "exit_price",
            "stop_price",
            "target_price",
            "units",
            "pnl",
            "exit_reason",
        ]
    )
    if signals.empty:
        return BacktestResult(empty_trades, pd.Series(params.min_equity, index=df.index))
    by_bar = {ts: grp for ts, grp in signals.groupby("timestamp")}
    cost = (params.spread_pips + params.slippage_pips) * params.pip_size

    equity = float(params.min_equity)
    equity_at = pd.Series(float("nan"), index=df.index)
    trades: list[dict[str, Any]] = []
    open_pos: dict[str, Any] | None = None

    for i in range(len(df)):
        ts = df.index[i]
        bar = df.iloc[i]
        if open_pos is not None:
            outcome = _check_exit(open_pos, bar, i, max_hold_bars)
            if outcome is not None:
                exit_price, reason = outcome
                signed = 1.0 if open_pos["direction"] == "long" else -1.0
                pnl = signed * (exit_price - open_pos["entry_price"]) * open_pos["units"]
                equity += pnl
                trades.append(
                    {
                        **open_pos,
                        "exit_ts": ts,
                        "exit_price": exit_price,
                        "pnl": pnl,
                        "exit_reason": reason,
                    }
                )
                equity_at[ts] = equity
                open_pos = None
        if open_pos is None and ts in by_bar:
            for _, s in by_bar[ts].iterrows():
                if i + 1 >= len(df):
                    break
                nxt = df.iloc[i + 1]
                fill = _fill_price(str(s["direction"]), float(s["limit_price"]), nxt, cost)
                if fill is None:
                    continue
                risk_dist = abs(float(s["stop_price"]) - fill)
                if not risk_dist > 0:
                    continue
                open_pos = {
                    "signal_ts": ts,
                    "entry_ts": df.index[i + 1],
                    "entry_idx": i + 1,
                    "direction": str(s["direction"]),
                    "entry_price": fill,
                    "stop_price": float(s["stop_price"]),
                    "target_price": float(s["target_price"]),
                    "units": equity * params.risk_per_trade_pct / 100.0 / risk_dist,
                }
                break  # one position at a time
    if open_pos is not None:  # force-close at the final close
        signed = 1.0 if open_pos["direction"] == "long" else -1.0
        exit_price = float(df["close"].iloc[-1])
        pnl = signed * (exit_price - open_pos["entry_price"]) * open_pos["units"]
        equity += pnl
        trades.append(
            {
                **open_pos,
                "exit_ts": df.index[-1],
                "exit_price": exit_price,
                "pnl": pnl,
                "exit_reason": "timeout",
            }
        )
        equity_at[df.index[-1]] = equity
    equity_at.iloc[0] = params.min_equity
    curve = equity_at.ffill()
    curve.name = "equity"
    trades_df = pd.DataFrame(trades).drop(columns=["entry_idx"]) if trades else empty_trades
    return BacktestResult(trades_df, curve)


def _fill_price(direction: str, limit: float, bar: pd.Series, cost: float) -> float | None:
    if direction == "long":
        if bar["low"] > limit:
            return None
        return min(float(bar["open"]), limit) + cost
    if bar["high"] < limit:
        return None
    return max(float(bar["open"]), limit) - cost


def _check_exit(
    pos: dict[str, Any], bar: pd.Series, i: int, max_hold_bars: int
) -> tuple[float, str] | None:
    if pos["direction"] == "long":
        if bar["low"] <= pos["stop_price"]:
            return pos["stop_price"], "stop"
        if bar["high"] >= pos["target_price"]:
            return pos["target_price"], "target"
    else:
        if bar["high"] >= pos["stop_price"]:
            return pos["stop_price"], "stop"
        if bar["low"] <= pos["target_price"]:
            return pos["target_price"], "target"
    if i - pos["entry_idx"] >= max_hold_bars:
        return float(bar["close"]), "timeout"
    return None
