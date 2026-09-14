"""
Shared ExperimentRecord/EvaluationReport/TraceEvent builders for
icab.export unit tests -- not a test module itself (no test_* functions),
pytest does not collect it.
"""

from datetime import UTC, datetime

from icab.agent.interface import EvidenceReference, InvestigationResult
from icab.evaluation.grounded import EvaluationReport
from icab.experiments.models import (
    AgentType,
    ExperimentConfig,
    ExperimentRecord,
    ExperimentRunStatus,
    RunValidity,
)
from icab.trace.models import TraceEvent


def make_evaluation(**overrides) -> EvaluationReport:
    base = dict(
        scenario_id="d1_reactor_pressure_reading",
        required_evidence_hits={"urn:icab:measurement:reactor_pressure": True},
        required_evidence_score=1.0,
        evidence_has_valid_provenance=True,
        canonical_id_validity={"urn:icab:measurement:reactor_pressure": True},
        canonical_id_score=1.0,
        temporal_evidence_required=False,
        temporal_evidence_acquired=False,
        expected_relationships=[],
        relationship_score=1.0,
        root_cause_identified=None,
        affected_assets_mentioned={},
        conclusion_correctness_score=1.0,
        unsupported_numeric_claims=[],
        grounding_score=1.0,
        context_acquired=["urn:icab:measurement:reactor_pressure"],
        context_consumed=["urn:icab:measurement:reactor_pressure"],
        tool_call_count=1,
        unique_tools_used=["get_measurement"],
        terminated_properly=True,
        completeness_score=1.0,
    )
    base.update(overrides)
    return EvaluationReport(**base)


def make_trace(**overrides) -> list[TraceEvent]:
    base = dict(
        timestamp=datetime(2026, 9, 14, tzinfo=UTC),
        step=0,
        action="tool_call",
        tool="get_measurement",
        arguments={"canonical_id": "urn:icab:measurement:reactor_pressure"},
        result={"value": 2705.0, "unit": "kPa"},
        latency_ms=120.5,
        token_usage={"input_tokens": 100, "output_tokens": 20},
        context_acquired=["urn:icab:measurement:reactor_pressure"],
        context_consumed=["urn:icab:measurement:reactor_pressure"],
    )
    base.update(overrides)
    return [TraceEvent(**base)]


def make_record(
    run_id: str,
    *,
    experiment_id: str = "exp",
    scenario_id: str = "d1_reactor_pressure_reading",
    task_id: str | None = "d1-qa-current-pressure",
    question_id: str | None = "Q-d1-qa-current-pressure",
    question_instance_id: str | None = "instance-1",
    isa95_level: str | None = "equipment",
    use_case_id: str | None = "eq-current-value-interpretation",
    repetition: int | None = 1,
    repetition_mode: str | None = "exact",
    architectures: list[str] | None = None,
    llm_model: str | None = "test-model",
    llm_temperature: float | None = 0.0,
    status: ExperimentRunStatus = ExperimentRunStatus.COMPLETED,
    evaluation: EvaluationReport | None = None,
    result: InvestigationResult | None = None,
    error: str | None = None,
    total_latency_ms: float | None = 120.5,
) -> ExperimentRecord:
    if result is None and status == ExperimentRunStatus.COMPLETED:
        result = InvestigationResult(
            objective="What is the current reactor pressure?",
            conclusion="Reactor pressure is approximately 2705 kPa, within the normal operating range.",
            evidence=[EvidenceReference(source="historian", identifier="urn:icab:measurement:reactor_pressure")],
        )

    return ExperimentRecord(
        run_id=run_id,
        experiment_id=experiment_id,
        config=ExperimentConfig(
            scenario_id=scenario_id,
            task_id=task_id,
            task_type="qa",
            isa95_level=isa95_level,
            use_case_id=use_case_id,
            question_id=question_id,
            question_instance_id=question_instance_id,
            repetition=repetition,
            repetition_mode=repetition_mode,
            architectures=architectures or ["historian"],
            agent_type=AgentType.LLM,
            llm_model=llm_model,
            llm_temperature=llm_temperature,
        ),
        scenario_difficulty="D1",
        simulation_seed=101,
        benchmark_version="1.0.0",
        started_at=datetime(2026, 9, 14, tzinfo=UTC),
        completed_at=datetime(2026, 9, 14, 0, 1, tzinfo=UTC),
        status=status,
        error=error,
        validity=RunValidity.VALID,
        result=result,
        evaluation=evaluation,
        trace_event_count=1,
        total_latency_ms=total_latency_ms,
    )
