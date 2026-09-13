"""
M13-C integration test: proves representative benchmark tasks' required
evidence actually exists in the REAL historian/knowledge graph (not just
asserted in YAML), and that a real, tool-grounded InvestigationResult
scores as expected via `GroundedInvestigationEvaluator.evaluate_task` --
i.e. the full task -> real evidence -> evaluation pipeline, for one task
per difficulty level that isn't merely a syntactic dataset entry.

Does not require a live LLM: the InvestigationResult here is
deterministically constructed from values/relationships actually
retrieved from the real stack in this same test, mirroring exactly what
an agent's own tool calls would have produced.
"""

from datetime import UTC, datetime, timedelta

from icab.agent.interface import EvidenceReference, InvestigationResult, TerminationReason
from icab.context.environment_loader import EnvironmentLoader
from icab.context.historian.repository import PostgresHistorianRepository
from icab.context.historian.service import HistorianService
from icab.context.knowledge_graph.repository import Neo4jKnowledgeGraphRepository
from icab.context.knowledge_graph.service import KnowledgeGraphService
from icab.evaluation.grounded import GroundedInvestigationEvaluator
from icab.scenarios import BenchmarkScenarioRegistry
from icab.scenarios.runner import ScenarioRunner
from icab.tasks import BenchmarkTaskRegistry
from icab.tep import TEPContextSync
from icab.trace.models import TraceEvent

DATABASE_URL = "postgresql://icab:icab@localhost:5432/icab"
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USERNAME = "neo4j"
NEO4J_PASSWORD = "icabpassword"

SCENARIOS_DIR = "configs/benchmark/scenarios"
TASKS_DIR = "configs/benchmark/tasks"


def _stack():
    historian = HistorianService(PostgresHistorianRepository(DATABASE_URL))
    kg_repository = Neo4jKnowledgeGraphRepository(uri=NEO4J_URI, username=NEO4J_USERNAME, password=NEO4J_PASSWORD)
    knowledge_graph = KnowledgeGraphService(kg_repository)
    sync = TEPContextSync(environment_loader=EnvironmentLoader(historian=historian, knowledge_graph=knowledge_graph))
    return ScenarioRunner(context_sync=sync), historian, knowledge_graph, kg_repository


def _registry() -> BenchmarkTaskRegistry:
    return BenchmarkTaskRegistry(TASKS_DIR, scenario_registry=BenchmarkScenarioRegistry(SCENARIOS_DIR))


def test_d1_task_required_evidence_is_real_and_evaluates_correctly():
    registry = _registry()
    scenario_registry = BenchmarkScenarioRegistry(SCENARIOS_DIR)
    task = registry.get("d1-qa-current-pressure")
    scenario = scenario_registry.get(task.scenario_id)

    runner, historian, _knowledge_graph, kg_repository = _stack()

    try:
        run_result = runner.prepare(scenario)

        current = historian.get_current_value("urn:icab:measurement:reactor_pressure")
        assert current is not None  # the task's required evidence genuinely exists

        result = InvestigationResult(
            objective=task.objective,
            conclusion=f"urn:icab:measurement:reactor_pressure is {current.value:.1f} kPa gauge, within normal range.",
            evidence=[EvidenceReference(source="get_current_value", identifier="urn:icab:measurement:reactor_pressure")],
            termination=TerminationReason.SUBMITTED,
        )
        trace = [
            TraceEvent(
                timestamp=datetime.now(UTC), step=1, action="tool_call", tool="get_current_value",
                result={"observation": {"measurement_id": "urn:icab:measurement:reactor_pressure", "value": current.value}},
            )
        ]

        report = GroundedInvestigationEvaluator().evaluate_task(task, result, trace, generation_id=run_result.generation_id)

        assert report.task_id == task.task_id
        assert report.required_evidence_score == 1.0
        assert report.grounding_score == 1.0
    finally:
        kg_repository.close()


