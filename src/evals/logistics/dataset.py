"""evals.logistics.dataset — LogisticsDataset: golden cases for the logistics eval.

Wraps the hand-authored CASES list as a DatasetSource[LogisticsCase, dict].
Each case carries self-contained inputs; no world engine or DB is needed.
"""

from __future__ import annotations

from evals.logistics.cases import LogisticsCase, build_cases
from evals.framework.core import Case


class LogisticsDataset:
    """DatasetSource backed by the hand-authored CASES list.

    Bump ``version`` when golden data changes. ``name`` derives the LangSmith
    dataset name from it, so a single bump both (a) points runners at a fresh
    dataset — forcing a reseed, since seed_dataset keys idempotency on the
    name — and (b) keeps run records traceable to the version they scored.
    """

    base_name = "logistics-eval-golden"
    version = "v4"

    @property
    def name(self) -> str:
        """LangSmith dataset name — the single source of truth for both runners."""
        return f"{self.base_name}-{self.version}"

    def load(self) -> list[Case[LogisticsCase, dict]]:
        return [_to_case(c) for c in build_cases()]

    def load_local(self) -> list[Case[LogisticsCase, dict]]:
        return build_cases()

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
