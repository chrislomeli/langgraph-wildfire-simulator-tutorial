# Agentic AI — Professional Patterns Curriculum

A competency curriculum organized around objectives and proof-of-competence
artifacts, structured on the NCP-AAI 10-domain blueprint but vendor-neutral and
focused on professional patterns.

## How this relates to the other docs in this folder

This is the **objectives + artifacts** lens. It is complementary to:

- `advanced_ai_engineering_learning_rubric.md` — the **tier roadmap** (what to
  learn, in what order, with which tools).
- `rubric-integration-plan.md` — the **build plan** mapping tiers onto wildfire
  simulator steps 10–14.
- `step-10-12-design.md` — detailed design for the next steps.
- `project-gap-analysis.md` — honest audit of this project (and `journal_agent`)
  against every domain below: what's covered, what's missing, and the one new
  kind of project the portfolio still needs.
- `eval-design.md` — the concrete design (output contract, terrain stake inputs,
  scenario DSL, expected schema, eval metric, code ripple, DB migrations) for
  the D3 retrofit recommended in the gap analysis.

Use the rubric for *sequencing and tooling*; use this doc for *what mastery
looks like and how to prove it*. Each domain below links back to the rubric tier
and build step where relevant.

**Depth layer:** this doc is a *map* — it names a concept in a line or two. The
*territory* lives in `deep-dives/` (see `deep-dives/README.md`): one concept per
note, taught at real depth, written **on demand** when you hit the wall on it.
A domain with no deep-dive link yet is not incomplete — the map is doing its
job; depth is a separate artifact, added when a real need pulls it.

### Honest gaps this doc fills

The existing rubric is strong on the eval → reliability → retrieval →
fine-tuning → inference spine. It is thin or silent on four areas that
disproportionately separate senior agent engineers:

1. **Agent Architecture & Design** — the *decision* of whether something should
   be an agent at all, and which topology. The rubric jumps straight to
   reliability mechanics.
2. **Context Engineering as a first-class discipline** — the rubric folds it
   under retrieval. It deserves its own treatment (budgeting, rot, poisoning).
3. **Safety, Ethics & Compliance** — essentially absent from the rubric. This is
   a real omission for "professional environment" work.
4. **Human-AI Interaction & Oversight** — also absent. HITL is a design
   discipline, not a checkbox.

### Three deviations from the NCP-AAI blueprint

- **"NVIDIA Platform Implementation (7%)" is deleted** and replaced with
  vendor-neutral serving/inference infrastructure.
- **Evaluation is treated as the #1 priority**, not the third. In production,
  eval *is* the job. Most "the agent is flaky" problems are "I have no eval
  harness" problems.
- **Context Engineering is added as a first-class domain** (Domain 5).

---

## Domain 1 — Agent Architecture & Design

> Rubric link: precedes Tier 1.5. Build link: already exercised in steps 01–09.

**Objective:** Justify from first principles whether a problem should be an
agent, and pick the minimal topology that solves it.

- Workflow (fixed control flow, LLM fills slots) vs. agent (LLM owns control
  flow). Most "agents" should be workflows.
- Canonical patterns and the failure mode of each: prompt chaining, routing,
  parallelization (sectioning/voting), orchestrator-workers,
  evaluator-optimizer, autonomous loop.
- Single- vs. multi-agent: the real cost of multi-agent (context fragmentation,
  coordination overhead, error compounding) and the narrow cases it pays for.
- Determinism budget: which decisions the model makes vs. which the graph
  hard-codes.

**Where the wildfire sim already exercises this:** `src/agents/supervisor/`
(orchestrator), `src/agents/cluster/` (workers via Send fan-out),
`src/agents/logistics/` (executor), `src/agents/commons/routing.py` (routing
pattern). You have a real orchestrator-workers topology — the missing skill is
articulating *why* this topology over a single ReAct agent.

