"""
M13-D: one real, complete benchmark invocation through `BenchmarkRunner`
using the actually-configured LLM provider (NIST RChat) and
`LLMInvestigationAgent` -- the "real LLM validation" requirement.

Like tests/integration/test_scenario_llm_end_to_end.py, this makes a
real, metered call to the configured LLM provider, so it is gated behind
ICAB_RUN_LLM_INTEGRATION_TESTS=1 and never runs as part of the default
suite.
"""

from __future__ import annotations

import os

import httpx
import pytest
from fastapi.testclient import TestClient

from icab.benchmark import BenchmarkConfig, BenchmarkRunner
from icab.common.config import get_settings
from icab.context.environment_loader import EnvironmentLoader
from icab.context.historian.repository import PostgresHistorianRepository
from icab.context.historian.service import HistorianService
from icab.context.knowledge_graph.repository import Neo4jKnowledgeGraphRepository
from icab.context.knowledge_graph.service import KnowledgeGraphService
from icab.experiments import ExperimentResultStore, ExperimentRunner, ExperimentRunStatus
from icab.scenarios import BenchmarkScenarioRegistry
from icab.scenarios.runner import ScenarioRunner
from icab.tep import TEPContextSync

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


def test_one_real_llm_benchmark_run_through_the_complete_runner(tmp_path, monkeypatch):
    settings = get_settings()

    if not (settings.llm_base_url and settings.llm_api_key and settings.llm_model):
        pytest.skip("ICAB_LLM_BASE_URL/ICAB_LLM_API_KEY/ICAB_LLM_MODEL are not fully configured in .env.")

    historian = HistorianService(PostgresHistorianRepository(DATABASE_URL))
    kg_repository = Neo4jKnowledgeGraphRepository(uri=NEO4J_URI, username=NEO4J_USERNAME, password=NEO4J_PASSWORD)
    knowledge_graph = KnowledgeGraphService(kg_repository)
    context_sync = TEPContextSync(environment_loader=EnvironmentLoader(historian=historian, knowledge_graph=knowledge_graph))

    from icab.gateway.app import app

    test_client = TestClient(app)

    def fake_post(url, **kwargs):
        path = url.split("/tools/", 1)[1]
        kwargs.pop("timeout", None)
        return test_client.post(f"/tools/{path}", **kwargs)

    def fake_get(url, **kwargs):
        path = url.split("/tools/", 1)[1]
        kwargs.pop("timeout", None)
        return test_client.get(f"/tools/{path}", **kwargs)

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr(httpx, "get", fake_get)

    try:
        experiment_runner = ExperimentRunner(
            gateway_base_url="http://testserver",
            scenario_runner=ScenarioRunner(context_sync=context_sync),
            scenario_registry=BenchmarkScenarioRegistry(SCENARIOS_DIR),
        )
        benchmark_runner = BenchmarkRunner(
            experiment_runner=experiment_runner,
            experiment_store=ExperimentResultStore(root=tmp_path),
        )

        config = BenchmarkConfig(
            suite="tep-v1",
            task_id="d1-qa-current-pressure",
            agent="llm",
            architectures="historian",
            seeds=[1],
            max_steps=6,
        )

        result = benchmark_runner.run(config)

        assert result.total_runs == 1
        store = ExperimentResultStore(root=tmp_path)
        record = store.load_record(result.run_ids[0])

        assert record.status == ExperimentRunStatus.COMPLETED
        assert record.config.agent_type.value == "llm"
        assert record.config.llm_model == settings.llm_model
        assert record.result is not None
        assert record.result.conclusion
        assert record.evaluation is not None

        trace = store.load_trace(result.run_ids[0])
        assert any(event.action == "llm_generate" for event in trace)
        assert any(event.action == "tool_call" for event in trace)
    finally:
        kg_repository.close()
