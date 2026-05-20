# Context Engineering

> Depth note for **Curriculum Domain 5 — Context Engineering**. Companions:
> `embeddings-and-retrieval-modeling.md` (Domain 6), `agent-architecture-patterns.md`
> (Domain 1). Build link: relevant to every prompt rewrite in `eval-design.md`.

This note exists because "context engineering" is widely conflated with token
pruning and budget management. Those are the plumbing. The discipline is
broader and most of the leverage lives upstream.

---

## 1. The one load-bearing fact

> **The model is a function of its inputs. At inference time you don't control
> the weights — you only control the context. So the context window is the
> *only* lever you have over model behavior on a given call, and curating it
> deliberately is the highest-leverage thing you do at inference time.**

The corollary is the conceptual shift most people miss:

> **Prompt engineering is to context engineering as page design is to
> publication design.** Prompt engineering treats one call as the unit; context
> engineering treats the *flow of information through calls* as the unit —
> what's persistent, what's just-in-time, what's compressed, what's isolated,
> what arrives in what order.

If you find yourself only tuning the system prompt, you're doing prompt
engineering. If you're deciding *which voices belong in this call vs.
another*, *what gets retrieved when*, *how history is compressed across
turns*, and *which sub-tasks get their own clean context* — that's context
engineering.

---

## 2. The framework — three layers, ordered by leverage

Most leverage is in Layer 1. Most teams spend time in Layer 3 because that's
where the alarming token bills show up. Reverse that instinct.

### Layer 1 — Composition (what goes in)

Every call is a mix of "voices" competing for the model's budget *and* its
attention. The seven canonical voices:

| Voice | Examples | Cost shape |
|---|---|---|
| **Instructions / role** | System prompt, persona, task framing | Stable across calls (cacheable); compounds with each iteration in loops |
| **Tool definitions** | JSON schemas the model sees for available tools | Fixed per-call cost; *each tool costs both tokens and attention* (more tools = worse tool selection) |
| **Examples / few-shot** | In-context demonstrations | Linear in count; high marginal value when tasks are unusual, near-zero when tasks are common |
| **Retrieved knowledge** | RAG passages, doctrine, lookup-table excerpts | Bursty; grows with k; competes hard with everything else |
| **Recalled memory** | Facts from prior runs, episodic memory | Often the noisiest voice; stale memory is a category of context poisoning |
| **Run history** | Accumulated messages within this run | Unbounded in autonomous loops; the killer in long runs |
| **Output spec** | Schema, format requirements, what to commit to | Small but load-bearing (anti-hedging) |

The Layer 1 questions:

- **Which voices belong in *this* call?** Not every call needs every voice.
- **Just-in-time vs. pre-stuffed?** Retrieve when the agent asks (tool-driven),
  or pack everything up front?
- **Where does each voice live?** Prompt, tool, scenario data, separate node?
- **What's the contract with the model?** What is it *responsible* for given
  what's in front of it? Contradictory voices = arbitrary behavior.

### Layer 2 — Shape and order

Once you've decided what's in, the *form* matters:

- **Position effects.** Lost-in-the-middle is real — content in the middle of
  long contexts gets ignored even if relevant. Recency and primacy biases are
  real. Instruction placement (top vs. bottom) matters by model.
- **Format effects.** Structured output forces commitment (categorical enums
  anti-hedge); free text invites it. JSON, XML, and Markdown carry different
  reading biases. Tables vs. prose for the same facts.
- **Delimiting voices.** How the model knows where one voice ends and another
  begins. Mixing prose retrieval with prose instructions invites blending.
- **Chain-of-thought scaffolding.** "Reason step by step before answering" vs.
  "answer first, justify after" — different output distributions for the same
  prompt.

### Layer 3 — Flow (across calls, over time)

This is where token pruning lives. Useful, often misnamed as "the whole thing":

- **Compression.** Rolling summarization, hierarchical summaries
  (recent-detailed + older-compressed), structured-state extraction (turn a
  chat into a fact set).
- **Memory.** Scratchpads as externalized memory (don't keep it in context;
  write it to state/disk and retrieve when needed). Episodic memory across
  sessions. Staleness/invalidation policy.
- **Isolation.** Spawn a sub-agent with a *clean* context for a specialized
  task; return only the result. The supervisor never sees the sub-agent's
  history.
