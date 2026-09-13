import httpx
import pytest

from icab.agent.client import AgentGatewayClient
from icab.trace.collector import TraceCollector


def test_agent_gateway_client_calls_tool(monkeypatch):
    captured = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["json"] = kwargs["json"]

        return httpx.Response(
            200,
            json={"observation": {"value": 2834.0}},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    client = AgentGatewayClient("http://localhost:8000/")

    result = client.call_tool(
        "get_current_value",
        {"measurement_id": ("urn:icab:measurement:tep_pv_reactor_pressure")},
    )

    assert result["observation"]["value"] == 2834.0
    assert captured["url"] == "http://localhost:8000/tools/get_current_value"
    assert captured["json"]["measurement_id"] == (
        "urn:icab:measurement:tep_pv_reactor_pressure"
    )


def test_agent_gateway_client_raises_for_http_error(monkeypatch):
    def fake_post(url, **kwargs):
        return httpx.Response(
            404,
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    client = AgentGatewayClient("http://localhost:8000")

    with pytest.raises(httpx.HTTPStatusError):
        client.call_tool("unknown_tool", {})


def test_agent_gateway_client_records_trace(monkeypatch):
    def fake_post(url, **kwargs):
        return httpx.Response(
            200,
            json={"value": 2834.0},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    trace = TraceCollector()

    client = AgentGatewayClient(
        "http://localhost:8000",
        trace_collector=trace,
    )

    result = client.call_tool(
        "get_current_value",
        {"measurement_id": "test-measurement"},
        step=3,
    )

    assert result["value"] == 2834.0

    events = trace.events()

    assert len(events) == 1
    assert events[0].step == 3
    assert events[0].action == "tool_call"
    assert events[0].tool == "get_current_value"
    assert events[0].arguments == {"measurement_id": "test-measurement"}
    assert events[0].result == {"value": 2834.0}


def test_agent_gateway_client_without_trace_still_works(monkeypatch):
    def fake_post(url, **kwargs):
        return httpx.Response(
            200,
            json={"value": 2834.0},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    client = AgentGatewayClient("http://localhost:8000")

    result = client.call_tool(
        "get_current_value",
        {"measurement_id": "test-measurement"},
    )

    assert result["value"] == 2834.0
