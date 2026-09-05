"""Phase 12 tests: baseline mechanics and the PASS/FAIL verdict."""

import pandas as pd

from sfp_reversion.backtest.engine import BacktestParams
from sfp_reversion.data.schema import validate_ohlc
from sfp_reversion.validation.random_baseline import (
    baseline_passes,
    random_signals,
    run_random_baseline,
)

PARAMS = BacktestParams(spread_pips=1.0, slippage_pips=0.5)


def _frame(n: int = 300) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=n, freq="h", tz="UTC")
    close = 1.10 + 0.001 * (pd.Series(range(n)).rolling(10).mean().fillna(0).to_numpy())
    df = pd.DataFrame(
        {"open": close, "high": close + 0.002, "low": close - 0.002, "close": close, "volume": 0.0},
        index=idx,
    )
    df.index.name = "timestamp"
    return validate_ohlc(df)


def test_seed_deterministic_and_sized() -> None:
    df = _frame()
    a = random_signals(df, 8, seed=7)
    b = random_signals(df, 8, seed=7)
    pd.testing.assert_frame_equal(a, b)
    assert len(a) == 8
    assert set(a["direction"]) <= {"long", "short"}


def test_baseline_runs_end_to_end() -> None:
    pnls = run_random_baseline(_frame(), n_signals=8, params=PARAMS, n_repeats=5, seed=0)
    assert len(pnls) == 5
    assert all(isinstance(p, float) for p in pnls)


def test_verdict_passes_on_losses() -> None:
    passed, s = baseline_passes([-50.0, -30.0, -70.0, -10.0, -40.0] * 4)
    assert passed
    assert s["mean"] < 0


def test_verdict_fails_on_significant_profit() -> None:
    passed, s = baseline_passes([80.0, 90.0, 70.0, 85.0, 75.0] * 4)
    assert not passed
    assert s["p"] < 0.05


def test_verdict_passes_on_noisy_zero() -> None:
    passed, _ = baseline_passes([5.0, -5.0, 3.0, -3.0, 1.0, -1.0] * 4)
    assert passed
