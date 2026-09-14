"""
ICAB v2 (context-requirement experimentation) integration test: the FULL
`ContextExperimentRunner` path against the real stack --

    task (M13-C, tep-v2) -> design strategy (icab.tasks.experiment_design)
    -> architecture resolution (icab.tasks.context_conditions) -> real TEP
    simulator -> real context synchronization -> real Agent Gateway
    (in-process via TestClient) -> deterministic baseline agent -> trace
    -> GroundedInvestigationEvaluator.evaluate_task -> ExperimentResultStore
    persistence.

Uses `ScenarioAwareBaselineAgent` (not the LLM agent) so this needs no
live-LLM dependency -- mirrors
tests/integration/test_benchmark_runner_against_real_stack.py's own
construction pattern exactly.
"""

from __future__ import annotations

import httpx
from fastapi.testclient import TestClient

from icab.benchmark.context_experiment import ContextExperimentConfig, ContextExperimentRunner
from icab.context.environment_loader import EnvironmentLoader
from icab.context.historian.repository import PostgresHistorianRepository
from icab.context.historian.service import HistorianService
from icab.context.knowledge_graph.repository import Neo4jKnowledgeGraphRepository
from icab.context.knowledge_graph.service import KnowledgeGraphService
from icab.experiments import ExperimentResultStore, ExperimentRunner, ExperimentRunStatus, RunValidity
from icab.scenarios import BenchmarkScenarioRegistry
from icab.scenarios.runner import ScenarioRunner
from icab.tep import TEPContextSync
from icab.usecases import IndustrialUseCaseRegistry

DATABASE_URL = "postgresql://icab:icab@localhost:5432/icab"
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USERNAME = "neo4j"
NEO4J_PASSWORD = "icabpassword"

SCENARIOS_DIR = "configs/benchmark/scenarios"
USECASES_DIR = "configs/usecases"


def _real_context_experiment_runner(tmp_path, monkeypatch) -> tuple[ContextExperimentRunner, Neo4jKnowledgeGraphRepository]:
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

    experiment_runner = ExperimentRunner(
        gateway_base_url="http://testserver",
        scenario_runner=ScenarioRunner(context_sync=context_sync),
        scenario_registry=BenchmarkScenarioRegistry(SCENARIOS_DIR),
    )

    use_case_registry = IndustrialUseCaseRegistry(USECASES_DIR, scenario_registry=BenchmarkScenarioRegistry(SCENARIOS_DIR))

    context_runner = ContextExperimentRunner(
        experiment_runner=experiment_runner,
        experiment_store=ExperimentResultStore(root=tmp_path),
        use_case_registry=use_case_registry,
    )

    return context_runner, kg_repository


def test_single_dimension_design_resolves_and_executes_against_real_infrastructure(tmp_path, monkeypatch):
    context_runner, kg_repository = _real_context_experiment_runner(tmp_path, monkeypatch)

    try:
        config = ContextExperimentConfig(
            suite="tep-v2",
            task_id="d4plant-qa-discover-equipment",  # available_architectures: [uns, opcua]
            design="single",
            agent="baseline",
            seeds=[1],
        )

        result = context_runner.run(config)

        # C1+C2 is exactly realizable via uns alone -- the only single
        # dimension in this task's real architectures that resolves EXACT.
        c1 = next(c for c in result.conditions if c.combination_id == "C1")
        c2 = next(c for c in result.conditions if c.combination_id == "C2")
        assert c1.resolution_status == "overshoot" and c1.executed is False
        assert c2.resolution_status == "overshoot" and c2.executed is False

        # Every one of the 7 single-dimension conditions was classified --
        # "not executed" (overshoot-skipped/not_applicable) never counts
        # as a failure.
        assert result.total_conditions == 7
        assert result.failed_runs == 0

        store = ExperimentResultStore(root=tmp_path)
        for outcome in result.conditions:
            if not outcome.executed:
                continue
            for run_id in outcome.run_ids:
                record = store.load_record(run_id)
                assert record.status == ExperimentRunStatus.COMPLETED
                assert record.validity == RunValidity.VALID
                assert record.config.suite == "tep-v2"
                assert record.config.context_combination_id == outcome.combination_id
                assert record.evaluation is not None
                assert record.generation_id is not None
    finally:
        kg_repository.close()


def test_ablation_design_against_a_two_architecture_task_executes_baseline_and_removals(tmp_path, monkeypatch):
    context_runner, kg_repository = _real_context_experiment_runner(tmp_path, monkeypatch)

    try:
        config = ContextExperimentConfig(
            suite="tep-v2",
            task_id="d2cooling-diagnosis-heat-transfer-category",  # historian + knowledge_graph
            design="ablation",
            baseline="C3+C5",
            allow_overshoot=True,
            agent="baseline",
            seeds=[1],
        )

        result = context_runner.run(config)

        assert result.total_conditions == 3  # baseline + 2 single-dimension removals
        assert result.executed_conditions == 3
        assert result.failed_runs == 0

        architectures_used = {
            architecture
            for outcome in result.conditions
            for architecture in (outcome.resolved_architectures or [])
        }
        # The two real architectures this task declares both actually ran.
        assert architectures_used == {"historian", "knowledge_graph"}
    finally:
        kg_repository.close()


def test_targeted_design_with_an_unrealizable_combination_is_never_executed(tmp_path, monkeypatch):
    """C1 needs uns/i3x -- unavailable to a historian-only task -- so this must be classified UNREALIZABLE and never touch the gateway/simulator at all."""

    context_runner, kg_repository = _real_context_experiment_runner(tmp_path, monkeypatch)
    # Disable use-case scoping for this test: eq-current-value-interpretation's
    # own candidate_context ({C4, C5}) happens to be fully realizable via
    # historian (as an overshoot), so nothing in it is ever UNREALIZABLE --
    # this test wants the pure architecture-resolution path instead.
    context_runner.use_case_registry = None

    try:
        config = ContextExperimentConfig(
            suite="tep-v2",
            task_id="d1-qa-current-pressure",  # historian only
            design="targeted",
            targets=["C1"],
            agent="baseline",
            seeds=[1],
        )

        result = context_runner.run(config)

        assert result.total_conditions == 1
        assert result.unrealizable_conditions == 1
        assert result.executed_conditions == 0
        assert result.total_runs == 0
        assert result.failed_runs == 0  # never attempted, never a failure
    finally:
        kg_repository.close()
