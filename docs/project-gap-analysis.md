# Project Gap Analysis — wildfire-simulator vs. the Agentic AI Curriculum

**Purpose:** an honest audit of this project (and, where relevant, the sibling
`journal_agent` project) against every domain in
[`agentic-ai-curriculum.md`](agentic-ai-curriculum.md), to decide what to
extend here, what to retrofit, and what genuinely requires *a different kind of
project*.

**Method:** grounded in the actual graphs/nodes/tests
(`src/agents/{supervisor,cluster,logistics}/`, `commons/routing.py`,
`logistics/nodes.py`, `tests/`), not the README claims. `journal_agent`
characterized from `/Users/chrislomeli/Source/PROJECTS/agenticAI/journal_agent`
(separate repo).

**Legend:** ✅ strong · 🟡 partial · ⛔ gap · ⬛ absent

**The portfolio in one sentence:** you have two *closed-world* projects on
opposite ends of the autonomy axis — **wildfire** (high-orchestration,
low-agency, deterministic, autonomous, has a ground-truth oracle) and
**journal_agent** (stateful, human-facing, memory + RAG + reflection,
LLM-routed). The gaps that matter are the ones *neither* produces.

---

## Domain-by-domain

### D1 — Agent Architecture & Design → 🟡 partial
Curriculum: *Domain 1*. Deep dive: `deep-dives/agent-architecture-patterns.md`
(to write).

- **Here:** clean orchestrator-workers *topology* (`supervisor/graph.py:80`,
  Send fan-out + sync barrier). But all control flow is deterministic;
  `route_base` (`commons/routing.py:31`) branches only on `status`, never on
  model output. Only `logistics` is a real agent.
- **Should have done better (as a learning artifact):** nothing is *wrong* for
  the problem — deterministic fan-out over fixed regions is the correct call.
  But it never demonstrates a case where agency is *required*, so it doesn't
  teach the judgment, only the conclusion.
- **Covered in `journal_agent`:** yes — `intent_classifier` + `route_on_intent`
  is genuine LLM-driven routing. So the *portfolio* covers LLM routing; this
  project alone does not.
- **Neither covers:** dynamic task decomposition, agent-to-agent communication,
  planner→replanner. Needs the open-environment project (below).

### D2 — Agent Development → ✅ strong (genuinely)
Curriculum: *Domain 2*.

- **Here, and to your credit:** structured outputs throughout; typed tool
  factories; `@node_executor` exception capture; a real ReAct loop with a
  **hard iteration cap** and a graceful truncation path
  (`logistics/nodes.py:258,292`), `_balance_dangling_tool_calls` to keep the
  Phase-2 structured call valid (`:306`), Phase-1/Phase-2 separation with a
  hard-won rationale about `.with_structured_output()` silently deleting tools
  (`:169`), and degradation when deps are missing (`logistics/graph.py:107`).
  The `MAX_LOGISTICS_ITERATIONS` comment references a real 82K-token runaway —
  this is a project that hit a production-class failure and fixed it. That is
  above tutorial grade.
- **Should have done better:** only ~3 tools; the iteration cap is a fixed int,
  not budget-aware; on cap-hit it *truncates* rather than reasoning about why it
  looped; no deliberate broken-tool recovery test.
- **Neither covers:** failure recovery against *genuinely unreliable* tools
  (this needs the open-environment project + the D3 harness).

### D3 — Evaluation & Tuning → ⛔ MAJOR gap (highest leverage)
Curriculum: *Domain 3*. Build: Step 11.

- **Here:** a solid *software* test suite (`tests/agents/*` topology,
  `tests/domains/wildfire/*` physics) and scenario fixtures
  (`eval_*.json`) — but these are correctness tests, **not agent-quality
  evals.** No scoring of agent output vs. the physics oracle, no LLM-judge, no
  trajectory eval, no regression gate on quality, no error-analysis discipline.
- **The painful part:** this project has the single best substrate for eval
  that exists — a deterministic ground-truth oracle — and does not exploit it.
