"""Signals package: Setup A SFP signals (decision_tree is parked Setup B)."""

from sfp_reversion.signals.decision_tree import DecisionTreeParams, generate_signals
from sfp_reversion.signals.sfp import SIGNAL_COLUMNS, SfpParams, generate_sfp_signals

__all__ = [
    "DecisionTreeParams",
    "SIGNAL_COLUMNS",
    "SfpParams",
    "generate_sfp_signals",
    "generate_signals",
]
