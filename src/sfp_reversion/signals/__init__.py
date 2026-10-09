"""Signals package: Setup A (SFP) and Setup B (breakout-then-return)."""

from sfp_reversion.signals.retest import RetestParams, generate_retest_signals
from sfp_reversion.signals.sfp import SIGNAL_COLUMNS, SfpParams, generate_sfp_signals

__all__ = [
    "RetestParams",
    "SIGNAL_COLUMNS",
    "SfpParams",
    "generate_retest_signals",
    "generate_sfp_signals",
]
