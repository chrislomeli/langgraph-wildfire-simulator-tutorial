"""evals.codel_intel.cases — golden cases for the code-intelligence RAG eval.

The corpus is a pinned snapshot of this project's own source, indexed for
vector search by CodeIntelRepo (src/stores/postgres/code_intel_repo.py).
Each case is a question whose answer lives somewhere in that code; the
``keywords`` are distinctive identifiers a grounded answer must cite, scored
by KeywordPresence (case-insensitive substring match against the answer).

Authoring guidance learned the hard way:
  - key on proper-noun identifiers (class/function names, enum values) — the
    synth model quotes those verbatim. Generic prose words ("system",
    "model") are weak discriminators and drift between runs.
  - target STABLE files that were present when the corpus was ingested.
    Brand-new files (e.g. local_runner.py) aren't in the pinned snapshot yet.
  - ``kind`` filters the retrieval scope; "source" = application code.
"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel


class RAGRetrievalCase(BaseModel):
    id: str
    description: str
    query: str
    kind: str
    expected: str = ""
    keywords: Sequence[str]
    max_chunks: int
    notes: str = ""


# ── Cases ─────────────────────────────────────────────────────────────────────


def build_cases() -> list[RAGRetrievalCase]:
    """Build and return the golden case list.

    Called by RAGRetrievalDataset.load() — not at import time.
    """
    return [
        RAGRetrievalCase(
            id="llm-token-callback",
            description="Token-usage callback wiring on the LLM registry.",
            query="How is the token-usage callback attached to chat models, and what does it track?",
            kind="source",
            keywords=("LLMRegistry", "callback", "on_llm_end", "on_tool_start"),
            max_chunks=20,
            expected=(
                "A TokenUsageCallback is constructed per role in build_llm_registry and "
                "passed to _build_chat_model, so every chat model fires it. on_llm_end "
                "accumulates token counts; on_tool_start/on_tool_end/on_tool_error log tool "
                "activity. LLMRegistry exposes reset_usage() and usage_report() over the "
                "per-role callbacks."
            ),
            notes="Baseline case — proven to pass 4/4.",
        ),
        RAGRetrievalCase(
            id="provider-credentials",
            description="How the registry resolves per-provider credentials/config.",
            query="How does the LLM registry resolve credentials and connection config for each provider?",
            kind="source",
            keywords=("Anthropic", "Bedrock", "Ollama", "api_key"),
            max_chunks=16,
            expected=(
                "_resolve_provider_kwargs is the credential seam. OpenAI/Anthropic read a "
                "single api_key from a Settings attribute (key_label); Ollama uses a base_url; "
                "Bedrock uses the AWS credential chain (optional region/profile). The role-based "
                "registry stays provider-agnostic above this function."
            ),
            notes="Keys on the provider enum members — distinctive identifiers.",
        ),
        RAGRetrievalCase(
            id="prompt-caching",
            description="Anthropic prompt-caching markup on system messages.",
            query="How is prompt caching set up for Anthropic system prompts in the LLM registry?",
            kind="source",
            keywords=("cache_control", "ephemeral", "Anthropic"),
            max_chunks=14,
            expected=(
                "make_system_message wraps the system text in an Anthropic content block with "
                "cache_control type 'ephemeral', so the system prompt is cached after the first "
                "call (cache hits ~10% of input price). For OpenAI/others it returns a plain "
                "SystemMessage and relies on server-side prefix caching."
            ),
            notes="cache_control / ephemeral are verbatim identifiers.",
        ),
        RAGRetrievalCase(
            id="vector-search",
            description="Top-k similarity retrieval of chunks from Postgres/pgvector.",
            query="How are the most similar code chunks retrieved from Postgres, and how is the score computed?",
            kind="source",
            keywords=("cosine", "vector", "score"),
            max_chunks=12,
            expected=(
                "search_chunks runs a pgvector query ordering by the <=> cosine-distance "
                "operator and returns the top-k rows. score is computed as 1 - distance so it "
                "reads as cosine similarity (0–1, higher = more similar). Results can be scoped "
                "by kind and a project_folder prefix."
            ),
            notes="Targets code_intel_repo.search_chunks.",
        ),
        RAGRetrievalCase(
            id="evaluator-strategies",
            description="The reusable evaluator strategies in the eval framework.",
            query="What evaluator strategies does the eval framework provide and how does each reduce across samples?",
            kind="source",
            keywords=("BooleanVote", "KeywordPresence", "NumericTolerance"),
            max_chunks=18,
            expected=(
                "evaluators.py provides BooleanVote (majority vote of a boolean vs expected), "
                "NumericTolerance (mean within ±tolerance, plus an MAE metric), KeywordPresence "
                "(all required substrings present), and ReferenceJudge (injected LLM-as-judge). "
                "Each owns its own sample reduction."
            ),
            notes="Class names are quoted verbatim by the synth model.",
        ),
        RAGRetrievalCase(
            id="role-model-mapping",
            description="Role→model mapping and how to swap a model for a role.",
            query="How are agent roles mapped to LLM models, and how do I change the model used for a role?",
            kind="source",
            keywords=("LLM_ROLE_CONFIG", "classifier", "role"),
            max_chunks=16,
            expected=(
                "LLM_ROLE_CONFIG maps a role name (e.g. classifier, logistics, "
                "logistics_extract, code_intel_synth, code_intel_judge) to an LLMLabel. It is "
                "the single source of truth; build_llm_registry reads it. Change a role's label "
                "there to swap the model everywhere that role is requested."
            ),
            notes="LLM_ROLE_CONFIG is the distinctive mapping name.",
        ),
        RAGRetrievalCase(
            id="stub-role-handling",
            description="What build_llm_registry does with STUB roles.",
            query="What happens to STUB roles when the LLM registry is built?",
            kind="source",
            keywords=("STUB", "skip", "registry"),
            max_chunks=12,
            expected=(
                "build_llm_registry skips any role whose label maps to None (the STUB label) — "
                "no client is registered for it. A later registry.get() on a stubbed role "
                "raises KeyError if there is no fallback."
            ),
            notes="Stricter check: relies on the synth surfacing 'skip' and 'KeyError'.",
        ),
    ]