**Deep dive:**
[`deep-dives/agent-architecture-patterns.md`](deep-dives/agent-architecture-patterns.md)
— the two-axis disentanglement (control flow vs. role decomposition), the full
pattern catalog with failure modes, the four-question filter for picking a
pattern, and a precise pattern-by-pattern read of the wildfire codebase as the
worked example.

**Proof of competence:**

- [ ] Implement one sim capability three ways (pure workflow, single ReAct
      agent, orchestrator-workers) and write a one-page postmortem on
      cost/latency/reliability differences. The writeup is the deliverable.

---

## Domain 2 — Agent Development

> Rubric link: Tier 1.5 (Agent Reliability). Build link: already exercised.

**Objective:** Build agents where tools and structured I/O are designed, not
improvised.

- Tool design as API design: idempotency, error messages written *for the
  model*, returning state not just success, granularity.
- Structured outputs / constrained decoding; recovery from schema violations.
- Control loops you write yourself: retry-with-reflection, max-step budgets,
  loop/oscillation detection, graceful degradation.
- Deliberate state-schema design (reducer contents, ephemeral vs. checkpointed).

**Where the wildfire sim already exercises this:**
`src/agents/commons/node_executor.py` (the retry/exception-capture decorator),
`src/agents/commons/schemas.py` and `src/stores/schemas.py` (Pydantic structured
outputs), typed tool factories in `src/tools/`. Strong foundation; the gap is
deliberate *failure injection* — the loop has not been proven against broken
tools.

**Proof of competence:**

- [ ] A tool-design checklist you actually apply.
- [ ] One agent that recovers cleanly from a deliberately broken tool (malformed
      JSON, timeout, plausible-but-wrong output) without crashing the loop.

---

## Domain 3 — Evaluation & Tuning  *(highest priority)*

> Rubric link: Tier 1. Build link: **Step 11 — Evaluation Harness**.

**Objective:** No agent ships without an eval harness; you can measure a change
before you believe it.

- Eval datasets from real/synthetic traces; LLM-as-judge and its failure modes
  (position bias, verbosity bias, self-preference); rubric vs. reference vs.
  pairwise judging.
- Component evals vs. end-to-end evals vs. trajectory evals (sensible *path*,
  not just final answer).
- Regression gating in CI that blocks a quality-dropping change.
- Error analysis as a discipline: read 50 traces by hand, cluster failures,
  *then* decide what to fix.

**Where the wildfire sim already exercises this:** The physics engine is a
ground-truth oracle — a rare and valuable asset most projects do not have.
Deterministic scripted scenarios mean reproducible golden datasets. See Step 11
plan in `rubric-integration-plan.md`.

**Proof of competence:**

- [ ] A CI-gated eval suite for one agent with ≥3 metric types: a deterministic
      check, an LLM-judge check, and a trajectory check.
- [ ] A written error-analysis over 50 hand-read traces.

---

## Domain 4 — Cognition, Planning & Memory

> Rubric link: partially Tier 1.5. Build link: extends the existing graphs.

**Objective:** Implement planning and memory as explicit, inspectable
components — not "the model figures it out."

- Planning: ReAct vs. Plan-and-Execute vs. tree/graph search; replanning
  triggers; plan as an editable artifact in state.
- Reflection/self-critique and its honest limit (models are poor at catching
  their own errors without an external signal).
- Memory taxonomy: short-term (context-window mgmt), episodic (past runs),
  semantic (facts/RAG), procedural (learned tool-use). Most "memory" systems are
  RAG with a nicer name — know the difference.
- Write/forget policy: promotion to long-term, dedup, staleness.

**Where the wildfire sim already exercises this:** The supervisor plans and
cluster agents evaluate (planner/executor separation). The grid-as-truth /
snapshot-deletion direction is, in effect, a memory write/forget policy problem
— the same intuition transfers directly.

**Proof of competence:**

- [ ] An agent with explicit, queryable episodic memory and a written policy for
      what it stores/forgets and why.

---

## Domain 5 — Context Engineering  *(added; do not skip)*

> Rubric link: under-treated in Tier 2. Build link: relevant to Steps 11–13.

**Objective:** Treat the context window as a managed, budgeted resource.

