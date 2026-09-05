"""Phase 13 tests: windows, Sharpe math, deflated Sharpe ordering, sweeps."""

import numpy as np
import pandas as pd

from sfp_reversion.validation.sensitivity import sweep_parameter
from sfp_reversion.validation.significance import (
    deflated_sharpe,
    sharpe_confidence_interval,
    sharpe_ratio,
    significance_report,
)
from sfp_reversion.validation.walk_forward import walk_forward_evaluate, walk_forward_windows


def test_windows_tile_exactly() -> None:
    start = pd.Timestamp("2024-01-01", tz="UTC")
    wins = walk_forward_windows(
        start, start + pd.Timedelta(days=365), pd.Timedelta(days=180), pd.Timedelta(days=90)
    )
    assert [(w[0], w[2], w[3]) for w in wins] == [
        (start, start + pd.Timedelta(days=180), start + pd.Timedelta(days=270)),
        (
            start + pd.Timedelta(days=90),
            start + pd.Timedelta(days=270),
            start + pd.Timedelta(days=360),
        ),
    ]
    assert (
        walk_forward_windows(
            start, start + pd.Timedelta(days=10), pd.Timedelta(days=180), pd.Timedelta(days=90)
        )
        == []
    )


def test_evaluate_calls_score_fn_per_window() -> None:
    idx = pd.date_range("2024-01-01", periods=400, freq="D", tz="UTC")
    hourly = pd.DataFrame({"close": 1.0}, index=idx)
    daily = hourly.copy()
    calls: list[tuple[int, int]] = []

    def score_fn(
        is_h: pd.DataFrame, is_d: pd.DataFrame, oos_h: pd.DataFrame, oos_d: pd.DataFrame
    ) -> tuple[float, int]:
        calls.append((len(is_h), len(oos_h)))
        return float(len(oos_h)), len(oos_h)

    res = walk_forward_evaluate(
        hourly, daily, score_fn, in_sample_years=0.5, out_of_sample_years=0.25
    )
    assert len(res) == 2
    assert calls[0] == (183, 91)
    assert [r.score for r in res] == [91.0, 92.0]


def test_sharpe_matches_hand_formula() -> None:
    rng = np.random.default_rng(0)
    r = pd.Series(rng.normal(0.001, 0.01, 500))
    expect = r.mean() / r.std(ddof=1) * np.sqrt(252.0)
    assert sharpe_ratio(r) == expect
    sr, lo, hi = sharpe_confidence_interval(r)
    assert lo < sr < hi
    assert sharpe_ratio(pd.Series([0.0, 0.0, 0.0])) == 0.0


def test_more_trials_deflates_more() -> None:
    rng = np.random.default_rng(1)
    r = pd.Series(rng.normal(0.0005, 0.01, 200))  # modest Sharpe: PSR can differentiate
    _, psr_few = deflated_sharpe(r, 5)
    _, psr_many = deflated_sharpe(r, 5000)
    assert psr_few > psr_many


def test_report_flags_thin_data() -> None:
    rep = significance_report(pd.Series([0.01, -0.005, 0.02]), min_trades=20)
    assert rep["enough_data"] is False
    assert rep["n"] == 3.0


def test_sweep_finds_peak_and_judges() -> None:
    res = sweep_parameter([0.06, 0.10, 0.14], lambda v: 10.0 - 1000.0 * (v - 0.10) ** 2)
    assert res.best_value == 0.10
    assert res.best_score == 10.0
    assert res.robust  # all positive, contained range
    knife = sweep_parameter([1.0, 2.0, 3.0], lambda v: 100.0 if v == 2.0 else -50.0)
    assert not knife.robust
    assert not knife.sign_stable
