"""
code_intel.agent.nodes

Two nodes for the v1 linear pipeline:

    retrieve  — embed the query, search pgvector, populate state.chunks
    synthesize — pack chunks into a prompt, call LLM, write state.answer

STUB_CODE_INTEL = True  runs without an LLM or database (topology tests).
STUB_CODE_INTEL = False requires the 'code_intel_synth' role in llm_registry
                        and a live Postgres + pgvector database.
"""

from __future__ import annotations

import logging

from langchain_core.messages import HumanMessage

from code_intel.agent.state import CodeIntelState, RetrievedChunk
from code_intel.process_files.embedder import Embedder
from llm.llm_registry import LLMRegistry
from prompts import PromptRegistry
from stores.postgres.code_intel_repo import CodeIntelRepo

logger = logging.getLogger(__name__)

STUB_CODE_INTEL = False


# ---------------------------------------------------------------------------
# retrieve node
# ---------------------------------------------------------------------------

def make_retrieve_node(embedder: Embedder, repo: CodeIntelRepo, k: int = 8):
    """Return a node function that embeds the query and fills state.chunks."""

    def retrieve(state: CodeIntelState) -> dict:
        if STUB_CODE_INTEL:
            logger.info("STUB: skipping retrieval")
            return {"chunks": []}

        vector = embedder.embed(state.query)
        kind = state.kind or None
        rows = repo.search_chunks(vector=vector, k=k, kind=kind)

        chunks = [
            RetrievedChunk(
                chunk_id=row["chunk_id"],
                project_folder=row["project_folder"],
                file_name=row["file_name"],
                kind=row["kind"],
                start_line=row["start_line"],
                end_line=row["end_line"],
                text=row["text"],
                symbol_name=row["symbol_name"],
                symbol_kind=row["symbol_kind"],
                parent_symbol=row["parent_symbol"],
                score=float(row["score"]),
            )
            for row in rows
        ]
        logger.info("retrieved %d chunks for query %r", len(chunks), state.query[:60])
        return {"chunks": chunks}

    return retrieve


# ---------------------------------------------------------------------------
# synthesize node
# ---------------------------------------------------------------------------

def make_synthesize_node(llm_registry: LLMRegistry, prompt_registry: PromptRegistry):
    """Return a node function that packs chunks into a prompt and calls the LLM."""

    def synthesize(state: CodeIntelState) -> dict:
        if STUB_CODE_INTEL:
            return {"answer": "STUB answer — set STUB_CODE_INTEL=False to use the LLM."}

        if not state.chunks:
            return {"answer": "No relevant code found for this query."}

        # Build the context_blocks list the prompt template iterates over.
        context_blocks = []
        for c in state.chunks:
            path = f"{c.project_folder}/{c.file_name}"
            symbol = None
            if c.symbol_kind and c.symbol_name:
                symbol = f"{c.symbol_kind} {c.symbol_name}"
                if c.parent_symbol:
                    symbol = f"{c.parent_symbol}.{c.symbol_name}"
            context_blocks.append({
                "path": path,
                "start_line": c.start_line,
                "end_line": c.end_line,
                "text": c.text,
                "symbol": symbol,
            })

        prompt_text = prompt_registry.render(
            "code_intel_synth",
            {"query": state.query, "context_blocks": context_blocks},
        )

        llm = llm_registry.get("code_intel_synth")
        human = HumanMessage(content=prompt_text)
        response = llm.invoke([human])
        answer = response.content if hasattr(response, "content") else str(response)

        logger.info("synthesized answer (%d chars) for query %r", len(answer), state.query[:60])
        return {"answer": answer, "messages": [human, response]}

    return synthesize
