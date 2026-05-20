# Agent Architecture Patterns

> Depth note for **Curriculum Domain 1 — Agent Architecture & Design**.
> Companion to `embeddings-and-retrieval-modeling.md` and the worked case
> study in `../project-gap-analysis.md` (D1 row).

This note exists because the field's vocabulary mixes two different things
together and that mixing is responsible for most of the confusion when people
read about "agentic AI." The cert blueprints, blog posts, and YouTube courses
all blur the same axes. Untangle them once and the whole space gets small and
navigable.

---

## 1. The one load-bearing fact

> **Patterns live on a spectrum of *who owns control flow* — from fully
> predetermined (you wrote the flow, the LLM fills slots) to fully
> model-decided (the LLM picks each step in a loop). The senior move is to
> pick the *leftmost point on that spectrum that solves the problem*.
> Agency is a cost, not a feature.**

Every architecture decision in agentic AI follows from taking that sentence
seriously. The cost of agency, made concrete:

- **Predictability cost.** Each token of model-decided flow is a token of
  variance. Workflows are reproducible; agents are statistical.
- **Cost / latency cost.** Each LLM step is one network round-trip and one
  decoding pass. Sequential LLM calls compound; a 6-step ReAct loop is 6×
  the latency floor of a 1-call workflow.
- **Failure-surface cost.** Tool calls fail, models hallucinate tool calls,
  loops oscillate, contexts rot. More agency = more failure modes.
- **Eval cost.** Workflow nodes have stable contracts you can eval against;
  autonomous loops have trajectories that can't be straightforwardly evaluated
  without trajectory-eval machinery.

You are not "settling" by choosing a workflow over an agent. You are spending
agency where it earns its keep. Most production systems people call "agentic"
are workflows with one or two genuinely agentic nodes inside.

---

## 2. The framework — two axes, disentangled

The blur most explanations carry is collapsing these two:

- **Axis 1 — control flow.** Who decides what runs next: you (workflow) or the
  LLM (agent)? This is the spectrum from §1.
- **Axis 2 — role decomposition.** Once a system has multiple LLM-bearing
  components, what's each one's job? *Controller, planner, worker, critic* are
  role names — they are not control-flow patterns.

When the cert blueprint lists "controller / planner / worker," those are *Axis
2*. When it lists "ReAct, plan-and-execute, prompt chaining," those are *Axis
1*. They're not the same kind of thing and they don't substitute for each
other.

You can have a single-agent system with role decomposition (one LLM plays
multiple roles via different prompts) or a multi-component system that's
fully workflow (no agency anywhere) or any combination. Stop trying to fit
your design into one pattern name; identify it on both axes.

---

## 3. The control-flow patterns (Axis 1)

There are five workflow patterns and one agent pattern. That's the whole
catalog at this axis.

### Workflows (predetermined control flow)

| Pattern | Shape | Right when | Fails when |
|---|---|---|---|
| **Prompt chaining** | Step → step → step, each consumes the previous; optional gate between | Task cleanly decomposes into a fixed sequence | A step depends on information you can't anticipate |
| **Routing** | A classifier LLM picks one of N specialized downstream paths | Distinct input categories want different treatment | Inputs cross categories; router becomes a bottleneck |
| **Parallelization** | Either *sectioning* (independent subtasks run concurrently) or *voting* (same task N times, aggregate) | Subtasks are independent, or you want consensus/diversity | Subtasks have hidden dependencies; aggregation is non-obvious |
| **Orchestrator–workers** | Central LLM decomposes the task *at runtime* and delegates to workers, then synthesizes | The subtasks cannot be predetermined — they depend on the input | Subtasks *can* be predetermined (you should use parallelization instead); orchestrator becomes a single point of failure |
| **Evaluator–optimizer** | Generator produces, evaluator critiques, loop until criteria met | Quality criteria are clear and iteration measurably helps | The evaluator is the same model in disguise — convergence to confidently wrong |

### The one true agent pattern