- **Neither project covers this.** This is the #1 retrofit, and wildfire is the
  correct home for it.

### D4 — Cognition, Planning & Memory → ⬛ absent here / covered in journal_agent
Curriculum: *Domain 4*.

- **Here:** no agent memory (state is per-tick world state), no plan artifact,
  no replanning, no reflection.
- **Covered in `journal_agent`:** strongly — persistent `Fragment` memory,
  vector recall, a reflection graph, a `Subject→Claim→Vote` insight model, and a
  checkpointer keyed by session. This is journal_agent's core competence.
- **Neither covers:** planning *under uncertainty* / replanning when the world
  fights back. Open-environment project.

### D5 — Context Engineering → 🟡 thin
Curriculum: *Domain 5*. Deep dive (touch): `embeddings-and-retrieval-modeling.md`.

- **Here:** `token_callback` + prompt registry exist; the 82K-token incident is
  a real war story — but the fix was a reactive cap, not a budgeting/compaction
  discipline. Runs are short (per-tick), so context rot never bites.
- **journal_agent:** more exposure (multi-turn, retrieval-conditioned context,
  checkpointed sessions) but still no explicit token-budgeting/compaction.
- **Neither covers:** context rot over *long autonomous* runs. Open-environment
  project.

### D6 — Knowledge Integration → ⬛ absent here / basics in journal_agent
Curriculum: *Domain 6*. Deep dive: `embeddings-and-retrieval-modeling.md`. Build: Step 12.

- **Here:** none yet (Step 12 future).
- **Covered in `journal_agent`:** real RAG — pgvector semantic retrieval,
  fragment ETL, embeddings. Basics covered at the portfolio level.
- **Neither covers:** retrieval *evaluated as a subsystem* (recall@k, golden
  set), hybrid + rerank. The embeddings deep-dive's slice targets exactly this
  in wildfire Step 12.

### D7 — Deployment, Scaling & Serving → 🟡 partial
Curriculum: *Domain 7*. Build: Steps 10/14.

- **Here:** clean runtime seam (`src/runtime/*`), multi-provider
  `LLMRegistry`, `DataStore` ABC profile wiring (the local/k8s/aws seam),
  graceful degradation.
- **journal_agent:** further along on *serving* — FastAPI runner, SSE token
  streaming, checkpointer = resume.
- **Neither covers:** running at load — cost/latency engineering, model-routing
  policy, concurrency/backpressure, provider-outage degradation, measured
  p95 / cost-per-task.

### D8 — Run, Monitor & Maintain → 🟡 thin (pairs with D3)
Curriculum: *Domain 8*.

- **Here:** `node_metrics` + `node_executor` = the trace-capture first hop only.
  No spans/tracing, no online eval, no drift detection, no anomaly alerting, no
  data flywheel.
- **Neither covers this.** Retrofit alongside D3 on wildfire.

### D9 — Safety, Ethics & Compliance → ⬛ absent in both
Curriculum: *Domain 9*.

- **Neither project:** no threat model, no prompt-injection defense, no
  least-privilege/sandboxing/allow-listing, no decision audit log, no
  governance. wildfire's closed world *masks* the gap; journal_agent ingests
  user content (mild surface).
- **Only learnable** with untrusted external content + consequential tools →
  open-environment project (indirect prompt injection is the canonical lesson
  there).

### D10 — Human-AI Interaction & Oversight → ⬛ absent here / partial in journal_agent
Curriculum: *Domain 10*.

- **Here:** fully autonomous sensor→dispatch. No approval gate, no plan editing,
  no confidence surfaced to a human, no feedback capture.
- **journal_agent:** conversational/human-in-loop by nature, but not the
  specific *oversight* patterns (editable-plan interrupt, feedback-as-eval-
  signal). Portfolio: partial.
- **Missing precise pattern** could be added to journal_agent or the new
  project.

### FT — Fine-Tuning → ⬛ not done / wildfire is the ideal substrate
Curriculum: *Fine-Tuning Track*. Build: Step 13.

