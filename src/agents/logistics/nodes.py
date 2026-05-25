"""
world-simulator.agents.logistics.nodes

Node functions for the logistics agent ReAct loop.

Loop shape
──────────
    START → logistics_agent ──(tool calls?)──► tools → logistics_agent (repeat)
                             ──(no tool calls)──► extract_plan → END

  logistics_agent : AI boundary. Stub mode returns a placeholder AIMessage
                    with no tool calls so the loop exits immediately.
                    LLM mode calls the model with all three tools bound.
  extract_plan    : Terminal node — copies the LLM's final message content
                    into state.logistics_plan and marks COMPLETED.
  route_after_logistics_agent : Reads the last message; routes to "tools"
                    if tool_calls present, otherwise to "extract_plan".

Milestone flag
──────────────
STUB_LOGISTICS = True  : runs without an LLM. Safe for graph topology tests.
STUB_LOGISTICS = False : requires the "logistics" role (Phase 1 ReAct loop)
                         and the "logistics_extract" role (Phase 2 structured
                         output) in llm_registry.
"""

from __future__ import annotations

import logging

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langgraph.graph import END

from agents.commons.node_executor import node_executor
from agents.commons.schemas import Colors, Escalation, SpreadRegion
from agents.commons.state_types import StatusValue
from agents.logistics.state import LogisticsAgentState, LogisticsAssessment
from llm.llm_registry import LLMRegistry
from prompts import PromptRegistry
from stores.base import AdvisoryRepository
from tools.advisory import dispatch_advisory
from world import HotspotSectors
from world.world_view import WorldView

logger = logging.getLogger(__name__)


# ── Milestone flag ─────────────────────────────────────────────────────────────
#
# True = no LLM, no tool calls, returns stub plan immediately.
# Flip to False once the prompt and LLM are wired in.

STUB_LOGISTICS = True


# ── Hotspot context rendering ───────────────────────────────────────────────────
#
# The logistics LLM reasons over a text "situation summary". Per the chosen
# design, each escalated hotspot is rendered with THREE complementary views:
#   1. The escalation header — why the cluster agent flagged it (ignition_risk,
#      confidence, reasoning) and its estimated spread bounding box.
#   2. A live 8-sector radial trace of the grid (burnable_miles + barriers) —
#      the settlement-in-path / natural-firebreak signal the advisory hinges on.
#   3. The cluster's spread-risk scenario (per-direction ignition risk) and the
#      weather forecast, both computed upstream and carried in logistics state.


def _fmt_corner(c) -> str:
    """Render a SpreadRegion Corner as (row, col)."""
    return f"({c.row}, {c.col})"


def _render_spread_box(box: SpreadRegion | None) -> str:
    if box is None:
        return "  (no spread-area estimate provided)"
    return (
        f"  corners (row,col): UL{_fmt_corner(box.upper_left_corner)} "
        f"UR{_fmt_corner(box.upper_right_corner)} "
        f"LL{_fmt_corner(box.lower_left_corner)} "
        f"LR{_fmt_corner(box.lower_right_corner)}"
    )


def _render_forecast(briefing: dict | None, periods: int = 4) -> str:
    if not briefing or not briefing.get("forecast"):
        return "  (no forecast available)"
    rows = briefing["forecast"].get("periods", [])[:periods]
    if not rows:
        return "  (no forecast periods)"
    lines = []
    for p in rows:
        pop = (p.get("probabilityOfPrecipitation") or {}).get("value", 0)
        lines.append(
            f"  {p.get('date', '?')}: {p.get('temperature')}"
            f"{p.get('temperatureUnit', '')} RH={p.get('humidity_pct')}% "
            f"wind={p.get('windSpeed')} {p.get('windDirection')} "
            f"fuel_moisture={p.get('fuel_moisture')} precip={pop}%"
        )
    return "\n".join(lines)


def _render_hotspot_context(
    escalation: Escalation,
    hotspot: HotspotSectors,
    briefing: dict | None,
) -> str:
    """Render one escalated hotspot into the rich combined situation block."""
    parts = [f"========== Hotspot ({escalation.row}, {escalation.col}) =========="]
    if escalation.reasoning:
        parts.append("Why the cluster agent escalated it:")
        parts += [f"  - {r}" for r in escalation.reasoning]
    parts.append("Estimated spread area (cluster bounding box):")
    parts.append(_render_spread_box(escalation.potential_spread_area))
    parts.append("")
    parts.append("Radial sector trace (live grid scan — burnable distance & barriers):")
    parts.append(hotspot.to_context_string())
    parts.append("")
    parts.append("Weather forecast (upcoming periods):")
    parts.append(_render_forecast(briefing))
    return "\n".join(parts)


