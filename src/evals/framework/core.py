"""evals.framework.core — the agent-agnostic evaluation spine.

This module is deliberately self-contained: it imports nothing from the rest of
the project (no agents, world, stores, langchain, or pydantic) — only the
stdlib. That isolation is the point: the spine never knows what it is
evaluating.

Architecture (the DRY spine):

    DatasetSource ─▶ [ Task × N samples ] ─▶ Evaluators ─▶ ExperimentStore
                                                        ╲
                                                         ╲▶ Aggregators ─▶ Report

What is DRY (lives here, built once): the run loop, the sampling, the scoring
orchestration, the persistence *interface*, the aggregation, and the Report
shape. None of it is agent-specific.

What VARIES (lives OUTSIDE this module, one per agent): the dataset content, the
``Task`` adapter (how to invoke the system under test), the evaluators' field
wiring, and the output/expected schema. The four Protocols below — ``Task``,
``Evaluator``, ``DatasetSource``, ``ExperimentStore`` — are the seams those plug
into.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any, Generic, Protocol, TypeVar

Input = TypeVar("Input")       # what the system under test consumes
Output = TypeVar("Output")     # what it produces (e.g. an Escalation)
Expected = TypeVar("Expected")  # the golden expectation for a case


# ── Dataset ───────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Case(Generic[Input, Expected]):
    """One golden example: an input to feed the SUT, and the expectation to score."""

    id: str
    input: Input
    expected: Expected
    tags: tuple[str, ...] = ()  # "edge" | "adversarial" | "failure-mode" | ...
    notes: str = ""


class DatasetSource(Protocol[Input, Expected]):
    """Where golden cases come from — a code list, DB rows, a JSON file.

    ``version`` is recorded on every run so results say which dataset they scored.
    """

    version: str

    def load(self) -> list[Case[Input, Expected]]: ...


# ── Cost ────────────────────────────────────────────────────────────────────────


@dataclass
class Usage:
    """Per-call cost/observability. Extend with prompt/completion split, $ cost, etc."""

    total_tokens: int = 0


# ── Task: the system-under-test seam ────────────────────────────────────────────


class Task(Protocol[Input, Output]):
    """The system under test, behind one async call.

    This is the ONLY agent-specific code besides the dataset and evaluators. An
    escalation classifier, a logistics ReAct loop, a RAG chain — each becomes a
    Task. ``output`` is None when the call failed to produce a parseable result
    (a real, *scored* failure mode — not an exception).
    """

    label: str  # identifies the SUT version in the run record, e.g. "gpt-4o/evaluate@v3"

    async def run(self, task_input: Input) -> tuple[Output | None, Usage]: ...


# ── Execution records ────────────────────────────────────────────────────────────


@dataclass
class Sample(Generic[Output]):
    """One execution of the Task for a case. LLMs are stochastic → we keep many."""

    output: Output | None
    latency_ms: float
    usage: Usage


@dataclass
class CaseExecution(Generic[Input, Output, Expected]):
    """A case plus every sample the Task produced for it."""

    case: Case[Input, Expected]
    samples: list[Sample[Output]]

    @property
    def outputs(self) -> list[Output]:
        """The non-None outputs (parse failures dropped)."""
        return [s.output for s in self.samples if s.output is not None]

    @property
    def parse_failures(self) -> int:
        return sum(1 for s in self.samples if s.output is None)


# ── Scores + evaluators ──────────────────────────────────────────────────────────


@dataclass
class Score:
    """One scored dimension for one case.

    ``passed`` is the gate: True/False for an assertion, or None for an
    informational metric (e.g. an MAE value) that feeds aggregation but never
    fails a case on its own.
    """

    name: str
    value: float
    passed: bool | None = None
    detail: str = ""


class Evaluator(Protocol[Output, Expected]):
    """Scores a whole CaseExecution against the expectation.

    Crucially, the evaluator OWNS sample reduction — majority vote for a boolean,
    mean for a number — because *how you collapse noisy samples* is
    metric-specific knowledge. The run loop stays dumb so it can be reused.
    """

    name: str

    def evaluate(self, execution: CaseExecution[Any, Output, Expected]) -> list[Score]: ...


# ── Experiment store: persistence + run tracking ──────────────────────────────────


RunId = int


class ExperimentStore(Protocol):
    """Persists a run (dataset × task × prompt_version) and its per-case scores.

    Implementations: an in-memory store and a JSON store ship in this package; a
    Postgres-backed store (eval_runs / eval_results) implements the same
    Protocol but lives OUTSIDE this isolated package because it depends on the
    DB layer.
    """

    def start_run(
        self,
        *,
        dataset_version: str,
        task_label: str,
        prompt_version: str,
        meta: dict[str, Any],
    ) -> RunId: ...

    def record(
        self, run_id: RunId, case_id: str, scores: list[Score], execution: CaseExecution
    ) -> None: ...

    def finish_run(self, run_id: RunId, report: Report) -> None: ...


# ── Aggregation + report ──────────────────────────────────────────────────────────


class Aggregator(Protocol):
    """Rolls per-case Scores into dataset-level metrics (pass rate, MAE, ...).

    Keys off score *names*, not agent fields, so it stays agent-agnostic.
    """

    def aggregate(self, scores_by_case: dict[str, list[Score]]) -> dict[str, float]: ...


@dataclass
class Report:
    run_id: RunId
    metrics: dict[str, float]
    passed_cases: int
    total_cases: int
    regressions: list[str] = field(default_factory=list)

    @property
    def pass_rate(self) -> float:
        return self.passed_cases / self.total_cases if self.total_cases else 0.0


def case_passed(scores: list[Score]) -> bool:
    """A case passes when every *gated* score passed.

    Informational scores (``passed is None``) never fail a case. A case with no
    gated scores at all is treated as a fail (nothing was actually asserted).
    """
    gated = [s.passed for s in scores if s.passed is not None]
    return bool(gated) and all(gated)


def detect_regressions(
    current: Report,
    baseline: Report,
    *,
    tolerance: float = 0.0,
    lower_is_better: Sequence[str] = ("mae", "error", "latency", "tokens", "cost"),
) -> list[str]:
    """Flag metrics that moved the wrong way vs the baseline, beyond ``tolerance``.

    Metrics whose name contains a ``lower_is_better`` token are flagged when they
    *increase*; all others (accuracy, pass rate, ...) are flagged when they
    *decrease*.
    """
    out: list[str] = []
    for name, value in current.metrics.items():
        if name not in baseline.metrics:
            continue
        base = baseline.metrics[name]
        lib = any(tok in name.lower() for tok in lower_is_better)
        worse = (value > base + tolerance) if lib else (value < base - tolerance)
        if worse:
            out.append(f"{name} ({'↑' if lib else '↓'} worse): {base:.3f} → {value:.3f}")
    return out


# ── The harness ───────────────────────────────────────────────────────────────────


async def run_eval(
    *,
    dataset: DatasetSource[Input, Expected],
    task: Task[Input, Output],
    evaluators: Sequence[Evaluator[Output, Expected]],
    store: ExperimentStore,
    prompt_version: str,
    repeats: int = 3,
    aggregators: Sequence[Aggregator] = (),
    baseline: Report | None = None,
) -> Report:
    """Run the dataset through the task, score, persist, aggregate, compare.

    Nondeterminism policy: this loop samples *blindly* — it runs each case
    ``repeats`` times and collects every Sample. It does NOT vote or average;
    that is each evaluator's job, because the reduction strategy is part of the
    metric. Keeping the loop dumb is what keeps it reusable.
    """
    cases = dataset.load()
    run_id = store.start_run(
        dataset_version=dataset.version,
        task_label=task.label,
        prompt_version=prompt_version,
        meta={"repeats": repeats},
    )

    scores_by_case: dict[str, list[Score]] = {}
    passed = 0
    for case in cases:
        samples: list[Sample[Output]] = []
        for _ in range(repeats):
            t0 = perf_counter()
            output, usage = await task.run(case.input)
            samples.append(Sample(output, (perf_counter() - t0) * 1000.0, usage))

        execution = CaseExecution(case, samples)
        scores = [s for ev in evaluators for s in ev.evaluate(execution)]
        store.record(run_id, case.id, scores, execution)
        scores_by_case[case.id] = scores
        passed += case_passed(scores)

    metrics: dict[str, float] = {}
    for agg in aggregators:
        metrics.update(agg.aggregate(scores_by_case))

    report = Report(
        run_id=run_id, metrics=metrics, passed_cases=passed, total_cases=len(cases)
    )
    if baseline is not None:
        report.regressions = detect_regressions(report, baseline)
    store.finish_run(run_id, report)
    return report
