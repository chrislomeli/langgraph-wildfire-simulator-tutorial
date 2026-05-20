# Embeddings & Retrieval Data Modeling

> Depth note for **Curriculum Domain 6 — Knowledge Integration & Data
> Handling**. Also underpins **Domain 5 — Context Engineering**.
> Build target: **Step 12 — RAG Knowledge Layer**
> (`../rubric-integration-plan.md`).

This note exists because "chunking strategy" and "hybrid retrieval" were one
line each in the curriculum, and that's not enough to design a real knowledge
layer. Here's the formal layer.

---

## 1. The one load-bearing fact

> **An embedding maps text to a point in space such that *semantic similarity*
> ≈ *geometric closeness*. That is the only thing it does. It is deliberately
> lossy about everything that isn't topical gist.**

Every design decision in retrieval follows from taking that sentence
seriously. What "lossy about everything else" means in practice:

| What it loses | Example (this domain) | Consequence |
|---|---|---|
| Numeric magnitude | `"fuel moisture 4%"` vs `"40%"` | Embed almost identically — vector search cannot tell a dangerous reading from a safe one |
| Negation | `"crews were not deployed"` vs `"crews were deployed"` | Near-identical vectors; opposite meaning |
| Exact tokens / codes | fuel model `GR1` vs `GR2`; station IDs | Blurred together; a lookup returns the wrong row |
| Logic / comparison / aggregation | "incidents over 5000 acres in 2020" | Not a similarity question *at all* — no embedding answers it |

If you internalize only this table, you already design better retrieval than
most production systems, because most systems embed everything and then act
surprised when numeric and exact-match queries fail.

---

## 2. The framework: classify by *access pattern*, then choose representation

Wrong first question: *"How do I chunk this document?"*
Right first question: *"For each piece of information, how will it be
**retrieved**?"*

There are four access patterns. Each wants a different representation. Most
real corpora contain all four, which is the formal reason "text + metadata +
vector is better" is not a nice-to-have but a correctness requirement.

| Access pattern | Example (wildfire) | Representation | Store |
|---|---|---|---|
| Fuzzy / semantic recall | "tactics for steep-slope grass fires" | Embed as text | pgvector |
| Exact / range / sort / filter | `fuel_model='GR2'`, `acres>5000`, date range | **Structured column — never embedding** | Postgres column + index |
| Exact keyword / rare token / ID | "ICS-209", a RAWS station ID, a statute § | Lexical / BM25 | Postgres FTS (`tsvector`) |
| Relational / aggregate | "total resources committed across the cluster" | SQL / typed tool | Existing repos / `src/tools/` |

The professional move is not "pick one." It is **hybrid retrieval + metadata
filtering**, where:

- **Pre-filter** (filter by metadata *then* vector-search the subset) is
  usually more correct than post-filter, but needs index support. pgvector
  supports `WHERE` alongside the ANN search — use it.
- **RRF** (Reciprocal Rank Fusion) merges the dense and lexical rankings
  without tuning a weight by hand. Already in the Step 12 plan.

### The separation most failed RAG systems collapse

There are **three independent design decisions**, and the classic failure is
treating them as one ("chunk the PDF → embed the chunk → return the chunk"):

1. **What you embed** — can be a *summary*, a *generated hypothetical
   question*, or a *proposition*, not necessarily the raw text. (Optimizes
   recall.)
2. **What you return** — usually the full parent passage, for grounding.
   (Optimizes answer quality.) This is "small-to-big" / parent-document
   retrieval.
3. **What you filter on** — metadata promoted to columns *before* indexing
   (source, date, fuel model, acreage, incident type). (Optimizes precision and
   makes exact/range queries possible at all.)

### Two more named patterns you'll want

- **Contextual augmentation** — before embedding a chunk, prepend a short
  situating header ("From *NWCG Fireline Handbook*, §Watch Out Situations: …")
  so the vector encodes *this paragraph, about X, from doc Y* rather than a
  dangling sentence. This is the single highest-ROI chunking improvement and is
  cheap.
- **Chunk = retrieval unit.** Granularity is a precision/context trade: too big
  → imprecise matches and wasted context; too small → fragments that don't mean
  anything alone. Decoupling (1) from (2) above lets you have both: embed
  small, return big.

---

## 3. Failure modes (recognize these in a trace)

