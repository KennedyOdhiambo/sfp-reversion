"""Validation package: falsification, walk-forward, significance, sensitivity."""

from sfp_reversion.validation.random_baseline import (
    baseline_passes,
    random_signals,
    run_random_baseline,
)
from sfp_reversion.validation.sensitivity import SweepResult, sweep_parameter
from sfp_reversion.validation.significance import (
    deflated_sharpe,
    sharpe_confidence_interval,
    sharpe_ratio,
    significance_report,
)
from sfp_reversion.validation.walk_forward import (
    WindowResult,
    walk_forward_evaluate,
    walk_forward_windows,
)

__all__ = [
    "SweepResult",
    "WindowResult",
    "baseline_passes",
    "deflated_sharpe",
    "random_signals",
    "run_random_baseline",
    "sharpe_confidence_interval",
    "sharpe_ratio",
    "significance_report",
    "sweep_parameter",
    "walk_forward_evaluate",
    "walk_forward_windows",
]
