import pytest

from icab.agent.llm.client import LLMResponse, MockLLMClient, ToolCall


def test_mock_llm_client_returns_scripted_responses_in_order():
    first = LLMResponse(content=None, tool_calls=(ToolCall("1", "tool_a", {}),))
    second = LLMResponse(content="done", tool_calls=())

    client = MockLLMClient([first, second])

    assert client.generate(messages=[], tools=[]) is first
    assert client.generate(messages=[], tools=[]) is second


def test_mock_llm_client_records_calls():
    client = MockLLMClient([LLMResponse(content="ok", tool_calls=())])

    messages = [{"role": "user", "content": "hi"}]
    tools = [{"type": "function", "function": {"name": "x"}}]

    client.generate(messages=messages, tools=tools)

    assert client.calls == [{"messages": messages, "tools": tools}]


def test_mock_llm_client_raises_when_exhausted():
    client = MockLLMClient([])

    with pytest.raises(AssertionError):
        client.generate(messages=[], tools=[])


def test_openai_compatible_client_construction_is_lazy_and_offline():
    """Constructing the client must not require network access."""

    from icab.agent.llm.client import OpenAICompatibleLLMClient

    client = OpenAICompatibleLLMClient(
        base_url="https://example.invalid/api/v1",
        api_key="unused-in-this-test",
        model="some-model",
    )

    assert client.model == "some-model"