- **Numeric blindness** — query asks for a threshold ("moisture below 6%"),
  retrieval returns topically-similar passages with the wrong numbers. Cause:
  numbers were embedded instead of extracted to a column.
- **Negation flip** — answer cites a passage that says the opposite. Cause:
  same as above; embeddings don't encode negation.
- **Orphan chunk** — retrieved chunk is correct but unusable because it lost
  its context ("It must be applied within 30 minutes" — *what* must?). Cause:
  no contextual augmentation.
- **Filter-as-search** — system tries to answer "all 2020 incidents over 5000
  acres" by semantic search and returns plausible-but-incomplete results.
  Cause: a relational/aggregate query was routed to vector search.
- **One-representation collapse** — recall is bad because you embedded
  500-token raw chunks; grounding is bad because you embedded one-line
  summaries. Cause: (1) and (2) weren't separated.

---

## 4. Worked in the wildfire domain

The Step 12 plan lists four knowledge sources. Naively, all four get chunked
and embedded. Correctly, you classify each by access pattern *first*:

| Source | Dominant access pattern | Representation decision |
|---|---|---|
| NWCG Fireline Handbook SOPs | Semantic recall ("what's the doctrine for X") | Embed, with contextual augmentation (prepend handbook §/situation). Return parent section. |
| LANDFIRE fuel model table | Exact lookup (`fuel_model = 'GR2'`) | **Do not embed.** Structured table; expose as a typed tool, not RAG. Embedding a lookup table is actively destructive. |
| ICS-209 historical incidents | *Mixed* | Narrative → embed for "similar past fires." Acreage, dates, resources, cause → metadata **columns** so "incidents > 5000 acres, 2020, lightning-caused" is answerable at all. |
| Terrain/weather reference | Semantic + thresholds | Prose → embed. Threshold tables (slope %, RH bands) → structured, queried not embedded. |

Notice the LANDFIRE row: the instinct you had ("pick the table data out of the
plain text and structure it") is *formally* correct here — tabular data has an
exact-lookup access pattern, so prose-embedding it guarantees the failure mode.

---

## 5. Build a slice here (scoped, decisive)

Don't build the whole knowledge layer to learn this. Build the **one
experiment that makes the load-bearing fact undeniable**:

1. Take ~30 ICS-209-style records (real or synthetic) with a narrative field
   and structured fields (`acres`, `year`, `cause`, `fuel_model`).
2. Index them **two ways**: (a) naive — embed the whole record as text;
   (b) modeled — embed only the narrative, promote `acres/year/cause/fuel_model`
   to columns.
3. Run two query classes against both:
   - Semantic: *"large grass fire that jumped a containment line"*
   - Exact/range: *"lightning-caused incidents over 5000 acres in 2020"*
4. Measure recall@5 for each. The modeled index will tie on the semantic query
   and **crush** the naive index on the exact/range query (which the naive one
   essentially cannot answer). One table. That's the whole lesson, proven, not
   asserted.

This slice fits inside Step 12's `src/stores/knowledge/` and reuses the
existing Postgres + `pgvector` dependency — no new infrastructure.

> This pre-answers your "can we tweak this project for learning" question for
> *this* concept: the answer is a ~1-day scoped experiment, not a rebuild. Every
> deep-dive note should end with a slice this small.

---

## 6. Proof of competence

Cross-links to **Curriculum Domain 6**:

- [ ] Take one wildfire knowledge source and produce a written
      **access-pattern classification** of its fields, justifying which go to
      vector / metadata / lexical / SQL.
- [ ] Build the two-index slice above and produce the recall@5 comparison
      table. The table is the deliverable.
- [ ] Add contextual augmentation to the embedded source and show the
      recall@5 delta from that change alone.

---

## 7. Go deeper

- **Anthropic — "Contextual Retrieval"** — the canonical write-up of the
  contextual-augmentation pattern, with measured numbers.
- **"Lost in the Middle" (Liu et al.)** — why position in the context window
  affects whether retrieved content is even used; informs what you *return*.
- **HyDE (Hypothetical Document Embeddings)** — the query-side mirror of
  embed-a-hypothetical-question; useful when queries and documents are
  stylistically far apart.
- **Jason Liu's writing on RAG ("RAG is more than embeddings" / structured
  extraction)** — the practitioner case for the access-pattern framing above.
