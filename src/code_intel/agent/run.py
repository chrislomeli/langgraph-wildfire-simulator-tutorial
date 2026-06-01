"""
code_intel.agent.run

CLI entry point for the v1 code intelligence agent.

Usage
─────
    python -m code_intel.agent.run "how does the ingestor handle Python files?"
    python -m code_intel.agent.run "what does VectorStore.flush do?" --k 12
"""

from __future__ import annotations

import argparse
import logging

from config import Settings, get_settings
from code_intel.agent.graph import build_code_intel_graph
from code_intel.process_files.embedder import Embedder
from llm.llm_registry import LLM_ROLE_CONFIG, build_llm_registry, models
from prompts import PromptRegistry
from stores.postgres import get_pg_gateway
from stores.postgres.code_intel_repo import CodeIntelRepo
from stores.postgres.gateway import PgGateway


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="Query the code intelligence agent")
    parser.add_argument("query", help="Natural language question about the codebase")
    parser.add_argument("--k", type=int, default=8, help="Number of chunks to retrieve (default 8)")
    args = parser.parse_args()
    query_collection(query=args.query, chunks=args.k)


def query_collection(query: str, chunks: int = 8) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    pg: PgGateway
    try:
        settings = get_settings()
        settings.apply_langsmith()

        llm_registry = build_llm_registry(settings, models, LLM_ROLE_CONFIG)
        prompt_registry = PromptRegistry()
        embedder = Embedder()

        pg = get_pg_gateway()
        pg.open()

        # CodeIntelRepo.__init__ truncates — use a read-only path for queries.
        # We bypass the constructor and talk to pgvector directly via a bare repo.
        repo = _ReadOnlyCodeIntelRepo(pg)

        graph = build_code_intel_graph(
            embedder=embedder,
            repo=repo,
            llm_registry=llm_registry,
            prompt_registry=prompt_registry,
            k=chunks,
        )

        result = graph.invoke({"query": query})

        print("\n" + "=" * 70)
        print(f"Query: {query}")
        print("=" * 70)
        print(result["answer"])
        print("=" * 70)

        if result.get("chunks"):
            print(f"\n{len(result['chunks'])} chunks retrieved:")
            for c in result["chunks"]:
                path = f"{c.project_folder}/{c.file_name}:{c.start_line}-{c.end_line}"
                sym = f"  ({c.symbol_kind} {c.symbol_name})" if c.symbol_name else ""
                print(f"  {c.score:.3f}  {path}{sym}")
    finally:
        if pg:
            pg.close()


class _ReadOnlyCodeIntelRepo(CodeIntelRepo):
    """CodeIntelRepo that skips the truncate on init — safe for read-only queries."""

    def __init__(self, pg_gateway: PgGateway) -> None:
        super().__init__(pg_gateway)
        self._pg = pg_gateway  # bypass truncate_pinned_corpus


if __name__ == "__main__":
    query_collection(query="how does VectorStore.flush work? ")
