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
import asyncio
import logging

from agents.logistics.state import LogisticsAssessment
from config import get_settings
from evals.logistics.dataset import LogisticsDataset
from evals.logistics.task import LogisticsTask
from evals.wip.langsmith.langsmith_runner import run_logistics_langsmith
from llm.llm_registry import LLM_ROLE_CONFIG, build_llm_registry, models
from prompts import PromptRegistry

logging.basicConfig(level=logging.WARNING)

async def local_runner(task : LogisticsTask, dataset: LogisticsDataset, limit: int = 0):
    data = dataset.load_local()

    for i, case in enumerate(data) :
        if i >= limit > 0:
            break
        print(f"case: {case.id}")
        output, usage = await task.run(case)


async def main(seed_only: bool = False, langsmith: bool = False) -> None:
    # get setting = normal
    settings = get_settings()

    # push lang setting to os.environment()
    settings.apply_langsmith()

    # build the databaset
    dataset = LogisticsDataset()

    # wildfire framework setup for prompt and llm
    llm_registry = build_llm_registry(settings, models, LLM_ROLE_CONFIG)
    prompt_registry = PromptRegistry()
    prompt_registry.register_models(LogisticsAssessment)

    task = LogisticsTask(
        prompt_registry=prompt_registry,
        llm_registry=llm_registry,
    )

    # Same task + dataset, two runners: tracked LangSmith experiment vs the
    # in-process local loop. --langsmith selects the tracked path.
    if langsmith:
        run_logistics_langsmith(
            task=task,
            llm_registry=llm_registry,
            dataset=dataset,
            seed_only=seed_only,
        )
    else:
        await local_runner(task=task, dataset=dataset, limit=1)

    print("Done.")
    for row in llm_registry.usage_report():
        cost = row["estimated_cost_usd"]
        cost_str = f"  cost=${cost:.4f}" if cost is not None else ""
        print(
            f"  [{row['role']}] calls={row['calls']}  tokens={row['total_tokens']}"
            f" (in={row['input_tokens']} out={row['output_tokens']}){cost_str}"
        )

"""
  python -m evals.wip                      # local loop (default) — direct, in-process, fast
  python -m evals.wip --langsmith          # tracked LangSmith experiment
  python -m evals.wip --langsmith --seed-only   # just seed the dataset, skip the run
"""
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed-only", action="store_true")
    parser.add_argument(
        "--langsmith",
        action="store_true",
        help="Run the tracked LangSmith experiment instead of the local loop.",
    )
    args = parser.parse_args()
    asyncio.run(main(seed_only=args.seed_only, langsmith=args.langsmith))
