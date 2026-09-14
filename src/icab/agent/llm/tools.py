"""
The ICAB tool registry exposed to the LLM investigation agent.

Tool parameter schemas are derived directly from the Agent Gateway's own
Pydantic request models (``icab.gateway.schemas``) rather than hand-written
a second time, so the LLM-visible tool contract cannot silently drift from
the actual gateway API. The agent never gets direct database/broker/OPC UA
access -- only these gateway-fronted tools, plus the synthetic
``submit_investigation`` action that ends an investigation.

The i3X tools are the exception: their gateway routes take individual
FastAPI query parameters rather than a Pydantic request body (see
``icab.gateway.app``'s ``i3x_get_*`` routes), so there is no request model
to derive a schema from -- their ``AgentTool.parameters`` is hand-written
JSON Schema instead, and they are called over GET (``AgentTool.http_method``)
rather than POST.
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
    request_model: type[BaseModel] | None = None
    parameters: dict[str, Any] | None = None
    http_method: str = "POST"

    def __post_init__(self) -> None:
        if (self.request_model is None) == (self.parameters is None):
            raise ValueError(
                f"AgentTool {self.name!r} must set exactly one of "
                "request_model or parameters."
            )


#: Tools available to the LLM agent.
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
    AgentTool(
        name="i3x_get_objects",
        description=(
            "Discover i3X objects (e.g. equipment) on ICAB's private "
            "TEP-backed i3X server, optionally filtered by object type."
        ),
        parameters={
            "type": "object",
            "properties": {
                "type_element_id": {
                    "type": "string",
                    "description": "Optional i3X object-type element id to filter by.",
                },
            },
        },
        http_method="GET",
    ),
    AgentTool(
        name="i3x_get_object",
        description=(
            "Get one i3X object by element id (e.g. an equipment or "
            "measurement discovered via i3x_get_objects/i3x_get_related_objects)."
        ),
        parameters={
            "type": "object",
            "properties": {
                "element_id": {"type": "string"},
            },
            "required": ["element_id"],
        },
        http_method="GET",
    ),
    AgentTool(
        name="i3x_get_related_objects",
        description=(
            "Get i3X objects related to one or more element ids (e.g. the "
            "measurements composed under an equipment object)."
        ),
        parameters={
            "type": "object",
            "properties": {
                "element_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "relationship_type": {
                    "type": "string",
                    "description": "Optional relationship type to filter by.",
                },
            },
            "required": ["element_ids"],
        },
        http_method="GET",
    ),
    AgentTool(
        name="i3x_get_value",
        description="Get the current value of an i3X object (e.g. a measurement).",
        parameters={
            "type": "object",
            "properties": {
                "element_id": {"type": "string"},
                "max_depth": {"type": "integer", "default": 1},
            },
            "required": ["element_id"],
        },
        http_method="GET",
    ),
    AgentTool(
        name="i3x_get_history",
        description="Get historical values of an i3X object between two ISO-8601 timestamps.",
        parameters={
            "type": "object",
            "properties": {
                "element_id": {"type": "string"},
                "start_time": {"type": "string"},
                "end_time": {"type": "string"},
                "max_depth": {"type": "integer", "default": 1},
            },
            "required": ["element_id", "start_time", "end_time"],
        },
        http_method="GET",
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

    parameters = (
        _json_schema_for(tool.request_model)
        if tool.request_model is not None
        else tool.parameters
    )

    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": parameters,
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
    "i3x": (
        "i3x_get_objects",
        "i3x_get_object",
        "i3x_get_related_objects",
        "i3x_get_value",
        "i3x_get_history",
    ),
}


def tools_for_architectures(
    architectures: list[str],
    *,
    tools: tuple[AgentTool, ...] = AGENT_TOOLS,
) -> tuple[AgentTool, ...]:
    """Return only the tools belonging to the given architecture names."""

    allowed_names: set[str] = set()

    for architecture in architectures:
        try:
            allowed_names.update(ARCHITECTURE_TOOL_NAMES[architecture])
        except KeyError:
            raise ValueError(f"Unknown architecture: {architecture!r}") from None

    return tuple(tool for tool in tools if tool.name in allowed_names)
