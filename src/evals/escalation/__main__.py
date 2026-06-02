"""Run the escalation eval against LangSmith.

    python -m evals.escalation [--seed-only]

Requires:
  - LANGCHAIN_API_KEY  (or LANGSMITH_API_KEY) in environment
  - LLM credentials the app uses (same as production)

On first run pass --seed-only to push the dataset to LangSmith before
evaluating. Subsequent runs can omit it — LangSmith uses the existing
dataset and appends a new experiment run.

What this evaluates:
  The escalation decision (Escalation.escalate True/False) for each of the
  6 golden cases. Cases where expect_escalate is None are skipped by the
  decision evaluator (genuinely ambiguous — confidence is observed instead).
"""

from __future__ import annotations

import argparse
import logging

from agents.commons.schemas import Escalation, EvaluationCell
from config import get_settings
from evals.escalation.cases import EscalationCase
from evals.escalation.dataset import ScenariosDataset
from evals.escalation.escalation_evaluators import AllFieldsPresent
from evals.escalation.task import EscalationTask
from evals.framework.evaluators import BooleanVote, ReferenceJudge
from evals.framework.harness import run_eval
from evals.framework.judge import make_llm_judge
from llm.llm_registry import LLM_ROLE_CONFIG, build_llm_registry, models
from prompts import PromptRegistry

logging.basicConfig(level=logging.WARNING)

# Domain-specific framing for the LLM judge — tells it what it is scoring so
# its scoring decisions are grounded in fire-risk assessment context.
_JUDGE_SYSTEM = """\
You are an impartial evaluator scoring a fire-risk assessment agent's reasoning.
You will be given evaluation criteria and the agent's four-axis reasoning to score.
Score it from 0.0 to 1.0:
  0.0 = reasoning does not meet the criteria at all
  0.5 = reasoning partially meets the criteria
  1.0 = reasoning fully meets the criteria
Always give a brief reason. When the score is below 1.0, state specifically what the
reasoning was missing or got wrong relative to the criteria.\
"""

EXPERIMENT_PREFIX = "evaluate-node"
REPEATS = 3


def main(langsmith: bool = True, seed_only: bool = False) -> None:
    settings = get_settings()
    settings.apply_langsmith()

    llm_registry = build_llm_registry(settings, models, LLM_ROLE_CONFIG)
    prompt_registry = PromptRegistry()
    prompt_registry.register_models(Escalation, EvaluationCell)

    task = EscalationTask(
        prompt_registry=prompt_registry,
        llm_registry=llm_registry,
    )

    judge = make_llm_judge(llm_registry.get("classifier"), system_prompt=_JUDGE_SYSTEM)

    evaluators = [
        # Gate: did the model make the right escalation decision?
        # Cases where expect_escalate is None are skipped (ambiguous).
        BooleanVote(
            name="decision",
            predict=lambda o: o.escalate,
            expected=lambda x: x.get("expect_escalate"),
        ),
        # Gate: did the model fill in all the axis factors.
        AllFieldsPresent(
            name="factors",
            predict=lambda o: o.factors
        ),
        # Rubric: did the model's reasoning satisfy the authored criteria?
        # Cases with no reasoning_criteria authored are skipped by make_llm_judge.
        ReferenceJudge(
            name="reasoning_quality",
            reference=lambda x: x.get("reasoning_criteria", ""),
            actual=lambda o: o.reasoning,
            judge=judge,
            threshold=0.7,
        ),
    ]

    run_eval(
        task=task,
        evaluators=evaluators,
        dataset=ScenariosDataset(),
        llm_registry=llm_registry,
        langsmith=langsmith,
        experiment_prefix=EXPERIMENT_PREFIX,
        repeats=REPEATS,
        input_model=EscalationCase,
        output_model=Escalation,
        seed_only=seed_only,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--local", action="store_true", help="Run in-process instead of via LangSmith.")
    parser.add_argument("--seed-only", action="store_true", help="Seed the LangSmith dataset and exit.")
    args = parser.parse_args()
    main(langsmith=not args.local, seed_only=args.seed_only)
