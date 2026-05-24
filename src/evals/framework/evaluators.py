"""evals.framework.evaluators — reusable, agent-agnostic scoring strategies.

These are the "scoring toolkit" half of an evaluator. Each strategy is generic
and is wired to a specific output via accessor callables you pass in — so you
build the strategies once, and per agent you only choose *which strategy reads
which field*. None of them import anything agent-specific.

    BooleanVote      — majority vote of a boolean decision vs expected (exact)
    NumericTolerance — mean of a number within ±tolerance of expected (banded + MAE)
    KeywordPresence  — cheap, deterministic groundedness: required substrings present
    ReferenceJudge   — the LLM-as-judge seam, with the judge injected (no LLM dep here)
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from statistics import mean
from typing import Any

from evals.framework.core import CaseExecution, Score


def _majority(flags: Sequence[bool]) -> bool:
    return sum(1 for f in flags if f) * 2 > len(flags)


@dataclass
class BooleanVote:
    """Score a boolean decision by majority vote across samples vs the expected bool.

    predict  : Output   -> bool   (e.g. lambda o: o.escalate)
    expected : Expected -> bool   (e.g. lambda x: x.escalate)
    """

    name: str
    predict: Callable[[Any], bool]
    expected: Callable[[Any], bool]

    def evaluate(self, ex: CaseExecution) -> list[Score]:
        outs = ex.outputs
        if not outs:
            return [Score(self.name, 0.0, passed=False, detail="all samples parse-failed")]
        actual_outputs = [bool(self.predict(o)) for o in outs]
        actual_majority = _majority(actual_outputs)
        expected = bool(self.expected(ex.case.expected))
        ok = actual_majority == expected
        return [
            Score(
                self.name,
                float(ok),
                passed=ok,
                detail=f"{sum(actual_outputs)}/{len(actual_outputs)} true; decided={actual_majority} want={expected}",
            )
        ]


@dataclass
class NumericTolerance:
    """Score a numeric field by mean-across-samples within ±tolerance of expected.

    Emits two scores: ``<name>`` (pass/fail within tolerance) and ``<name>_mae``
    (absolute error, informational — feeds a mean/MAE aggregator).
    """

    name: str
    predict: Callable[[Any], float]
    expected: Callable[[Any], float]
    tolerance: float

    def evaluate(self, ex: CaseExecution) -> list[Score]:
        outs = ex.outputs
        if not outs:
            return [Score(self.name, 0.0, passed=False, detail="all samples parse-failed")]
        avg = mean(float(self.predict(o)) for o in outs)
        want = float(self.expected(ex.case.expected))
        err = abs(avg - want)
        ok = err <= self.tolerance
        return [
            Score(
                self.name,
                float(ok),
                passed=ok,
                detail=f"mean={avg:.2f} want={want:.2f} err={err:.2f} tol={self.tolerance}",
            ),
            Score(f"{self.name}_mae", err, passed=None),
        ]


@dataclass
class KeywordPresence:
    """Deterministic groundedness check: all required substrings appear in the text.

    text : Output -> str  (e.g. lambda o: " ".join(o.reasoning))

    Useful where 'fuzzy' is actually checkable without a judge — cheaper and more
    reliable than an LLM when you just need "did it cite the thing it must cite".
    """

    name: str
    text: Callable[[Any], str]
    required: Sequence[str]

    def evaluate(self, ex: CaseExecution) -> list[Score]:
        outs = ex.outputs
        if not outs or not self.required:
            return [Score(self.name, 0.0, passed=None, detail="not scored")]
        haystack = " ".join(self.text(o).lower() for o in outs)
        hits = [kw for kw in self.required if kw.lower() in haystack]
        ok = len(hits) == len(self.required)
        return [
            Score(
                self.name,
                len(hits) / len(self.required),
                passed=ok,
                detail=f"{len(hits)}/{len(self.required)} keywords present",
            )
        ]


@dataclass
class ReferenceJudge:
    """The LLM-as-judge seam — with NO LLM dependency baked in.

    You inject ``judge``, a function ``(reference, actual) -> score in [0, 1]``.
    In production that's a rubric-pinned LLM call; in tests it's a stub. Scores
    ≥ ``threshold`` pass. This is where prose / faithfulness scoring plugs in,
    without coupling the framework to any model provider.
    """

    name: str
    reference: Callable[[Any], str]  # Expected -> reference text
    actual: Callable[[Any], str]  # Output   -> produced text
    judge: Callable[[str, str], float]
    threshold: float = 0.7

    def evaluate(self, ex: CaseExecution) -> list[Score]:
        outs = ex.outputs
        if not outs:
            return [Score(self.name, 0.0, passed=False, detail="all samples parse-failed")]
        ref = self.reference(ex.case.expected)
        graded = [self.judge(ref, self.actual(o)) for o in outs]
        avg = mean(graded)
        ok = avg >= self.threshold
        return [
            Score(self.name, avg, passed=ok, detail=f"judge mean={avg:.2f} thr={self.threshold}")
        ]
