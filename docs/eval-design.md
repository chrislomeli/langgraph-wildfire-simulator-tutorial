# Eval Design — Stakes-Grounded Escalation Contract

**Purpose.** Design record for the D3 (Evaluation) retrofit identified in
[`project-gap-analysis.md`](project-gap-analysis.md). Captures the new
`evaluate`-node contract, the input/output schemas, the scenario DSL,
the expected-output (label) schema, the eval metric, the labeling principle,
the downstream code ripple, and the concrete database changes required.

This is a reference document. It is meant to be acted on without re-reading
the conversation that produced it. If you find yourself needing more rationale
than this doc gives, that's a sign to extend it.

**Doc-set position:** see [`agentic-ai-curriculum.md`](agentic-ai-curriculum.md)
for the 10-domain map, [`project-gap-analysis.md`](project-gap-analysis.md)
for *why* this retrofit is the highest-leverage move, and
[`deep-dives/`](deep-dives/) for concept-level depth notes.

---

## 1. What changed and why

**Before.** `evaluate` produced a `CollatedRecordRisk { risk_score: 0–10,
confidence, … }`. Downstream `sector_analysis` in logistics thresholded
`risk_score >= 5` to find hotspots; logistics then reasoned about whether to
dispatch an advisory.

**After.** `evaluate` produces an `EscalationDecision { escalate: bool,
property_at_risk, lives_at_risk, rationale, confidence }`. Logistics no longer
reasons about risk — it does resource math (do we have coverage, are resources
committed, when do they roll off) and emits an advisory mechanically when
coverage is insufficient.

**Why.** Two reasons that together justify the contract change:

1. **A 0–10 scalar risk score can't express stakes.** A 30%-likely ignition next
   to a hospital is operationally different from a 60%-likely ignition in remote
   backcountry. A scalar threshold collapses that. Stakes-grounded escalation is
   the judgment a threshold genuinely cannot reproduce — and it is the judgment
   an LLM is uniquely good for.
2. **Fire-behavior magnitude is physics, not judgment.** If you have Rothermel
   or RMRS-derived doctrine, *risk magnitude is computable*. The LLM
   should not be guessing what physics could calculate; it should be doing the
   layer physics can't — escalation under stake + uncertainty.

**Trade-off explicitly accepted.** The decision is now *opaque* — there's no
tunable threshold knob. The `rationale` field is the audit trail and is
load-bearing for that reason. Treat it as a first-class field, not freeform
afterthought.

---

## 2. The output contract — `EscalationDecision`

```python
class StakeLevel(str, Enum):
    NONE = "none"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"

class EscalationDecision(BaseModel):
    escalate: bool
    confidence: int = Field(ge=1, le=10)
    property_at_risk: StakeLevel    # currently threatened — not baseline
    lives_at_risk: StakeLevel       # currently threatened — not baseline
    rationale: str = Field(min_length=1)
```

