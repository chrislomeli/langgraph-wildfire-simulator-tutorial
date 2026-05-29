# Code Intelligence Agent — Project Design Sketch

*A LangGraph agent over the wildfire-simulator codebase, with hybrid RAG as
one of its tools. Designed to demonstrate agentic competence with
professional-level RAG underneath — not the other way around.*

---

## Up front Phased build

Each phase ends with a measurable result. None of the phases require the
later ones to be useful.

See details below for more information

### Phase 0 — Scaffolding (1–2 sessions)
~~- Set up pgvector schema (or reuse journal_agent's)~~ use wildfire
- Implement ingestion: walk the tree, extract chunks (naive baseline first),
  embed, store with metadata
- Stand up Layer A eval scaffolding with 5 hand-authored queries
- Verify: can retrieve anything, can score retrieval

### Phase 1 — Baseline + structural chunking (1–2 sessions)
- Implement tree-sitter chunking alongside naive
- Build v1 graph: linear pipeline, single retrieval, synthesize
- Expand eval to full 15–20 queries
- **Skill check delta:** structural beats naive on the eval, with numbers
  and a per-query explanation

### Phase 2 — Hybrid + reranking + decomposition (2–3 sessions)
- Add Postgres FTS for keyword search
- Implement RRF fusion
- Add FlashRank reranker
- Move to v2 graph: planner-decompose + parallel sub-retrievals + fusion
- Author Layer B answer-quality eval
- **Skill check deltas:** hybrid beats vector on identifier-heavy queries;
  rerank improves top-k precision; decomposition improves answer correctness
  on multi-part questions

### Phase 3 — ReAct loop + fallback (2–3 sessions)
- v3 graph: ReAct retrieve loop with iteration cap and forced-exit synthesis
- Implement fallback: empty retrieval → broaden or route to different tool
- Optional: call-graph lookup tool via tree-sitter
- **Skill check:** agent answers a multi-hop exploratory question correctly,
  demonstrates fallback when a retrieval returns nothing

### Phase 4 (optional) — Personal-tool polish
- CLI ergonomics (file:line citations rendered well, syntax highlighting)
- Index more repos
- Watch-mode re-indexing

Only do Phase 4 if the tool feels actually useful by Phase 3.

---

## What this project intentionally does NOT explore

Honest scope limits, so the project stays focused:

- **Multi-tenant or enterprise indexing infra** — CDC, sharding, namespace
  isolation. Skip entirely.
- **Embedding migrations** — pick MiniLM-L6 and stay.
- **ColBERT, late-interaction retrieval** — read about, don't build.
- **GraphRAG / Neo4j** — the call-graph tool in Phase 3 is the closest this
  project gets; no separate graph DB.
- **Online evaluation in production** — eval is offline-only.
- **Streaming / async at scale** — synchronous is fine for this corpus size.
- **Cost optimization** — small corpus, cheap embeddings; not the lesson.

---

---

## Goal

Build a LangGraph agent that answers questions about a codebase by
decomposing the question, routing each sub-question to the right retrieval
tool, fusing and reranking results, and synthesizing a grounded answer with
citations. The project exists primarily to demonstrate **agentic
orchestration competence** and secondarily to demonstrate **professional RAG
competence**. RAG is the tool layer; the agent is the spine.

## Non-goals

To keep scope honest:

- Not building a RAG framework, library, or product
- Not learning enterprise indexing infrastructure (CDC, sharding, multi-tenant
  isolation, embedding migration pipelines)
- Not chasing the long tail of advanced retrieval research (ColBERT,
  GraphRAG, differentiable retrieval) — read about them, don't build them
- Not aiming for a production UI; CLI output is sufficient
- Not building multi-modal (the corpus is text/code)

The personal-tool use case (cross-project code search) is welcome if it
emerges, but is not driving design decisions.

## Why this project

It exercises the right surface of the personal RAG rubric
(`docs/rag-learning-rubric.md`, Part A — Must Touch) **in the context of an
agent**, which matches the stated primary identity goal (agentic expert) and
secondary goal (professionally competent at RAG). Specific Must-Touch items
this project hits:

- Hybrid search (dense + sparse)
- Reranking
- Chunking strategy experimentation
- Parent-child chunking (Phase 2+)
- Query transformation / decomposition
- Multi-query expansion (Phase 2+)
- Eval-driven development (carries directly from the wildfire eval work)
- Faithfulness / groundedness measurement
- Context precision & recall
- LLM-as-judge systems
- Observability & tracing (LangSmith — already wired)
- **Agentic / iterative retrieval in LangGraph**
- **Multi-source routing**
- Retrieval fallback strategies
- Context packing / prompt construction
- Lost-in-the-middle awareness (long-document spot check)

That's the bulk of Part A in a single coherent project.

---

## Corpus

### What goes in
- `src/**/*.py` — source code
- `tests/**/*.py` — tests (often the best "how is X used" examples)
- `docs/**/*.md` — design docs, rubrics, this file
- `src/prompts/templates/**/*.j2` — prompt templates (substantive content)
- `*.toml`, manifest YAMLs — small, occasionally queried

### What stays out
- `.venv/`, `__pycache__/`, `.git/`, build outputs
- Lockfiles (`uv.lock`)
- Binary or large data files (CSV sensor data, images)

### Metadata per chunk
- `file_path`, `language`, `kind` (source / test / doc / config / template)
- For code: `symbol_name` (function/class), `line_start`, `line_end`
- `last_modified` (cheap, rarely queried, occasionally useful)

### Stability
Pin the corpus to a specific commit during eval iteration. Re-author ground
truth when the corpus changes materially.

---

## Chunking

Three strategies, intentionally implemented in this order so the deltas
become teachable comparisons:

1. **Naive (baseline)** — fixed-size character chunks with overlap. Bad
   for code; useful as the baseline that hybrid + structural beats.
2. **Structural via tree-sitter** — for code: chunk per function / class /
   method, with the docstring attached. For markdown: chunk by heading
   hierarchy. This is the right baseline for code intelligence.
3. **Parent-child (Phase 2+)** — embed small units (function bodies) but
   return larger context (the whole file, or function + its callers) at
   query time. Resolves the chunk-size precision/context trade-off.

Tree-sitter handles all the file types in scope (Python, Markdown, YAML,
TOML). No per-language parsers to write.

---

## Retrieval tools (agent-facing)

The agent calls these as LangGraph tools. Each is a deterministic function
with a typed signature; the agent decides which to call and with what args.

| Tool | Purpose | Implementation |
|---|---|---|
| `semantic_search(query, k, filters)` | Find chunks semantically similar to a query | pgvector cosine over MiniLM-L6 embeddings (reuse journal_agent infra) |
| `keyword_search(term, k, filters)` | Exact-identifier matches: function names, class names, error messages | Postgres FTS (`tsvector`/`tsquery`) |
| `hybrid_search(query, k, filters)` | Run both above, fuse via RRF | Wraps the two with rank fusion |
| `rerank(query, chunks, top_k)` | Precision pass on top-N retrieved | Cross-encoder (FlashRank, local) |

Optional Phase 3+:
| Tool | Purpose |
|---|---|
| `call_graph_lookup(symbol)` | "Who calls X / what does X call" via tree-sitter graph |
| `file_context(path)` | Return the whole file given a path hint |

All tools accept a `filters` dict for metadata-based scoping (kind, language,
path prefix). Same filter shape across tools so the agent learns one
contract.

---

## Graph topology

The agent grows in three versions. Earlier versions stay valid as fallbacks
or for simple queries.

### v1 — Linear pipeline (Phase 1)
```
START → retrieve_hybrid → rerank → synthesize → END
```
Single retrieval call. No decomposition. The shape used for short, focused
queries. Establishes the baseline numbers and proves the retrieval layer
works.

### v2 — Planner + parallel retrieval (Phase 2)
```
START → plan_decompose → ┬─ retrieve_hybrid(subq_1) ─┐
                         ├─ retrieve_hybrid(subq_2) ─┤ → fuse → rerank → synthesize → END
                         └─ retrieve_hybrid(subq_n) ─┘
```
Planner LLM breaks a complex question into 1–N sub-queries. Each runs in
parallel. Results fused (RRF or simple union), reranked once, synthesized.
This is multi-query expansion + decomposition in one shape.

### v3 — ReAct over retrieval (Phase 3)
```
START → react_agent ──(retrieve / rerank / call_graph_lookup tool calls)──┐
        ↑                                                                  │
        └──────────────────────────────────────────────────────────────────┘
                              (loop, with iteration cap)
                              ↓
                       extract_answer → END
```
Standard ReAct loop. The agent decides whether it has enough information or
needs to call another retrieval tool. Includes:
- **Iteration cap** (lesson carried directly from the logistics agent)
- **Forced-exit synthesis** when the cap is hit (lesson carried directly)
- **Fallback handling** when a retrieval returns empty: agent broadens the
  query or routes to a different tool

### Routing
The agent chooses which version applies (or routes between tools within v3)
based on the question. A trivial classifier-prompt up front:
*"Is this a single-fact lookup, a multi-part question, or an exploratory
investigation?"* → routes to v1 / v2 / v3.

---

## Evaluation — two layers

This is where the project's Tier 1 lineage pays off. Carry over the same
framework (`src/evals/framework/`) and the same patterns (BooleanVote,
ReferenceJudge, structured-output judge with reasons, single-version-knob
datasets).

### Layer A — Retrieval quality
Author 15–20 queries spanning four categories:
- **Conceptual** (vector's home turf): *"How do we handle tool failures?"*
- **Identifier-heavy** (keyword's home turf): *"Find usages of
  `_balance_dangling_tool_calls`"*
- **Mixed** (hybrid should win): *"How is the logistics prompt template
  rendered?"*
- **Onboarding** (free-form): *"What's the entry point to the cluster
  agent?"*

Ground truth: hand-authored list of relevant `(file_path, symbol_name)`
tuples per query. ~2–3 relevant chunks per query.

Metrics: **Precision@5, Recall@5, MRR.** Three numbers, intuitive, sufficient
for a learning project. Keep these **hand-rolled** — Ragas offers
`context_precision` and `context_recall`, but those use LLM judges, whereas
your hand-authored ground truth makes deterministic IR metrics simpler,
cheaper, and more controllable. Skip Ragas at this layer.

Use this layer to compare strategies: naive vs structural chunking, pure
vector vs hybrid, hybrid vs hybrid+rerank, decomposition on vs off.

### Layer B — Answer quality
The agent's final synthesized answer, evaluated by LLM-as-judge metrics.
Same conceptual pattern as `advisory_quality` in the wildfire eval, but
**use Ragas** for the metric implementations here rather than hand-authoring
the judge prompts. The three Ragas metrics that map directly to what Layer B
needs to measure:

- **`faithfulness`** — does every claim in the answer have support in the
  retrieved context? Catches hallucinated functions, fabricated APIs.
- **`answer_relevance`** — does the answer actually address the question
  asked? Catches plausible-but-off-topic responses.
- **`answer_correctness`** — combines factual accuracy and semantic
  similarity against a ground-truth answer. Needs authored reference
  answers per query (worth it for the multi-part / onboarding queries).

**Integration pattern**: wrap each Ragas metric as an `Evaluator` in
`src/evals/framework/` so it conforms to the existing protocol:

```python
class RagasFaithfulness:
    name = "faithfulness"
    def evaluate(self, ex: CaseExecution) -> list[Score]:
        # call ragas with (question, contexts, answer)
        # route the float score and explanation into Score(...)
```

Plug into the same `run_langsmith_eval(evaluators=[...])` call you already
use. Scores and reasons flow through `Score.detail` → LangSmith comment via
the existing adapter. No new infrastructure.

**Bootstrapping the test set**: Ragas's `TestsetGenerator` can synthesize
question/ground-truth-answer pairs from your corpus chunks. Use it to
generate ~50–100 candidate Layer B queries, then curate down to a clean
set. This is the legitimate "synthesize *queries* against *real* data"
pattern — corpus stays authentic, only the questions are bootstrapped.

### Why two layers
Retrieval can be perfect and the answer can still be wrong (synthesis
hallucinates). Answer can be right and retrieval can be subtly bad (the
right chunk happened to be in the LLM's training data). Measuring both
separately is the only way to tell which layer needs work.

### Eval tooling at a glance

| Layer | Metrics | Implementation | Why |
|---|---|---|---|
| **A (Retrieval)** | Precision@5, Recall@5, MRR | Hand-rolled in `src/evals/framework/` | Deterministic IR metrics over authored ground truth — cheaper, more controllable than LLM-judge versions |
| **B (Answer quality)** | `faithfulness`, `answer_relevance`, `answer_correctness` | Ragas, wrapped as `Evaluator`s in the existing framework | Standard, well-vetted judge prompts; integrates cleanly with the LangSmith adapter we already built |
| **B test set bootstrap** | Synthesized Q&A pairs from corpus | Ragas `TestsetGenerator` | Legitimate use of synthetic data (corpus stays real, only questions are synthesized) |

The hand-rolled-then-libraries progression mirrors the wildfire eval work:
hand-rolling the patterns first taught the lessons; reaching for the
library now is the professional move once the patterns are understood.


## Skill checks (proof you've arrived)

By the end of this project you should be able to demonstrate, with numbers
and a worked explanation:

1. **Structural chunking beats naive** on a held-out retrieval eval.
2. **Hybrid retrieval beats pure vector** on identifier-heavy queries
   specifically (not just on average — be able to show *which queries*
   improved).
3. **Reranking improves top-k precision** on top of hybrid retrieval.
4. **Query decomposition improves answer correctness** on multi-part
   questions (Layer B eval).
5. **The agent handles a failed retrieval** by falling back to a different
   tool or broadened query, without producing a hallucinated answer.
6. **Faithfulness is measurable** — you can show whether the agent's claims
   are grounded in retrieved context, and catch when they aren't.

These map directly to the Must-Touch items in the RAG rubric and to the
Tier 2 / Tier 4 skill checks in the engineering rubric.

---

## Decisions (settled before Phase 0)

1. **Storage** — use the existing wildfire database (pgvector already
   enabled); add new tables under a `code_intel.*` naming convention for
   chunks and metadata. Self-contained in this repo; no cross-project
   dependency on `journal_agent`.

2. **Embedding model** — `jinaai/jina-embeddings-v2-base-code`. Code-aware
   embeddings should outperform a generic sentence transformer on code
   queries; the small extra setup cost is worth it. (Not following
   `journal_agent`'s MiniLM-L6 choice here — different corpus, different
   right answer.)

3. **Reranker** — FlashRank (local, free, fast). No hosted-service
   dependency.

4. **LLM roles** — two new roles in `llm_registry`, distinct from the
   wildfire roles, following the wildfire pattern of separating worker and
   judge so they can be tuned independently:
   - **`code_intel_synth`** — agent synthesis (the doer)
   - **`code_intel_judge`** — answer-quality judging (the grader; also used
     by the Ragas metric wrappers)

5. **Project location** — `src/code_intel/` in this repo. Designed to be
   **repo-portable** from day one: corpus path is a CLI argument
   (`--repo /path/to/repo`), not hardcoded. No imports from
   `agents/cluster/`, `agents/logistics/`, `agents/supervisor/`, or
   `world/` — only from `evals/framework/`, `llm/`, `prompts/`,
   `stores/postgres/`. Keeps the boundary clean so extraction to its own
   repo later is a copy + small `setup.py`, not a re-architecture.

---

## Closing framing

This is a portfolio project for an agentic engineer who happens to use RAG
fluently. The win condition is not "I built a code search." It's: *"I can
design and ship an agent that decomposes questions, routes across retrieval
modalities, recovers from retrieval failures, and produces grounded answers
— and I can prove every layer of it works with numbers."*

Hold this doc loosely. Revise as the build teaches you what was wrong about
the sketch.
