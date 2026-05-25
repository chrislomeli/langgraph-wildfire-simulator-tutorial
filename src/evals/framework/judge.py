"""evals.framework.judge — LLM-as-judge factory.

Returns a judge callable: (reference: str, actual: str) -> float
suitable for injection into ReferenceJudge.

The callable is synchronous (LangSmith's evaluator contract is sync).
LangSmith calls each evaluator independently after the target run completes,
so the judge fires once per sample per case — not in the hot path.

Usage:
    from evals.framework.judge import make_llm_judge

    judge = make_llm_judge(llm_registry.get("classifier"))
    ReferenceJudge(name="reasoning_quality", ..., judge=judge)
"""

from __future__ import annotations

import re

from langchain_core.messages import HumanMessage, SystemMessage

_SYSTEM = """\
You are an impartial evaluator scoring a fire-risk assessment agent's reasoning.
You will be given evaluation criteria and the agent's reasoning to score.
Respond with a single float between 0.0 and 1.0 — nothing else.
  0.0 = reasoning does not meet the criteria at all
  0.5 = reasoning partially meets the criteria
  1.0 = reasoning fully meets the criteria\
"""

_TEMPLATE = """\
Criteria:
{reference}

Agent reasoning to evaluate:
{actual}

Score:\
"""


def make_llm_judge(llm):
    """Return a judge callable backed by `llm`.

    The returned callable is: (reference: str, actual: str) -> float

    Cases where `reference` is empty string are skipped (returns 0.0 with
    no LLM call) — this lets you add ReferenceJudge to the evaluators list
    once and it quietly no-ops on cases that have no criteria authored yet.
    """

    def judge(reference: str, actual: str) -> float:
        if not reference:
            return 0.0
        prompt = _TEMPLATE.format(reference=reference, actual=actual)
        response = llm.invoke([SystemMessage(_SYSTEM), HumanMessage(prompt)])
        text = response.content.strip()
        m = re.search(r"[01](?:\.\d+)?|\d+\.\d+", text)
        return min(1.0, max(0.0, float(m.group()))) if m else 0.0

    return judge