**Sub-decisions, with rationale (so they don't get re-litigated):**

| Decision | Choice | Why |
|---|---|---|
| `escalate` granularity | binary | Trinary (`escalate/monitor/dismiss`) adds calibration cost without earned signal. Add later if a real need emerges. |
| `confidence` | keep (1–10) | Cheap; lets eval distinguish "confidently wrong" from "uncertain"; natural HITL hook for D10. |
| `property_at_risk` / `lives_at_risk` | categorical enum | Anti-hedging; field-match eval-able; 5-second hand-labeling. Avoids pre-designing an asset-category taxonomy you don't yet know matters. |
| `rationale` | required, no length cap | Only audit trail for *why* escalate fired. |
| `contributing_factors` (weather/fuel/terrain) | **dropped** | Logistics no longer reasons about cause. If ops needs *why*, it reads `rationale`. Keeps the contract minimal. |
| Per-cell vs. per-cluster output | per-cell | Preserves cluster-fanout topology; logistics can group escalated cells if it wants. |
| Stake-level enum cardinality | 4 (NONE/LOW/MODERATE/HIGH) | 3 is too coarse (no "negligible" floor); 5 (+SEVERE) wastes hand-labeling time at the top end. |

---

## 3. The input contract — terrain stakes

Stakes are *static* facts about a place — same shape as `fuel_model` or
`slope`. They live on **terrain**, loaded at scenario seed, never changed by
the plan.

```python
class CellStakeAttributes(BaseModel):
    property_stake: StakeLevel       # baseline value/presence
    life_stake: StakeLevel           # baseline life presence
    stake_notes: str | None = None   # optional, e.g. "12 residences, WUI"
```

### The load-bearing semantic distinction

| Concept | Lives on | Meaning |
|---|---|---|
| `property_stake` (terrain input) | `terrain` table | *Baseline* — does this place have valuable things, regardless of any fire today? |
| `property_at_risk` (decision output) | `EscalationDecision` | *Currently threatened* — given baseline stake AND current fire dynamics, what's at risk *right now*? |

Without this distinction, the task degenerates to "copy input to output" and
labels drift. **Document this at the top of the prompt and at the top of the
scenario table comment.**

The pattern lets you author scenarios that probe real judgment:

| Scenario | `property_stake` | Weather | Fuel | Expected `property_at_risk` | Expected `escalate` |
|---|---|---|---|---|---|
| High stake, calm day | HIGH | calm | normal | LOW or NONE | false |
| High stake, hot/dry/windy, burnable | HIGH | extreme | burnable | HIGH | true |
| High stake, extreme weather, **NB terrain** | HIGH | extreme | NB | NONE | false |
| No stake, extreme weather, burnable | NONE | extreme | burnable | NONE | false (nothing to protect) |
| Moderate stake, marginal weather | MODERATE | marginal | burnable | LOW–MODERATE | judgment-boundary scenario |

The last row is where eval gets discriminating; everything else is sanity check.

---

## 4. The scenario DSL — finalized

The plan DSL drives *dynamic* inputs (weather) deterministically over ticks.
Stakes do not go here — they go on terrain.

```yaml
plan:
  - metric: humidity_pct
    start_tick: 1
    duration_ticks: 5
    start_value: 0.55
    target_value: 0.15
```

**Five fields.** That's the whole DSL.

### Semantics, written down

| Rule | Resolution |
|---|---|
| Top-level cell-state value | Seed/static default for that metric. If no plan covers a metric, it stays at this value. |
| Plan in scope at tick t | Plan is the authority — top-level is irrelevant where the plan applies. |
| At `start_tick` | Value **snaps** to `start_value` (implicit in the imperative seed-then-update model). |
| Interpolation | Linear, between `start_value` (tick `start_tick`) and `target_value` (tick `start_tick + duration_ticks − 1`). |
| After `duration_ticks` ends | Value persists at `target_value` (imperative: nothing rewrites it). |
| Two segments same metric, overlapping windows | **Forbidden.** Validate at load time. |
| Two segments same metric, abutting | Allowed; previous segment's tail (`target_value`) is the next segment's effective prior value. |

### What was removed and why

- **`curve` field — removed.** With snap-at-`start_tick`, any abrupt change is a
  1-tick segment; any non-linear shape is well-approximated by piecewise linear.
  Reversible (add the field back with `linear` as default) if a real scenario
  needs it.
- **`hold_after` field — removed.** Under imperative semantics it was a
  silent no-op (last-written value persists either way). If a "transient
  event" scenario ever needs the value to revert, author a follow-on segment
  that interpolates back. Reversible.

---

## 5. The expected-output schema (per scenario, per cell)

Labels live next to scenarios — atomic with the fixture.

```yaml
expected:
  escalate: bool
  property_at_risk: StakeLevel
  lives_at_risk: StakeLevel
  rationale_must_mention: [str, ...]    # optional keyword grounding test
```

Labels are *per scenario, per cell* (one row per (scenario, cell) pair). For
v1, the expected output applies at scenario *resolution time* (the tick by
which conditions stabilize); per-tick expected fields are deliberately deferred.

---

## 6. Eval metric

| Field | Comparison | Per-scenario score |
|---|---|---|
| `escalate` | exact bool match | required for pass |
| `property_at_risk` | exact = 1.0, ±1 level = 0.5, else 0 | within ±1 required for pass |
| `lives_at_risk` | same | within ±1 required for pass |
| `rationale` | optional keyword presence | diagnostic, not pass/fail in v1 |
| `confidence` | not used for pass/fail | logged for calibration analysis |

**Per-scenario pass:** `escalate` matches AND both stake levels within ±1.

**Across-scenario aggregates that matter:**

- Scenario pass rate (the headline number).
- `escalate` precision/recall + confusion matrix (false escalations and missed
  escalations are different failures; you want them separated).
- Per-stake-level confusion matrix.
- `confidence` calibration: do high-confidence-wrong scenarios cluster on a
  feature?

LLM-judge on `rationale` is intentionally deferred to v2 — overkill for the
first cut, and noisy.

---

## 7. Labeling principle

**Hand-labeled by the project author, using fire-science reasoning + RMRS
doctrine as reference.** Each `(scenario, cell)` row carries its `expected`
fields, written by hand at scenario authorship time.

Why this and not a codified rule:

- ~20–30 scenarios is the right first batch; that's not a scale problem.
- The labeling effort *is* the reasoning work you'd have to do anyway to
  write the prompt.
- Hand-labels become the dataset that could *train* a codified rule later;
  preserve the optionality.
- Premature codification before you know what corner cases matter is wasted
  work.

Layer in a frozen-baseline regression signal later (snapshot a known-good run,
detect drift) as a secondary signal. Defer a codified oracle until patterns
are obvious.

### Scenario types worth authoring

Most homemade eval suites fill up with trivial-positives and trivial-negatives,
which only catch totally broken agents. The scenarios that move the needle are
adversarial to a naive scoring model — they probe whether the agent is actually
reasoning, or running a thermometer.

| Type | What it tests | Example |
|---|---|---|
| **Confounder** | Feature X looks dangerous, feature Y overrides it | High weather + NB terrain → no escalate |
| **Directional / spatial** | Magnitude isn't enough; alignment matters | High spread potential, wind blowing wrong way |
| **Threshold straddler** | Right at the decision boundary, ±1 unit | Humidity 14% vs. 16% across a 15% line |
| **Trajectory** | Currently fine but rapidly worsening (or vice versa) | Calm → gust ramp; humidity recovery |
| **Multi-cluster coherence** | One cluster benign, one emerging | Tests parallel cluster behavior end-to-end |
| **Stake-only / weather-only** | High stake + no fire conditions; low stake + extreme weather | Forces the baseline-vs-at-risk distinction |
| **Trivial ±** | Sanity checks (obvious fire / calm day) | Keep a few; don't fill the suite with them |

A useful first batch is ~3–4 in each of the first six categories, plus 2–3
trivials. That's a real eval set (~20–30 scenarios), not a fixture pile, and
hand-labeling stays a one-sitting exercise.

---

## 8. Downstream code ripple

What changes, file by file. Critical path is the minimal set to make the new
contract flow through.

| File | Change |
|---|---|
| `src/agents/commons/schemas.py` | Add `StakeLevel`, `EscalationDecision`, `CellStakeAttributes`. Mark `CollatedRecordRisk` / `CellRiskAssessment` deprecated (delete after migration). |
| `src/agents/cluster/nodes.py` (`evaluate`) | Rewrite to emit `EscalationDecision`. Heuristic gate stays but now combines stake × weather signal (no-stake cells with extreme weather → still `escalate=false`). Silent-drop-on-LLM-failure bug (line 262–273) — emit a default `escalate=false, confidence=1` with an error rationale so the row exists for eval. |
| `src/agents/cluster/state.py` | Replace `risk_assessments` field with `escalations`. |
| `src/agents/logistics/nodes.py` (`sector_analysis`) | **Replace** with `group_escalations` — much smaller node that clusters spatially-close `escalate=true` cells into "incidents." Drop 8-sector radial reasoning. |
| `src/agents/logistics/nodes.py` (`logistics_agent`) | Rewrite prompt: *given these incidents (cells, property_at_risk, lives_at_risk), report on resource coverage and commitments.* No advisory decision in the prompt. |
| `src/agents/logistics/nodes.py` (`extract_plan`) | Advisory dispatch becomes mechanical: `coverage_required > coverage_available → emit advisory`. No LLM judgment at that step. |
| `src/agents/logistics/state.py` | Adjust `LogisticsAssessment` if needed (resource summary + auto-derived advisory). |
| `src/prompts/templates/evaluate/v1/` | Rewrite for new task (stakes-grounded escalation). **Document the baseline-vs-at-risk distinction at the top of the prompt.** |
| `src/prompts/templates/logistics/` | Rewrite for resource-only job statement. |
| `src/world/cell_state.py` | Add stake fields to `GenericCell` so terrain stakes propagate to evaluate input. |
| `src/stores/postgres/terrain_repo.py` | Read new stake columns. |
| `src/stores/schemas.py` | Add `CellStakeAttributes` if it lives there. |
| `src/agents/commons/risk_view.py` | `GridRiskView.hotspots()` changes from `risk_score >= threshold` to `escalate == true`. Used by `group_escalations`. |
| Tests under `tests/agents/` | Update fixtures and expected outputs. |

---

## 9. Database changes

Concrete DDL diffs against the current `ddl.sql`.

**Suggested implementation order.** Not all eight subsections are equally
load-bearing. If implementing piecemeal:

- **First three (do together): §9.1, §9.2, §9.4.** These unlock the prompt
  rewrites and the new contract. No backfill, no cross-table dependencies.
- **Defer until you actually need to run an eval: §9.5, §9.6, §9.7.** Scenario
  identity, expected labels, and run-history tables are only needed once
  there's a harness to run. Doing them first front-loads schema work without
  any test of the design.
- **§9.3 (`cell_escalation`)** can go in with the first three or with the
  harness work — it's needed the moment the rewritten `evaluate` node persists
  output, so do it before you flip the node from stub to live.

### 9.1 `terrain` — add stake columns

```sql
alter table terrain
    add column property_stake varchar(10) default 'none' not null,
    add column life_stake     varchar(10) default 'none' not null,
    add column stake_notes    text;

alter table terrain
    add constraint terrain_property_stake_ck
        check (property_stake in ('none','low','moderate','high'));

alter table terrain
    add constraint terrain_life_stake_ck
        check (life_stake in ('none','low','moderate','high'));
```

Stake columns on `terrain` (rather than a separate table) because there is
exactly one stake row per cell and the access pattern is "join with terrain."
Normalization isn't bought here.

### 9.2 `cell_state` — retire old risk columns

```sql
-- Old contract residue. Drop after the migration ships; keep during transition
-- if any old data still reads them.
alter table cell_state
    drop column risk_score,
    drop column confidence;
```

If preserving historical rows matters, rename to `legacy_risk_score` /
`legacy_confidence` instead of dropping outright. For a learning project, drop.

### 9.3 New table: `cell_escalation` — agent output

```sql
create table cell_escalation
(
    state_group        varchar(40)              not null,  -- 'sim', etc.
    grid_row           integer                  not null,
    grid_column        integer                  not null,
    layer              integer       default 0  not null,
    region             varchar(60)              not null,
    tick               integer                  not null,
    escalate           boolean                  not null,
    confidence         integer                  not null,
    property_at_risk   varchar(10)              not null,
    life_at_risk       varchar(10)              not null,
    rationale          text                     not null,
    created_at         timestamp with time zone default now() not null,
    constraint cell_escalation_pk
        unique (state_group, region, grid_row, grid_column, layer, tick),
    constraint cell_escalation_confidence_ck
        check (confidence >= 1 and confidence <= 10),
    constraint cell_escalation_property_ck
        check (property_at_risk in ('none','low','moderate','high')),
    constraint cell_escalation_life_ck
        check (life_at_risk in ('none','low','moderate','high'))
);

create index idx_cell_escalation_lookup
    on cell_escalation (region, tick, escalate);
```

Separation rationale: `cell_state` holds environmental state; `cell_escalation`
holds agent output. Keeps each table's purpose clean and lets you query "what
did the agent decide on this scenario" without polluting state queries.

**FK omission is deliberate.** No `references` clause back to `cell_state` or
`terrain`. Loose coupling — easier to evolve, no cascade surprises during
migrations. If you want enforced referential integrity, add
`references cell_state(state_group, region, grid_row, grid_column, layer)` on
the matching columns. Either is defensible.

### 9.4 `scenario_cell_plan` — drop dead fields

```sql
alter table scenario_cell_plan
    drop constraint scp_curve_ck,
    drop column curve,
    drop column hold_after;
```

Update `v_cell_plan` view to stop emitting `curve` and `hold_after` in the JSON.

### 9.5 New: scenario identity

The current schema implicitly identifies a scenario by `region`. That's
insufficient — you want multiple scenarios per region for diverse testing.

```sql
create table scenarios
(
    scenario_id    serial primary key,
    name           varchar(120) not null,
    description    text,
    version        integer     default 1 not null,
    region         varchar(60) not null,
    horizon_ticks  integer     not null,         -- max tick to run
    created_at     timestamp with time zone default now() not null,
    constraint scenarios_name_version_uk unique (name, version)
);
```

Then `scenario_cell_plan` gets a scenario FK:

```sql
alter table scenario_cell_plan
    add column scenario_id integer references scenarios(scenario_id);
-- Backfill existing rows into a default scenario per region, then:
alter table scenario_cell_plan
    alter column scenario_id set not null;
-- Adjust the PK to include scenario_id:
alter table scenario_cell_plan
    drop constraint scenario_cell_plan_pk,
    add constraint scenario_cell_plan_pk
        unique (scenario_id, grid_row, grid_column, layer, metric, start_tick);
```

**Pragmatic shortcut.** Current `scenario_cell_plan` seed data is four rows
under `lpnf-south`. If it's not yet load-bearing in tests, **truncate and
reseed under the new schema** instead of running a proper backfill migration.
Two minutes vs. an hour, and you lose nothing meaningful.

### 9.6 New: `expected_escalation` — the labels

```sql
create table expected_escalation
(
    scenario_id              integer     not null references scenarios(scenario_id),
    grid_row                 integer     not null,
    grid_column              integer     not null,
    layer                    integer     default 0 not null,
    expected_escalate        boolean     not null,
    expected_property_at_risk varchar(10) not null,
    expected_life_at_risk     varchar(10) not null,
    rationale_keywords       text[]      default '{}'::text[] not null,
    notes                    text,
    constraint expected_escalation_pk
        unique (scenario_id, grid_row, grid_column, layer),
    constraint expected_escalation_property_ck
        check (expected_property_at_risk in ('none','low','moderate','high')),
    constraint expected_escalation_life_ck
        check (expected_life_at_risk in ('none','low','moderate','high'))
);
```

Atomic with the scenario (FK + cascade if you want), one row per (scenario, cell).

### 9.7 New: `eval_runs` and `eval_results` — eval persistence (optional v1)

For tracking eval runs over time so you have a history, not just a most-recent.
Include in v1 because regression detection needs it.

```sql
create table eval_runs
(
    eval_run_id    serial primary key,
    scenario_id    integer not null references scenarios(scenario_id),
    model_label    varchar(60) not null,            -- which model/prompt version
    prompt_version varchar(30) not null,
    started_at     timestamp with time zone not null,
    finished_at    timestamp with time zone,
    pass_count     integer,
    fail_count     integer,
    notes          text
);

create table eval_results
(
    eval_run_id              integer not null references eval_runs(eval_run_id),
    grid_row                 integer not null,
    grid_column              integer not null,
    layer                    integer default 0 not null,
    actual_escalate          boolean not null,
    actual_confidence        integer not null,
    actual_property_at_risk  varchar(10) not null,
    actual_life_at_risk      varchar(10) not null,
    actual_rationale         text not null,
    passed                   boolean not null,
    escalate_match           boolean not null,
    property_distance        integer not null,        -- 0 exact, 1 = ±1, 2 = ±2 …
    life_distance            integer not null,
    constraint eval_results_pk
        unique (eval_run_id, grid_row, grid_column, layer)
);
```

### 9.8 What does **not** change

- `resources`, `resource_assignments`, `current_fires`, `wildfire_activity`,
  `resource_advisories` — the logistics-side tables are correct as-is; the new
  logistics consumes them in simpler ways but their schemas hold.
- `sensors` — unrelated to this design.

---

## 10. Standing state

| # | Item | Status |
|---|---|---|
| 1 | `EscalationDecision` output schema | ✅ locked (§2) |
| 2 | Terrain stakes input + baseline-vs-at-risk distinction | ✅ locked (§3) |
| 3 | Plan DSL — drop `curve`, drop `hold_after`, forbid overlap, snap-at-start | ✅ locked (§4) |
| 4 | `expected` schema | ✅ defined (§5) |
| 5 | Eval metric | ✅ defined (§6) |
| 6 | Labeling principle (hand-label) | ✅ (§7) |
| 7 | Code ripple list | ✅ enumerated (§8); implementation pending |
| 8 | DB migrations | ✅ specified (§9); not applied |
| 9 | `evaluate` prompt rewrite | ⏭ critical path, not started |
| 10 | `logistics` prompt rewrite | ⏭ critical path, not started |
| 11 | Eval harness plumbing | ⏭ ~½ day after 7–10 |
| 12 | Tier 2 DSL discipline sweep (scenario identity is in §9.5; other items pending) | ⏭ mostly parallel |

---

## 11. Out of scope (deliberately deferred)

- **Per-tick expected outputs.** v1 uses scenario-resolution-time labels.
- **LLM-judge on `rationale`.** v1 uses keyword presence; LLM-judge later if
  warranted.
- **Seeded noise / robustness eval.** Capability eval first; robustness is a
  production concern, not where we are.
- **Codified oracle (deterministic rule for expected labels).** Hand-label
  first; codify only if patterns become obvious in the labels.
- **Trinary `escalate`** (`escalate / monitor / dismiss`). Binary first.
- **Structured asset categories on output** (`categories: [structures,
  infrastructure, …]`). Free `rationale` carries this for now.
- **Trajectory eval** (did the agent take a sensible internal path). The
  contract-level eval is architecture-agnostic; trajectory eval comes after
  the architecture settles.

---

## 12. Existing eval-related artifacts in the repo

`scripts/data_wrangling/scenario_data/eval_*.json` exists and predates this
design. They are scenario *inputs* without `expected` labels — useful as
seed data for the new `scenarios` + `expected_escalation` tables, but they
do not constitute an eval harness on their own. Migration: import them as
scenarios, hand-label them, then they participate in the new harness.

Likewise the `tests/agents/*` and `tests/domains/wildfire/*` suites are
correctness/topology tests, not agent-quality eval — both should continue to
exist; they're complementary, not redundant.
