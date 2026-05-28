"""evals.logistics.logistics_evaluators — logistics-specific scoring strategies.

    AssessmentPopulated   — checks that all prose fields are non-empty across runs.
    assessment_for_judge  — renders the FULL assessment (incl. the advisory's
                            situation/location/recommendation) for the quality judge.
"""

from __future__ import annotations

from dataclasses import dataclass

from evals.framework.core import CaseExecution, Score


def assessment_for_judge(o) -> str:
    """Render a LogisticsAssessment for the advisory_quality judge.

    The rubric criteria reference the threatened location, the threat vector,
    urgency, and the pre-positioning recommendation — but those live in the
    nested ``advisory`` object, not in ``assessment``/``advisory_rationale``.
    Feeding only those two fields blinds the judge to the recommendation and
    location it is asked to grade. Include the advisory fields so the judge
    evaluates the whole output, not a slice of it.
    """
    parts = [o.assessment, f"Rationale: {o.advisory_rationale}"]
    if o.advisory is not None:
        a = o.advisory
        parts.append(
            "Advisory — "
            f"situation: {a.situation} | "
            f"location: {a.location_description} | "
            f"urgency_level: {a.urgency_level} | "
            f"recommendation: {a.recommendation}"
        )
    return "\n\n".join(parts)


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
