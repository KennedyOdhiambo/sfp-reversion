"""Validation package: falsification, walk-forward, significance."""

from sfp_reversion.validation.random_baseline import (
    baseline_passes,
    random_signals,
    run_random_baseline,
)

__all__ = ["baseline_passes", "random_signals", "run_random_baseline"]
