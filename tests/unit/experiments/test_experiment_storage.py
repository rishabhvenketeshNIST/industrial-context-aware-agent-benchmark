import csv
import json
from datetime import UTC, datetime

import pytest

from icab.agent.interface import EvidenceReference, InvestigationResult, TerminationReason
from icab.evaluation.grounded import GroundedInvestigationEvaluator
from icab.evaluation.information_flow import InformationFlowAnalyzer
from icab.experiments import AgentType, ExperimentConfig, ExperimentRecord, ExperimentResultStore
from icab.experiments.models import ExperimentRunStatus, RunValidity
from icab.experiments.storage import HeterogeneousControlsError
from icab.scenarios import BenchmarkScenarioRegistry
from icab.trace.models import TraceEvent

SCENARIOS_DIR = "configs/benchmark/scenarios"


def _record(
    run_id: str,
    experiment_id: str = "exp-1",
    *,
    validity: RunValidity = RunValidity.VALID,
    validity_reason: str | None = None,
    llm_model: str = "test-model",
    llm_temperature: float = 0.0,
    max_steps: int = 6,
    architecture_combination_key: str | None = None,
    architectures: list[str] | None = None,
) -> tuple[ExperimentRecord, list[TraceEvent]]:
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
            result={"observation": {"measurement_id": "urn:icab:measurement:reactor_pressure", "value": 2705.0}},
            latency_ms=12.5,
        ),
        TraceEvent(
            timestamp=datetime(2026, 9, 13, tzinfo=UTC),
            step=1,
            action="llm_generate",
            token_usage={"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
        ),
    ]

    evaluation = GroundedInvestigationEvaluator().evaluate(scenario, result, trace)
    information_flow = InformationFlowAnalyzer().analyze(trace)

    config = ExperimentConfig(
        scenario_id=scenario.scenario_id,
        architectures=architectures or ["historian"],
        architecture_combination_key=architecture_combination_key,
        agent_type=AgentType.LLM,
        llm_model=llm_model,
        llm_temperature=llm_temperature,
        max_steps=max_steps,
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
        validity=validity,
        validity_reason=validity_reason,
        result=result,
        evaluation=evaluation,
        information_flow=information_flow,
        trace_event_count=len(trace),
        total_latency_ms=12.5,
        total_tokens=120,
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
    assert len(loaded_trace) == 2
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


def test_write_aggregate_excludes_invalid_runs_by_default(tmp_path):
    store = ExperimentResultStore(root=tmp_path / "results")

    valid_record, valid_trace = _record("run-valid", experiment_id="compare-2")
    invalid_record, invalid_trace = _record(
        "run-invalid",
        experiment_id="compare-2",
        validity=RunValidity.LEGACY_CONTROL_ONLY,
        validity_reason="legacy baseline against a real scenario",
    )
    store.save(valid_record, valid_trace)
    store.save(invalid_record, invalid_trace)

    # Both runs are still fully persisted regardless of validity.
    assert store.load_record("run-valid").run_id == "run-valid"
    assert store.load_record("run-invalid").run_id == "run-invalid"

    json_path, csv_path = store.write_aggregate(
        "compare-2", [valid_record, invalid_record]
    )

    with csv_path.open(newline="", encoding="utf-8") as file:
        rows = list(csv.DictReader(file))

    # The main comparison table must not silently include the invalid run.
    assert len(rows) == 1
    assert rows[0]["run_id"] == "run-valid"

    aggregate_data = json.loads(json_path.read_text(encoding="utf-8"))
    assert aggregate_data["excluded_invalid_runs"] == 1
    assert len(aggregate_data["runs"]) == 1


def test_write_aggregate_include_invalid_still_labels_them_clearly(tmp_path):
    store = ExperimentResultStore(root=tmp_path / "results")

    valid_record, valid_trace = _record("run-valid-2", experiment_id="compare-3")
    invalid_record, invalid_trace = _record(
        "run-invalid-2",
        experiment_id="compare-3",
        validity=RunValidity.LEGACY_CONTROL_ONLY,
        validity_reason="legacy baseline against a real scenario",
    )
    store.save(valid_record, valid_trace)
    store.save(invalid_record, invalid_trace)

    _json_path, csv_path = store.write_aggregate(
        "compare-3", [valid_record, invalid_record], include_invalid=True
    )

    with csv_path.open(newline="", encoding="utf-8") as file:
        rows = {row["run_id"]: row for row in csv.DictReader(file)}

    assert len(rows) == 2
    assert rows["run-valid-2"]["validity"] == "valid"
    assert rows["run-invalid-2"]["validity"] == "legacy_control_only"
    assert rows["run-invalid-2"]["validity_reason"] != ""


def test_write_aggregate_includes_information_flow_and_cost_columns(tmp_path):
    store = ExperimentResultStore(root=tmp_path / "results")

    record, trace = _record(
        "run-flow", experiment_id="compare-flow", architecture_combination_key="historian_only"
    )
    store.save(record, trace)

    _json_path, csv_path = store.write_aggregate("compare-flow", [record])

    with csv_path.open(newline="", encoding="utf-8") as file:
        rows = list(csv.DictReader(file))

    assert rows[0]["architecture_combination_key"] == "historian_only"
    assert rows[0]["acquisition_count"] == "1"
    assert rows[0]["redundant_acquisition_count"] == "0"
    assert rows[0]["tool_error_count"] == "0"
    assert rows[0]["total_latency_ms"] == "12.5"
    assert rows[0]["total_tokens"] == "120"


def test_write_aggregate_rejects_runs_with_different_controls_by_default(tmp_path):
    store = ExperimentResultStore(root=tmp_path / "results")

    record_a, trace_a = _record("run-c1", experiment_id="compare-controls", max_steps=6)
    record_b, trace_b = _record("run-c2", experiment_id="compare-controls", max_steps=12)
    store.save(record_a, trace_a)
    store.save(record_b, trace_b)

    with pytest.raises(HeterogeneousControlsError, match="max_steps"):
        store.write_aggregate("compare-controls", [record_a, record_b])


def test_write_aggregate_allows_heterogeneous_controls_when_declared(tmp_path):
    store = ExperimentResultStore(root=tmp_path / "results")

    record_a, trace_a = _record("run-c3", experiment_id="compare-controls-2", max_steps=6)
    record_b, trace_b = _record("run-c4", experiment_id="compare-controls-2", max_steps=12)
    store.save(record_a, trace_a)
    store.save(record_b, trace_b)

    json_path, csv_path = store.write_aggregate(
        "compare-controls-2", [record_a, record_b], allow_heterogeneous_controls=True
    )

    aggregate_data = json.loads(json_path.read_text(encoding="utf-8"))
    assert aggregate_data["controls_consistent"] is False
    assert "max_steps" in aggregate_data["control_variance"]
    assert len(aggregate_data["runs"]) == 2

    with csv_path.open(newline="", encoding="utf-8") as file:
        rows = list(csv.DictReader(file))
    assert len(rows) == 2


def test_write_aggregate_reports_controls_consistent_when_uniform(tmp_path):
    store = ExperimentResultStore(root=tmp_path / "results")

    record_a, trace_a = _record("run-c5", experiment_id="compare-controls-3")
    record_b, trace_b = _record("run-c6", experiment_id="compare-controls-3")
    store.save(record_a, trace_a)
    store.save(record_b, trace_b)

    json_path, _csv_path = store.write_aggregate("compare-controls-3", [record_a, record_b])

    aggregate_data = json.loads(json_path.read_text(encoding="utf-8"))
    assert aggregate_data["controls_consistent"] is True
    assert aggregate_data["control_variance"] == {}
