"""
code_intel.agent.graph

v1 linear pipeline:

    START → retrieve → synthesize → END

Build once at startup, invoke with {"query": "..."}.
"""

from __future__ import annotations

import logging

from langgraph.graph import END, START, StateGraph

from code_intel.agent.nodes import make_retrieve_node, make_synthesize_node
from code_intel.agent.state import CodeIntelGraph, CodeIntelState
from code_intel.process_files.embedder import Embedder
from llm.llm_registry import LLMRegistry
from prompts import PromptRegistry
from stores.postgres.code_intel_repo import CodeIntelRepo

logger = logging.getLogger(__name__)


def build_code_intel_graph(
    *,
    embedder: Embedder,
    repo: CodeIntelRepo,
    llm_registry: LLMRegistry,
    prompt_registry: PromptRegistry,
    k: int = 8,
) -> CodeIntelGraph:
    """Compile and return the v1 code intelligence graph.

    Parameters
    ----------
    embedder       : Embeds the query for pgvector search.
    repo           : CodeIntelRepo backed by a live PgGateway.
    llm_registry   : Must have 'code_intel_synth' registered.
    prompt_registry: Must have 'code_intel_synth' template loaded.
    k              : Number of chunks to retrieve per query.
    """
    builder = StateGraph(CodeIntelState)

    builder.add_node("retrieve", make_retrieve_node(embedder, repo, k=k))
    builder.add_node("synthesize", make_synthesize_node(llm_registry, prompt_registry))

    builder.add_edge(START, "retrieve")
    builder.add_edge("retrieve", "synthesize")
    builder.add_edge("synthesize", END)

    return CodeIntelGraph(builder.compile())
