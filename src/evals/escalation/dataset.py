"""evals.escalation.dataset — ScenariosDataset: golden cases for the escalation eval.

Wraps the hand-authored CASES list as a DatasetSource[EscalationCase, dict].
Each Case carries self-contained prompt inputs; no world engine is needed.
"""

from __future__ import annotations

from evals.escalation.cases import EscalationCase, build_cases
from evals.framework.core import Case


class ScenariosDataset:
    """DatasetSource backed by the hand-authored CASES list.

    Bump version when golden data changes — LangSmith run records are
    traceable to the dataset version they scored.
    """

    version = "v4"

    def load(self) -> list[Case[EscalationCase, dict]]:
        return [_to_case(c) for c in build_cases()]


def _to_case(c: EscalationCase) -> Case[EscalationCase, dict]:
    return Case(
        id=c.id,
        input=c,
        expected={
            "expect_escalate": c.expect_escalate,
            "expect_keywords": list(c.expect_keywords),
            "reasoning_criteria": c.reasoning_criteria,
        },
        notes=c.notes,
    )