- Context as a budget: instructions, tools, memory, retrieved docs, history all
  compete. Measure token allocation.
- Compaction: summarization, trimming, hierarchical summaries, scratchpads /
  external state, sub-agent isolation for clean contexts.
- Retrieval *for agents*: just-in-time tool-driven retrieval vs. pre-stuffed
  RAG; lost-in-the-middle; context rot over long runs.
- Failure modes: context poisoning, distraction, clash — diagnosable from a
  trace.

**Where the wildfire sim already exercises this:**
`src/llm/token_callback.py` (token accounting hook already exists),
`src/prompts/registry.py` (centralized prompt management). The instrumentation
seam is already there; the skill is using it to budget and diagnose.

**Deep dive:**
[`deep-dives/context-engineering.md`](deep-dives/context-engineering.md) —
the three layers of the discipline (composition / shape & order / flow), the
seven voices competing for attention, named failure modes, and the wildfire
codebase (including the 82K-token incident) as the worked example. The
embedding-limitation fact also touches this domain —
[`deep-dives/embeddings-and-retrieval-modeling.md`](deep-dives/embeddings-and-retrieval-modeling.md).

**Proof of competence:**

- [ ] Instrument one long-running agent to log token allocation per category
      over a run; identify and fix one context-rot failure.

---

## Domain 6 — Knowledge Integration & Data Handling

> Rubric link: Tier 2. Build link: **Step 12 — RAG Knowledge Layer**.

**Objective:** Build retrieval that's evaluated as its own subsystem.

- Chunking strategy and why naive fixed-size chunking is usually wrong;
  semantic/structural chunking.
- Hybrid retrieval (dense + lexical), reranking, query rewriting/decomposition
  for agentic retrieval.
- Retrieval eval independent of the LLM: recall@k, MRR, golden set.
- Grounding & citation; detecting/penalizing unsupported claims.

**Where the wildfire sim already exercises this:** Step 12 plan
(`rubric-integration-plan.md`) — pgvector + Postgres FTS + RRF + FlashRank, with
the analyst chat as the full retrieval-eval surface. `pgvector` is already a
dependency.

**Deep dive:**
[`deep-dives/embeddings-and-retrieval-modeling.md`](deep-dives/embeddings-and-retrieval-modeling.md)
— what an embedding actually represents, the access-pattern → representation
framework, and a scoped two-index experiment that proves it in this codebase.

**Proof of competence:**

- [ ] A retrieval subsystem with its own eval (golden Q→passage set) reported
      separately from end-to-end agent eval.

---

## Domain 7 — Deployment, Scaling & Serving Infra  *(replaces NVIDIA domain)*

> Rubric link: Tier 4 + Tier 5. Build link: **Step 10 (API)** and **Step 14
> (inference)**.

**Objective:** Run an agent as a production service with the operational
properties of a real service.

- Inference serving (vendor-neutral): batching, KV-cache, streaming, concurrency
  limits; agent latency is dominated by *number of sequential LLM calls*, not
  tokens.
- Cost & latency engineering: model routing (cheap model for easy steps),
  prompt/result caching, parallel steps; the latency-quality-cost triangle as an
  explicit decision.
- Statefulness in production: durable execution / checkpointing, resuming a
  half-finished run, idempotent tool calls under retry.
- Concurrency, rate-limit handling, backpressure, graceful degradation under
  provider outage.

**Where the wildfire sim already exercises this:**
`src/runtime/orchestrator.py`, `composition.py`, `facade.py`,
`graph_client.py` (clean runtime seam). `src/llm/llm_registry.py` already
abstracts STUB/OpenAI/Anthropic/Ollama providers — adding vLLM is one entry. The
`DataStore` ABC with mock/postgres impls is the profile-selected wiring seam for
local/k8s/aws.

**Proof of competence:**

- [ ] Deploy one agent behind an API with checkpoint/resume and a model-routing
      policy. Produce a cost-per-task and p95-latency number, then cut one
      measurably without quality loss.

---