| **Autonomous loop (ReAct-style)** | LLM in a loop with tools + environment feedback, choosing each step until done or budget exhausted | The task requires adaptation to information the LLM only sees at runtime, AND tool failure modes are tolerable | Predetermined sequence would do; cost/latency dominate; no good signal to bound the loop |

This pattern is the most flexible *and* the most expensive *and* the most
brittle. It is the right answer for fewer problems than its prominence in
discourse suggests.

---

## 4. The role vocabulary (Axis 2)

Once you go multi-component, you assign roles. Same names, different sources:

- **Controller / Supervisor / Orchestrator** — owns state, decides who acts
  next. (Anthropic calls it *orchestrator*, LangGraph *supervisor*, the cert
  *controller*. Same role.)
- **Planner** — produces a structured plan; usually separated from execution.
  When paired with a separate executor, this is the *plan-and-execute* pattern.
- **Worker / Specialist** — narrow, single-responsibility component invoked by
  a controller.
- **Critic / Evaluator** — the reflection role; this is *evaluator–optimizer*
  wearing a multi-agent hat.
- **Hierarchical** — supervisors of supervisors; teams of teams.
- **Handoff / Swarm** — peer agents pass control directly to each other (no
  central supervisor).

"Controller, planner, worker" is one architecture: **supervisor decomposes →
workers execute → optional critic verifies.** Recognize that triple and the
cert language stops being mysterious.

---

## 5. Three sharp contrasts that disambiguate the field

These come up in interviews and cert questions because confusing them is
where most people slip.

**Orchestrator–workers vs. parallelization.** Both fan out to multiple workers.
The difference: *who decides the subtasks?* Parallelization = you wrote them.
Orchestrator–workers = the LLM decides at runtime. If your "supervisor" sends
to a fixed list of workers based on something you wrote in code, it's
parallelization — even if the supervisor uses an LLM somewhere.

**Plan-and-execute vs. ReAct.** Both involve planning and acting. The
difference: *when does the plan exist?* Plan-and-execute = make the whole plan
first, then run each step (cheaper, inspectable, brittle to surprises). ReAct
= interleave think → act → observe one step at a time (adaptive, costlier,
can wander). Plan-and-execute fails when the environment fights back; ReAct
fails when the environment is stable and the loop just wastes tokens.

**Routing vs. orchestrator–workers.** Both involve an LLM directing flow.
The difference: routing picks *one of N specialized paths* (the input goes one
place); orchestrator–workers *decomposes into multiple subtasks* that all run.

---

## 6. How to choose: a four-question filter

Before adopting any pattern — *especially* before reaching for an autonomous
loop — run the candidate through this:

1. **What failure does this fix?** Not "this is more sophisticated." A named
   failure: a class of inputs the current design gets wrong, a coordination
   problem, a latency cliff. If you can't name the failure, you don't need
   the pattern.
2. **Is it the leftmost point on the agency spectrum that fixes it?** If a
   workflow would have done, the agent is wrong.
3. **Contract change or implementation change?** Implementation-only is cheap
   and reversible; contract changes ripple to consumers and to eval. Be
   deliberate about contract changes; don't do them at the same time as
   implementation explorations.
4. **Can the oracle verify it?** If you have no way to tell whether the new
   design helped, the design is unfalsifiable. That's a yellow flag —
   build the eval first.

Most of the "this needs to be an agent" instinct dies at question 1 or 2.

---

## 7. Bonus principle: stabilize the *contract*, not the *architecture*

The thing that has to stop moving before you can measure isn't the
architecture — it's the contract (inputs in, outputs out). A contract-level
eval written against `inputs → outputs` is **architecture-agnostic by
construction**: you can rip the implementation out and replace it with a
multi-step subgraph, a critic loop, or a fine-tuned model, and the eval
doesn't move. That's what lets architecture iteration be safe.

Conversely, *trajectory* evals (did the node take a sensible internal path)
are architecture-coupled and *do* become moving targets as you iterate.

