import httpx

from icab.agent.client import AgentGatewayClient
from icab.agent.llm.agent import LLMInvestigationAgent
from icab.agent.llm.client import LLMResponse, MockLLMClient, ToolCall


def _client(monkeypatch, response_json):
    def fake_post(url, **kwargs):
        return httpx.Response(200, json=response_json, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)

    return AgentGatewayClient("http://localhost:8000")


def test_agent_calls_tool_then_submits(monkeypatch):
    gateway_client = _client(
        monkeypatch,
        {"observation": {"value": 2705.0, "unit": "kPa gauge"}},
    )

    llm = MockLLMClient(
        [
            LLMResponse(
                content=None,
                tool_calls=(
                    ToolCall(
                        id="call-1",
                        name="get_current_value",
                        arguments={
                            "measurement_id": "urn:icab:measurement:reactor_pressure"
                        },
                    ),
                ),
            ),
            LLMResponse(
                content=None,
                tool_calls=(
                    ToolCall(
                        id="call-2",
                        name="submit_investigation",
                        arguments={"conclusion": "Reactor pressure is 2705 kPa."},
                    ),
                ),
            ),
        ]
    )

    agent = LLMInvestigationAgent(gateway_client, llm)

    result = agent.run(
        objective="Investigate reactor pressure.",
        initial_state={},
    )

    assert result.conclusion == "Reactor pressure is 2705 kPa."
    assert len(result.evidence) == 1
    assert result.evidence[0].source == "get_current_value"
    assert result.evidence[0].identifier == "urn:icab:measurement:reactor_pressure"
    assert len(result.findings) == 1


def test_agent_feeds_tool_result_back_to_llm(monkeypatch):
    gateway_client = _client(monkeypatch, {"observation": {"value": 42.0}})

    llm = MockLLMClient(
        [
            LLMResponse(
                content=None,
                tool_calls=(
                    ToolCall(id="call-1", name="get_current_value", arguments={"measurement_id": "x"}),
                ),
            ),
            LLMResponse(
                content=None,
                tool_calls=(ToolCall(id="call-2", name="submit_investigation", arguments={"conclusion": "done"}),),
            ),
        ]
    )

    agent = LLMInvestigationAgent(gateway_client, llm)
    agent.run(objective="obj", initial_state={})

    # Second generate() call must have seen the tool's observation.
    second_call_messages = llm.calls[1]["messages"]
    tool_messages = [m for m in second_call_messages if m["role"] == "tool"]

    assert len(tool_messages) == 1
    assert "42.0" in tool_messages[0]["content"]


def test_agent_returns_direct_answer_with_no_tool_calls(monkeypatch):
    gateway_client = _client(monkeypatch, {})

    llm = MockLLMClient([LLMResponse(content="I cannot investigate this.", tool_calls=())])

    agent = LLMInvestigationAgent(gateway_client, llm)

    result = agent.run(objective="obj", initial_state={})

    assert result.conclusion == "I cannot investigate this."
    assert result.evidence == []


def test_agent_stops_at_max_steps_without_submission(monkeypatch):
    gateway_client = _client(monkeypatch, {"observation": {"value": 1.0}})

    # Always calls a tool, never submits.
    responses = [
        LLMResponse(
            content=None,
            tool_calls=(ToolCall(id=f"call-{i}", name="get_current_value", arguments={"measurement_id": "x"}),),
        )
        for i in range(10)
    ]
    llm = MockLLMClient(responses)

    agent = LLMInvestigationAgent(gateway_client, llm, max_steps=3)

    result = agent.run(objective="obj", initial_state={})

    assert "step budget" in result.conclusion
    assert len(llm.calls) == 3
    assert len(result.evidence) == 3


def test_agent_handles_unknown_tool_call_gracefully(monkeypatch):
    gateway_client = _client(monkeypatch, {"observation": {"value": 1.0}})

    llm = MockLLMClient(
        [
            LLMResponse(
                content=None,
                tool_calls=(ToolCall(id="call-1", name="not_a_real_tool", arguments={}),),
            ),
            LLMResponse(
                content=None,
                tool_calls=(ToolCall(id="call-2", name="submit_investigation", arguments={"conclusion": "done"}),),
            ),
        ]
    )

    agent = LLMInvestigationAgent(gateway_client, llm)

    result = agent.run(objective="obj", initial_state={})

    assert result.conclusion == "done"
    assert "not_a_real_tool#1" in result.findings
    assert result.findings["not_a_real_tool#1"] == {"error": "Unknown tool: not_a_real_tool"}


def test_agent_passes_objective_and_initial_state_to_llm(monkeypatch):
    gateway_client = _client(monkeypatch, {})

    llm = MockLLMClient([LLMResponse(content="ok", tool_calls=())])
    agent = LLMInvestigationAgent(gateway_client, llm)

    agent.run(
        objective="Investigate the reactor.",
        initial_state={"operating_state": "NORMAL"},
    )

    first_call_messages = llm.calls[0]["messages"]
    user_message = next(m for m in first_call_messages if m["role"] == "user")

    assert "Investigate the reactor." in user_message["content"]
    assert "NORMAL" in user_message["content"]
