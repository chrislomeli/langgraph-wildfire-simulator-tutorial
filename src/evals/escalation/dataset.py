"""evals.escalation.dataset — ScenariosDataset: golden cases for the escalation eval.

Wraps the hand-authored CASES list as a DatasetSource[EscalationCase, dict].
Each Case carries self-contained prompt inputs; no world engine is needed.
"""

from __future__ import annotations

from evals.escalation.cases import CASES, EscalationCase
from evals.framework.core import Case, DatasetSource


class ScenariosDataset:
    """DatasetSource backed by the hand-authored CASES list.

    Bump version when golden data changes — LangSmith run records are
    traceable to the dataset version they scored.
    """

    version = "v2"

    def load(self) -> list[Case[EscalationCase, dict]]:
        return [_to_case(c) for c in CASES]


def _to_case(c: EscalationCase) -> Case[EscalationCase, dict]:
    return Case(
        id=c.id,
        input=c,
        expected={
            "expect_escalate": c.expect_escalate,
            "expect_confidence": c.expect_confidence,
            "expect_keywords": list(c.expect_keywords),
        },
        notes=c.notes,
    )
