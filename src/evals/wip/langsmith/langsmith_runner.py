from __future__ import annotations

from langsmith import Client

from agents.logistics.state import LogisticsAssessment
from evals.framework.evaluators import BooleanVote, ReferenceJudge
from evals.framework.judge import make_llm_judge
from evals.framework.langsmith_adapter import run_langsmith_eval, seed_dataset
from evals.logistics.cases import LogisticsCase
from evals.logistics.logistics_evaluators import AssessmentPopulated, assessment_for_judge

_JUDGE_SYSTEM = """\
You are an impartial evaluator scoring a wildfire logistics agent's resource deployment reasoning.
You will be given evaluation criteria and the agent's assessment and advisory rationale to score.
Score it from 0.0 to 1.0:
  0.0 = reasoning does not meet the criteria at all
  0.5 = reasoning partially meets the criteria
  1.0 = reasoning fully meets the criteria
Always give a brief reason. When the score is below 1.0, state specifically what the
reasoning was missing or got wrong relative to the criteria.\
"""

EXPERIMENT_PREFIX = "logistics-graph"
# Debugging defaults: 1 repetition and serial execution so breakpoints in the
# logistics node fire once per case and aren't tangled across parallel threads.
REPEATS = 1
MAX_CONCURRENCY = 1


def run_logistics_langsmith(task, llm_registry, dataset, seed_only):
    # langsmith - client, dataset seed,
    langsmith_client = Client()
    dataset_name = dataset.name  # derived from dataset.version — single knob
    dataset_id = seed_dataset(dataset, client=langsmith_client, dataset_name=dataset_name)
    print(f"Dataset '{dataset_name}' ready (id={dataset_id})")
    if seed_only:
        print("--seed-only: skipping eval run.")
        return None

    # Langsmith evaluators
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
            actual=assessment_for_judge,
            judge=judge,
            threshold=0.7,
        ),
    ]

    # runner
    print(f"Running eval: {EXPERIMENT_PREFIX} × {REPEATS} repetitions …")

    results = run_langsmith_eval(
        task=task,
        evaluators=evaluators,
        dataset_name=dataset_name,
        experiment_prefix=EXPERIMENT_PREFIX,
        num_repetitions=REPEATS,
        max_concurrency=MAX_CONCURRENCY,
        input_model=LogisticsCase,
        output_model=LogisticsAssessment,
    )
    print("Done.")
    return results