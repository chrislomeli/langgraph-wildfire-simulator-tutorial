"""evals.framework — an agent-agnostic evaluation harness.

The spine::

    DatasetSource ─▶ [ Task × N samples ] ─▶ Evaluators ─▶ ExperimentStore
                                                        ╲▶ Aggregators ─▶ Report

Nothing in this package imports the agents, world, or DB layers. The pieces that
vary per agent — the dataset, the ``Task`` adapter, and the evaluators' field
wiring — plug in from OUTSIDE. The pieces that are DRY — the run loop, sampling,
persistence interface, aggregation, and the Report — live here and are reused
across every agent you evaluate.

Runnable walkthrough (no LLM, no DB)::

    python -m evals.framework.demo
"""

from evals.framework.core import (
    Aggregator,
    Case,
    CaseExecution,
    DatasetSource,
    Evaluator,
    ExperimentStore,
    Report,
    RunId,
    Sample,
    Score,
    Task,
    Usage,
    case_passed,
    detect_regressions,
    run_eval,
)

__all__ = [
    "Aggregator",
    "Case",
    "CaseExecution",
    "DatasetSource",
    "Evaluator",
    "ExperimentStore",
    "Report",
    "RunId",
    "Sample",
    "Score",
    "Task",
    "Usage",
    "case_passed",
    "detect_regressions",
    "run_eval",
]
