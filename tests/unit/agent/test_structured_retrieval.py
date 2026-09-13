import httpx

from icab.agent.baseline.structured_retrieval import (
    REACTOR_ID,
    REACTOR_PRESSURE_ID,
    StructuredRetrievalAgent,
)
from icab.agent.client import AgentGatewayClient
from icab.trace.collector import TraceCollector
from icab.trace.storage import JsonlTraceStorage


class FakeGatewayClient:
    def __init__(self):
        self.calls = []

    def call_tool(self, tool_name, arguments, *, step=0):
        self.calls.append((tool_name, arguments, step))

        if tool_name == "get_current_value":
            return {
                "observation": {
                    "measurement_id": REACTOR_PRESSURE_ID,
                    "value": 2834.0,
                    "unit": "kPa",
                }
            }

        if tool_name == "get_entity_relationships":
            return {
                "relationships": [
                    {
                        "subject": REACTOR_ID,
                        "predicate": "PART_OF",
                        "object": "urn:icab:processcell:reaction",
                    }
                ]
            }

        raise AssertionError(f"Unexpected tool: {tool_name}")


def test_structured_retrieval_agent_runs_investigation():
    client = FakeGatewayClient()
    agent = StructuredRetrievalAgent(client)

    result = agent.run(
        objective="Investigate reactor operating condition.",
        initial_state={
            "operating_state": "NORMAL",
        },
    )

    assert result.objective == ("Investigate reactor operating condition.")

    assert result.findings["reactor_pressure"]["observation"]["value"] == 2834.0

    assert len(result.findings["reactor_relationships"]["relationships"]) == 1

    assert result.evidence[0].identifier == REACTOR_PRESSURE_ID
    assert result.evidence[1].identifier == REACTOR_ID

    assert client.calls == [
        (
            "get_current_value",
            {
                "measurement_id": REACTOR_PRESSURE_ID,
            },
            1,
        ),
        (
            "get_entity_relationships",
            {
                "canonical_id": REACTOR_ID,
            },
            2,
        ),
    ]


def test_structured_retrieval_agent_records_execution_trace(
    monkeypatch,
):
    def fake_post(url, **kwargs):
        if url.endswith("/get_current_value"):
            return httpx.Response(
                200,
                json={
                    "observation": {
                        "value": 2834.0,
                        "unit": "kPa",
                    }
                },
                request=httpx.Request("POST", url),
            )

        if url.endswith("/get_entity_relationships"):
            return httpx.Response(
                200,
                json={
                    "relationships": [
                        {
                            "subject": REACTOR_ID,
                            "predicate": "PART_OF",
                            "object": "urn:icab:processcell:reaction",
                        }
                    ]
                },
                request=httpx.Request("POST", url),
            )

        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr(httpx, "post", fake_post)

    trace = TraceCollector()

    client = AgentGatewayClient(
        "http://localhost:8000",
        trace_collector=trace,
    )

    agent = StructuredRetrievalAgent(client)

    agent.run(
        objective="Investigate reactor operating condition.",
        initial_state={
            "operating_state": "NORMAL",
        },
    )

    events = trace.events()

    assert len(events) == 2

    assert events[0].step == 1
    assert events[0].tool == "get_current_value"

    assert events[1].step == 2
    assert events[1].tool == "get_entity_relationships"


def test_structured_retrieval_agent_trace_can_be_persisted(
    monkeypatch,
    tmp_path,
):
    def fake_post(url, **kwargs):
        if url.endswith("/get_current_value"):
            return httpx.Response(
                200,
                json={
                    "observation": {
                        "value": 2834.0,
                        "unit": "kPa",
                    }
                },
                request=httpx.Request("POST", url),
            )

        if url.endswith("/get_entity_relationships"):
            return httpx.Response(
                200,
                json={
                    "relationships": [
                        {
                            "subject": REACTOR_ID,
                            "predicate": "PART_OF",
                            "object": "urn:icab:processcell:reaction",
                        }
                    ]
                },
                request=httpx.Request("POST", url),
            )

        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr(httpx, "post", fake_post)

    trace = TraceCollector()

    client = AgentGatewayClient(
        "http://localhost:8000",
        trace_collector=trace,
    )

    agent = StructuredRetrievalAgent(client)

    agent.run(
        objective="Investigate reactor operating condition.",
        initial_state={
            "operating_state": "NORMAL",
        },
    )

    path = tmp_path / "investigation.jsonl"

    storage = JsonlTraceStorage()
    storage.write(path, trace.events())

    loaded_events = storage.read(path)

    assert len(loaded_events) == 2
    assert loaded_events[0].step == 1
    assert loaded_events[0].tool == "get_current_value"
    assert loaded_events[1].step == 2
    assert loaded_events[1].tool == "get_entity_relationships"
