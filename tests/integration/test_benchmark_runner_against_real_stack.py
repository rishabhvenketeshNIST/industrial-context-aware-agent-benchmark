"""
M13-D integration test: the FULL benchmark orchestration path against the
real stack --

    task (M13-C) -> scenario (M5) -> real TEP simulator -> fault injection
    (M13-B) -> real context synchronization (historian/knowledge graph) ->
    real Agent Gateway (in-process via TestClient, same app/tool
    implementations a live server would run) -> deterministic baseline
    agent -> trace -> GroundedInvestigationEvaluator.evaluate_task ->
    ExperimentResultStore persistence -> aggregation -> M12 report.

Uses `ScenarioAwareBaselineAgent` (not the LLM agent) so this exercises
the complete `BenchmarkRunner`/`ExperimentRunner.run_task` orchestration
deterministically, with no live-LLM dependency and no gating needed --
see tests/integration/test_benchmark_runner_llm_real.py for the
gated real-LLM variant.
"""

from __future__ import annotations

from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from icab.benchmark import BenchmarkConfig, BenchmarkRunner
from icab.context.environment_loader import EnvironmentLoader
from icab.context.historian.repository import PostgresHistorianRepository
from icab.context.historian.service import HistorianService
from icab.context.knowledge_graph.repository import Neo4jKnowledgeGraphRepository
from icab.context.knowledge_graph.service import KnowledgeGraphService
from icab.experiments import ExperimentResultStore, ExperimentRunner, ExperimentRunStatus, RunValidity
from icab.scenarios import BenchmarkScenarioRegistry
from icab.scenarios.runner import ScenarioRunner
from icab.tasks.registry import BenchmarkTaskRegistry
from icab.tep import TEPContextSync

DATABASE_URL = "postgresql://icab:icab@localhost:5432/icab"
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USERNAME = "neo4j"
NEO4J_PASSWORD = "icabpassword"

SCENARIOS_DIR = "configs/benchmark/scenarios"
TASKS_DIR = "configs/benchmark/tasks"


def _real_benchmark_runner(tmp_path, monkeypatch) -> tuple[BenchmarkRunner, Neo4jKnowledgeGraphRepository]:
    historian = HistorianService(PostgresHistorianRepository(DATABASE_URL))
    kg_repository = Neo4jKnowledgeGraphRepository(uri=NEO4J_URI, username=NEO4J_USERNAME, password=NEO4J_PASSWORD)
    knowledge_graph = KnowledgeGraphService(kg_repository)
    context_sync = TEPContextSync(environment_loader=EnvironmentLoader(historian=historian, knowledge_graph=knowledge_graph))

    # Real ICAB Gateway app, routed in-process via TestClient -- same
    # convention as test_scenario_llm_end_to_end.py -- so no separately
    # running uvicorn process is required for this test.
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

    benchmark_runner = BenchmarkRunner(
        experiment_runner=experiment_runner,
        experiment_store=ExperimentResultStore(root=tmp_path),
    )

    return benchmark_runner, kg_repository


