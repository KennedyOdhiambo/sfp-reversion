"""Walk-forward validation: tune in-sample, judge out-of-sample, roll forward.

Windows tile the history: each window trains/selects on [t, t+IS] and is scored
on (t+IS, t+IS+OOS], stepping by OOS. The ``score_fn`` owns selection (it may
sweep parameters on the IS slice); this module owns honest splitting.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import pandas as pd

ScoreFn = Callable[[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame], tuple[float, int]]
"""(is_hourly, is_daily, oos_hourly, oos_daily) -> (oos_score, oos_n_trades)."""


@dataclass
class WindowResult:
    is_start: pd.Timestamp
    is_end: pd.Timestamp
    oos_start: pd.Timestamp
    oos_end: pd.Timestamp
    score: float
    n_trades: int


def walk_forward_windows(
    start: pd.Timestamp, end: pd.Timestamp, in_sample: pd.Timedelta, out_of_sample: pd.Timedelta
) -> list[tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp, pd.Timestamp]]:
    wins = []
    t = start
    while t + in_sample + out_of_sample <= end:
        wins.append((t, t + in_sample, t + in_sample, t + in_sample + out_of_sample))
        t += out_of_sample
    return wins


def walk_forward_evaluate(
    hourly: pd.DataFrame,
    daily: pd.DataFrame,
    score_fn: ScoreFn,
    in_sample_years: float = 0.75,
    out_of_sample_years: float = 0.25,
    start: pd.Timestamp | None = None,
    end: pd.Timestamp | None = None,
) -> list[WindowResult]:
    ist = pd.Timedelta(days=365.25 * in_sample_years)
    oost = pd.Timedelta(days=365.25 * out_of_sample_years)
    out = []
    for is_start, is_end, oos_start, oos_end in walk_forward_windows(
        hourly.index[0], hourly.index[-1], ist, oost
    ):
        if start is not None and oos_end <= start:
            continue
        if end is not None and oos_start >= end:
            continue
        oos_h = hourly[(hourly.index >= oos_start) & (hourly.index < oos_end)]
        oos_d = daily[(daily.index >= oos_start) & (daily.index < oos_end)]
        if oos_h.empty:
            continue
        score, n = score_fn(
            hourly[(hourly.index >= is_start) & (hourly.index < is_end)],
            daily[(daily.index >= is_start) & (daily.index < is_end)],
            oos_h,
            oos_d,
        )
        out.append(WindowResult(is_start, is_end, oos_start, oos_end, score, n))
    return out
