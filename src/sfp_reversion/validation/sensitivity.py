"""Parameter sensitivity: is the edge robust or a knife-edge artifact?

Sweep one parameter over candidate values through a caller-supplied ``run_fn``
(value -> score, e.g. OOS PnL). Robust = same sign and contained range across
the sweep; knife-edge = the best value surrounded by collapse.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class SweepResult:
    values: list[float]
    scores: list[float]
    best_value: float
    best_score: float
    sign_stable: bool
    range_ratio: float  # (max-min)/|max|; large = knife-edge territory

    @property
    def robust(self) -> bool:
        return self.sign_stable and self.range_ratio <= 1.0


def sweep_parameter(values: list[float], run_fn: Callable[[float], float]) -> SweepResult:
    scores = [float(run_fn(v)) for v in values]
    peak = max(scores, key=abs)
    best = max(range(len(values)), key=lambda i: scores[i])
    nonzero = [s for s in scores if s != 0]
    stable = bool(nonzero) and (all(s > 0 for s in nonzero) or all(s < 0 for s in nonzero))
    ratio = (max(scores) - min(scores)) / abs(peak) if peak != 0 else 0.0
    return SweepResult(
        values=list(values),
        scores=scores,
        best_value=values[best],
        best_score=scores[best],
        sign_stable=stable,
        range_ratio=float(ratio),
    )
