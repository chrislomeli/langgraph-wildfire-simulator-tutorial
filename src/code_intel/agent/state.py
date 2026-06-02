from __future__ import annotations

from typing import Annotated

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel, Field
from typing import NewType


CodeIntelGraph = NewType("CodeIntelGraph", CompiledStateGraph)


class RetrievedChunk(BaseModel):
    """One row returned from pgvector search — flattened for easy prompt packing."""
    chunk_id: int
    project_folder: str
    file_name: str
    kind: str
    start_line: int
    end_line: int
    text: str
    symbol_name: str | None
    symbol_kind: str | None
    parent_symbol: str | None
    score: float  # cosine similarity (0–1); higher = more similar


class CodeIntelState(BaseModel):
    model_config = {"arbitrary_types_allowed": True}

    # ── Input ──────────────────────────────────────────────────────────────────
    query: str
    kind: str


    # ── Written by retrieve node ───────────────────────────────────────────────
    chunks: list[RetrievedChunk] = Field(default_factory=list)

    # ── LLM conversation ───────────────────────────────────────────────────────
    messages: Annotated[list[BaseMessage], add_messages] = Field(default_factory=list)

    # ── Output ─────────────────────────────────────────────────────────────────
    answer: str | None = None
