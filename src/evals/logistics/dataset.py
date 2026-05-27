"""evals.logistics.dataset — LogisticsDataset: golden cases for the logistics eval.

Wraps the hand-authored CASES list as a DatasetSource[LogisticsCase, dict].
Each case carries self-contained inputs; no world engine or DB is needed.
"""

from __future__ import annotations

from evals.logistics.cases import LogisticsCase, build_cases
from evals.framework.core import Case


class LogisticsDataset:
    """DatasetSource backed by the hand-authored CASES list.

    Bump version when golden data changes — LangSmith run records are
    traceable to the dataset version they scored.
    """

    version = "v1"

    def load(self) -> list[Case[LogisticsCase, dict]]:
        return [_to_case(c) for c in build_cases()]


def _to_case(c: LogisticsCase) -> Case[LogisticsCase, dict]:
    return Case(
        id=c.id,
        input=c,
        expected={
            "expect_advisory": c.expect_advisory,
            "advisory_criteria": c.advisory_criteria,
        },
        notes=c.notes,
    )