The senior pattern: freeze the contract early → build a contract-level eval →
iterate architecture with the eval as the instrument → defer trajectory eval
until the architecture has settled.

This is the principle that makes Domain 1 work safe to do iteratively rather
than as a big up-front design exercise.

---

## 8. Failure modes (recognize these in a trace)

Named so you can spot them by description, not just by symptom:

- **Agency creep.** Using an autonomous loop where a workflow would suffice.
  Symptom: unpredictable cost, "the agent went off in the weeds," runs vary
  wildly in step count on similar inputs. Fix: replace the loop with a
  prompt chain or orchestrator-workers; only keep the loop where adaptation
  genuinely earns its place.
- **Multi-agent disease.** Splitting into multiple agents when one (or none)
  would do. Symptom: contexts fragment between agents, handoffs lose
  information, error compounds across hops. Fix: collapse adjacent agents
  with overlapping context into one.
- **Hidden threshold.** The LLM emits a binary decision (escalate / not) when
  a continuous score with an external threshold would be more inspectable and
  tunable. Symptom: can't dial sensitivity without rewriting the prompt; eval
  is harder because the threshold is opaque. (Exception, important: when the
  judgment requires integrating richly-contextual factors that can't be
  reduced to a scalar — e.g. stake-grounded escalation — the binary decision
  is actually the right move. See the eval-design pivot for the worked case.)
- **Critic loop without ground truth.** Evaluator–optimizer where the
  evaluator is the same model that generated the output. Symptom: convergence
  to confidently wrong. Fix: external signal (a test result, a tool's
  response, a different model, a rule).
- **Stateless routing in a stateful problem.** Router doesn't carry context;
  downstream paths can't see what's already been tried. Symptom: loops where
  the router keeps picking the same path. Fix: router consumes recent history
  or downstream nodes write back to shared state.
- **Workflow shaped as agent.** ReAct loop for a task with a known sequence.
  Symptom: token waste, brittleness, every run takes the same path anyway.
  Fix: replace with prompt chain.

---

## 9. Worked in the wildfire domain

The wildfire-simulator project is the case study. Let me name what's actually
there with precision, because folder names ("agents/supervisor",
"agents/cluster", "agents/logistics") oversell the agency.

### `supervisor/graph.py:80`
- **Topology shape:** orchestrator-workers (one central node fans out to N
  workers, then synthesizes via `assess_situation`).
- **Reality:** `fan_out_to_clusters` returns a `Send` per cluster — a
  *predetermined* scatter to every cluster_id, not an LLM-decided
  decomposition. `route_after_assess` is rule-based on `status`, not
  LLM-decided.
- **Correct pattern naming:** **parallelization (sectioning)** with rule-based
  routing. NOT orchestrator-workers (no runtime decomposition). NOT an agent
  at this level.

### `cluster/graph.py:88–91`
- **Topology shape:** linear pipeline (`update_world → evaluate → report_risk`).
- **Reality:** `evaluate` is a structured-output LLM call per cell, run in
  bounded parallel via `asyncio.Semaphore` (`cluster/nodes.py:244`). No tool
  use; no decision-making loop.
- **Correct pattern naming:** **prompt chaining** at the graph level, with
  **parallelization (sectioning)** inside the evaluate node. Not an agent.
  Workflow node with an LLM inside.

### `logistics/graph.py:92–97`
- **Topology shape:** ReAct loop wrapped in a phase split.
- **Reality:** the only genuinely agentic component. Phase 1 is a bounded
  autonomous loop (LLM-with-tools ↔ ToolNode) with `MAX_LOGISTICS_ITERATIONS
  = 4` (`logistics/nodes.py:258`) and `_balance_dangling_tool_calls`
  (`logistics/nodes.py:306`) — *real production scarring*, references an
  incident where a runaway loop hit 82K tokens. Phase 2 is a separate
  structured-output call on the finished transcript.
