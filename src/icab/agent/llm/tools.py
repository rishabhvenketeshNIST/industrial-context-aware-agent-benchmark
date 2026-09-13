"""
The ICAB tool registry exposed to the LLM investigation agent.

Tool parameter schemas are derived directly from the Agent Gateway's own
Pydantic request models (``icab.gateway.schemas``) rather than hand-written
a second time, so the LLM-visible tool contract cannot silently drift from
the actual gateway API. The agent never gets direct database/broker/OPC UA
access -- only these gateway-fronted tools, plus the synthetic
``submit_investigation`` action that ends an investigation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from icab.gateway.schemas import (
    BrowseMQTTRequest,
    BrowseUNSRequest,
    GetCurrentValueRequest,
    GetEntityRelationshipsRequest,
    GetHistoricalValuesRequest,
    OPCUABrowseRequest,
    OPCUAReadRequest,
    ReadMQTTRequest,
)


@dataclass(frozen=True)
class AgentTool:
    """One gateway tool as exposed to the LLM."""

    name: str
    description: str
    request_model: type[BaseModel]


#: Tools available to the LLM agent. Limited to the gateway's POST-based
#: tools that `icab.agent.client.AgentGatewayClient.call_tool` supports
#: today; the GET-based i3X tools (`i3x_get_*`) are not yet included --
#: see docs/architecture/llm-agent.md.
AGENT_TOOLS: tuple[AgentTool, ...] = (
    AgentTool(
        name="get_current_value",
        description=(
            "Get the latest historian value for a measurement, by its "
            "canonical ICAB measurement id (e.g. "
            "'urn:icab:measurement:reactor_pressure')."
        ),
        request_model=GetCurrentValueRequest,
    ),
    AgentTool(
        name="get_historical_values",
        description=(
            "Get historian values for a measurement between two "
            "ISO-8601 timestamps."
        ),
        request_model=GetHistoricalValuesRequest,
    ),
    AgentTool(
        name="get_entity_relationships",
        description=(
            "Get knowledge-graph relationships for a canonical ICAB "
            "entity id (e.g. an equipment or measurement id)."
        ),
        request_model=GetEntityRelationshipsRequest,
    ),
    AgentTool(
        name="browse_uns",
        description=(
            "Browse the Unified Namespace tree under a path to discover "
            "child assets/measurements (e.g. 'site/tep/reaction/reactor')."
        ),
        request_model=BrowseUNSRequest,
    ),
    AgentTool(
        name="opcua_browse",
        description="Browse OPC UA server nodes under a node id.",
        request_model=OPCUABrowseRequest,
    ),
    AgentTool(
        name="opcua_read",
        description="Read the current value of an OPC UA node.",
        request_model=OPCUAReadRequest,
    ),
    AgentTool(
        name="browse_mqtt",
        description=(
            "Discover ICAB MQTT topics (and their retained values) under "
            "a topic filter, e.g. 'icab/tep/reactor/#'."
        ),
        request_model=BrowseMQTTRequest,
    ),
    AgentTool(
        name="read_mqtt",
        description="Read the retained value on a single, fully-qualified MQTT topic.",
        request_model=ReadMQTTRequest,
    ),
)

#: The synthetic action that ends an investigation. Not a gateway tool --
#: handled directly by LLMInvestigationAgent.
SUBMIT_INVESTIGATION_TOOL_NAME = "submit_investigation"

_SUBMIT_INVESTIGATION_SPEC: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": SUBMIT_INVESTIGATION_TOOL_NAME,
        "description": (
            "Submit the final investigation conclusion once enough evidence "
            "has been gathered through the other tools. Call this exactly "
            "once, as the last action, instead of answering directly."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "conclusion": {
                    "type": "string",
                    "description": (
                        "A concise, evidence-grounded conclusion, referencing "
                        "only values actually observed through tool calls."
                    ),
                },
            },
            "required": ["conclusion"],
        },
    },
}


def _json_schema_for(model: type[BaseModel]) -> dict[str, Any]:
    schema = model.model_json_schema()
    schema.pop("title", None)

    for prop in schema.get("properties", {}).values():
        prop.pop("title", None)

    return schema


def build_tool_spec(tool: AgentTool) -> dict[str, Any]:
    """Build one OpenAI-format ``tools=[...]`` entry for an :class:`AgentTool`."""

    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": _json_schema_for(tool.request_model),
        },
    }


def build_tool_specs(
    tools: tuple[AgentTool, ...] = AGENT_TOOLS,
) -> list[dict[str, Any]]:
    """Build the full OpenAI-format ``tools=[...]`` list, including submission."""

    return [build_tool_spec(tool) for tool in tools] + [_SUBMIT_INVESTIGATION_SPEC]


#: Which AGENT_TOOLS belong to each named context architecture. Used to
#: restrict a scenario's agent to only the architectures it declares
#: available (`BenchmarkScenario.available_architectures`) -- per the
#: locked research principle that architecture comparisons must reflect
#: real tool restrictions, not just a relabeled run with every tool given
#: to every agent.
ARCHITECTURE_TOOL_NAMES: dict[str, tuple[str, ...]] = {
    "historian": ("get_current_value", "get_historical_values"),
    "knowledge_graph": ("get_entity_relationships",),
    "uns": ("browse_uns",),
    "opcua": ("opcua_browse", "opcua_read"),
    "mqtt": ("browse_mqtt", "read_mqtt"),
}


def tools_for_architectures(
    architectures: list[str],
    *,
    tools: tuple[AgentTool, ...] = AGENT_TOOLS,
) -> tuple[AgentTool, ...]:
    """Return only the tools belonging to the given architecture names."""

    tools_by_name = {tool.name: tool for tool in tools}
    allowed_names: set[str] = set()

    for architecture in architectures:
        try:
            allowed_names.update(ARCHITECTURE_TOOL_NAMES[architecture])
        except KeyError:
            raise ValueError(f"Unknown architecture: {architecture!r}") from None

    return tuple(tool for tool in tools if tool.name in allowed_names)
