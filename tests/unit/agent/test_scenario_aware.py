import pytest

from icab.agent.baseline.scenario_aware import ScenarioAwareBaselineAgent


class FakeGatewayClient:
    def __init__(self):
        self.calls = []

    def call_tool(
        self,
        tool_name,
        arguments,
        *,
        step=0,
        context_acquired=None,
        context_consumed=None,
    ):
        self.calls.append((tool_name, arguments, step))

        if tool_name == "browse_uns":
            return {
                "nodes": [
                    {
                        "path": "site/tep/reactor/reactor_pressure",
                        "display_name": "Reactor pressure",
                        "node_type": "measurement",
                        "canonical_id": "urn:icab:measurement:reactor_pressure",
                    },
                    {
                        "path": "site/tep/reactor/reactor_level",
                        "display_name": "Reactor level",
                        "node_type": "measurement",
                        "canonical_id": "urn:icab:measurement:reactor_level",
                    },
                ]
            }

        if tool_name == "get_current_value":
            measurement_id = arguments["measurement_id"]
            return {
                "observation": {
                    "measurement_id": measurement_id,
                    "value": 2705.0 if "pressure" in measurement_id else 75.0,
                    "unit": "kPa gauge" if "pressure" in measurement_id else "%",
                }
            }

        if tool_name == "get_entity_relationships":
            return {
                "relationships": [
                    {
                        "subject": "urn:icab:equipment:reactor",
                        "predicate": "MONITORS",
                        "object": "urn:icab:measurement:reactor_pressure",
                    }
                ]
            }

        raise AssertionError(f"Unexpected tool: {tool_name}")


def test_rejects_unknown_equipment_key():
    client = FakeGatewayClient()

    with pytest.raises(ValueError):
        ScenarioAwareBaselineAgent(client, equipment_key="not_a_real_equipment")


def test_defaults_to_reactor_and_uses_real_canonical_ids():
    client = FakeGatewayClient()
    agent = ScenarioAwareBaselineAgent(client)

    assert agent.equipment_key == "reactor"
    assert agent.equipment_id == "urn:icab:equipment:reactor"
    assert agent.equipment_path == "site/tep/reactor"


def test_run_discovers_and_retrieves_real_measurements():
    client = FakeGatewayClient()
    agent = ScenarioAwareBaselineAgent(client)

    result = agent.run(objective="Investigate the reactor.", initial_state={})

    assert client.calls[0] == ("browse_uns", {"path": "site/tep/reactor"}, 1)

    value_calls = [call for call in client.calls if call[0] == "get_current_value"]
    assert len(value_calls) == 2
    measurement_ids = {call[1]["measurement_id"] for call in value_calls}
    assert measurement_ids == {
        "urn:icab:measurement:reactor_pressure",
        "urn:icab:measurement:reactor_level",
    }

    relationship_calls = [
        call for call in client.calls if call[0] == "get_entity_relationships"
    ]
    assert relationship_calls == [
        ("get_entity_relationships", {"canonical_id": "urn:icab:equipment:reactor"}, 4)
    ]


def test_result_carries_real_ids_as_structured_evidence():
    client = FakeGatewayClient()
    agent = ScenarioAwareBaselineAgent(client)

    result = agent.run(objective="Investigate the reactor.", initial_state={})

    identifiers = {evidence.identifier for evidence in result.evidence}
    assert "urn:icab:measurement:reactor_pressure" in identifiers
    assert "urn:icab:measurement:reactor_level" in identifiers
    assert "urn:icab:equipment:reactor" in identifiers

    assert "urn:icab:measurement:reactor_pressure" in result.conclusion
    assert "2705.0" in result.conclusion


def test_run_is_deterministic_across_repeated_calls():
    client_a = FakeGatewayClient()
    client_b = FakeGatewayClient()

    result_a = ScenarioAwareBaselineAgent(client_a).run(objective="obj", initial_state={})
    result_b = ScenarioAwareBaselineAgent(client_b).run(objective="obj", initial_state={})

    assert result_a.conclusion == result_b.conclusion
    assert client_a.calls == client_b.calls


def test_can_target_a_different_equipment_item():
    client = FakeGatewayClient()
    agent = ScenarioAwareBaselineAgent(client, equipment_key="stripper")

    assert agent.equipment_id == "urn:icab:equipment:stripper"
    assert agent.equipment_path == "site/tep/stripper"
