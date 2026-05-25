"""evals.framework — agent-agnostic evaluation protocols.

LangSmith is the run loop, storage, and UI. These protocols are the seam:
Task and Evaluator are what you implement per agent; DatasetSource is how
you load golden cases. langsmith_adapter.py translates them to LangSmith's
calling conventions.

    DatasetSource ──▶ seed_dataset()   ──▶ LangSmith Dataset
    Task          ──▶ make_target()    ──▶ LangSmith target fn
    Evaluator     ──▶ make_evaluator() ──▶ LangSmith evaluator fn
"""

from evals.framework.core import (
    Case,
    CaseExecution,
    DatasetSource,
    Evaluator,
    Sample,
    Score,
    Task,
    Usage,
)

__all__ = [
    "Case",
    "CaseExecution",
    "DatasetSource",
    "Evaluator",
    "Sample",
    "Score",
    "Task",
    "Usage",
]
