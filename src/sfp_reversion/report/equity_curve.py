"""Equity-curve plot: the one chart a human actually reviews."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


def plot_equity_curve(equity: pd.Series, path: str | Path, title: str = "Equity curve") -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.plot(equity.index, equity.to_numpy(), linewidth=1.2)
    ax.set_title(title)
    ax.set_xlabel("Date")
    ax.set_ylabel("Equity")
    ax.grid(alpha=0.3)
    fig.autofmt_xdate()
    fig.savefig(path, dpi=100, bbox_inches="tight")
    plt.close(fig)
    return path
