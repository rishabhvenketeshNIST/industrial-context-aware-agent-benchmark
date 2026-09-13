from unittest import result
from unittest.mock import Mock

import pytest

from icab.agent.architecture_aware import ArchitectureAwareAgent


def make_client() -> Mock:
    client = Mock()
    client.call_tool.side_effect = [
        {
            "nodes": [
                {
                    "node_id": "ns=2;i=2",
                    "display_name": "Pressure",
                    "node_class": "Variable",
                },
                {
                    "node_id": "ns=2;i=3",
                    "display_name": "Temperature",
                    "node_class": "Variable",
                },
            ]
        },
        {"node_id": "ns=2;i=2", "value": 2834.0},
        {"node_id": "ns=2;i=3", "value": 120.0},
    ]
    return client


def test_invalid_architecture():
    client = Mock()

    with pytest.raises(ValueError, match="Unsupported architecture"):
        ArchitectureAwareAgent(
            client,
            architecture="invalid",
        )


def test_opcua_architecture():
    client = make_client()

    agent = ArchitectureAwareAgent(
        client,
        architecture="opcua",
    )

    result = agent.run(
        objective="Investigate the reactor.",
        initial_state={},
    )

    assert result.findings["architecture"] == "opcua"
    assert result.findings["values"]["ns=2;i=2"]["value"] == 2834.0
    assert result.findings["values"]["ns=2;i=3"]["value"] == 120.0

    assert len(result.context.measurements) == 2
    assert result.context.measurements[0]["value"] in {2834.0, 120.0}
    assert result.context.provenance[0].source == "opcua"

    assert client.call_tool.call_count == 3

    calls = client.call_tool.call_args_list

    assert calls[0].args[0] == "opcua_browse"
    assert calls[1].args[0] == "opcua_read"
    assert calls[2].args[0] == "opcua_read"


def test_uns_architecture():
    client = Mock()

    client.call_tool.side_effect = [
        {
            "nodes": [
                {
                    "node_type": "measurement",
                    "canonical_id": "urn:icab:measurement:tep_pv_reactor_pressure",
                },
            ]
        },
        {
            "measurement_id": "urn:icab:measurement:tep_pv_reactor_pressure",
            "value": 2834.0,
        },
    ]

    agent = ArchitectureAwareAgent(
        client,
        architecture="uns",
    )

    result = agent.run(
        objective="Investigate the reactor.",
        initial_state={},
    )

    assert result.findings["architecture"] == "uns"
    assert (
        result.findings["measurements"]["urn:icab:measurement:tep_pv_reactor_pressure"][
            "value"
        ]
        == 2834.0
    )

    assert result.context.measurements[0]["value"] == 2834.0
    assert result.context.provenance[0].source == "uns"

    assert client.call_tool.call_args_list[0].args[0] == "browse_uns"
    assert client.call_tool.call_args_list[1].args[0] == "get_current_value"


def test_i3x_architecture():
    client = Mock()

    client.call_tool.side_effect = [
        {
            "objects": [
                {
                    "element_id": "reactor-001",
                    "display_name": "Reactor",
                }
            ]
        },
        {
            "object": {
                "element_id": "reactor-001",
                "display_name": "Reactor",
            }
        },
        {
            "related_objects": [
                {
                    "element_id": "pressure-001",
                    "display_name": "Reactor Pressure",
                },
                {
                    "element_id": "temperature-001",
                    "display_name": "Reactor Temperature",
                },
                {
                    "element_id": "level-001",
                    "display_name": "Reactor Level",
                },
            ]
        },
        {
            "element_id": "pressure-001",
            "value": 2834.0,
        },
        {
            "element_id": "temperature-001",
            "value": 120.0,
        },
        {
            "element_id": "level-001",
            "value": 50.0,
        },
    ]

    agent = ArchitectureAwareAgent(
        client,
        architecture="i3x",
    )

    result = agent.run(
        objective="Investigate the reactor.",
        initial_state={},
    )

    assert result.findings["architecture"] == "i3x"
    assert result.findings["context"]["object"]["element_id"] == "reactor-001"

    assert result.findings["values"]["pressure-001"]["value"] == 2834.0
    assert result.findings["values"]["temperature-001"]["value"] == 120.0
    assert result.findings["values"]["level-001"]["value"] == 50.0

    assert len(result.context.measurements) == 3
    assert result.context.provenance[0].source == "i3x"
    assert len(result.context.relationships) == 3

    calls = client.call_tool.call_args_list

    assert calls[0].args[0] == "i3x_get_objects"
    assert calls[1].args[0] == "i3x_get_object"
    assert calls[2].args[0] == "i3x_get_related_objects"
    assert calls[3].args[0] == "i3x_get_value"
    assert calls[4].args[0] == "i3x_get_value"
    assert calls[5].args[0] == "i3x_get_value"


def test_kg_architecture():
    client = Mock()

    client.call_tool.return_value = {
        "relationships": [
            {
                "subject": "urn:icab:equipment:reactor",
                "predicate": "MEASURES",
                "object": "urn:icab:measurement:tep_pv_reactor_pressure",
            }
        ]
    }

    agent = ArchitectureAwareAgent(
        client,
        architecture="kg",
    )

    result = agent.run(
        objective="Investigate the reactor.",
        initial_state={},
    )

    assert result.findings["architecture"] == "kg"
    assert len(result.findings["relationships"]["relationships"]) == 1

    assert result.context.relationships[0]["predicate"] == "MEASURES"
    assert result.context.provenance[0].source == "kg"

    client.call_tool.assert_called_once_with(
        "get_entity_relationships",
        {"entity_id": "urn:icab:equipment:reactor"},
        step=1,
        context_acquired=["urn:icab:equipment:reactor"],
    )
