"""evals.framework.aggregators — roll per-case Scores into dataset-level metrics.

Generic and agent-agnostic: they key off score *names*, not agent fields. Richer
metrics (precision/recall, confusion matrices, calibration curves) are natural
extensions — have an evaluator emit the labelled values they need and add an
aggregator that reads them.

    PassRate(score_name)  — fraction of cases where that gated score passed
    MeanValue(score_name) — mean of that score's value across cases (e.g. an MAE)
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean

from evals.framework.core import Score


def _collect(scores_by_case: dict[str, list[Score]], name: str) -> list[Score]:
    return [s for scores in scores_by_case.values() for s in scores if s.name == name]


@dataclass
class PassRate:
    """Fraction of cases where the named (gated) score passed."""

    score_name: str

    def aggregate(self, scores_by_case: dict[str, list[Score]]) -> dict[str, float]:
        gated = [s for s in _collect(scores_by_case, self.score_name) if s.passed is not None]
        if not gated:
            return {}
        return {f"{self.score_name}.pass_rate": sum(1 for s in gated if s.passed) / len(gated)}


@dataclass
class MeanValue:
    """Mean of the named score's value across cases (e.g. ``risk_mae`` → mean abs error)."""

    score_name: str

    def aggregate(self, scores_by_case: dict[str, list[Score]]) -> dict[str, float]:
        vals = [s.value for s in _collect(scores_by_case, self.score_name)]
        if not vals:
            return {}
        return {f"{self.score_name}.mean": mean(vals)}
