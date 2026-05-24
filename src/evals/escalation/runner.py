"""Eval engine: run scenarios through a classifier, score, print a scorecard.

The classifier is injected so the same runner works against the real LLM
(`make_real_classifier`) or a fake one (tests / dry runs without API keys).
Each scenario is run several times because the LLM is not deterministic —
we report the vote, not a single sample, and surface instability as a signal.
"""

from __future__ import annotations

import json
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from statistics import mean

from langchain_core.messages import HumanMessage, SystemMessage

from agents.commons.schemas import Escalation, EvaluationCell
from evals.escalation.scenarios import Scenario

# A classifier maps (sector_id, cells, bounding) -> (Escalation | None, usage).
# None means the structured-output call failed to parse (a real failure mode).
Classifier = Callable[
    [str, list[EvaluationCell], tuple[int, int]],
    Awaitable[tuple[Escalation | None, dict]],
]

# Calibration thresholds on Escalation.confidence (0-3 scale). Tunable.
HIGH_CONF_MIN = 2.0
LOW_CONF_MAX = 1.0


def make_real_classifier(prompt_registry, llm) -> Classifier:
    """Mirror the `evaluate` node's invocation so we test the real prompt path.

    Uses include_raw=True so we can read token usage and detect parse failures
    instead of letting them raise.
    """
    structured = llm.with_structured_output(Escalation, include_raw=True)

    async def classify(sector_id, cells, bounding):
        max_rows, max_columns = bounding
        system_prompt = prompt_registry.render(
            "evaluate",
            {"sector_id": sector_id, "max_rows": max_rows, "max_columns": max_columns},
        )
        human_prompt = json.dumps([c.model_dump(mode="json") for c in cells], indent=2)
        out = await structured.ainvoke([SystemMessage(system_prompt), HumanMessage(human_prompt)])
        parsed: Escalation | None = out.get("parsed")
        raw = out.get("raw")
        usage = getattr(raw, "usage_metadata", None) or {}
        return parsed, usage

    return classify


@dataclass
class ScenarioResult:
    scenario: Scenario
    escalations: list[Escalation | None]
    latencies_ms: list[float]
    tokens: list[int]

    @property
    def valid(self) -> list[Escalation]:
        return [e for e in self.escalations if e is not None]

    @property
    def parse_failures(self) -> int:
        return len(self.escalations) - len(self.valid)

    @property
    def escalate_votes(self) -> int:
        return sum(1 for e in self.valid if e.escalate)

    @property
    def majority_escalate(self) -> bool | None:
        if not self.valid:
            return None
        return self.escalate_votes * 2 > len(self.valid)

    @property
    def avg_confidence(self) -> float | None:
        return mean(e.confidence for e in self.valid) if self.valid else None

    @property
    def stable(self) -> bool:
        # Same decision every run, and nothing failed to parse.
        return self.parse_failures == 0 and len({e.escalate for e in self.valid}) == 1

    # ── component checks (None = not scored for this scenario) ──────────

    @property
    def decision_ok(self) -> bool | None:
        if self.scenario.expect_escalate is None:
            return None
        return self.majority_escalate == self.scenario.expect_escalate

    @property
    def confidence_ok(self) -> bool | None:
        want = self.scenario.expect_confidence
        if want is None or self.avg_confidence is None:
            return None
        if want == "high":
            return self.avg_confidence >= HIGH_CONF_MIN
        if want == "low":
            return self.avg_confidence <= LOW_CONF_MAX
        return None

    @property
    def keywords_ok(self) -> bool | None:
        if not self.scenario.expect_keywords:
            return None
        haystack = " ".join(f.lower() for e in self.valid for f in e.contributing_factors)
        return all(kw.lower() in haystack for kw in self.scenario.expect_keywords)

    @property
    def passed(self) -> bool:
        if self.parse_failures or not self.valid:
            return False
        checks = [self.decision_ok, self.confidence_ok, self.keywords_ok]
        return all(c for c in checks if c is not None)

    @property
    def avg_tokens(self) -> int:
        return round(mean(self.tokens)) if self.tokens else 0

    @property
    def avg_latency_ms(self) -> int:
        return round(mean(self.latencies_ms)) if self.latencies_ms else 0


async def run(
    scenarios: list[Scenario], classify: Classifier, repeats: int = 3
) -> list[ScenarioResult]:
    results: list[ScenarioResult] = []
    for s in scenarios:
        escalations: list[Escalation | None] = []
        latencies: list[float] = []
        tokens: list[int] = []
        for _ in range(repeats):
            t0 = time.perf_counter()
            esc, usage = await classify(s.id, s.cells, s.bounding)
            latencies.append((time.perf_counter() - t0) * 1000)
            escalations.append(esc)
            tokens.append(int(usage.get("total_tokens", 0)) if usage else 0)
        results.append(ScenarioResult(s, escalations, latencies, tokens))
    return results


def _flag(ok: bool | None) -> str:
    return "—" if ok is None else ("ok" if ok else "X")


def print_scorecard(results: list[ScenarioResult]) -> None:
    repeats = len(results[0].escalations) if results else 0
    header = (
        f"{'scenario':<16} {'expect':<7} {'votes':<7} {'conf':<5} "
        f"{'stbl':<5} {'dec':<4} {'cnf':<4} {'kw':<4} {'tok':<6} {'ms':<6} {'result':<6}"
    )
    print(f"\nEscalation eval — {len(results)} scenarios × {repeats} runs\n")
    print(header)
    print("-" * len(header))

    passed = 0
    for r in results:
        s = r.scenario
        expect = {True: "yes", False: "no", None: "?"}[s.expect_escalate]
        votes = f"{r.escalate_votes}/{len(r.escalations)}"
        if r.parse_failures:
            votes += f"!{r.parse_failures}"  # ! = parse failures
        conf = "—" if r.avg_confidence is None else f"{r.avg_confidence:.1f}"
        result = "PASS" if r.passed else "FAIL"
        passed += r.passed
        print(
            f"{s.id:<16} {expect:<7} {votes:<7} {conf:<5} "
            f"{('yes' if r.stable else 'no'):<5} "
            f"{_flag(r.decision_ok):<4} {_flag(r.confidence_ok):<4} {_flag(r.keywords_ok):<4} "
            f"{r.avg_tokens:<6} {r.avg_latency_ms:<6} {result:<6}"
        )

    total_tokens = sum(t for r in results for t in r.tokens)
    print("-" * len(header))
    print(
        f"{passed}/{len(results)} passed   "
        f"total tokens {total_tokens}   "
        f"legend: dec=decision cnf=confidence kw=keywords  '—'=not scored  '!'=parse fail"
    )
