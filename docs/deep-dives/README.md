# Deep Dives

The depth layer for `../agentic-ai-curriculum.md`.

The curriculum is a **map**: it names a concept and says what mastery looks
like. These notes are the **territory**: one concept per file, taught at the
depth you'd want when you actually hit the wall on it.

## Philosophy: pull, not push

Write a deep-dive **when you hit a real need**, not upfront. A 200-page
"learn everything" doc written before you need it fails for the same reason
shallow video courses fail — depth without a felt need doesn't stick. Each note
here should exist because a real question forced it.

## Note template

Every deep-dive follows the same shape (this is what made the embeddings note
land):

1. **The one load-bearing fact** — the single insight everything else follows
   from. If you only remember one sentence, this is it.
2. **The framework** — the formal mental model: tables, decision axes, the
   "how to think about it" structure.
3. **Failure modes** — what specifically breaks when you ignore the fact, named
   so you can recognize it in a trace.
4. **Worked in the wildfire domain** — concrete examples from this project, not
   abstract ones.
5. **Build a slice here** — a small, scoped extension to the wildfire simulator
   that makes the concept viscerally real. One decisive experiment beats a big
   build.
6. **Proof of competence** — the artifact, cross-linked to the curriculum.
7. **Go deeper** — the best 2–4 resources for *this specific concept*.

## Index

- [`embeddings-and-retrieval-modeling.md`](embeddings-and-retrieval-modeling.md)
  — what an embedding actually represents, and how to decide what to embed vs.
  structure vs. filter. (Curriculum Domain 6; touches Domain 5.)
- [`agent-architecture-patterns.md`](agent-architecture-patterns.md) — the
  two-axis disentanglement (control flow vs. role decomposition), the pattern
  catalog, the four-question filter, the contract-vs-architecture principle,
  and the wildfire codebase as the worked example. (Curriculum Domain 1.)
- [`context-engineering.md`](context-engineering.md) — what the discipline
  actually covers beyond token pruning: the three layers
  (composition / shape & order / flow), the seven voices competing for
  attention, named failure modes, and the wildfire 82K-token incident as
  case study. (Curriculum Domain 5.)
