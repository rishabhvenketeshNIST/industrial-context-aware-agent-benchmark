"""
Integration test against the real configured LLM provider (e.g. NIST RChat).

Unlike the other integration tests in this directory (which assume the
docker-compose stack is always up), this one is gated behind an explicit
opt-in environment variable: it makes real, billed/metered calls to a
live LLM endpoint, so it must never run silently as part of the default
suite.

Enable with:

    ICAB_RUN_LLM_INTEGRATION_TESTS=1 uv run pytest tests/integration/test_llm_rchat.py
"""

import os

import httpx
import pytest

from icab.agent.client import AgentGatewayClient
from icab.agent.llm.agent import LLMInvestigationAgent
from icab.common.config import get_settings

RUN_LLM_TESTS = os.environ.get("ICAB_RUN_LLM_INTEGRATION_TESTS") == "1"

pytestmark = pytest.mark.skipif(
    not RUN_LLM_TESTS,
    reason=(
        "Set ICAB_RUN_LLM_INTEGRATION_TESTS=1 to exercise the real "
        "configured LLM provider (makes live, metered API calls)."
    ),
)


def _real_llm_client():
    from icab.agent.llm.client import OpenAICompatibleLLMClient

    settings = get_settings()

    if not (settings.llm_base_url and settings.llm_api_key and settings.llm_model):
        pytest.skip(
            "ICAB_LLM_BASE_URL/ICAB_LLM_API_KEY/ICAB_LLM_MODEL are not fully "
            "configured in .env."
        )

    return OpenAICompatibleLLMClient(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
    )


def test_real_llm_calls_a_tool_for_a_measurement_question(monkeypatch):
    """
    The configured provider, given a gateway-fronted tool, should choose to
    call it rather than fabricate a value -- this is the core LLM-agent
    behavior H5 (grounding) depends on.
    """

    def fake_post(url, **kwargs):
        assert url.endswith("/tools/get_current_value")
        return httpx.Response(
            200,
            json={
                "observation": {
                    "observation_id": "integration-test-001",
                    "measurement_id": kwargs["json"]["measurement_id"],
                    "timestamp": "2026-09-09T12:00:00Z",
                    "value": 2705.0,
                    "unit": "kPa gauge",
                    "quality": "GOOD",
                    "source": "tep",
                }
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    gateway_client = AgentGatewayClient("http://localhost:8000")
    llm = _real_llm_client()

    agent = LLMInvestigationAgent(gateway_client, llm, max_steps=5)

    result = agent.run(
        objective=(
            "What is the current reactor pressure? Use "
            "'urn:icab:measurement:reactor_pressure' as the measurement id."
        ),
        initial_state={"operating_state": "NORMAL"},
    )

    assert result.evidence, "Expected the real LLM to call a tool at least once."
    assert any(
        reference.source == "get_current_value" for reference in result.evidence
    )
    assert "2705" in result.conclusion
