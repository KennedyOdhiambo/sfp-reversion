"""Statistical significance: Sharpe confidence intervals and deflated Sharpe.

A backtest number is evidence only with an error bar. Sharpe CI (Lo 2002) says
how wide the bar is; the deflated Sharpe (Bailey & Lopez de Prado 2014) further
discounts for how many parameter combinations were tried to get it.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats


def sharpe_ratio(returns: pd.Series, periods_per_year: float = 252.0) -> float:
    r = returns.dropna().to_numpy(dtype=float)
    if len(r) < 2 or r.std(ddof=1) == 0:
        return 0.0
    return float(r.mean() / r.std(ddof=1) * np.sqrt(periods_per_year))


def sharpe_confidence_interval(
    returns: pd.Series, confidence: float = 0.95, periods_per_year: float = 252.0
) -> tuple[float, float, float]:
    """(sharpe, lower, upper): two-sided normal CI with Lo's standard error."""
    r = returns.dropna().to_numpy(dtype=float)
    sr = sharpe_ratio(returns, periods_per_year)
    if len(r) < 2:
        return sr, sr, sr
    se = float(np.sqrt((1.0 + 0.5 * sr**2) / len(r)))
    z = float(stats.norm.ppf(0.5 + confidence / 2.0))
    return sr, sr - z * se, sr + z * se


def deflated_sharpe(
    returns: pd.Series, n_trials: int, periods_per_year: float = 252.0
) -> tuple[float, float]:
    """(deflated Sharpe, PSR): expected SR under the null given ``n_trials`` tries."""
    r = returns.dropna().to_numpy(dtype=float)
    sr = sharpe_ratio(returns, periods_per_year)
    if len(r) < 3 or n_trials < 1:
        return 0.0, 0.0
    skew = float(stats.skew(r))
    kurt = float(stats.kurtosis(r))  # excess kurtosis
    gamma = 3.0  # Euler-Mascheroni approx constant used in the reference formula
    expected = np.sqrt(np.var(r, ddof=1)) * (
        (1.0 - gamma) * stats.norm.ppf(1.0 - 1.0 / n_trials)
        + gamma * stats.norm.ppf(1.0 - 1.0 / (n_trials * np.e))
    )
    if expected <= 0:
        return sr, 1.0
    sr_std = float(np.sqrt((1.0 - skew * sr + kurt * sr**2 / 4.0) / (len(r) - 1.0)))
    psr = float(stats.norm.cdf((sr - expected) / sr_std)) if sr_std > 0 else 0.0
    return sr, psr


def significance_report(
    returns: pd.Series,
    n_trials: int = 50,
    confidence: float = 0.95,
    min_trades: int = 20,
) -> dict[str, float | bool]:
    sr, lo, hi = sharpe_confidence_interval(returns, confidence)
    _, psr = deflated_sharpe(returns, n_trials)
    n = int(returns.dropna().shape[0])
    return {
        "n": float(n),
        "sharpe": sr,
        "ci_low": lo,
        "ci_high": hi,
        "deflated_psr": psr,
        "enough_data": n >= min_trades and lo > 0,
    }
