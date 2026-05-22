"""Run the escalation eval against the real LLM.

    python -m evals.escalation

Mirrors main_advisor.build_agent_deps for the LLM/prompt wiring, then runs
every scenario `repeats` times and prints a scorecard. Needs the same LLM
credentials/config that the app uses; makes real (billable) model calls.
"""

from __future__ import annotations

import asyncio
import logging

from agents.commons.schemas import Escalation
from config import get_settings
from evals.escalation.runner import make_real_classifier, print_scorecard, run
from evals.escalation.scenarios import SCENARIOS
from llm.llm_registry import LLM_ROLE_CONFIG, build_llm_registry, models
from prompts import PromptRegistry

logging.basicConfig(level=logging.WARNING)

REPEATS = 3


def build_classifier():
    settings = get_settings()
    settings.apply_langsmith()

    llm_registry = build_llm_registry(settings, models, LLM_ROLE_CONFIG)
    prompt_registry = PromptRegistry()
    prompt_registry.register_models(Escalation)

    llm = llm_registry.get("classifier")
    return make_real_classifier(prompt_registry, llm)


async def main() -> None:
    classify = build_classifier()
    results = await run(SCENARIOS, classify, repeats=REPEATS)
    print_scorecard(results)


if __name__ == "__main__":
    asyncio.run(main())
