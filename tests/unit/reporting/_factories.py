"""
Shared ExperimentRecord/EvaluationReport/InformationFlowReport builders
for icab.reporting unit tests. Not a test module itself (no test_*
functions) -- pytest does not collect it.
"""

from datetime import UTC, datetime

from icab.evaluation.grounded import EvaluationReport
from icab.evaluation.information_flow import InformationFlowReport
from icab.experiments.models import (
    AgentType,
    DeterministicAgentKind,
    ExperimentConfig,
    ExperimentRecord,
    ExperimentRunStatus,
    RunValidity,
)


def make_evaluation(**overrides) -> EvaluationReport:
    base = dict(
        scenario_id="d4_plant_wide_investigation",
        required_evidence_hits={},
        required_evidence_score=0.0,
        evidence_has_valid_provenance=True,
        canonical_id_validity={},
        canonical_id_score=1.0,
        temporal_evidence_required=False,
        temporal_evidence_acquired=False,
        expected_relationships=[],
        relationship_score=0.0,
        root_cause_identified=None,
        affected_assets_mentioned={},
        conclusion_correctness_score=0.0,
        unsupported_numeric_claims=[],
        grounding_score=1.0,
        context_acquired=[],
        context_consumed=[],
        tool_call_count=0,
        unique_tools_used=[],
        terminated_properly=True,
        completeness_score=0.0,
    )
    base.update(overrides)
    return EvaluationReport(**base)


def make_information_flow(**overrides) -> InformationFlowReport:
    base = dict(
        discovered_canonical_ids=[],
        acquisitions=[],
        architectures_used_per_measurement={},
        redundant_measurements=[],
        redundant_acquisition_count=0,
        unresolved_acquisition_count=0,
        tool_error_count=0,
    )
    base.update(overrides)
    return InformationFlowReport(**base)


def make_record(
    run_id: str,
    *,
    experiment_id: str = "exp",
    scenario_id: str = "d4_plant_wide_investigation",
    difficulty: str = "D4",
    architectures: list[str] | None = None,
    combination_key: str | None = None,
    agent_type: AgentType = AgentType.LLM,
    deterministic_agent: DeterministicAgentKind | None = None,
    llm_model: str | None = "test-model",
    llm_temperature: float | None = 0.0,
    max_steps: int | None = 20,
    simulation_seed: int = 104,
    validity: RunValidity = RunValidity.VALID,
    status: ExperimentRunStatus = ExperimentRunStatus.COMPLETED,
    evaluation: EvaluationReport | None = None,
    information_flow: InformationFlowReport | None = None,
    total_latency_ms: float | None = None,
    total_tokens: int | None = None,
) -> ExperimentRecord:
    return ExperimentRecord(
        run_id=run_id,
        experiment_id=experiment_id,
        config=ExperimentConfig(
            scenario_id=scenario_id,
            architectures=architectures or ["historian"],
            architecture_combination_key=combination_key,
            agent_type=agent_type,
            deterministic_agent=deterministic_agent,
            llm_model=llm_model if agent_type == AgentType.LLM else None,
            llm_temperature=llm_temperature if agent_type == AgentType.LLM else None,
            max_steps=max_steps if agent_type == AgentType.LLM else None,
        ),
        scenario_difficulty=difficulty,
        simulation_seed=simulation_seed,
        started_at=datetime(2026, 9, 13, tzinfo=UTC),
        completed_at=datetime(2026, 9, 13, 0, 1, tzinfo=UTC),
        status=status,
        validity=validity,
        evaluation=evaluation,
        information_flow=information_flow,
        trace_event_count=1,
        total_latency_ms=total_latency_ms,
        total_tokens=total_tokens,
    )
