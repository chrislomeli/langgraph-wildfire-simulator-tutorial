"""evals.escalation.task — EscalationTask: system-under-test adapter.

Wraps the evaluate node's LLM path as a Task[EscalationCase, Escalation].
All prompt context (sector summary, forecast, history) is carried by the
EscalationCase — no world engine, no DB, no grid required at eval time.

The only dependencies are PromptRegistry and the 'classifier' LLM.
"""

from __future__ import annotations

import json

from langchain_core.messages import HumanMessage, SystemMessage

from agents.commons.schemas import Escalation, Evaluation
from evals.escalation.cases import EscalationCase
from evals.framework.core import Task, Usage
from llm.llm_registry import LLMRegistry
from prompts import PromptRegistry


class EscalationTask:
    """Task[EscalationCase, Escalation] — runs one authored case through the evaluate LLM.

    Mirrors make_evaluate_node's LLM path exactly (same prompt template, same
    structured-output call), but takes pre-built context from the case rather
    than deriving it from the world engine.
    """

    def __init__(
        self,
        *,
        prompt_registry: PromptRegistry,
        llm_registry: LLMRegistry,
        prompt_version: str = "v1",
    ) -> None:
        self.label = f"evaluate-node/{prompt_version}"
        self._prompts = prompt_registry
        llm = llm_registry.get("classifier")
        self._structured = llm.with_structured_output(
            Evaluation, method="function_calling", include_raw=True
        )

    async def run(self, case: EscalationCase) -> tuple[Escalation | None, Usage]:
        row, col = case.cell.row, case.cell.col

        system_prompt = self._prompts.render(
            "evaluate",
            context=dict(
                sector_id=case.id,
                max_rows=case.max_rows,
                max_columns=case.max_cols,
                row=row,
                column=col,
                scenario=case.scenario_text,
                history=json.dumps(case.history, indent=2),
                forecast=json.dumps(case.forecast, indent=2),
            ),
        )
        human_prompt = (
            f"Readings for ANCHOR cell ({row},{col})\n"
            + case.cell.model_dump_json(indent=2)
        )

        try:
            out = await self._structured.ainvoke(
                [SystemMessage(system_prompt), HumanMessage(human_prompt)]
            )
        except Exception:
            return None, Usage()

        evaluation: Evaluation | None = out.get("parsed")
        if evaluation is None:
            return None, Usage()

        raw = out.get("raw")
        tokens = getattr(getattr(raw, "usage_metadata", None), "total_tokens", 0) or 0

        escalation = Escalation(
            row=row,
            col=col,
            layer=case.cell.layer,
            sector_id=case.id,
            **evaluation.model_dump(),
        )
        return escalation, Usage(total_tokens=tokens)