def make_sector_analysis_node(
    world: WorldView,
    risk_threshold: int = 5,
    max_sector_miles: float = 20.0,
):
    """Factory: builds the logistics situation summary from the escalations.

    The cluster agents have already found and scored the hotspots. Each
    ``Escalation`` carries an anchor cell, ignition_risk, confidence, the
    reasoning that flagged it, and an estimated spread bounding box. This node
    consumes those escalations directly — it does NOT rediscover hotspots by
    scanning the grid (the old RiskView/grid-scan path is gone).

    For each escalated hotspot it builds a ``HotspotSectors`` via a live
    8-sector radial trace (burnable distance + barriers), then renders a rich
    text block combining that trace with the cluster's spread-risk scenario and
    the weather forecast carried in logistics state.

    Parameters
    ──────────
    world            : Read-only view over the world (the engine satisfies this).
    risk_threshold   : Advisory guidance threshold, shown in the summary header.
                       The upstream ``escalate`` flag is the actual gate.
    max_sector_miles : Maximum distance to trace in each radial sector.

    Returns
    ───────
    Node function that returns {"sector_analysis": [...], "situation_summary":
    str, "status": PROCESSING}.
    """
    @node_executor("sector_analysis")
    def sector_analysis(state: LogisticsAgentState) -> dict:
        """Build per-hotspot situation context from the escalations."""
        escalations = [e for e in state.escalations if e.escalate]

        if not escalations:
            logger.info("sector_analysis: no escalated hotspots handed to logistics")
            return {
                "sector_analysis": [],
                "situation_summary": "No escalated hotspots were handed to logistics.",
                "status": StatusValue.PROCESSING,
            }

        hotspots: list[HotspotSectors] = []
        context_parts = [
            f"{len(escalations)} escalated fire hotspot(s) handed off for resource "
            f"assessment (advisory threshold risk ≥ {risk_threshold}):",
            "",
        ]

        for esc in escalations:
            row, col = esc.row, esc.col

            # Long-range radial trace via the world engine.
            hotspot = world.hotspot_sectors(row, col, max_miles=max_sector_miles)
            hotspot = HotspotSectors(
                epicenter_row=row,
                epicenter_col=col,
                risk_score=esc.ignition_risk,
                confidence=esc.confidence,
                sectors=hotspot.sectors,
            )
            hotspots.append(hotspot)

            briefing = state.briefings.get((row, col, esc.layer)) or state.briefings.get(
                (row, col, 0)
            )
            context_parts.append(_render_hotspot_context(esc, hotspot, briefing))
            context_parts.append("")

            logger.info(
                "Hotspot at (%d, %d): ignition_risk=%d, 8 sectors traced, max_burnable=%.1f miles",
                row,
                col,
                esc.ignition_risk,
                max(s.burnable_miles for s in hotspot.sectors),
            )

        logger.info(
            "sector_analysis complete: %d hotspot(s), %d total sectors",
            len(hotspots),
            len(hotspots) * 8,
        )

        return {
            "sector_analysis": [h.model_dump() for h in hotspots],
            "situation_summary": "\n".join(context_parts),
            "status": StatusValue.PROCESSING,
        }

    return sector_analysis


# ── Node: logistics_agent ─────────────────────────────────────────────────────


