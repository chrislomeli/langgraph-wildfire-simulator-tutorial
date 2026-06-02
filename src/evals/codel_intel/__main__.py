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

from evals.codel_intel.handler import evaluation_handler

logging.basicConfig(level=logging.WARNING)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--langsmith", action="store_true", help="Run via LangSmith instead of in-process.")
    parser.add_argument("--seed-only", action="store_true", help="Seed the LangSmith dataset and exit.")
    args = parser.parse_args()
    evaluation_handler(langsmith=args.langsmith, seed_only=args.seed_only)
