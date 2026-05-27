"""Run the logistics eval against LangSmith.

    python -m evals.logistics [--seed-only]

Requires:
  - LANGCHAIN_API_KEY  (or LANGSMITH_API_KEY) in environment
  - LLM credentials the app uses (same as production)

On first run pass --seed-only to push the dataset to LangSmith before
evaluating. Subsequent runs can omit it — LangSmith uses the existing
dataset and appends a new experiment run.

What this evaluates:
  The full LogisticsGraph (logistics_agent ReAct loop → extract_plan) for
  each of the 4 golden cases. data_store=None so tool calls are skipped and
  the agent reasons from the authored sector analysis alone.

  Three evaluators:
    advisory_decision  — BooleanVote: did the agent correctly issue or
                         withhold a ResourceAdvisory? Cases where
                         expect_advisory is None are skipped (ambiguous).
    assessment_populated — all prose fields non-empty across runs.
    advisory_quality   — ReferenceJudge: does the assessment reasoning
                         satisfy the authored rubric criteria?
"""

from __future__ import annotations

import argparse
import logging

from langsmith import Client

from agents.logistics.state import LogisticsAssessment
from config import get_settings
from evals.logistics.cases import LogisticsCase
from evals.logistics.dataset import LogisticsDataset
from evals.logistics.logistics_evaluators import AssessmentPopulated
from evals.logistics.task import LogisticsTask
from evals.framework.evaluators import BooleanVote, ReferenceJudge
from evals.framework.judge import make_llm_judge
from evals.framework.langsmith_adapter import run_langsmith_eval, seed_dataset
from llm.llm_registry import LLM_ROLE_CONFIG, build_llm_registry, models
from prompts import PromptRegistry

logging.basicConfig(level=logging.WARNING)

_JUDGE_SYSTEM = """\
You are an impartial evaluator scoring a wildfire logistics agent's resource deployment reasoning.
You will be given evaluation criteria and the agent's assessment and advisory rationale to score.
Respond with a single float between 0.0 and 1.0 — nothing else.
  0.0 = reasoning does not meet the criteria at all
  0.5 = reasoning partially meets the criteria
  1.0 = reasoning fully meets the criteria\
"""

DATASET_NAME = "logistics-golden-v1"
EXPERIMENT_PREFIX = "logistics-graph"
REPEATS = 3


def main(seed_only: bool = False) -> None:
    settings = get_settings()
    settings.apply_langsmith()

    langsmith_client = Client()
    dataset = LogisticsDataset()

    dataset_id = seed_dataset(dataset, client=langsmith_client, dataset_name=DATASET_NAME)
    print(f"Dataset '{DATASET_NAME}' ready (id={dataset_id})")

    if seed_only:
        print("--seed-only: skipping eval run.")
        return

    llm_registry = build_llm_registry(settings, models, LLM_ROLE_CONFIG)
    prompt_registry = PromptRegistry()
    prompt_registry.register_models(LogisticsAssessment)

    task = LogisticsTask(
        prompt_registry=prompt_registry,
        llm_registry=llm_registry,
    )

    judge = make_llm_judge(llm_registry.get("classifier"), system_prompt=_JUDGE_SYSTEM)

    evaluators = [
        BooleanVote(
            name="advisory_decision",
            predict=lambda o: o.advisory is not None,
            expected=lambda x: x.get("expect_advisory"),
        ),
        AssessmentPopulated(name="assessment_populated"),
        ReferenceJudge(
            name="advisory_quality",
            reference=lambda x: x.get("advisory_criteria", ""),
            actual=lambda o: f"{o.assessment}\n\nRationale: {o.advisory_rationale}",
            judge=judge,
            threshold=0.7,
        ),
    ]

    llm_registry.reset_usage()

    print(f"Running eval: {EXPERIMENT_PREFIX} × {REPEATS} repetitions …")
    results = run_langsmith_eval(
        task=task,
        evaluators=evaluators,
        dataset_name=DATASET_NAME,
        experiment_prefix=EXPERIMENT_PREFIX,
        num_repetitions=REPEATS,
        input_model=LogisticsCase,
        output_model=LogisticsAssessment,
    )
    print(f"Done. View results at: {results.experiment_results_url}")
    for row in llm_registry.usage_report():
        cost = row["estimated_cost_usd"]
        cost_str = f"  cost=${cost:.4f}" if cost is not None else ""
        print(
            f"  [{row['role']}] calls={row['calls']}  tokens={row['total_tokens']}"
            f" (in={row['input_tokens']} out={row['output_tokens']}){cost_str}"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed-only", action="store_true")
    args = parser.parse_args()
    main(seed_only=args.seed_only)