## Domain 8 — Run, Monitor & Maintain

> Rubric link: under-treated (folded into Tier 1). Build link: extends Step 11.

**Objective:** Operate agents with observability designed for non-determinism.

- Tracing (spans for every LLM/tool call); what to log (full prompts, tool I/O,
  token counts, latencies); PII handling in traces.
- Online eval: sampling production traffic into the judge pipeline; drift
  detection when a provider silently changes a model.
- Agent-specific incidents: in-the-wild prompt injection, tool-API drift, cost
  runaway / infinite loops, silent quality regression.
- The data flywheel: production traces → eval set → improvement → ship → repeat.

**Where the wildfire sim already exercises this:**
`src/agents/commons/node_metrics.py` and the `node_executor` decorator already
capture per-node I/O — the flywheel's first hop (trace capture) is already
wired; Step 13's `trace_exporter.py` is the next hop.

**Proof of competence:**

- [ ] Full tracing on one agent plus an alert that fires on a cost-per-task or
      loop-length anomaly.

---

## Domain 9 — Safety, Ethics & Compliance  *(gap in existing rubric)*

> Rubric link: absent. This is a real omission to close.

**Objective:** Threat-model an agent and implement defense-in-depth.

- Agent-specific threats: prompt injection (direct & indirect via
  retrieved/tool content), tool misuse, excessive agency, data exfiltration via
  tool calls.
- Defenses: least-privilege tools, sandboxing, human-in-the-loop on
  irreducibly dangerous actions, output filtering, injection detection — and why
  none is individually sufficient.
- Guardrails as code: input/output validation, allow-listing, dual-LLM /
  quarantine patterns for untrusted content.
- Governance: audit logs, data residency, what regulated environments require.

**Where the wildfire sim can exercise this:** Step 12's RAG ingestion is the
natural place to test indirect prompt injection (poisoned knowledge documents).
The typed tool factories in `src/tools/` are where least-privilege and
allow-listing would be enforced.

**Proof of competence:**

- [ ] A written threat model for one agent (STRIDE-style or attack-tree).
- [ ] An indirect-prompt-injection test in the eval suite that must stay green.

---

## Domain 10 — Human-AI Interaction & Oversight  *(gap in existing rubric)*

> Rubric link: absent. This is a real omission to close.

**Objective:** Design the human's role into the system, not bolt it on.

- HITL patterns: approve/reject gates, edit-the-plan, escalation on low
  confidence, interruptible/resumable runs (ties to checkpointing in Domain 7).
- Confidence communication & uncertainty surfacing; designing for appropriate
  trust (avoiding over- and under-reliance).
- Feedback capture that feeds the flywheel: thumbs/edits/corrections as eval
  data.

**Where the wildfire sim can exercise this:** The logistics agent's
recommendations are a natural approval gate; the planned analyst chat (Step 12)
is the natural feedback-capture surface. LangGraph's interrupt/checkpoint
primitives make the edit-the-plan pattern directly implementable.

**Proof of competence:**

- [ ] Add a human-approval interrupt where the human can *edit* the plan (not
      just approve/reject), and the edit is captured as training/eval signal.

---

## Fine-Tuning Track

> Rubric link: Tier 3. Build link: **Step 13 — Fine-Tuning Pipeline**.

**The uncomfortable truth first:** for agentic AI, fine-tuning is rarely the
first lever and frequently the wrong one. The ROI ladder is almost always:
prompt/tool design → few-shot/structured output → retrieval → context
engineering → *then* fine-tuning. **You cannot fine-tune productively without
the Domain 3 eval harness — it is the prerequisite, not optional.**

Where it genuinely earns its place:

- **The decision objective:** for a given failure, state whether it is a
  knowledge gap (→ RAG), an instruction/format gap (→ prompt or SFT), a
  capability gap (→ bigger model or fine-tune), or a cost/latency problem
  (→ distillation). This diagnostic skill matters more than the mechanics.
