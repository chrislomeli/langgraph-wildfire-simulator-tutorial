"""evals.escalation.judge — LLM-as-judge factory for the escalation eval.

Returns a judge callable: (reference: str, actual: str) -> float
suitable for injection into ReferenceJudge.

The callable is synchronous (LangSmith's evaluator contract is sync).
LangSmith calls each evaluator independently after the target run completes,
so the judge fires once per sample per case — not in the hot path.

Usage:
    from evals.escalation.judge import make_llm_judge

    judge = make_llm_judge(llm, system_prompt=_JUDGE_SYSTEM)
    ReferenceJudge(name="reasoning_quality", ..., judge=judge)
"""

from __future__ import annotations

import re

from langchain_core.messages import HumanMessage, SystemMessage

# Generic default — domain-neutral framing. Pass system_prompt= to make_llm_judge
# when the eval domain benefits from more specific context for the judge.
_DEFAULT_SYSTEM = """\
You are an impartial evaluator scoring an AI agent's output against provided criteria.
You will be given evaluation criteria and the agent's output to score.
Respond with a single float between 0.0 and 1.0 — nothing else.
  0.0 = output does not meet the criteria at all
  0.5 = output partially meets the criteria
  1.0 = output fully meets the criteria\
"""

_TEMPLATE = """\
Criteria:
{reference}

Agent output to evaluate:
{actual}

Score:\
"""


def make_llm_judge(llm, *, system_prompt: str = _DEFAULT_SYSTEM):
    """Return a judge callable backed by `llm`.

    Parameters
    ----------
    llm:
        Any LangChain chat model. Invoked synchronously.
    system_prompt:
        Framing shown to the judge before the criteria and output. Override
        this per eval domain so the judge understands what it is scoring —
        e.g. fire-risk reasoning, logistics plan quality, forecast accuracy.

    The returned callable is: (reference: str, actual: str) -> float

    Cases where `reference` is empty string are skipped (returns 0.0 with
    no LLM call) — this lets you add ReferenceJudge to the evaluators list
    once and it quietly no-ops on cases that have no criteria authored yet.
    """

    def judge(reference: str, actual: str) -> float:
        if not reference:
            return 0.0
        prompt = _TEMPLATE.format(reference=reference, actual=actual)
        response = llm.invoke([SystemMessage(system_prompt), HumanMessage(prompt)])
        text = response.content.strip()
        m = re.search(r"[01](?:\.\d+)?|\d+\.\d+", text)
        return min(1.0, max(0.0, float(m.group()))) if m else 0.0

    return judge
