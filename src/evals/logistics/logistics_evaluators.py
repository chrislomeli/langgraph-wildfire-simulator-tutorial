"""evals.logistics.logistics_evaluators — logistics-specific scoring strategies.

    AssessmentPopulated — checks that all prose fields are non-empty across runs.
"""

from __future__ import annotations

from dataclasses import dataclass

from evals.framework.core import CaseExecution, Score


@dataclass
class AssessmentPopulated:
    """Check that all required LogisticsAssessment prose fields are filled across runs.

    Passes only when every run produces non-empty observations, assessment,
    and advisory_rationale. score = passing_runs / total_runs.
    """

    name: str

    def evaluate(self, ex: CaseExecution) -> list[Score]:
        outs = ex.outputs
        if not outs:
            return [Score(self.name, 0.0, passed=False, detail="all samples parse-failed")]

        pass_count = sum(
            1 for o in outs
            if bool(o.observations) and bool(o.assessment) and bool(o.advisory_rationale)
        )
        run_count = len(outs)
        score = pass_count / run_count
        return [
            Score(
                self.name,
                score,
                passed=(score == 1.0),
                detail=f"passing runs: {pass_count}/{run_count}",
            )
        ]
