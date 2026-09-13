"""
LLM client abstraction for ICAB's LLM-based investigation agent (M6).

``icab.agent.llm.agent.LLMInvestigationAgent`` depends only on the
:class:`LLMClient` interface, never on a specific provider SDK -- so the
provider (NIST RChat, or any other OpenAI-compatible/custom endpoint) is
configurable, and unit tests can exercise the agent deterministically via
:class:`MockLLMClient` without any network access or API key.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ToolCall:
    """One tool invocation requested by the LLM."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class LLMResponse:
    """
    One assistant turn: either a final text message, one or more tool
    calls, or both (some providers return an interim message alongside
    tool calls).
    """

    content: str | None
    tool_calls: tuple[ToolCall, ...] = field(default_factory=tuple)


class LLMClient(ABC):
    """Abstraction over a tool-calling LLM provider."""

    @abstractmethod
    def generate(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> LLMResponse:
        """Given a conversation and the available tools, produce the next assistant turn."""

        raise NotImplementedError


class OpenAICompatibleLLMClient(LLMClient):
    """
    LLMClient backed by any OpenAI-compatible chat-completions endpoint
    (e.g. NIST RChat, a vLLM/Ollama/etc. server, or the public OpenAI API).

    Configure ``base_url``/``api_key``/``model`` from
    :class:`~icab.common.config.ICABSettings` (environment variables) --
    never hard-code a provider or a key here.
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        temperature: float = 0.0,
        max_tokens: int | None = 1024,
    ) -> None:
        from openai import OpenAI

        self._client = OpenAI(base_url=base_url, api_key=api_key)
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

    def generate(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> LLMResponse:
        response = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=tools,
            tool_choice="auto",
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )

        message = response.choices[0].message

        tool_calls = tuple(
            ToolCall(
                id=call.id,
                name=call.function.name,
                arguments=json.loads(call.function.arguments or "{}"),
            )
            for call in (message.tool_calls or [])
        )

        return LLMResponse(content=message.content, tool_calls=tool_calls)


class MockLLMClient(LLMClient):
    """
    Deterministic, scriptable :class:`LLMClient` for unit tests.

    Returns one pre-programmed :class:`LLMResponse` per call to
    :meth:`generate`, in order, and records every call it received (so
    tests can assert on what the agent sent, e.g. that tool results were
    fed back correctly) without making any network call.
    """

    def __init__(self, responses: list[LLMResponse]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def generate(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> LLMResponse:
        self.calls.append({"messages": messages, "tools": tools})

        if not self._responses:
            raise AssertionError(
                "MockLLMClient ran out of scripted responses "
                f"after {len(self.calls)} call(s)."
            )

        return self._responses.pop(0)
