import csv
from datetime import UTC, datetime

from icab.agent.interface import EvidenceReference, InvestigationResult, TerminationReason
from icab.evaluation.grounded import GroundedInvestigationEvaluator
from icab.experiments import AgentType, ExperimentConfig, ExperimentRecord, ExperimentResultStore
from icab.experiments.models import ExperimentRunStatus
from icab.scenarios import BenchmarkScenarioRegistry
from icab.trace.models import TraceEvent

SCENARIOS_DIR = "configs/benchmark/scenarios"


def _record(run_id: str, experiment_id: str = "exp-1") -> tuple[ExperimentRecord, list[TraceEvent]]:
    scenario = BenchmarkScenarioRegistry(SCENARIOS_DIR).get("d1_reactor_pressure_reading")

    result = InvestigationResult(
        objective=scenario.objective,
        conclusion="urn:icab:measurement:reactor_pressure is 2705 kPa, normal.",
        evidence=[
            EvidenceReference(
                source="get_current_value", identifier="urn:icab:measurement:reactor_pressure"
            )
        ],
        termination=TerminationReason.SUBMITTED,
    )

    trace = [
        TraceEvent(
            timestamp=datetime(2026, 9, 13, tzinfo=UTC),
            step=1,
            action="tool_call",
            tool="get_current_value",
            result={"observation": {"value": 2705.0}},
        )
    ]

    evaluation = GroundedInvestigationEvaluator().evaluate(scenario, result, trace)

    config = ExperimentConfig(
        scenario_id=scenario.scenario_id,
        architectures=["historian"],
        agent_type=AgentType.LLM,
        llm_model="test-model",
        llm_temperature=0.0,
        max_steps=6,
    )

    record = ExperimentRecord(
        run_id=run_id,
        experiment_id=experiment_id,
        config=config,
        scenario_difficulty=scenario.difficulty.value,
        simulation_seed=scenario.seed,
        started_at=datetime(2026, 9, 13, 0, 0, tzinfo=UTC),
        completed_at=datetime(2026, 9, 13, 0, 1, tzinfo=UTC),
        status=ExperimentRunStatus.COMPLETED,
        result=result,
        evaluation=evaluation,
        trace_event_count=len(trace),
    )

    return record, trace


def test_save_and_load_round_trip(tmp_path):
    store = ExperimentResultStore(root=tmp_path / "results")
    record, trace = _record("run-1")

    store.save(record, trace)

    loaded = store.load_record("run-1")
    assert loaded.run_id == "run-1"
    assert loaded.result.conclusion == record.result.conclusion
    assert loaded.evaluation.required_evidence_score == 1.0

    loaded_trace = store.load_trace("run-1")
    assert len(loaded_trace) == 1
    assert loaded_trace[0].tool == "get_current_value"


def test_save_creates_separate_raw_trace_and_evaluation_files(tmp_path):
    root = tmp_path / "results"
    store = ExperimentResultStore(root=root)
    record, trace = _record("run-2")

    store.save(record, trace)

    assert (root / "raw" / "run-2.json").exists()
    assert (root / "traces" / "run-2.jsonl").exists()
    assert (root / "evaluations" / "run-2.json").exists()


def test_list_run_ids(tmp_path):
    store = ExperimentResultStore(root=tmp_path / "results")

    assert store.list_run_ids() == []

    store.save(*_record("run-a"))
    store.save(*_record("run-b"))

    assert store.list_run_ids() == ["run-a", "run-b"]


def test_write_aggregate_produces_json_and_csv(tmp_path):
    store = ExperimentResultStore(root=tmp_path / "results")

    record_a, trace_a = _record("run-a", experiment_id="compare-1")
    record_b, trace_b = _record("run-b", experiment_id="compare-1")
    store.save(record_a, trace_a)
    store.save(record_b, trace_b)

    json_path, csv_path = store.write_aggregate("compare-1", [record_a, record_b])

    assert json_path.exists()
    assert csv_path.exists()

    with csv_path.open(newline="", encoding="utf-8") as file:
        rows = list(csv.DictReader(file))

    assert len(rows) == 2
    assert {row["run_id"] for row in rows} == {"run-a", "run-b"}
    assert rows[0]["required_evidence_score"] == "1.0"
