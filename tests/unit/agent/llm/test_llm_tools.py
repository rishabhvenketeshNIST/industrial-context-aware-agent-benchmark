import pytest

from icab.agent.llm.tools import (
    AGENT_TOOLS,
    ARCHITECTURE_TOOL_NAMES,
    SUBMIT_INVESTIGATION_TOOL_NAME,
    AgentTool,
    build_tool_spec,
    build_tool_specs,
)


def test_build_tool_spec_matches_openai_function_shape():
    tool = AGENT_TOOLS[0]

    spec = build_tool_spec(tool)

    assert spec["type"] == "function"
    assert spec["function"]["name"] == tool.name
    assert spec["function"]["description"] == tool.description
    assert spec["function"]["parameters"]["type"] == "object"


def test_get_current_value_tool_schema_requires_measurement_id():
    tool = next(t for t in AGENT_TOOLS if t.name == "get_current_value")

    spec = build_tool_spec(tool)
    parameters = spec["function"]["parameters"]

    assert "measurement_id" in parameters["properties"]
    assert "measurement_id" in parameters["required"]


def test_build_tool_specs_includes_submit_investigation():
    specs = build_tool_specs()

    names = {spec["function"]["name"] for spec in specs}

    assert SUBMIT_INVESTIGATION_TOOL_NAME in names
    assert len(specs) == len(AGENT_TOOLS) + 1


def test_every_agent_tool_produces_a_valid_spec():
    for tool in AGENT_TOOLS:
        spec = build_tool_spec(tool)
        assert spec["function"]["parameters"].get("type") == "object"
        # No leaked pydantic model titles in the LLM-facing schema.
        assert "title" not in spec["function"]["parameters"]


def test_i3x_tools_use_get_and_hand_written_parameters():
    i3x_tools = {tool.name: tool for tool in AGENT_TOOLS if tool.name.startswith("i3x_")}

    assert set(i3x_tools) == set(ARCHITECTURE_TOOL_NAMES["i3x"])

    for tool in i3x_tools.values():
        assert tool.http_method == "GET"
        assert tool.request_model is None
        assert tool.parameters is not None

    value_spec = build_tool_spec(i3x_tools["i3x_get_value"])
    assert "element_id" in value_spec["function"]["parameters"]["properties"]
    assert "element_id" in value_spec["function"]["parameters"]["required"]


def test_agent_tool_requires_exactly_one_of_request_model_or_parameters():
    with pytest.raises(ValueError):
        AgentTool(name="x", description="x")

    with pytest.raises(ValueError):
        from icab.gateway.schemas import GetCurrentValueRequest

        AgentTool(
            name="x",
            description="x",
            request_model=GetCurrentValueRequest,
            parameters={"type": "object"},
        )
