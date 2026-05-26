"""evals.escalation.escalation_evaluators — escalation-specific scoring strategies.

    AllFieldsPresent — checks that all four AxisFactors axes are populated across runs
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from agents.commons.schemas import AxisFactors
from evals.framework.core import CaseExecution, Score

@dataclass
class AllFieldsPresent:
    """Check that all four AxisFactors axes are non-empty across all runs.

    predict  : Escalation -> AxisFactors   (e.g. lambda o: o.factors)

    score = pass_count / run_count. passed=True only when every run populates all axes.
    """

    name: str
    predict: Callable[[Any], AxisFactors]

    def evaluate(self, ex: CaseExecution) -> list[Score]:
        outs = ex.outputs
        if not outs:
            return [Score(self.name, 0.0, passed=False, detail="all samples parse-failed")]

        axis_factors: list[AxisFactors] = [self.predict(o) for o in outs]
        pass_count = sum([all([
            bool(o.temperature_humidity),
            bool(o.wind),
            bool(o.fuel_and_terrain),
            bool(o.moisture_trend)
        ]) for o in axis_factors])

        run_count = len(axis_factors)
        score = pass_count / run_count

        return [
            Score(
                self.name,
                score,
                passed=(score == 1.0),
                detail=f"passing runs: {pass_count}/{run_count}, score={score}",
            )
        ]
