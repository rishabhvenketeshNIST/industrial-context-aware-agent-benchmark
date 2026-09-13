"""
LLM-based ICAB investigation agent (M6/M7).

This is a separate, additional Agent implementation -- it does not replace
the deterministic baselines (StructuredRetrievalAgent, ContextAwareAgent,
ArchitectureAwareAgent), which remain the controlled baseline the LLM agent
is compared against.

Loop::

    objective -> LLM -> choose ICAB tool -> tool result/observation -> LLM
    -> choose next tool -> ... -> submit_investigation -> InvestigationResult

The agent only ever reaches process/context information through
`AgentGatewayClient.call_tool`, i.e. through the Agent Gateway's HTTP tool
API -- never through a database/broker/OPC UA connection directly.

What is (and is not) recorded
------------------------------
The agent's own hidden reasoning is never captured or exposed: only
structured tool decisions (name + arguments), their observations (raw tool
results), and the final conclusion are kept, in `InvestigationResult` and
in the trace recorded via `AgentGatewayClient`'s `TraceCollector` (which
tracks per-call context_acquired/context_consumed -- the same mechanism
`ArchitectureAwareAgent` uses).
"""

from __future__ import annotations

import json
from typing import Any

from icab.agent.client import AgentGatewayClient
from icab.agent.interface import (
    Agent,
    EvidenceReference,
    InvestigationResult,
    TerminationReason,
)

from .client import LLMClient, ToolCall
from .tools import AGENT_TOOLS, SUBMIT_INVESTIGATION_TOOL_NAME, AgentTool, build_tool_specs

DEFAULT_SYSTEM_PROMPT = (
    "You are an industrial process investigation agent for the Tennessee "
    "Eastman Process. You have no knowledge of the current plant state -- "
    "you must acquire ALL process information through the provided tools. "
    "Investigate the objective by calling tools to discover and read "
    "process context, then call submit_investigation exactly once with a "
    "concise conclusion grounded only in values you actually observed "
    "through a tool call. Never state a specific measurement value you did "
    "not obtain from a tool result."
)

#: Default per-investigation tool-call budget (submit_investigation included).
DEFAULT_MAX_STEPS = 10


class LLMInvestigationAgent(Agent):
    """Agent that investigates by driving an LLMClient through a tool-calling loop."""

    def __init__(
        self,
        client: AgentGatewayClient,
        llm: LLMClient,
        *,
        max_steps: int = DEFAULT_MAX_STEPS,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        tools: tuple[AgentTool, ...] = AGENT_TOOLS,
    ) -> None:
        self.client = client
        self.llm = llm
        self.max_steps = max_steps
        self.system_prompt = system_prompt
        self.tools = tools
        self._tool_specs = build_tool_specs(tools)
        self._tools_by_name = {tool.name: tool for tool in tools}

    def run(
        self,
        *,
        objective: str,
        initial_state: dict[str, Any],
    ) -> InvestigationResult:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self.system_prompt},
            {
                "role": "user",
                "content": (
                    f"Objective: {objective}\n"
                    f"Initial state: {json.dumps(initial_state, default=str)}"
                ),
            },
        ]

        findings: dict[str, Any] = {}
        evidence: list[EvidenceReference] = []

        for step in range(1, self.max_steps + 1):
            response = self.llm.generate(messages=messages, tools=self._tool_specs)

            if not response.tool_calls:
                # The model answered directly instead of submitting -- its
                # text carries no tool-backed evidence, but is still
                # returned rather than discarded.
                return InvestigationResult(
                    objective=objective,
                    conclusion=response.content or "",
                    findings=findings,
                    evidence=evidence,
                    termination=TerminationReason.NO_TOOL_CALL,
                )

            messages.append(self._assistant_message(response.content, response.tool_calls))

            for call in response.tool_calls:
                if call.name == SUBMIT_INVESTIGATION_TOOL_NAME:
                    return InvestigationResult(
                        objective=objective,
                        conclusion=str(call.arguments.get("conclusion", "")),
                        findings=findings,
                        evidence=evidence,
                        termination=TerminationReason.SUBMITTED,
                    )

                result = self._execute_tool(call, step=step)
                findings[f"{call.name}#{step}"] = result
                evidence.append(self._evidence_for(call))

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": json.dumps(result, default=str),
                    }
                )

        return InvestigationResult(
            objective=objective,
            conclusion="Investigation did not conclude within the step budget.",
            findings=findings,
            evidence=evidence,
            termination=TerminationReason.STEP_BUDGET_EXCEEDED,
        )

    def _execute_tool(self, call: ToolCall, *, step: int) -> dict[str, Any]:
        tool = self._tools_by_name.get(call.name)

        if tool is None:
            return {"error": f"Unknown tool: {call.name}"}

        identifier = self._identifier_for(call)

        try:
            return self.client.call_tool(
                call.name,
                call.arguments,
                step=step,
                context_acquired=[identifier] if identifier else None,
                method=tool.http_method,
            )
        except Exception as error:  # surfaced to the LLM as an observation, not raised
            return {"error": str(error)}

    @staticmethod
    def _identifier_for(call: ToolCall) -> str | None:
        """Best-effort evidence/context identifier for a tool call's arguments."""

        for key in (
            "measurement_id",
            "canonical_id",
            "path",
            "node_id",
            "topic",
            "topic_filter",
        ):
            if key in call.arguments:
                return str(call.arguments[key])

        return None

    def _evidence_for(self, call: ToolCall) -> EvidenceReference:
        return EvidenceReference(
            source=call.name,
            identifier=self._identifier_for(call) or call.name,
        )

    @staticmethod
    def _assistant_message(
        content: str | None,
        tool_calls: tuple[ToolCall, ...],
    ) -> dict[str, Any]:
        return {
            "role": "assistant",
            "content": content,
            "tool_calls": [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.name,
                        "arguments": json.dumps(call.arguments),
                    },
                }
                for call in tool_calls
            ],
        }
