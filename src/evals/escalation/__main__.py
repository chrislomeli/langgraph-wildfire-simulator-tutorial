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

from langsmith import Client

from agents.commons.schemas import Escalation, EvaluationCell
from config import get_settings
from evals.escalation.cases import EscalationCase
from evals.escalation.dataset import ScenariosDataset
from evals.escalation.task import EscalationTask
from evals.framework.evaluators import BooleanVote
from evals.framework.langsmith_adapter import run_langsmith_eval, seed_dataset
from llm.llm_registry import LLM_ROLE_CONFIG, build_llm_registry, models
from prompts import PromptRegistry

logging.basicConfig(level=logging.WARNING)

DATASET_NAME = "escalation-golden-v2"
EXPERIMENT_PREFIX = "evaluate-node"
REPEATS = 3


def main(seed_only: bool = False) -> None:
    settings = get_settings()
    settings.apply_langsmith()

    client = Client()
    dataset = ScenariosDataset()

    dataset_id = seed_dataset(dataset, client=client, dataset_name=DATASET_NAME)
    print(f"Dataset '{DATASET_NAME}' ready (id={dataset_id})")

    if seed_only:
        print("--seed-only: skipping eval run.")
        return

    llm_registry = build_llm_registry(settings, models, LLM_ROLE_CONFIG)
    prompt_registry = PromptRegistry()
    prompt_registry.register_models(Escalation, EvaluationCell)

    task = EscalationTask(
        prompt_registry=prompt_registry,
        llm_registry=llm_registry,
    )

    evaluators = [
        BooleanVote(
            name="decision",
            predict=lambda o: o.get("escalate", False) if isinstance(o, dict) else o.escalate,
            expected=lambda x: x.get("expect_escalate"),
        ),
    ]

    print(f"Running eval: {EXPERIMENT_PREFIX} × {REPEATS} repetitions …")
    results = run_langsmith_eval(
        task=task,
        evaluators=evaluators,
        dataset_name=DATASET_NAME,
        experiment_prefix=EXPERIMENT_PREFIX,
        num_repetitions=REPEATS,
        input_model=EscalationCase,
        output_model=Escalation,
    )
    print(f"Done. View results at: {results.experiment_results_url}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed-only", action="store_true")
    args = parser.parse_args()
    main(seed_only=args.seed_only)
