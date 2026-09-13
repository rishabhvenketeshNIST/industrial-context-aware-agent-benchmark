"""
Proves GroundedInvestigationEvaluator correctly parses REAL gateway tool
responses (not just hand-written dicts in unit tests): runs the D3
scenario against the real simulator/historian/knowledge graph, drives a
small deterministic sequence of real gateway tool calls (through the real
FastAPI app, in-process via TestClient) that a temporal+relational
investigation would make, and evaluates the resulting trace.
"""

from datetime import timedelta

import httpx
from fastapi.testclient import TestClient

from icab.agent.client import AgentGatewayClient
from icab.agent.interface import EvidenceReference, InvestigationResult
from icab.context.environment_loader import EnvironmentLoader
from icab.context.historian.repository import PostgresHistorianRepository
from icab.context.historian.service import HistorianService
from icab.context.knowledge_graph.repository import Neo4jKnowledgeGraphRepository
from icab.context.knowledge_graph.service import KnowledgeGraphService
from icab.evaluation.grounded import GroundedInvestigationEvaluator
from icab.scenarios import BenchmarkScenarioRegistry
from icab.scenarios.runner import ScenarioRunner
from icab.tep import TEPContextSync
from icab.trace.collector import TraceCollector

DATABASE_URL = "postgresql://icab:icab@localhost:5432/icab"
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USERNAME = "neo4j"
NEO4J_PASSWORD = "icabpassword"

SCENARIOS_DIR = "configs/benchmark/scenarios"

REACTOR_PRESSURE_ID = "urn:icab:measurement:reactor_pressure"
REACTOR_EQUIPMENT_ID = "urn:icab:equipment:reactor"


def test_grounded_evaluator_scores_a_real_investigation_trace(monkeypatch):
    registry = BenchmarkScenarioRegistry(SCENARIOS_DIR)
    scenario = registry.get("d3_reactor_pressure_deviation")

    historian = HistorianService(PostgresHistorianRepository(DATABASE_URL))
    kg_repository = Neo4jKnowledgeGraphRepository(
        uri=NEO4J_URI,
        username=NEO4J_USERNAME,
        password=NEO4J_PASSWORD,
    )
    knowledge_graph = KnowledgeGraphService(kg_repository)

    sync = TEPContextSync(
        environment_loader=EnvironmentLoader(historian=historian, knowledge_graph=knowledge_graph)
    )

    try:
        run_result = ScenarioRunner(context_sync=sync).prepare(scenario)

        from icab.gateway.app import app

        test_client = TestClient(app)

        def fake_post(url, **kwargs):
            path = url.split("/tools/", 1)[1]
            kwargs.pop("timeout", None)  # TestClient is in-process; no network timeout applies
            return test_client.post(f"/tools/{path}", **kwargs)

        monkeypatch.setattr(httpx, "post", fake_post)

        trace_collector = TraceCollector()
        gateway_client = AgentGatewayClient("http://testserver", trace_collector=trace_collector)

        start = run_result.simulator.epoch
        end = start + timedelta(hours=scenario.warmup_hours + scenario.duration_hours)

        history_result = gateway_client.call_tool(
            "get_historical_values",
            {
                "measurement_id": REACTOR_PRESSURE_ID,
                "start_time": start.isoformat(),
                "end_time": end.isoformat(),
            },
            step=1,
            context_acquired=[REACTOR_PRESSURE_ID],
        )
        relationships_result = gateway_client.call_tool(
            "get_entity_relationships",
            {"canonical_id": REACTOR_EQUIPMENT_ID},
            step=2,
            context_acquired=[REACTOR_EQUIPMENT_ID],
        )

        assert len(history_result["observations"]) > 10
        assert any(
            rel["predicate"] == "MONITORS" and rel["object"] == REACTOR_PRESSURE_ID
            for rel in relationships_result["relationships"]
        )

        first_value = history_result["observations"][0]["value"]
        last_value = history_result["observations"][-1]["value"]

        investigation_result = InvestigationResult(
            objective=scenario.objective,
            conclusion=(
                f"Reactor pressure ({REACTOR_PRESSURE_ID}) declined from "
                f"{first_value:.1f} to {last_value:.1f} kPa, consistent with "
                "idv_01 (A/C feed ratio). The knowledge graph confirms the "
                f"Reactor equipment ({REACTOR_EQUIPMENT_ID}) monitors this "
                "measurement."
            ),
            evidence=[
                EvidenceReference(
                    source="get_historical_values", identifier=REACTOR_PRESSURE_ID
                ),
                EvidenceReference(
                    source="get_entity_relationships", identifier=REACTOR_EQUIPMENT_ID
                ),
            ],
        )

        report = GroundedInvestigationEvaluator().evaluate(
            scenario,
            investigation_result,
            trace=trace_collector.events(),
        )

        assert report.required_evidence_score == 1.0
        assert report.canonical_id_score == 1.0
        assert report.temporal_evidence_required is True
        assert report.temporal_evidence_acquired is True
        assert report.relationship_score == 1.0
        assert report.expected_relationships[0].confirmed is True
        assert report.root_cause_identified is True
        assert report.grounding_score == 1.0
        assert report.unsupported_numeric_claims == []
        assert report.terminated_properly is True
    finally:
        kg_repository.close()