- **The highest-value pattern: distillation into agent sub-tasks.** Take a
  narrow, high-volume node (routing, classification, extraction, query
  rewriting), generate a dataset with a frontier model, fine-tune a *small*
  model to do just that step cheaply. This is the fine-tuning that ships. The
  cluster `evaluate` node (sensor data → risk assessment) is an ideal target —
  see Step 13 plan.
- **Mechanics:** full SFT vs. PEFT (LoRA/QLoRA) and *why* PEFT works (low
  intrinsic rank of the update); quantization basics; data-quality-over-quantity
  (a few hundred clean examples > tens of thousands of noisy ones);
  catastrophic forgetting.
- **Preference optimization:** SFT vs. DPO vs. RLHF/RLAIF — what each optimizes
  and when DPO's simplicity is worth it. Know when it's the answer; you needn't
  implement RLHF from scratch.
- **Reasoning / RL fine-tuning (frontier):** rejection sampling / reasoning
  distillation and reinforcement fine-tuning on verifiable rewards. The sim
  *has* ground truth, which is rare — this is unusually applicable here.
- **Evaluation of a fine-tune:** held-out eval, regression against the base
  model on general capability (did you make it dumber elsewhere?), and the
  cost/latency win quantified.

**Proof of competence:**

- [ ] Distill one agent sub-task into a fine-tuned small model. Deliverable: a
      table of base vs. fine-tuned quality/cost/latency on a held-out eval,
      including a general-capability regression check.

---

## Suggested Sequencing (not a calendar)

1. **Domains 3 (Eval) and 5 (Context) early and in parallel** with everything
   else — they are force-multipliers; every other artifact gets better once you
   can measure and once you control context.
2. Work the rest opportunistically against the existing build steps 10–14.
3. **Fine-tuning last** — its prerequisite (a real eval harness) comes from
   Domain 3, and doing it earlier teaches you to reach for weights when you
   should be reaching for prompts.

---

## Consolidated Artifact Checklist

- [ ] D1 — Three-topology implementation + cost/latency/reliability postmortem
- [ ] D2 — Applied tool-design checklist
- [ ] D2 — Agent that survives a deliberately broken tool
- [ ] D3 — CI-gated eval suite with ≥3 metric types
- [ ] D3 — Error analysis over 50 hand-read traces
- [ ] D4 — Agent with explicit episodic memory + written write/forget policy
- [ ] D5 — Token-allocation instrumentation + one context-rot fix
- [ ] D6 — Retrieval subsystem with its own independent eval
- [ ] D7 — Deployed agent with checkpoint/resume + model routing, with a
      measured cost or latency cut
- [ ] D8 — Full tracing + cost/loop-length anomaly alert
- [ ] D9 — Written threat model + green indirect-injection eval test
- [ ] D10 — Editable-plan human interrupt with captured feedback signal
- [ ] FT — Distilled sub-task model with base-vs-tuned comparison table

---

## Resources (vendor-neutral, practitioner-grade)

- **Anthropic — "Building Effective Agents"** and the engineering blog (context
  engineering, multi-agent, tool design). Best free signal for D1–D2, D5.
- **Chip Huyen — *AI Engineering* (book).** Closest thing to a textbook for this
  whole list.
- **Hamel Husain & Shreya Shankar — LLM evals / error-analysis methodology.**
  This *is* Domain 3.
- **Lilian Weng's blog** ("LLM Powered Autonomous Agents," hallucination
  posts) — rigorous; D4, D9.
- **Maxime Labonne — LLM Course** and **Sebastian Raschka** (blog + *Build a
  LLM from Scratch*) for fine-tuning mechanics; Hugging Face TRL/alignment docs
  for hands-on SFT/DPO.
- **Eugene Yan's blog** — senior-practitioner perspective across D3, D7, D8.
- **Simon Willison's blog** on prompt injection / agent security — practical
  Domain 9.
- **DeepLearning.AI short courses** — use selectively as *labs* layered on the
  reading above, not as the primary source.
- **Provider cookbooks** (Anthropic/OpenAI) — pattern references for eval, tool
  use, fine-tuning.