- **Plumbing.** Token accounting, pruning rules, prompt caching, KV-cache
  awareness. Necessary infrastructure.

---

## 3. Failure modes (recognize these in a trace)

Each has a name and a typical cause. If you can name what's wrong, you can
fix the right layer.

- **Context rot.** Quality degrades over long runs even when the window
  isn't full. *Cause:* distractor accumulation; attention dispersion across
  history. *Fix at Layer 3:* periodic compression; or Layer 1: reset to a
  digest at handoff points.
- **Context poisoning.** A bad earlier turn (hallucination, wrong tool
  result, off-topic tangent) gets carried forward and corrupts later
  reasoning. *Cause:* append-only history without curation. *Fix:* surgical
  removal of bad turns; or summarize-and-restart at trust boundaries.
- **Context clash.** Contradictory information in context — system prompt
  says one thing, retrieved doc says another. *Cause:* uncurated retrieval;
  multiple instruction sources. *Fix at Layer 1:* reconcile sources before
  injection; pick a single authority.
- **Distraction.** Irrelevant details derail focus. *Cause:* too much
  "just in case" content. *Fix at Layer 1:* be ruthless about what each call
  needs.
- **Lost in the middle.** Information in the middle of long context gets
  ignored. *Cause:* position bias. *Fix at Layer 2:* put the most important
  voices at the top *and* bottom; or split into multiple shorter calls.
- **Tool-induced attention drift.** Long tool definitions push instructions
  into the noise; tool selection degrades. *Cause:* too many tools, too
  verbose tool descriptions. *Fix at Layer 1:* fewer, tighter tools;
  task-conditional tool exposure.
- **Stale memory.** Recalled memory from prior runs is no longer accurate.
  *Cause:* no staleness check or write-time invalidation. *Fix at Layer 3:*
  version memories; treat recall as a hypothesis, not ground truth.
- **Context starvation.** Too little context to make the decision (opposite
  failure). *Cause:* over-aggressive pruning. *Fix:* per-voice minimum
  guarantees, not blanket cuts.

---

## 4. Worked in the wildfire domain

What's there, and what it teaches.

### Already present (with file refs)
- `src/prompts/registry.py` — centralized prompt management with versioning
  (`templates/evaluate/v1/`). Layer 1 hygiene. The version dir is a small
  but important detail — it means a context change is identifiable, not silent.
