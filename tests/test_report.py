"""Phase 14 tests: metrics math and plot output."""

import pandas as pd

from sfp_reversion.report.equity_curve import plot_equity_curve
from sfp_reversion.report.metrics_table import max_drawdown, metrics_table


def _trades() -> pd.DataFrame:
    return pd.DataFrame({"pnl": [100.0, -50.0, 200.0, -50.0]})


def _equity() -> pd.Series:
    idx = pd.date_range("2024-01-01", periods=5, freq="D", tz="UTC")
    return pd.Series([10000.0, 10100.0, 10050.0, 10250.0, 10200.0], index=idx)


def test_metrics_exact() -> None:
    m = metrics_table(_trades(), _equity(), 10000.0).set_index("metric")["value"]
    assert m["n_trades"] == 4.0
    assert m["win_rate"] == 0.5
    assert m["total_pnl"] == 200.0
    assert m["avg_win"] == 150.0
    assert m["avg_loss"] == -50.0
    assert m["profit_factor"] == 3.0
    assert m["ending_equity"] == 10200.0


def test_max_drawdown_known_series() -> None:
    assert max_drawdown(_equity()) == (10100.0 - 10050.0) / 10100.0
    idx = pd.date_range("2024-01-01", periods=3, freq="D", tz="UTC")
    assert max_drawdown(pd.Series([1.0, 2.0, 3.0], index=idx)) == 0.0


def test_empty_trades() -> None:
    m = metrics_table(pd.DataFrame({"pnl": []}), _equity(), 10000.0).set_index("metric")["value"]
    assert m["n_trades"] == 0.0
    assert m["ending_equity"] == 10000.0


def test_plot_writes_file(tmp_path) -> None:
    out = plot_equity_curve(_equity(), tmp_path / "equity.png")
    assert out.exists() and out.stat().st_size > 0
