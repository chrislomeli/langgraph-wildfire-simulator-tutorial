"""Run the code-intelligence RAG eval, locally or against LangSmith.

    python -m evals.codel_intel              # local, in-process (default)
    python -m evals.codel_intel --langsmith  # seed + run via LangSmith
    python -m evals.codel_intel --langsmith --seed-only

What this evaluates:
  The code-intelligence RAG agent over a pinned snapshot of this project's
  source. Each golden case is a question; KeywordPresence scores whether the
  answer cites the grounded identifiers it must.

LangSmith requires LANGCHAIN_API_KEY (or LANGSMITH_API_KEY); the local path
needs none. Both still spend LLM tokens (the agent runs either way).
"""

from __future__ import annotations

import logging

from agents.commons.schemas import Escalation, EvaluationCell
from config import get_settings
from evals.codel_intel.cases import RAGRetrievalCase
from evals.codel_intel.dataset import RAGRetrievalDataset
from evals.codel_intel.task import RAGRetrievalTask
from evals.framework.evaluators import KeywordPresence
from evals.framework.harness import run_eval
from llm.llm_registry import LLM_ROLE_CONFIG, build_llm_registry, models
from prompts import PromptRegistry
from stores.postgres import get_pg_gateway

logging.basicConfig(level=logging.WARNING)

EXPERIMENT_PREFIX = "evaluate-rag"
REPEATS = 3


def evaluation_handler(langsmith: bool = False, seed_only: bool = False) -> None:
    settings = get_settings()
    settings.apply_langsmith()

    llm_registry = build_llm_registry(settings, models, LLM_ROLE_CONFIG)
    prompt_registry = PromptRegistry()
    prompt_registry.register_models(Escalation, EvaluationCell)  # todo

    task = RAGRetrievalTask(
        prompt_registry=prompt_registry,
        llm_registry=llm_registry,
    )

    evaluators = [
        KeywordPresence(
            name="keyword-presence",
            text=lambda o: o,
            required=lambda c: c.expected["expected_keywords"],
        ),
    ]

    try:
        run_eval(
            task=task,
            evaluators=evaluators,
            dataset=RAGRetrievalDataset(),
            llm_registry=llm_registry,
            langsmith=langsmith,
            experiment_prefix=EXPERIMENT_PREFIX,
            repeats=REPEATS,
            input_model=RAGRetrievalCase,
            seed_only=seed_only,
        )
    finally:
        # Composition root owns pool teardown: the task uses the shared
        # singleton but never closes it. Drain it once here so background
        # pool threads stop cleanly on exit.
        get_pg_gateway().close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--langsmith", action="store_true", help="Run via LangSmith instead of in-process.")
    parser.add_argument("--seed-only", action="store_true", help="Seed the LangSmith dataset and exit.")
    args = parser.parse_args()
    evaluation_handler(langsmith=args.langsmith, seed_only=args.seed_only)
