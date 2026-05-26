"""evals.escalation.task — EscalationTask: system-under-test adapter.

Proxies directly to call_evaluate_llm() in the cluster node so the eval
runs the exact same prompt-render + LLM path as the live graph.

The only dependencies are PromptRegistry and the 'classifier' LLM.
No world engine, DB, or grid is required at eval time — all context is
pre-built inside each EscalationCase.
"""

from __future__ import annotations

from agents.cluster.nodes import call_evaluate_llm
from agents.commons.schemas import Escalation
from evals.escalation.cases import EscalationCase
from evals.framework.core import Usage


class EscalationTask:
    """Task[EscalationCase, Escalation] — runs one authored case through the evaluate LLM."""

    def __init__(
        self,
        *,
        prompt_registry,
        llm_registry,
        prompt_version: str = "v1",
    ) -> None:
        self.label = f"evaluate-node/{prompt_version}"
        self._prompt_registry = prompt_registry
        self._llm_registry = llm_registry

    async def run(self, case: EscalationCase) -> tuple[Escalation | None, Usage]:
        escalation, tokens = await call_evaluate_llm(
            case,
            prompt_registry=self._prompt_registry,
            llm_registry=self._llm_registry,
            trial_only=False,
        )
        return escalation, Usage(total_tokens=tokens)