def test_no_fault_task_runs_end_to_end_and_persists_everything(tmp_path, monkeypatch):
    benchmark_runner, kg_repository = _real_benchmark_runner(tmp_path, monkeypatch)

    try:
        config = BenchmarkConfig(
            suite="tep-v1",
            task_id="d1-qa-current-pressure",
            agent="baseline",
            architectures="historian",
            seeds=[1],
        )

        result = benchmark_runner.run(config)

        assert result.successful_runs == 1
        assert result.failed_runs == 0
        assert result.skipped_runs == 0
        assert len(result.run_ids) == 1

        store = ExperimentResultStore(root=tmp_path)
        record = store.load_record(result.run_ids[0])

        assert record.status == ExperimentRunStatus.COMPLETED
        assert record.validity == RunValidity.VALID
        assert record.config.task_id == "d1-qa-current-pressure"
        assert record.config.suite == "tep-v1"
        assert record.config.split == "development"
        assert record.config.repetition == 1
        assert record.simulation_seed == 1  # the --seeds override actually took effect
        assert record.fault_id is None  # d1_reactor_pressure_reading has no fault schedule
        assert record.scenario_version is not None
        assert record.task_version is not None
        assert record.benchmark_version is not None
        assert record.configuration_hash is not None
        assert record.generation_id is not None

        # Evaluation actually ran (M8/M13-C GroundedInvestigationEvaluator,
        # via evaluate_task -- not fabricated for a failed run, and not an
        # LLM-as-judge call).
        assert record.evaluation is not None
        assert record.evaluation.task_id == "d1-qa-current-pressure"
        assert record.evaluation.generation_id == record.generation_id

        # Trace was collected and is loadable separately.
        trace = store.load_trace(result.run_ids[0])
        assert len(trace) >= 1
        assert all(event.action != "llm_generate" for event in trace)  # deterministic baseline: no LLM calls at all

        # Aggregation + M12 report were produced automatically.
        assert result.aggregate_json_path is not None
        assert Path(result.aggregate_json_path).exists()
        assert Path(result.aggregate_csv_path).exists()
        assert Path(result.report_json_path).exists()
        assert Path(result.report_markdown_path).exists()

        # The researcher-facing QA report was produced automatically too,
        # and its rendered ground truth never appeared in the real trace
        # this real run actually produced (the agent's own tool-call
        # arguments/observations) -- the report legitimately knows more
        # than the agent ever saw.
        assert result.qa_report_json_path is not None
        assert Path(result.qa_report_json_path).exists()
        assert Path(result.qa_report_markdown_path).exists()

        task_registry = BenchmarkTaskRegistry(TASKS_DIR, scenario_registry=BenchmarkScenarioRegistry(SCENARIOS_DIR))
        reference_conclusion = task_registry.get("d1-qa-current-pressure").ground_truth.conclusion

        qa_report_text = Path(result.qa_report_markdown_path).read_text(encoding="utf-8")
        assert reference_conclusion in qa_report_text  # the ground truth's own readable content
        assert record.result.conclusion in qa_report_text  # the agent's real answer, verbatim

        trace_text = Path(store.traces_dir / f"{result.run_ids[0]}.jsonl").read_text(encoding="utf-8")
        assert reference_conclusion not in trace_text  # the ground truth text itself never reached the agent
    finally:
        kg_repository.close()


def test_faulted_scenario_task_propagates_fault_id_onto_the_record(tmp_path, monkeypatch):
    benchmark_runner, kg_repository = _real_benchmark_runner(tmp_path, monkeypatch)

    try:
        config = BenchmarkConfig(
            suite="tep-v1",
            task_id="d2cooling-qa-current-value",
            agent="baseline",
            architectures="historian",
            seeds=[2],
        )

        result = benchmark_runner.run(config)

        assert result.successful_runs == 1
        store = ExperimentResultStore(root=tmp_path)
        record = store.load_record(result.run_ids[0])

        assert record.status == ExperimentRunStatus.COMPLETED
        assert record.fault_id == "idv_17"  # d2_reactor_cooling_deviation's real scheduled fault
        assert record.fault_version is not None  # looked up from the real fault_catalog.json
        assert record.config.split == "validation"
        assert record.simulation_seed == 2

        # The QA report surfaces the fault id for a researcher, but the
        # real fault-injection isolation guarantee (M13-B, unchanged
        # here) means it was never in the objective/trace the agent saw.
        qa_report_text = Path(result.qa_report_markdown_path).read_text(encoding="utf-8")
        assert "idv_17" in qa_report_text

        trace_text = Path(store.traces_dir / f"{result.run_ids[0]}.jsonl").read_text(encoding="utf-8")
        assert "idv_17" not in trace_text
    finally:
        kg_repository.close()
