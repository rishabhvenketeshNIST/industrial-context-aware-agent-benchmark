from typing import Any

import httpx

from icab.trace.collector import TraceCollector


class AgentGatewayClient:
    """Client used by an ICAB agent to invoke Gateway tools."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 30.0,
        trace_collector: TraceCollector | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.trace_collector = trace_collector

    def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        *,
        step: int = 0,
        context_acquired: list[str] | None = None,
        context_consumed: list[str] | None = None,
        method: str = "POST",
    ) -> dict[str, Any]:
        """
        Invoke a Gateway tool and optionally record the interaction.

        Most tools are POST with a JSON body; the i3X tools are GET with
        query parameters (matching their FastAPI routes) -- pass
        ``method="GET"`` for those.
        """

        url = f"{self.base_url}/tools/{tool_name}"

        if method == "GET":
            response = httpx.get(url, params=arguments, timeout=self.timeout)
        else:
            response = httpx.post(url, json=arguments, timeout=self.timeout)

        response.raise_for_status()

        result = response.json()

        if self.trace_collector is not None:
            self.trace_collector.record(
                step=step,
                action="tool_call",
                tool=tool_name,
                arguments=arguments,
                result=result,
                context_acquired=context_acquired,
                context_consumed=context_consumed,
            )

        return result