def make_logistics_agent_node(
    tools: list, prompt_registry: PromptRegistry, llm_registry: LLMRegistry | None
):
    """Factory: binds tools to the LLM for the ReAct loop (Phase 1).

    Phase 1 is tool-calling ONLY. We deliberately do NOT chain
    ``.with_structured_output()`` here. In LangChain that helper is implemented
    as a *forced single-tool call*: it re-binds the tool list to just the
    schema, forces ``tool_choice`` to it, and returns a parsed Pydantic object
    instead of an AIMessage. Chaining it after ``.bind_tools(tools)`` therefore
    silently deletes the real tools and makes the ReAct router unreachable.

    Structured output is done separately in the ``extract_plan`` node (Phase 2),
    as its own LLM call over the finished conversation — see make_extract_plan_node.

    Parameters
    ──────────
    tools        : List of bound @tool callables (resources, wildfires, advisory).
    llm_registry : Registry for looking up the LLM. May be None in stub mode.
    """
    llm_with_tools = None
    if not STUB_LOGISTICS and llm_registry is not None:
        try:
            llm = llm_registry.get("logistics")
            llm_with_tools = llm.bind_tools(tools)  # ReAct tool calling — no structured output
        except KeyError:
            logger.warning("No 'logistics' LLM registered — logistics agent will use stub mode.")

    @node_executor("logistics_agent")
    def logistics_agent(state: LogisticsAgentState) -> dict:
        """Call the LLM with tools bound, or return a stub response.

        If this is the first call (no messages yet), the initial human prompt
        is built from the situation summary and cluster findings. On subsequent
        calls (after tool results), the accumulated messages are passed as-is —
        LangGraph's add_messages reducer has already appended the ToolMessages.

        Always returns an AIMessage. The router inspects it: tool_calls present
        → "tools" (keep looping); absent → "extract_plan" (Phase 2).
        """
        # The logistics prompt is only needed for the live LLM call. Render it
        # defensively so a stub-only deployment — or a missing/broken template —
        # doesn't take down the stub path. A failure here is surfaced as a
        # warning; the live path below proceeds without a system prompt.
        try:
            system_prompt = prompt_registry.render("logistics", {"state": state})
        except Exception as exc:  # noqa: BLE001 — keep the stub path resilient
            logger.warning("logistics_agent: 'logistics' prompt render failed: %s", exc)
            system_prompt = None

        # Build the conversation as DISTINCT, role-tagged messages. On the first
        # call state.messages is empty, so we seed the human turn; on later ReAct
        # iterations it already holds the prior AIMessage(tool_calls) + ToolMessages
        # (appended by add_messages). Do NOT wrap this list in a single
        # HumanMessage — that collapses the tool-call/result history into one
        # turn's content and breaks the loop (and fails validation once the list
        # contains Message objects).
        convo = list(state.messages)
        if not convo:
            convo = [
                HumanMessage(
                    content=(
                        f"Situation summary:\n\n{state.situation_summary}\n\n"
                        "Using the tools available, gather resource information for "
                        "each hotspot and decide whether a ResourceAdvisory is warranted."
                    )
                )
            ]

        # Visibility regardless of stub mode — log what we would send.
        logger.info("logistics_agent SYSTEM prompt:\n%s", system_prompt)
        logger.info(
            "logistics_agent OUTGOING: %s",
            [(type(m).__name__, m.content) for m in convo],
        )

        if STUB_LOGISTICS or llm_with_tools is None:
            print(f"""\n{Colors.YELLOW}● STUB the LLM - no call to logistics {Colors.RESET}""")
            stub_content = "[STUB] Logistics plan — LLM not active in this milestone."
            stub = AIMessage(content=stub_content)
            return {
                "messages": [stub],
                "logistics_plan": stub_content,
                "status": StatusValue.COMPLETED,
            }

        # Prepend the system prompt on every call — it carries the instructions
        # and sector-analysis format the LLM needs on each ReAct iteration. If
        # the render failed above we proceed without it (already warned).
        outgoing = [SystemMessage(content=system_prompt), *convo] if system_prompt else list(convo)
        response = llm_with_tools.invoke(outgoing)

        if getattr(response, "tool_calls", None):
            logger.info(
                "logistics_agent: tool_calls=%d, continuing ReAct", len(response.tool_calls)
            )
        else:
            logger.info(
                "logistics_agent: no tool_calls — ReAct loop complete, routing to extract_plan"
            )
        return {"messages": [response], "status": StatusValue.PROCESSING}

    return logistics_agent


# ── Router ────────────────────────────────────────────────────────────────────

# Hard cap on ReAct iterations. Each round = one AI message with tool_calls
# followed by one or more ToolMessages. A normal run needs at most 2 rounds
# (resources call + advisory call). 4 allows for multiple hotspots while
# stopping runaway loops that accumulated 82K tokens in one tick.
MAX_LOGISTICS_ITERATIONS = 4


def route_after_logistics_agent(state: LogisticsAgentState) -> str:
    """Conditional edge after logistics_agent (Phase 1 ReAct loop).

    Outcomes:
      - status == ERROR             → END (node_executor already set this)
      - status == COMPLETED         → END (stub mode short-circuit)
      - no messages                 → END (nothing happened to extract)
      - last message has tool_calls → "tools" (continue the ReAct loop),
                                       unless the iteration cap is hit, in
                                       which case → "extract_plan" so we
                                       still produce a structured record of
                                       the (truncated) run
      - last message is plain text  → "extract_plan" (loop done — Phase 2
                                       converts the transcript into a
                                       LogisticsAssessment)
    """
    if state.status == StatusValue.ERROR:
        return END

    if state.status == StatusValue.COMPLETED:
        return END

    if not state.messages:
        return END

    last = state.messages[-1]
    if getattr(last, "tool_calls", None):
        tool_call_rounds = sum(
            1 for m in state.messages if isinstance(m, AIMessage) and getattr(m, "tool_calls", None)
        )
        if tool_call_rounds >= MAX_LOGISTICS_ITERATIONS:
            logger.warning(
                "logistics_agent: max iterations (%d) reached — forcing extract_plan",
                MAX_LOGISTICS_ITERATIONS,
            )
            return "extract_plan"
        return "tools"

    return "extract_plan"


