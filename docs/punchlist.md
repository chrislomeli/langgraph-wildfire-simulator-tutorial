# Wildfire Advisory — Product Punchlist

_Last updated: 2026-05-23_

**Pitch (one line):** Read landscape conditions continuously, predict where a fire is
likely to ignite and spread, and recommend pre-positioning crews/engines — *before*
anything burns.

> Note: this is a **learning / portfolio** build. The punchlist is intentionally heavy
> in the hard technical middle (the AI agents + the evaluation discipline) and thin at
> the commodity ends (live data feeds, UI, deploy). That's the right shape for the goal —
> but a real buyer would poke at the thin ends first.

**Legend:** `[x]` done · `[~]` partial / wired-but-stubbed · `[ ]` not started · ⛔ blocked

---

## 1. SENSE — the world / data feed
- [x] DB-backed landscape sim (terrain, per-cell weather, `cell_state` seed + simulation copies)
- [x] Scripted weather ramps drive each cell deterministically (`ScriptedTrendPhysics`)
- [x] Per-tick writeback to DB working copy + change events (`iter_tick_events`)
- [x] Generator wired to call the advisory controller in-process per changed tick
- [ ] Real data feeds (NWS / sensors) instead of scripted ramps
- [ ] Decide on the `hold_after` firing behavior (held cells re-fire every tick)

## 2. ASSESS RISK — the risk agent _(core IP)_
- [x] Cluster/`evaluate` agent runs end-to-end on the **live LLM** (`STUB_RISK_SCORE=False`)
- [x] Structured output: `escalate`, `ignition_risk`, `potential_spread_area` (Corner box), `confidence`, `reasoning`
- [x] Heuristic pre-filter gates which cells reach the LLM (`apply_thresholds`)
- [x] Forecast/history anchored to the real cell + correct tick (`_baseline_cell`, `set_tick`)
- [ ] Tune the evaluate prompt against a baseline (needs evals first — see §5)

## 3. PLAN RESPONSE — the logistics agent + advisory _(other half of IP)_
- [x] `sector_analysis` consumes escalations (anchor + box + scenario + forecast)
- [x] ReAct loop + tools (`get_resources_within`, `get_wildfire_activity`) structurally in place
- [x] Message-threading + render bugs fixed (ready to flip the stub)
- [~] LLM tool-loop still **off** (`STUB_LOGISTICS=True`)
- [ ] Populate resource / availability data in the DB
- [ ] Flip `STUB_LOGISTICS=False` and tune
- [ ] Verify advisory dispatch path end-to-end

## 4. DELIVER — the output
- [x] Structured `ResourceAdvisory` (epicenter, situation, urgency 1–4, recommendation)
- [x] `AdvisoryController` returns a clean `AdvisoryResult`; transport-agnostic
- [ ] FastAPI endpoint (thin shim over the controller)
- [ ] Any UI / dashboard a customer could open

## 5. PROVE IT — evaluation & observability _(highest leverage)_
- [x] Agent-agnostic eval framework built + isolated + runnable (`src/evals/framework/`, `demo.py`)
- [x] Spine: dataset → task ×N → evaluators → store → aggregate → report → baseline/regression
- [x] In-memory + JSON stores (no DB needed to run)
- [~] Older narrow escalation harness exists (`src/evals/escalation/`, ephemeral)
- [ ] **Escalation `Task` adapter** — drive the *real* risk agent through the framework
- [ ] **Golden dataset** — scenarios with known-right answers (code or DB)
- [ ] **DB-backed `ExperimentStore`** — write `eval_runs` / `eval_results`
- [ ] **First baseline numbers** — so we can claim an accuracy figure at all
- [ ] LLM-as-judge (rubric-pinned) for the reasoning prose
- [ ] Tool-call evaluator for logistics ("called `get_resources_within` once per hotspot?")

## 6. SHIP — deployment / ops
- [ ] Packaging / containerization
- [ ] Cloud deploy (local/k8s/aws profile selection — the deployment-mode goal)
- [ ] Monitoring / persisted traces as a product surface (LangSmith hook exists, not surfaced)

---

## ⛔ Blocking decisions
- **Eval output-contract reconciliation:** the eval DDL expects `property_at_risk` /
  `life_at_risk` per cell, but the agent outputs `ignition_risk` + spread box + `confidence`.
  Pick one ontology before wiring the DB-backed eval store (§5). This decides what the
  evaluators read and what `eval_results` stores.

## 🎯 Highest-leverage next move
Wire the eval rig to the **real** risk agent and produce a **first baseline number**
(§5: `Task` adapter + golden dataset + reconcile the contract). Until there's an accuracy
figure, we can't tell whether flipping logistics on, changing a prompt, or swapping a model
helped or hurt — and "we measure our agents rigorously" is itself a differentiator.

## Honest claim check
- **Can say today:** "Working end-to-end prototype — senses a landscape, an AI assesses
  ignition risk with real model reasoning, drafts a response plan; measurement framework
  stood up."
- **Cannot say yet:** "runs on live data" · "it's X% accurate" (no baseline) · "customers
  can use it" (no API/UI) · "it's deployed."

---

## Recently done (this session, for when you return)
- Logistics agent rewired to consume cluster escalations; `sector_analysis` rebuilt.
- Fixed `run_cluster_agent` KeyError (below-gate clusters), the `logistics_agent` message
  flattening, `get_plan` KeyError on unplanned cells, and `SimpleFirePhysicsModule.get_plan`.
- Cluster/supervisor tests rewritten to the current escalation contract (90 agent tests green).
- `request.tick` now carried into the engine; forecast baseline anchored to the real grid cell.
- `SpreadRegion` → nested `Corner` schema; structured-output uses `method="function_calling"`.
- `AdvisoryController` extracted; `main_generator` builds one controller and `await`s it.
- Built the isolated, runnable eval framework (`src/evals/framework/`).
