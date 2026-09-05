"""Metrics table: one row per stat, computed from closed trades + equity curve."""

from __future__ import annotations

import numpy as np
import pandas as pd


def max_drawdown(equity: pd.Series) -> float:
    """Largest peak-to-trough fall as a fraction of the peak."""
    values = equity.dropna().to_numpy(dtype=float)
    if len(values) == 0:
        return 0.0
    peak = np.maximum.accumulate(values)
    dd = np.where(peak > 0, (peak - values) / peak, 0.0)
    return float(dd.max())


def metrics_table(
    trades_df: pd.DataFrame, equity: pd.Series, starting_equity: float
) -> pd.DataFrame:
    rows: list[tuple[str, float]] = [("starting_equity", starting_equity)]
    if trades_df.empty:
        rows += [("n_trades", 0.0), ("ending_equity", starting_equity)]
        return pd.DataFrame(rows, columns=["metric", "value"])
    pnl = trades_df["pnl"].to_numpy(dtype=float)
    wins = pnl[pnl > 0]
    losses = pnl[pnl <= 0]
    rows += [
        ("n_trades", float(len(pnl))),
        ("win_rate", float(len(wins) / len(pnl))),
        ("total_pnl", float(pnl.sum())),
        ("avg_win", float(wins.mean()) if len(wins) else 0.0),
        ("avg_loss", float(losses.mean()) if len(losses) else 0.0),
        (
            "profit_factor",
            float(wins.sum() / abs(losses.sum())) if losses.sum() != 0 else float("inf"),
        ),
        ("max_drawdown", max_drawdown(equity)),
        ("ending_equity", float(equity.dropna().iloc[-1])),
    ]
    return pd.DataFrame(rows, columns=["metric", "value"])
