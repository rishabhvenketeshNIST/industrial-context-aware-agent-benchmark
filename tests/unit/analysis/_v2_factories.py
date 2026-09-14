"""Shared ExperimentRecord/EvaluationReport builders for icab.analysis unit tests. Not a test module itself."""

from __future__ import annotations

from datetime import UTC, datetime

from icab.evaluation.grounded import EvaluationReport
from icab.experiments.models import AgentType, ExperimentConfig, ExperimentRecord, ExperimentRunStatus, RunValidity


def make_evaluation(**overrides) -> EvaluationReport:
    base = dict(
        scenario_id="d2_reactor_context_combination",
        required_evidence_hits={},
        required_evidence_score=1.0,
        evidence_has_valid_provenance=True,
        canonical_id_validity={},
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
        context_consumed=[],
        tool_call_count=1,
        unique_tools_used=["get_current_value"],
        terminated_properly=True,
        completeness_score=1.0,
    )
    base.update(overrides)
    return EvaluationReport(**base)


def make_v2_record(
    run_id: str,
    *,
    use_case_id: str = "eq-value-and-relationship-combination",
    isa95_level: str = "equipment",
    context_combination_id: str,
    architectures: list[str],
    status: ExperimentRunStatus = ExperimentRunStatus.COMPLETED,
    validity: RunValidity = RunValidity.VALID,
    evaluation: EvaluationReport | None = None,
    error: str | None = None,
) -> ExperimentRecord:
    now = datetime.now(UTC)
    return ExperimentRecord(
        run_id=run_id,
        experiment_id="test-exp",
        config=ExperimentConfig(
            scenario_id="d2_reactor_context_combination",
            task_id="d2ctx-investigation-combine-value-and-relationship",
            task_type="investigation",
            isa95_level=isa95_level,
            use_case_id=use_case_id,
            context_combination_id=context_combination_id,
            suite="tep-v2",
            architectures=architectures,
            agent_type=AgentType.LLM,
            llm_model="test-model",
            llm_temperature=0.0,
        ),
        scenario_difficulty="D2",
        simulation_seed=1,
        started_at=now,
        completed_at=now,
        status=status,
        error=error,
        validity=validity,
        evaluation=evaluation if status == ExperimentRunStatus.COMPLETED else None,
        trace_event_count=1,
    )
