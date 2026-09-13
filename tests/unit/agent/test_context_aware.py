from icab.agent.context_aware import (
    REACTOR_UNS_PATH,
    ContextAwareAgent,
)


class FakeGatewayClient:
    def __init__(self):
        self.calls = []

    def call_tool(
        self,
        tool_name,
        arguments,
        *,
        step=0,
        context_acquired: list[str] | None = None,
        context_consumed: list[str] | None = None,
    ):
        self.calls.append((tool_name, arguments, step))

        if tool_name == "browse_uns":
            return {
                "nodes": [
                    {
                        "path": ("site/tep/reaction/reactor/pressure"),
                        "display_name": "Reactor Pressure",
                        "node_type": "measurement",
                        "canonical_id": (
                            "urn:icab:measurement:tep_pv_reactor_pressure"
                        ),
                    },
                    {
                        "path": ("site/tep/reaction/reactor/temperature"),
                        "display_name": "Reactor Temperature",
                        "node_type": "measurement",
                        "canonical_id": (
                            "urn:icab:measurement:tep_pv_reactor_temperature"
                        ),
                    },
                    {
                        "path": ("site/tep/reaction/reactor/level"),
                        "display_name": "Reactor Level",
                        "node_type": "measurement",
                        "canonical_id": ("urn:icab:measurement:tep_pv_reactor_level"),
                    },
                ]
            }

        if tool_name == "get_current_value":
            return {
                "observation": {
                    "measurement_id": arguments["measurement_id"],
                    "value": 100.0,
                    "unit": "prototype",
                }
            }

        raise AssertionError(f"Unexpected tool: {tool_name}")


def test_context_aware_agent_discovers_measurements():
    client = FakeGatewayClient()
    agent = ContextAwareAgent(client)

    result = agent.run(
        objective="Investigate reactor operating condition.",
        initial_state={"operating_state": "NORMAL"},
    )

    assert result.objective == "Investigate reactor operating condition."

    assert client.calls[0] == (
        "browse_uns",
        {"path": REACTOR_UNS_PATH},
        1,
    )

    measurement_calls = [
        call for call in client.calls if call[0] == "get_current_value"
    ]

    assert len(measurement_calls) == 3

    measurement_ids = {call[1]["measurement_id"] for call in measurement_calls}

    assert measurement_ids == {
        "urn:icab:measurement:tep_pv_reactor_pressure",
        "urn:icab:measurement:tep_pv_reactor_temperature",
        "urn:icab:measurement:tep_pv_reactor_level",
    }


def test_context_aware_agent_records_execution_steps():
    client = FakeGatewayClient()
    agent = ContextAwareAgent(client)

    agent.run(
        objective="Investigate reactor operating condition.",
        initial_state={"operating_state": "NORMAL"},
    )

    assert client.calls[0] == (
        "browse_uns",
        {"path": REACTOR_UNS_PATH},
        1,
    )

    assert client.calls[1][0] == "get_current_value"
    assert client.calls[1][2] == 2

    assert client.calls[2][0] == "get_current_value"
    assert client.calls[2][2] == 3

    assert client.calls[3][0] == "get_current_value"
    assert client.calls[3][2] == 4


def test_context_aware_agent_tool_call_count():
    fake_client = FakeGatewayClient()
    agent = ContextAwareAgent(fake_client)

    agent.run(
        objective="Investigate the current reactor operating condition.",
        initial_state={},
    )

    assert len(fake_client.calls) == 4
    assert fake_client.calls[0][0] == "browse_uns"
    assert all(call[0] == "get_current_value" for call in fake_client.calls[1:])
