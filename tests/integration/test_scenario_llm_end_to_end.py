"""
The complete M4/M5/M6/M7 path, end to end:

    TEP simulator -> industrial context architecture -> ICAB Gateway
    -> RChat LLM -> tool calls -> observations -> investigation result
    -> trace -> evaluation

Like tests/integration/test_llm_rchat.py, this makes real, metered calls to
the configured LLM provider, so it is gated behind
ICAB_RUN_LLM_INTEGRATION_TESTS=1 and must never run silently as part of the
default suite.
"""

import os

import httpx
import pytest
from fastapi.testclient import TestClient

from icab.agent.client import AgentGatewayClient
from icab.agent.llm.agent import LLMInvestigationAgent
from icab.agent.llm.tools import tools_for_architectures
from icab.common.config import get_settings
from icab.context.environment_loader import EnvironmentLoader
from icab.context.historian.repository import PostgresHistorianRepository
from icab.context.historian.service import HistorianService
from icab.context.knowledge_graph.repository import Neo4jKnowledgeGraphRepository
from icab.context.knowledge_graph.service import KnowledgeGraphService
from icab.evaluation.cases import InvestigationCase
from icab.evaluation.investigation import InvestigationEvaluator
from icab.scenarios import BenchmarkScenarioRegistry
from icab.scenarios.runner import ScenarioRunner
from icab.tep import TEPContextSync
from icab.trace.collector import TraceCollector

RUN_LLM_TESTS = os.environ.get("ICAB_RUN_LLM_INTEGRATION_TESTS") == "1"

pytestmark = pytest.mark.skipif(
    not RUN_LLM_TESTS,
    reason=(
        "Set ICAB_RUN_LLM_INTEGRATION_TESTS=1 to exercise the real "
        "configured LLM provider (makes live, metered API calls)."
    ),
)

DATABASE_URL = "postgresql://icab:icab@localhost:5432/icab"
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USERNAME = "neo4j"
NEO4J_PASSWORD = "icabpassword"

SCENARIOS_DIR = "configs/benchmark/scenarios"


def test_d1_scenario_end_to_end_through_the_real_gateway_and_llm(monkeypatch):
    settings = get_settings()

    if not (settings.llm_base_url and settings.llm_api_key and settings.llm_model):
        pytest.skip(
            "ICAB_LLM_BASE_URL/ICAB_LLM_API_KEY/ICAB_LLM_MODEL are not fully "
            "configured in .env."
        )

    registry = BenchmarkScenarioRegistry(SCENARIOS_DIR)
    scenario = registry.get("d1_reactor_pressure_reading")

    historian = HistorianService(PostgresHistorianRepository(DATABASE_URL))
    kg_repository = Neo4jKnowledgeGraphRepository(
        uri=NEO4J_URI,
        username=NEO4J_USERNAME,
        password=NEO4J_PASSWORD,
    )
    knowledge_graph = KnowledgeGraphService(kg_repository)

    sync = TEPContextSync(
        environment_loader=EnvironmentLoader(
            historian=historian,
            knowledge_graph=knowledge_graph,
        ),
    )

    try:
        # -- TEP simulator -> industrial context architecture ------------
        ScenarioRunner(context_sync=sync).prepare(scenario)

        # -- ICAB Gateway (the real FastAPI app, real tool implementations,
        #    same docker-compose services) -- routed in-process via
        #    TestClient rather than a separate server process/port.
        from icab.gateway.app import app

        test_client = TestClient(app)

        def fake_post(url, **kwargs):
            path = url.split("/tools/", 1)[1]
            kwargs.pop("timeout", None)  # TestClient is in-process; no network timeout applies
            return test_client.post(f"/tools/{path}", **kwargs)

        monkeypatch.setattr(httpx, "post", fake_post)

        trace_collector = TraceCollector()
        gateway_client = AgentGatewayClient(
            "http://testserver",
            trace_collector=trace_collector,
        )

        # -- RChat LLM ------------------------------------------------------
        from icab.agent.llm.client import OpenAICompatibleLLMClient

        llm = OpenAICompatibleLLMClient(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            model=settings.llm_model,
        )

        tools = tools_for_architectures(scenario.available_architectures)
        agent = LLMInvestigationAgent(gateway_client, llm, tools=tools, max_steps=6)

        # -- tool calls -> observations -> investigation result -----------
        result = agent.run(
            objective=scenario.objective,
            initial_state={"scenario_id": scenario.scenario_id},
        )

        assert result.conclusion
        assert result.evidence, "expected the LLM to call a tool at least once"

        # -- trace ------------------------------------------------------------
        events = trace_collector.events()
        assert len(events) >= 1
        assert all(event.action == "tool_call" for event in events)
        assert any(event.tool == "get_current_value" for event in events)

        # -- evaluation (existing, unmodified InvestigationEvaluator) -----
        case = InvestigationCase(
            case_id=scenario.scenario_id,
            objective=scenario.objective,
            expected_architecture=",".join(scenario.available_architectures),
            required_evidence=tuple(scenario.ground_truth.expected_evidence),
        )
        evaluation = InvestigationEvaluator().evaluate(case, result)

        assert evaluation["evidence_score"] > 0.0
    finally:
        kg_repository.close()
