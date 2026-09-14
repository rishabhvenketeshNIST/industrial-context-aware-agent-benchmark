"""
Regression tests for the M13-D follow-up context_acquired/context_consumed
audit (docs/architecture/llm-agent.md#context_acquired-vs-context_consumed).

Locks in `LLMInvestigationAgent`'s ACTUAL, now-accurately-documented
behavior: it always tags `context_acquired` at every tool call, but never
tags `context_consumed` -- for a single direct call (the audited D1 case)
AND for a multi-step browse-then-read sequence (where the deterministic
baselines WOULD tag context_consumed). This is deliberate (see the linked
doc) -- these tests exist so a future change either preserves this
documented behavior or updates the docs/QA-report glossary alongside it,
rather than silently drifting.
"""

from __future__ import annotations

import httpx

from icab.agent.client import AgentGatewayClient
from icab.agent.llm.agent import LLMInvestigationAgent
from icab.agent.llm.client import LLMResponse, MockLLMClient, ToolCall
from icab.trace.collector import TraceCollector


def _client(monkeypatch, responses_by_tool: dict[str, dict]) -> tuple[AgentGatewayClient, TraceCollector]:
    def fake_post(url, **kwargs):
        tool_name = url.rsplit("/tools/", 1)[1]
        return httpx.Response(200, json=responses_by_tool[tool_name], request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)

    trace_collector = TraceCollector()
    return AgentGatewayClient("http://localhost:8000", trace_collector=trace_collector), trace_collector


class TestSingleDirectCall:
    """The exact scenario a researcher flagged: one get_current_value call, no discovery step."""

    def test_context_acquired_is_one_and_context_consumed_is_empty(self, monkeypatch):
        gateway_client, trace_collector = _client(
            monkeypatch,
            {"get_current_value": {"observation": {"measurement_id": "urn:icab:measurement:reactor_pressure", "value": 2712.39, "unit": "kPa gauge"}}},
        )

        llm = MockLLMClient(
            [
                LLMResponse(
                    content=None,
                    tool_calls=(
                        ToolCall(id="call-1", name="get_current_value", arguments={"measurement_id": "urn:icab:measurement:reactor_pressure"}),
                    ),
                ),
                LLMResponse(
                    content=None,
                    tool_calls=(
                        ToolCall(id="call-2", name="submit_investigation", arguments={"conclusion": "2712.39 kPa gauge, within normal range."}),
                    ),
                ),
            ]
        )

        agent = LLMInvestigationAgent(gateway_client, llm, max_steps=5)
        agent.run(objective="What is the current reactor pressure?", initial_state={})

        events = trace_collector.events()
        tool_events = [event for event in events if event.action == "tool_call"]

        assert len(tool_events) == 1
        assert tool_events[0].context_acquired == ["urn:icab:measurement:reactor_pressure"]
        # The documented, CORRECT value for a single direct call with no
        # preceding discovery step -- not a bug (see module docstring).
        assert tool_events[0].context_consumed == []


class TestMultiStepBrowseThenRead:
    """
    Even when the LLM DOES browse first and then read a discovered
    measurement -- the pattern the deterministic baselines tag
    context_consumed for -- LLMInvestigationAgent still does not,
    confirming this is a blanket, not situational, gap.
    """

    def test_context_consumed_stays_empty_even_after_a_browse_then_read_sequence(self, monkeypatch):
        gateway_client, trace_collector = _client(
            monkeypatch,
            {
                "browse_uns": {
                    "nodes": [
                        {
                            "path": "site/tep/reactor/reactor_pressure",
                            "display_name": "Reactor pressure",
                            "node_type": "measurement",
                            "canonical_id": "urn:icab:measurement:reactor_pressure",
                        }
                    ]
                },
                "get_current_value": {"observation": {"measurement_id": "urn:icab:measurement:reactor_pressure", "value": 2712.39, "unit": "kPa gauge"}},
            },
        )

        llm = MockLLMClient(
            [
                LLMResponse(content=None, tool_calls=(ToolCall(id="call-1", name="browse_uns", arguments={"path": "site/tep/reactor"}),)),
                LLMResponse(
                    content=None,
                    tool_calls=(ToolCall(id="call-2", name="get_current_value", arguments={"measurement_id": "urn:icab:measurement:reactor_pressure"}),),
                ),
                LLMResponse(content=None, tool_calls=(ToolCall(id="call-3", name="submit_investigation", arguments={"conclusion": "2712.39 kPa gauge."}),)),
            ]
        )

        agent = LLMInvestigationAgent(gateway_client, llm, max_steps=5)
        agent.run(objective="Investigate reactor pressure.", initial_state={})

        events = trace_collector.events()
        tool_events = [event for event in events if event.action == "tool_call"]

        assert len(tool_events) == 2
        assert tool_events[0].tool == "browse_uns"
        assert tool_events[0].context_acquired == ["site/tep/reactor"]
        assert tool_events[1].tool == "get_current_value"
        assert tool_events[1].context_acquired == ["urn:icab:measurement:reactor_pressure"]
        # Unlike ScenarioAwareBaselineAgent/ArchitectureAwareAgent, which
        # would tag context_consumed=["site/tep/reactor"] on the second
        # call -- LLMInvestigationAgent tags neither call's
        # context_consumed. Documented, not a bug.
        assert tool_events[0].context_consumed == []
        assert tool_events[1].context_consumed == []


class TestContrastWithDeterministicBaselineConvention:
    """
    Demonstrates the actual, established context_consumed convention this
    agent does NOT follow -- using the real ScenarioAwareBaselineAgent, so
    the contrast is against real code, not a hypothetical description.
    """

    def test_scenario_aware_baseline_does_tag_context_consumed_for_the_same_pattern(self, monkeypatch):
        from icab.agent.baseline.scenario_aware import ScenarioAwareBaselineAgent

        def fake_post(url, **kwargs):
            tool_name = url.rsplit("/tools/", 1)[1]
            if tool_name == "browse_uns":
                return httpx.Response(
                    200,
                    json={
                        "nodes": [
                            {
                                "path": "site/tep/reactor/reactor_pressure",
                                "display_name": "Reactor pressure",
                                "node_type": "measurement",
                                "canonical_id": "urn:icab:measurement:reactor_pressure",
                            }
                        ]
                    },
                    request=httpx.Request("POST", url),
                )
            if tool_name == "get_current_value":
                return httpx.Response(
                    200,
                    json={"observation": {"measurement_id": "urn:icab:measurement:reactor_pressure", "value": 2712.39, "unit": "kPa gauge"}},
                    request=httpx.Request("POST", url),
                )
            if tool_name == "get_entity_relationships":
                return httpx.Response(200, json={"relationships": []}, request=httpx.Request("POST", url))
            raise AssertionError(f"unexpected tool: {tool_name}")

        monkeypatch.setattr(httpx, "post", fake_post)

        trace_collector = TraceCollector()
        gateway_client = AgentGatewayClient("http://localhost:8000", trace_collector=trace_collector)
        agent = ScenarioAwareBaselineAgent(gateway_client)

        agent.run(objective="Investigate the reactor.", initial_state={})

        events = trace_collector.events()
        get_current_value_events = [event for event in events if event.tool == "get_current_value"]

        assert get_current_value_events  # sanity: the fixture actually ran a value call
        for event in get_current_value_events:
            assert event.context_consumed == ["site/tep/reactor"]
