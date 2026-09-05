"""Falsification gate (§5a): random entries must lose on an honest engine.

Same data, same engine, same costs — only the timing and direction are random
(market-entry limit, 1×ATR stop, 2×ATR target). If random trading shows a
significant profit, the engine has a bug (lookahead, missing costs, bad fills),
not the strategy an edge. Run this before trusting any strategy result.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from sfp_reversion.backtest.engine import BacktestParams, run_backtest
from sfp_reversion.levels.detection import atr_series


def random_signals(
    df: pd.DataFrame,
    n: int,
    seed: int,
    stop_atr: float = 1.0,
    target_atr: float = 2.0,
    max_hold_bars: int = 120,
) -> pd.DataFrame:
    """Random-timing, random-direction signals with fixed-geometry exits."""
    rng = np.random.default_rng(seed)
    atr = atr_series(df).shift(1)
    tradable = np.where((atr > 0).to_numpy())[0]
    tradable = tradable[(tradable >= 1) & (tradable < len(df) - max_hold_bars - 1)]
    if len(tradable) == 0:
        return pd.DataFrame(
            columns=["timestamp", "direction", "limit_price", "stop_price", "target_price"]
        )
    picks = rng.choice(tradable, size=min(n, len(tradable)), replace=False)
    closes = df["close"].to_numpy()
    rows = []
    for p in picks:
        direction = str(rng.choice(["long", "short"]))
        entry = float(closes[p])
        dist = float(atr.iloc[p])
        if direction == "long":
            stop, target = entry - stop_atr * dist, entry + target_atr * dist
        else:
            stop, target = entry + stop_atr * dist, entry - target_atr * dist
        rows.append(
            {
                "timestamp": df.index[p],
                "direction": direction,
                "limit_price": entry,  # market-ish: fills next bar almost surely
                "stop_price": stop,
                "target_price": target,
            }
        )
    return pd.DataFrame(rows)


def run_random_baseline(
    df: pd.DataFrame,
    n_signals: int,
    params: BacktestParams | None = None,
    n_repeats: int = 20,
    seed: int = 0,
    max_hold_bars: int = 120,
) -> list[float]:
    """Total PnL per repeat of random trading. Deterministic given ``seed``."""
    params = params or BacktestParams.from_config()
    pnls = []
    for r in range(n_repeats):
        sigs = random_signals(df, n_signals, seed + r, max_hold_bars=max_hold_bars)
        res = run_backtest(df, sigs, params, max_hold_bars=max_hold_bars)
        pnls.append(float(res.trades_df["pnl"].sum()) if not res.trades_df.empty else 0.0)
    return pnls


def baseline_passes(pnls: list[float]) -> tuple[bool, dict[str, float]]:
    """PASS unless random trading is significantly profitable (engine suspect).

    One-sided t-test of mean <= 0. Zero-variance edge case: passes iff mean <= 0.
    """
    arr = np.asarray(pnls, dtype=float)
    mean = float(arr.mean())
    std = float(arr.std(ddof=1)) if len(arr) > 1 else 0.0
    if std == 0:
        return mean <= 0, {"mean": mean, "std": 0.0, "t": 0.0, "p": 1.0 if mean <= 0 else 0.0}
    t = mean / (std / np.sqrt(len(arr)))
    p = float(1.0 - stats.t.cdf(t, df=len(arr) - 1))  # P(mean > 0)
    return (t < 0) or (p >= 0.05), {"mean": mean, "std": std, "t": float(t), "p": p}
