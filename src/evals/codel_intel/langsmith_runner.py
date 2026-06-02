from __future__ import annotations

from langsmith import Client

from evals.codel_intel.dataset import RAGRetrievalDataset
from evals.framework.langsmith_adapter import seed_dataset

EXPERIMENT_PREFIX = "code-intel"
REPEATS = 1
MAX_CONCURRENCY = 1

def initialize_dataset():
    langsmith_client = Client()
    dataset = RAGRetrievalDataset()
    dataset_name = dataset.name  # derived from dataset.version — single knob
    dataset_id = seed_dataset(dataset, client=langsmith_client, dataset_name=dataset_name)
    print(f"Dataset '{dataset_name}' ready (id={dataset_id})")





