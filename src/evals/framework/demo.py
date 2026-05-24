"""evals.framework.demo — a runnable, dependency-free walkthrough of the spine.

Run it::

    python -m evals.framework.demo      # from the src/ directory

No LLM, no DB. A fake Task stands in for the system under test so you can watch
one case flow end to end: golden case → run N times → each evaluator scores →
stored per run → aggregated → reported → compared to a baseline.

The fake Task is handed the "truth" plus noise on purpose, to imitate an
imperfect, nondeterministic model. A real Task would receive the agent's input
(a cell, a scenario) and would NOT know the expected answer.
"""

from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass

from evals.framework.aggregators import MeanValue, PassRate
from evals.framework.core import Case, Report, Usage, run_eval
from evals.framework.evaluators import BooleanVote, NumericTolerance
from evals.framework.reporting import render_scorecard
from evals.framework.stores import InMemoryStore

# ── A toy "agent output" + "expectation" (stand-ins for real schemas) ───────────


@dataclass
class FakeOutput:
    escalate: bool
    risk: float
    reasoning: str


@dataclass
class FakeExpected:
    escalate: bool
    risk: float


# ── A fake Task: nondeterministic on purpose, like a real LLM ───────────────────


class FakeTask:
    """Implements the Task protocol. Input here is (truth_escalate, truth_risk)."""

    def __init__(self, label: str, *, wobble: float = 1.0, flip_rate: float = 0.1) -> None:
        self.label = label
        self._wobble = wobble
        self._flip = flip_rate

    async def run(self, task_input: tuple[bool, float]) -> tuple[FakeOutput | None, Usage]:
        truth_escalate, truth_risk = task_input
        escalate = truth_escalate if random.random() > self._flip else not truth_escalate
        risk = truth_risk + random.uniform(-self._wobble, self._wobble)
        out = FakeOutput(escalate, risk, f"risk≈{risk:.1f}, escalate={escalate}")
        return out, Usage(total_tokens=42)


# ── A code-based dataset (the simplest DatasetSource) ───────────────────────────


class DemoDataset:
    version = "demo-v1"

    def load(self) -> list[Case[tuple[bool, float], FakeExpected]]:
        return [
            Case("hot-dry", input=(True, 8.0), expected=FakeExpected(True, 8.0), tags=("sanity",)),
            Case("mild", input=(False, 2.0), expected=FakeExpected(False, 2.0)),
            Case("borderline", input=(True, 6.0), expected=FakeExpected(True, 6.0), tags=("edge",)),
        ]


async def main() -> None:
    random.seed(7)
    dataset = DemoDataset()
    store = InMemoryStore()

    # The evaluators: same generic strategies, just wired to FakeOutput's fields.
    evaluators = [
        BooleanVote("escalate", predict=lambda o: o.escalate, expected=lambda x: x.escalate),
        NumericTolerance("risk", predict=lambda o: o.risk, expected=lambda x: x.risk, tolerance=2.0),
    ]
    aggregators = [PassRate("escalate"), PassRate("risk"), MeanValue("risk_mae")]

    # Run 1 — a decent model.
    good: Report = await run_eval(
        dataset=dataset,
        task=FakeTask("fake-model/v1"),
        evaluators=evaluators,
        store=store,
        prompt_version="prompt@v1",
        repeats=5,
        aggregators=aggregators,
    )
    print("=== RUN 1 (baseline) ===")
    print(render_scorecard(good))


    # Run 2 — a worse model, compared against run 1 as the baseline.
    worse: Report = await run_eval(
        dataset=dataset,
        task=FakeTask("fake-model/v2", wobble=4.0, flip_rate=0.4),
        evaluators=evaluators,
        store=store,
        prompt_version="prompt@v2",
        repeats=5,
        aggregators=aggregators,
        baseline=store.latest_report(),
    )
    print("\n=== RUN 2 (vs baseline) ===")
    print(render_scorecard(worse))


if __name__ == "__main__":
    asyncio.run(main())