- Neither project fine-tunes. wildfire is the *best* substrate anywhere in your
  portfolio: a verifiable oracle enables distillation/RFT of the cluster
  `evaluate` node, and `node_executor` already captures the traces. Prerequisite
  is D3. **This is wildfire's endgame, not a new project.**

---

## Portfolio map

| Domain | wildfire | journal_agent | Still uncovered by both |
|---|---|---|---|
| D1 Architecture | 🟡 topology only | ✅ LLM routing | dynamic decomposition, agent↔agent |
| D2 Development | ✅ strong | 🟡 | failure vs. unreliable tools |
| D3 Evaluation | ⛔ | ⛔ | **everything — top priority** |
| D4 Memory/Planning | ⬛ | ✅ memory/reflection | planning under uncertainty |
| D5 Context Eng. | 🟡 thin | 🟡 thin | long-run context rot |
| D6 Knowledge/RAG | ⬛ | ✅ basics | retrieval-as-evaluated-subsystem |
| D7 Deploy/Serve | 🟡 | 🟡 (FastAPI/SSE) | running at load |
| D8 Monitor | 🟡 capture only | 🟡 | observability + flywheel |
| D9 Safety | ⬛ | ⬛ | **all of it** |
| D10 Human/Oversight | ⬛ | 🟡 conversational | editable-plan + feedback signal |
| FT Fine-tuning | ⬛ (ideal substrate) | ⬛ | — |

---

## The conclusion: what's actually missing

Between the two projects you cover more than it feels like. The genuine
*neither-covers* gaps cluster into three moves:

### 1. Retrofit eval + observability + fine-tuning onto **wildfire** (not a new project)
D3 + D8 + FT. wildfire is the right home because the deterministic oracle is a
rare asset most projects never have. This is Steps 11/13 of the existing
integration plan — now with a sharpened *why*: it is the **highest-leverage,
lowest-new-surface** move available, and it unblocks fine-tuning. Do this first.

→ [`eval-design.md`](eval-design.md) is the concrete design for the
evaluate-node side of this retrofit (stakes-grounded escalation contract,
scenario DSL, expected schema, eval metric, code ripple, DB migrations).

### 2. Build ONE new project: a long-horizon, high-agency agent on an environment it does not control
This is the single missing *category*. D1 (real agency), D2 (failure vs.
unreliable tools), D4 (planning/replanning under uncertainty), D5 (context rot
over long runs), and D9 (indirect prompt injection) only bite **simultaneously**
in this kind of system. No closed world produces them. Options:

- **(Recommended) A coding/repo agent.** Given a real repo + an issue:
  plan → edit → run tests → iterate. Uniquely, it *also* produces a **verifiable
  reward** (tests pass/fail), which feeds D3 and the fine-tuning track — so it
  compounds with move (1) instead of being orthogonal. Best single ROI, and it
  reuses the eval instincts you'll have just built.
- A **deep-research agent over the live web** — forces indirect prompt
  injection (the canonical D9 lesson), source conflict, long-context synthesis,
  grounding/citation.
- A **computer/browser-use task agent** — forces the hardest failure recovery
  and the strongest case for D10 approval gates on irreversible actions.

### 3. Make Safety (D9) a deliberate pass on project #2
Threat-model the coding/research agent explicitly; add an indirect-injection
test that must stay green. Safety is not a project — it's a discipline applied
*to* the one project that has a real attack surface.

### Suggested order
1. Eval + observability retrofit on wildfire (unblocks everything, incl. FT).
2. Coding agent (project #2) — gets D1/D2/D4/D5 under real conditions.
3. D9 threat-model pass on the coding agent.
4. Fine-tuning as wildfire's endgame (now that D3 exists).
5. D10 editable-plan + feedback-as-signal — add to journal_agent or the coding
   agent, wherever the human surface is most natural.

> Every item above links to a curriculum domain and (where written) a deep-dive.
> When you start any of these, pull the matching deep-dive note first — that's
> the depth layer doing its job.
