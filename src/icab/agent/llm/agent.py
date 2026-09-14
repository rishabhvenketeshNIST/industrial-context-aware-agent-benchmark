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
tracks per-call context_acquired -- the same mechanism `ArchitectureAwareAgent`
uses). Unlike the deterministic baselines, this agent does NOT currently
populate context_consumed for any call -- see
docs/architecture/llm-agent.md#context_acquired-vs-context_consumed for
the precise definitions and why (a documented gap, not a scoring bug:
context_acquired/context_consumed feed no EvaluationReport score).
"""

from __future__ import annotations

import json
import time
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
        max_tool_calls: int | None = None,
        max_context_tokens: int | None = None,
        max_wall_time_seconds: float | None = None,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        tools: tuple[AgentTool, ...] = AGENT_TOOLS,
    ) -> None:
        self.client = client
        self.llm = llm
        self.max_steps = max_steps
        #: M13-D: three additional, OPTIONAL budgets -- all default to
        #: None (unbounded), so existing callers/tests see no behavior
        #: change unless they opt in. `max_steps` alone (unchanged) still
        #: counts LOOP ITERATIONS, not individual tool calls -- one LLM
        #: turn can request several tool calls at once, which
        #: `max_tool_calls` counts and bounds separately.
        self.max_tool_calls = max_tool_calls
        self.max_context_tokens = max_context_tokens
        self.max_wall_time_seconds = max_wall_time_seconds
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
        started_at = time.perf_counter()
        total_tool_calls = 0
        total_tokens_used = 0

        for step in range(1, self.max_steps + 1):
            if (
                self.max_wall_time_seconds is not None
                and time.perf_counter() - started_at >= self.max_wall_time_seconds
            ):
                return InvestigationResult(
                    objective=objective,
                    conclusion="Investigation stopped: wall-time budget exceeded.",
                    findings=findings,
                    evidence=evidence,
                    termination=TerminationReason.WALL_TIME_BUDGET_EXCEEDED,
                )

            response = self.llm.generate(messages=messages, tools=self._tool_specs)

            if self.client.trace_collector is not None and response.token_usage is not None:
                # A separate action from "tool_call" -- this is the LLM
                # provider call itself, not an ICAB Gateway tool, recorded
                # only for token-usage accounting (ExperimentRecord.total_tokens).
                self.client.trace_collector.record(
                    step=step,
                    action="llm_generate",
                    token_usage=response.token_usage,
                )

            if response.token_usage is not None:
                total_tokens_used += response.token_usage.get("total_tokens", 0)
                if self.max_context_tokens is not None and total_tokens_used > self.max_context_tokens:
                    return InvestigationResult(
                        objective=objective,
                        conclusion="Investigation stopped: token budget exceeded.",
                        findings=findings,
                        evidence=evidence,
                        termination=TerminationReason.TOKEN_BUDGET_EXCEEDED,
                    )

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

                if self.max_tool_calls is not None and total_tool_calls >= self.max_tool_calls:
                    return InvestigationResult(
                        objective=objective,
                        conclusion="Investigation stopped: tool-call budget exceeded.",
                        findings=findings,
                        evidence=evidence,
                        termination=TerminationReason.TOOL_CALL_BUDGET_EXCEEDED,
                    )

                result = self._execute_tool(call, step=step)
                total_tool_calls += 1
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
                # Deliberately never passes context_consumed -- see
                # docs/architecture/llm-agent.md#context_acquired-vs-context_consumed.
                # This agent's tool sequence has no single, deterministic
                # earlier-discovery to attribute a later call to, unlike
                # the fixed baselines that mechanically iterate over
                # their own browse response.
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
