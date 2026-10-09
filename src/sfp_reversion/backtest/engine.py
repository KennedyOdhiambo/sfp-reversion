"""Setup A backtest: market/limit entries, stop/target/warning exits, costs, sizing.

A signal at bar ``t`` resolves on the execution frame (H1 or M5): market
orders fill at bar ``t+1``'s open; limit orders fill at the limit price if a
bar trades through it within ``expiry_bars`` (unfilled limits expire with no
trade). Exits per bar, checked in order: stop (worst case first), target,
warning-sign close back through the sweep extreme, timeout. One position at
a time; the warning exit applies only when the signal carries ``sweep_extreme``.
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
    exit_slippage_pips: float = 1.0
    pip_size: float = 0.0001
    risk_per_trade_pct: float = 1.0
    min_equity: float = 10000.0
    max_hold_bars: int = 120

    @classmethod
    def from_config(cls) -> BacktestParams:
        bt = get_config().section("backtest")
        return cls(
            spread_pips=float(bt.get("spread_pips", 1.0)),
            slippage_pips=float(bt.get("slippage_pips", 0.5)),
            exit_slippage_pips=float(bt.get("exit_slippage_pips", 1.0)),
            pip_size=float(bt.get("pip_size", 0.0001)),
            risk_per_trade_pct=float(bt.get("risk_per_trade_pct", 1.0)),
            min_equity=float(bt.get("min_equity", 10000)),
            max_hold_bars=int(bt.get("max_hold_bars", 120)),
        )


@dataclass
class BacktestResult:
    trades_df: pd.DataFrame
    equity_curve: pd.Series


def run_backtest(
    df: pd.DataFrame,
    signals: pd.DataFrame,
    params: BacktestParams | None = None,
    max_hold_bars: int | None = None,
) -> BacktestResult:
    params = params or BacktestParams.from_config()
    max_hold = params.max_hold_bars if max_hold_bars is None else max_hold_bars
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
    exit_cost = params.exit_slippage_pips * params.pip_size

    equity = float(params.min_equity)
    equity_at = pd.Series(float("nan"), index=df.index)
    trades: list[dict[str, Any]] = []
    open_pos: dict[str, Any] | None = None

    for i in range(len(df)):
        ts = df.index[i]
        bar = df.iloc[i]
        if open_pos is not None:
            outcome = _check_exit(open_pos, bar, i, max_hold, exit_cost)
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
                mode = s.get("entry_mode", "market")
                expiry = int(s.get("expiry_bars", 0) or 0)
                if mode == "limit":
                    fill, fill_idx = _limit_fill(
                        str(s["direction"]), float(s["entry_price"]), df, i, expiry, cost
                    )
                    if fill is None:
                        continue  # expired unfilled: no trade
                else:
                    fill, fill_idx = _fill_price(str(s["direction"]), df.iloc[i + 1], cost), i + 1
                risk_dist = abs(float(s["stop_price"]) - fill)
                if not risk_dist > 0:
                    continue
                open_pos = {
                    "signal_ts": ts,
                    "entry_ts": df.index[fill_idx],
                    "entry_idx": fill_idx,
                    "direction": str(s["direction"]),
                    "entry_price": fill,
                    "stop_price": float(s["stop_price"]),
                    "target_price": float(s["target_price"]),
                    "sweep_extreme": (
                        float(s["sweep_extreme"])
                        if "sweep_extreme" in s and pd.notna(s["sweep_extreme"])
                        else None
                    ),
                }
                open_pos["units"] = equity * params.risk_per_trade_pct / 100.0 / risk_dist
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
    trades_df = (
        pd.DataFrame(trades).drop(columns=["entry_idx", "sweep_extreme"])
        if trades
        else empty_trades
    )
    return BacktestResult(trades_df, curve)


def _fill_price(direction: str, bar: pd.Series, cost: float) -> float:
    if direction == "long":
        return float(bar["open"]) + cost
    return float(bar["open"]) - cost


def _limit_fill(
    direction: str, limit: float, df: pd.DataFrame, i: int, expiry: int, cost: float
) -> tuple[float | None, int]:
    """First bar after ``i`` (up to ``expiry`` bars out) trading through ``limit``."""
    last = min(i + expiry, len(df) - 1)
    for j in range(i + 1, last + 1):
        bar = df.iloc[j]
        touched = bar["low"] <= limit if direction == "long" else bar["high"] >= limit
        if touched:
            fill = limit + cost if direction == "long" else limit - cost
            return fill, j
    return None, -1


def _check_exit(
    pos: dict[str, Any], bar: pd.Series, i: int, max_hold_bars: int, exit_cost: float = 0.0
) -> tuple[float, str] | None:
    if pos["direction"] == "long":
        if bar["low"] <= pos["stop_price"]:
            return pos["stop_price"] - exit_cost, "stop"
        if bar["high"] >= pos["target_price"]:
            return pos["target_price"] - exit_cost, "target"
        if pos["sweep_extreme"] is not None and bar["close"] < pos["sweep_extreme"]:
            return float(bar["close"]) - exit_cost, "warning"
    else:
        if bar["high"] >= pos["stop_price"]:
            return pos["stop_price"] + exit_cost, "stop"
        if bar["low"] <= pos["target_price"]:
            return pos["target_price"] + exit_cost, "target"
        if pos["sweep_extreme"] is not None and bar["close"] > pos["sweep_extreme"]:
            return float(bar["close"]) + exit_cost, "warning"
    if i - pos["entry_idx"] >= max_hold_bars:
        return float(bar["close"]), "timeout"
    return None