# ── Node: extract_plan (Phase 2 — structured output) ──────────────────────────


def _balance_dangling_tool_calls(messages: list[BaseMessage]) -> list[BaseMessage]:
    """Close any unanswered tool_calls with a synthetic ToolMessage.

    Phase 2 re-issues the whole conversation to the provider, which rejects an
    AIMessage whose tool_calls have no matching ToolMessage. That only happens
    on the max-iteration path (loop cut before the ToolNode ran); we stub the
    open calls so the structured-output call still succeeds.
    """
    if not messages:
        return messages
    open_calls = getattr(messages[-1], "tool_calls", None) or []
    if not open_calls:
        return messages
    closers = [
        ToolMessage(
            content="Tool execution skipped: logistics ReAct iteration cap reached.",
            tool_call_id=call["id"],
        )
        for call in open_calls
    ]
    return list(messages) + closers


def _assessment_to_plan(assessment: LogisticsAssessment) -> str:
    """Render a human-readable plan string for the supervisor (which prints it)."""
    decision = "ADVISORY DISPATCHED" if assessment.advisory is not None else "NO ADVISORY"
    lines = [
        f"Logistics decision: {decision}",
        "",
        "Assessment:",
        assessment.assessment,
        "",
        f"Rationale: {assessment.advisory_rationale}",
    ]
    if assessment.data_gaps:
        lines += ["", "Data gaps:"] + [f"  - {g}" for g in assessment.data_gaps]
    if assessment.advisory is not None:
        lines += [
            "",
            f"Advisory situation: {assessment.advisory.situation}",
            f"Urgency level: {assessment.advisory.urgency_level}",
            f"Recommendation: {assessment.advisory.recommendation}",
        ]
    return "\n".join(lines)


def make_extract_plan_node(
    prompt_registry: PromptRegistry,
    llm_registry: LLMRegistry | None,
    advisory_repo: AdvisoryRepository | None = None,
):
    """Factory: Phase 2 terminal node — structured output over the finished loop.

    Reads the accumulated ReAct transcript and makes a separate LLM call with
    ``.with_structured_output(LogisticsAssessment)``. The agent's job is data
    gathering and reasoning only; this node owns the dispatch decision.

    If assessment.advisory is not None and advisory_repo is available, the
    advisory is written to the database here — not by the agent as a tool call.
    """
    structured_llm = None
    if not STUB_LOGISTICS and llm_registry is not None:
        try:
            llm = llm_registry.get("logistics_extract")
            structured_llm = llm.with_structured_output(LogisticsAssessment)
        except KeyError:
            logger.warning(
                "No 'logistics_extract' LLM registered — extract_plan will pass through."
            )

    @node_executor("extract_plan")
    def extract_plan(state: LogisticsAgentState) -> dict:
        """Convert the ReAct transcript into a structured LogisticsAssessment."""
        if structured_llm is None:
            last_text = next(
                (
                    m.content
                    for m in reversed(state.messages)
                    if isinstance(m, AIMessage) and m.content
                ),
                "No logistics plan produced.",
            )
            return {"logistics_plan": last_text, "status": StatusValue.COMPLETED}

        system_prompt = prompt_registry.render("logistics_extract", {})
        convo = _balance_dangling_tool_calls(state.messages)

        assessment: LogisticsAssessment = structured_llm.invoke(
            [SystemMessage(system_prompt), *convo]
        )

        if assessment.advisory is not None and advisory_repo is not None:
            dispatch_advisory(assessment.advisory, advisory_repo)

        plan_text = _assessment_to_plan(assessment)
        print(f"""{Colors.TEAL}{assessment.model_dump_json(indent=2)}{Colors.RESET}""")
        logger.info(
            "extract_plan: advisory=%s, observations=%d, data_gaps=%d",
            assessment.advisory is not None,
            len(assessment.observations),
            len(assessment.data_gaps),
        )

        return {
            "logistics_assessment": assessment,
            "logistics_plan": plan_text,
            "messages": [AIMessage(content=plan_text)],
            "status": StatusValue.COMPLETED,
        }

    return extract_plan
