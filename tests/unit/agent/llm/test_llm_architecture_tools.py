import pytest

from icab.agent.llm.tools import AGENT_TOOLS, tools_for_architectures


def test_historian_only_excludes_knowledge_graph_and_uns():
    tools = tools_for_architectures(["historian"])
    names = {tool.name for tool in tools}

    assert names == {"get_current_value", "get_historical_values"}


def test_multiple_architectures_are_unioned_without_duplicates():
    tools = tools_for_architectures(["historian", "knowledge_graph"])
    names = {tool.name for tool in tools}

    assert names == {
        "get_current_value",
        "get_historical_values",
        "get_entity_relationships",
    }


def test_all_architectures_cover_every_agent_tool():
    all_architectures = ["historian", "knowledge_graph", "uns", "opcua", "mqtt"]
    tools = tools_for_architectures(all_architectures)

    assert set(tools) == set(AGENT_TOOLS)


def test_unknown_architecture_raises():
    with pytest.raises(ValueError):
        tools_for_architectures(["not_a_real_architecture"])
