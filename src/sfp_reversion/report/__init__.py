"""Report package: equity plots and metrics tables."""

from sfp_reversion.report.equity_curve import plot_equity_curve
from sfp_reversion.report.metrics_table import max_drawdown, metrics_table

__all__ = ["max_drawdown", "metrics_table", "plot_equity_curve"]