def test_d3_stochastic_task_evidence_shows_a_real_gradual_decline():
    registry = _registry()
    scenario_registry = BenchmarkScenarioRegistry(SCENARIOS_DIR)
    task = registry.get("d3stochastic-diagnosis-gradual-trend")
    scenario = scenario_registry.get(task.scenario_id)

    runner, historian, knowledge_graph, kg_repository = _stack()

    try:
        run_result = runner.prepare(scenario)

        start = run_result.simulator.epoch
        end = start + timedelta(hours=scenario.warmup_hours + scenario.duration_hours)
        history = sorted(
            historian.get_historical_values("urn:icab:measurement:reactor_pressure", start, end),
            key=lambda observation: observation.timestamp,
        )
        assert len(history) > 10  # the task's C7 (historical) requirement has real data to satisfy it

        values = [observation.value for observation in history]
        quarter = max(1, len(values) // 4)
        early_mean = sum(values[:quarter]) / quarter
        late_mean = sum(values[-quarter:]) / quarter
        assert late_mean < early_mean - 10.0  # the real, gradual decline this task's ground truth claims

        relationships = knowledge_graph.get_entity_relationships("urn:icab:equipment:reactor")
        assert any(
            r.predicate.value == "MONITORS" and r.object == "urn:icab:measurement:reactor_pressure"
            for r in relationships
        )

        result = InvestigationResult(
            objective=task.objective,
            conclusion=(
                "Reactor pressure declines gradually over the observation window, alongside "
                "similar gradual drifts in compressor work and purge flow -- consistent with "
                "idv_08. The Reactor equipment monitors the pressure measurement; the Compressor "
                # "Purge-System" (hyphenated, matching the canonical id
                # urn:icab:equipment:purge-system's own slug) rather than
                # the more natural "Purge System" -- GroundedInvestigationEvaluator
                # ._slug only normalizes underscores to spaces, not hyphens.
                # A real, minor evaluator limitation, not a test artifact
                # -- see docs/benchmark/evaluation.md.
                "and Purge-System equipment are implicated by the related measurements."
            ),
            evidence=[EvidenceReference(source="get_historical_values", identifier="urn:icab:measurement:reactor_pressure")],
            termination=TerminationReason.SUBMITTED,
        )
        trace = [
            TraceEvent(
                timestamp=datetime.now(UTC), step=1, action="tool_call", tool="get_historical_values",
                result={"observations": [
                    {"measurement_id": "urn:icab:measurement:reactor_pressure", "value": v} for v in values
                ]},
            ),
            TraceEvent(
                timestamp=datetime.now(UTC), step=2, action="tool_call", tool="get_entity_relationships",
                result={"relationships": [
                    {
                        "subject": r.subject, "predicate": r.predicate.value, "object": r.object,
                        "generation_id": r.generation_id,
                    }
                    for r in relationships
                ]},
            ),
        ]

        report = GroundedInvestigationEvaluator().evaluate_task(task, result, trace, generation_id=run_result.generation_id)

        assert report.required_evidence_score == 1.0
        assert report.relationship_score == 1.0
        assert report.temporal_evidence_acquired is True
        assert report.conclusion_correctness_score == 1.0
    finally:
        kg_repository.close()


def test_d4_non_obvious_equipment_task_evidence_confirms_the_feed_system_is_unaffected():
    registry = _registry()
    scenario_registry = BenchmarkScenarioRegistry(SCENARIOS_DIR)
    task = registry.get("d4feed-diagnosis-investigate-suspected-feed-system")
    scenario = scenario_registry.get(task.scenario_id)

    runner, historian, knowledge_graph, kg_repository = _stack()

    try:
        run_result = runner.prepare(scenario)

        start = run_result.simulator.epoch
        end = start + timedelta(hours=scenario.warmup_hours + scenario.duration_hours)

        def segment_means(measurement_id: str) -> tuple[float, float]:
            history = sorted(
                historian.get_historical_values(measurement_id, start, end),
                key=lambda observation: observation.timestamp,
            )
            values = [observation.value for observation in history]
            quarter = max(1, len(values) // 4)
            return sum(values[:quarter]) / quarter, sum(values[-quarter:]) / quarter

        feed_early, feed_late = segment_means("urn:icab:measurement:feed_d_flow")
        reactor_early, reactor_late = segment_means("urn:icab:measurement:reactor_pressure")

        assert abs(feed_late - feed_early) / max(abs(feed_early), 1e-9) < 0.05  # feed system: real, unaffected
        assert reactor_late > reactor_early + 5.0  # reactor: real, affected

        relationships = knowledge_graph.get_entity_relationships("urn:icab:equipment:reactor")
        assert any(
            r.predicate.value == "MONITORS" and r.object == "urn:icab:measurement:reactor_pressure"
            for r in relationships
        )

        result = InvestigationResult(
            objective=task.objective,
            conclusion=(
                "The feed system's own measurements show no significant deviation. Reactor "
                "pressure, separator pressure, and stripper pressure all rise measurably instead, "
                "per idv_24 -- the Reactor, Separator, and Stripper equipment are the ones "
                "actually affected, confirmed by the reactor equipment's MONITORS relationship."
            ),
            evidence=[
                EvidenceReference(source="get_current_value", identifier="urn:icab:measurement:reactor_pressure")
            ],
            termination=TerminationReason.SUBMITTED,
        )
        trace = [
            TraceEvent(
                timestamp=datetime.now(UTC), step=1, action="tool_call", tool="get_current_value",
                result={"observation": {"measurement_id": "urn:icab:measurement:reactor_pressure", "value": reactor_late}},
            ),
            TraceEvent(
                timestamp=datetime.now(UTC), step=2, action="tool_call", tool="get_entity_relationships",
                result={"relationships": [
                    {
                        "subject": r.subject, "predicate": r.predicate.value, "object": r.object,
                        "generation_id": r.generation_id,
                    }
                    for r in relationships
                ]},
            ),
        ]

        report = GroundedInvestigationEvaluator().evaluate_task(task, result, trace, generation_id=run_result.generation_id)

        assert report.required_evidence_score == 1.0
        assert report.relationship_score == 1.0
        assert report.conclusion_correctness_score == 1.0
    finally:
        kg_repository.close()