- `src/llm/token_callback.py` — the plumbing layer (Layer 3, #8). It's
  *infrastructure for measurement*, not measurement itself; nothing currently
  consumes its output to produce a per-voice breakdown.
- `agents/logistics/nodes.py:235` — `messages = [SystemMessage(system_prompt)] + messages`.
  System prompt prepended at every ReAct iteration. That's a deliberate Layer 2
  choice — keeps instructions primary even as history accumulates. Worth
  recognizing as good engineering; many ReAct implementations let the system
  prompt drift back as history grows.

### The 82K-token incident — a Layer 3 patch over a Layer 1/2 problem
The `MAX_LOGISTICS_ITERATIONS = 4` cap (`logistics/nodes.py:258`) was
introduced after a runaway loop that "accumulated 82K tokens in one tick." The
cap is *reactive* — it prevents the runaway from happening but accepts low-quality
output when the loop hits the cap (truncated reasoning, stub tool results from
`_balance_dangling_tool_calls`).

A Layer 1/2 fix would prevent the runaway in the first place: per-iteration
history compression, fewer tools, or per-iteration tool-set rotation
("on iteration N, only these tools are available"). Both fixes can coexist —
the iteration cap is a safety belt; Layer 1/2 work is the design that means
the belt rarely engages. **Naming this distinction matters because the cap is
currently doing the work two layers are supposed to do.**

### The categorical thresholds question — a Layer 1 composition decision
`scripts/data_wrangling/fire_model/categorical_thresholds.json` (if these are
RMRS-derived weather → risk-level thresholds) is a perfect Layer 1 question
right now, mirroring the access-pattern framework from the embeddings note but
applied to *grounding doctrine* rather than retrieval data:

| If the thresholds are… | Then they belong in… |
|---|---|
| Always-needed core doctrine (every call uses them) | **System prompt** — embedding them in retrievable knowledge is an anti-pattern: you'd fetch the same thing every call |
| Lookup tables consulted by exact value | **Structured tool** — the LLM calls `classify(metric, value) → category`. Not embedded text. (Embeddings can't do exact-value lookup; same rule as the embeddings deep-dive.) |
| Reference material consulted occasionally | **RAG** — long-tail, retrieved only when relevant |

The wrong move (and a common one): dump all thresholds into the system prompt
"just to be safe." That's both wasteful (every call pays the cost) and
counterproductive (tool descriptions and instructions get pushed deeper into
the context, attention dilutes across mostly-irrelevant numbers).

### The `evaluate` prompt rewrite — Layer 1 + 2 as a real exercise
The forthcoming rewrite (per `eval-design.md`) is a Layer 1/2 exercise:
- Which voices belong (role definition, baseline-vs-at-risk semantic, doctrine
  excerpts, scenario context, output schema)
- In what shape (categorical enums for output to force commitment)
- In what order (instructions first, schema last, dynamic context in between)

If the rewrite is done without conscious composition decisions, it'll work but
the choices will be vibes. With conscious decisions, the prompt becomes
reproducible across rewrites and a real artifact to iterate on.

### Implicit context engineering already present
The `supervisor → cluster → logistics` flow performs sub-agent isolation
(Layer 3): logistics doesn't see raw cluster reasoning, only `assess_situation`'s
digest. That's a context-engineering pattern even if it wasn't named one when
built. Naming it is useful — it tells you the pattern is available for other
splits too.

---

## 5. Build a slice here

Don't redesign anything to learn this. Make context engineering *visible* in
your own code, because right now it isn't.

**The slice:** instrument one full simulation tick to log, per LLM call, the
token allocation broken down by voice — system / tool definitions / message
history / retrieved content / output schema. Render it as a stacked bar per
call, or just a table.

Pieces you already have:
- `token_callback.py` for per-call token totals.
- LangChain's message and tool-binding APIs let you inspect what gets sent.
- Per-node wrapping via `@node_executor` to associate calls with their node.

What you'll likely discover, sight unseen:
1. **Tool definitions are bigger than you thought.** They're stable across
   calls and rarely scrutinized; that makes them invisible bloat.
2. **History grows unboundedly in logistics.** You'll see the curve that
   produces the 82K incident. The cap hides this; the chart reveals it.
3. **At least one voice has poor ROI.** Something stable in every call that
   the model rarely uses. That's a free saving.

Then make **one** deliberate Layer 1 or 2 change — drop a tool, compress
tool descriptions, shorten the system prompt, or split a multi-purpose call
into two — and re-measure. The deliverable is the before/after comparison:
token count, latency, *and* eval-substrate quality. If quality holds at lower
tokens, you've engineered context, not just trimmed it.

This slice composes with the `eval-design.md` work — once the eval harness
exists, quality holds becomes a number, not a vibe. Until then, "looks the
same to me" is the floor of what you can claim.

---

## 6. Proof of competence

Cross-links to **Curriculum Domain 5**:

- [ ] Per-call token breakdown by voice for one full simulation tick — a
      stacked-bar chart or a CSV with `call_id, node, voice, tokens` rows.
- [ ] Identify and *name* the highest-leverage Layer 1 or 2 change for either
      the `evaluate` rewrite or the `logistics_agent` loop. Naming matters —
      "remove tool X because per-tick it costs N tokens and is used in
      fewer than M% of calls" is a real claim; "feel like the prompt is
      bloated" is not.
- [ ] Make the change; produce the before/after comparison on tokens,
      latency, and one eval-substrate quality metric.
- [ ] (Stretch) Identify which named failure mode from §3 best describes
      the 82K incident, and propose a Layer 1/2 fix that would reduce
      reliance on the iteration cap.

---

## 7. Go deeper

- **Anthropic — "Effective context engineering for AI agents"** — the
  canonical practitioner write-up of this material. Read this first.
- **Anthropic — "Contextual Retrieval"** — the retrieval-side intersection
  (also referenced in the embeddings deep-dive).
- **Liu et al. — "Lost in the Middle: How Language Models Use Long Contexts"**
  — the canonical position-effects paper. Quick, decisive, changes how you
  order things.
- **Drew Breunig — "How long contexts fail"** (multi-part series) — failure
  modes catalog with concrete examples; the §3 list above borrows from this
  taxonomy.
- **Lance Martin / LangChain blog on context engineering** — practitioner
  POV with framework-specific patterns.
