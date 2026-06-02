"""evals.logistics.dataset — LogisticsDataset: golden cases for the logistics eval.

Wraps the hand-authored CASES list as a DatasetSource[LogisticsCase, dict].
Each case carries self-contained inputs; no world engine or DB is needed.
"""

from __future__ import annotations

from evals.codel_intel.cases import RAGRetrievalCase, build_cases
from evals.framework.core import Case


class RAGRetrievalDataset:
    """DatasetSource backed by the hand-authored CASES list.

    Bump version when golden data changes — LangSmith run records are
    traceable to the dataset version they scored.
    """

    version = "v1"

    def __init__(self):
        self.name = self.__class__.__name__

    def load(self) -> list[Case[RAGRetrievalCase, dict]]:
        return [_to_case(c) for c in build_cases()]

    def load_local(self):
        pass


def _to_case(c: RAGRetrievalCase) -> Case[RAGRetrievalCase, dict]:
    return Case(
        id=c.id,
        input=c,
        expected={
            "expected_output": c.expected,
            "expected_keywords": c.keywords,
            # Retrieval ground truth rides in `expected` as plain dicts (not on
            # c.input) so it survives the LangSmith JSON round-trip — on that path
            # case.input is a deserialized dict, but case.expected is read straight
            # from example.outputs. model_dump keeps these JSON-safe on both paths.
            "relevant": [a.model_dump() for a in c.relevant],
        },
        notes=c.notes,
    )