- **Correct pattern naming:** **autonomous loop** (Phase 1) wrapped in a
  **prompt chain** with a terminal **structured output** stage. The Phase
  split is itself a workflow-around-an-agent pattern, deliberately keeping
  tool-calling and structured output as separate LLM calls because chaining
  `.with_structured_output()` after `.bind_tools()` silently breaks the loop
  (`logistics/nodes.py:170`).

### Putting it together

In pattern terms, the wildfire system is:

> **parallelization → prompt chain (with internal parallelization) → autonomous loop wrapped in prompt chain**

It is a workflow at the top with **one** agent embedded. Two of the three
"agents" are workflow nodes that happen to live in `agents/` folders.

**The lesson — and this is the load-bearing one — is that this is the
right design.** The wildfire problem doesn't need agency at the supervisor
or cluster level. Deterministic fan-out over a known set of cluster regions
is correct. Per-cell structured-output classification is correct. Adding
agency where it doesn't earn its place would degrade the system.

The project demonstrates *good judgment about minimizing agency* — which
paradoxically makes it a poor showcase of multi-agent autonomy but a good
example of pattern-correct design. Pattern-correct design often looks less
impressive than pattern-bombastic design. The senior thing is to do it anyway.

---

## 10. Build a slice here

Don't redesign anything to learn this. Build the smallest experiment that
makes the pattern-choice question *falsifiable* in your own code.

### The slice, anchored to the eval-design work

The new `evaluate` contract (`docs/eval-design.md`) is being rewritten anyway.
That's the perfect moment for a three-way comparison:

1. **Workflow version** (the planned rewrite) — single structured-output LLM
   call per cell, emitting `EscalationDecision`.
2. **ReAct version** — same job, but as an autonomous loop with one or two
   tools (e.g., `lookup_doctrine(situation_keywords)`, `nearby_assets(cell)`).
3. **Orchestrator-workers version** — a small sub-graph: a planner LLM
   decides which of two sub-evaluators (e.g., "stake-led" vs "weather-led")
   should produce the decision, then a synthesizer combines.

Run all three against the same 20–30 hand-labeled scenarios. The harness
already produces precision/recall on `escalate`, distance on the two
`StakeLevel` fields, plus cost and latency per scenario. **The deliverable is
not the three implementations — it's the comparison table and the postmortem
naming which pattern won and why.**

Three things this slice teaches that nothing else does:
- Cost/latency of agency made *measurable* in your own code, not in the
  abstract.
- Quality difference (or absence of one) between the patterns on real
  scenarios.
- The four-question filter applied to a real decision — and the table itself
  is what lets you answer Q1 ("what failure does this fix?") next time.

If the table shows the workflow version winning on cost+latency at equal or
better quality, you've learned the senior lesson directly from your own data:
agency was a cost, not a feature, for this task.

---

## 11. Proof of competence

Cross-link to **Curriculum Domain 1**:

- [ ] Implement the three-way `evaluate` comparison above, run against the
      hand-labeled scenarios from the eval harness, and produce the table
      (quality / cost / latency per pattern).
- [ ] Write a one-page postmortem naming which pattern won, why, and what
      the four-question filter would have said *a priori*. The writeup is the
      deliverable, not the code.

---

## 12. Go deeper

- **Anthropic — "Building Effective Agents"** — the canonical version of the
  control-flow taxonomy in §3 and the spectrum framing in §1. The single best
  free source on this material.
- **Yao et al. — "ReAct" (2022)** — origin paper for the autonomous loop
  pattern. Worth reading for the framing, not for current best practice.
- **Wang et al. — "Plan-and-Solve Prompting" (2023)** — origin of the
  plan-and-execute split.
- **LangGraph multi-agent docs** — concrete supervisor / swarm / handoff
  patterns in the framework you're using. Practitioner-grade.
- **The cert blueprints** (NCP-AAI, etc.) — useful as vocabulary references
  once you've internalized the two-axis disentanglement; otherwise
  confusing for the reasons §2 names.
