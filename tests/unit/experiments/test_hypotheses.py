from datetime import UTC, datetime

from icab.evaluation.grounded import EvaluationReport
from icab.evaluation.information_flow import InformationFlowReport
from icab.experiments.architecture_combinations import list_combination_keys
from icab.experiments.hypotheses import (
    HYPOTHESIS_SPECS,
    HypothesisID,
    combinations_for_hypothesis,
    evaluate_all_hypotheses,
    evaluate_hypothesis,
    get_spec,
)
from icab.experiments.models import (
    AgentType,
    ExperimentConfig,
    ExperimentRecord,
    ExperimentRunStatus,
    RunValidity,
)


def _evaluation(**overrides) -> EvaluationReport:
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


def _information_flow(**overrides) -> InformationFlowReport:
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


def _record(
    run_id: str,
    *,
    combination_key: str,
    validity: RunValidity = RunValidity.VALID,
    status: ExperimentRunStatus = ExperimentRunStatus.COMPLETED,
    evaluation: EvaluationReport | None = None,
    information_flow: InformationFlowReport | None = None,
) -> ExperimentRecord:
    return ExperimentRecord(
        run_id=run_id,
        experiment_id="hyp-test",
        config=ExperimentConfig(
            scenario_id="d4_plant_wide_investigation",
            architectures=["historian"],
            architecture_combination_key=combination_key,
            agent_type=AgentType.LLM,
            llm_model="test-model",
            llm_temperature=0.0,
            max_steps=20,
        ),
        scenario_difficulty="D4",
        simulation_seed=104,
        started_at=datetime(2026, 9, 13, tzinfo=UTC),
        completed_at=datetime(2026, 9, 13, 0, 1, tzinfo=UTC),
        status=status,
        validity=validity,
        evaluation=evaluation,
        information_flow=information_flow,
        trace_event_count=1,
    )


def test_every_spec_references_only_registered_combination_keys():
    known = set(list_combination_keys())
    for spec in HYPOTHESIS_SPECS:
        for key in (*spec.treatment_combinations, *spec.control_combinations):
            assert key in known, f"{spec.id} references unknown combination {key!r}"


def test_every_spec_has_a_nonempty_rationale_and_statement():
    for spec in HYPOTHESIS_SPECS:
        assert spec.statement.strip()
        assert spec.rationale.strip()


def test_get_spec_accepts_string_or_enum():
    assert get_spec("H1").id == HypothesisID.H1
    assert get_spec(HypothesisID.H1).id == HypothesisID.H1


def test_combinations_for_hypothesis_deduplicates_and_preserves_order():
    spec = get_spec(HypothesisID.H1)
    assert combinations_for_hypothesis(spec) == ["kg_historian", "historian_only"]


def test_h1_higher_conclusion_correctness_in_treatment_supports_hypothesis():
    spec = get_spec(HypothesisID.H1)
    records = [
        _record(
            "t1",
            combination_key="kg_historian",
            evaluation=_evaluation(conclusion_correctness_score=0.8),
        ),
        _record(
            "c1",
            combination_key="historian_only",
            evaluation=_evaluation(conclusion_correctness_score=0.0),
        ),
    ]

    result = evaluate_hypothesis(spec, records)

    assert result.hypothesis == HypothesisID.H1
    assert result.treatment_run_ids == ["t1"]
    assert result.control_run_ids == ["c1"]
    assert result.treatment_mean == 0.8
    assert result.control_mean == 0.0
    assert result.mean_difference == 0.8
    assert result.direction_supports_hypothesis is True


def test_h2_lower_tool_call_count_in_treatment_supports_hypothesis():
    spec = get_spec(HypothesisID.H2)
    records = [
        _record("t1", combination_key="uns_historian_kg", evaluation=_evaluation(tool_call_count=3)),
        _record("c1", combination_key="kg_historian", evaluation=_evaluation(tool_call_count=9)),
    ]

    result = evaluate_hypothesis(spec, records)

    assert result.mean_difference == -6
    assert result.direction_supports_hypothesis is True


def test_h4_uses_information_flow_redundant_acquisition_count():
    spec = get_spec(HypothesisID.H4)
    records = [
        _record(
            "t1",
            combination_key="kg_historian",
            information_flow=_information_flow(redundant_acquisition_count=2),
        ),
        _record(
            "c1",
            combination_key="full",
            information_flow=_information_flow(redundant_acquisition_count=5),
        ),
    ]

    result = evaluate_hypothesis(spec, records)

    assert result.treatment_values == [2.0]
    assert result.control_values == [5.0]
    assert result.direction_supports_hypothesis is True  # lower redundancy supports H4


def test_h5_uses_unsupported_numeric_claims_count_synthetic_metric():
    spec = get_spec(HypothesisID.H5)
    records = [
        _record(
            "t1",
            combination_key="kg_historian",
            evaluation=_evaluation(unsupported_numeric_claims=[]),
        ),
        _record(
            "c1",
            combination_key="historian_only",
            evaluation=_evaluation(unsupported_numeric_claims=[2705.0, 120.4]),
        ),
    ]

    result = evaluate_hypothesis(spec, records)

    assert result.treatment_values == [0.0]
    assert result.control_values == [2.0]
    assert result.direction_supports_hypothesis is True


def test_missing_evaluation_or_information_flow_is_excluded_not_treated_as_zero():
    spec = get_spec(HypothesisID.H1)
    records = [
        _record("t1", combination_key="kg_historian", evaluation=None),
        _record("c1", combination_key="historian_only", evaluation=_evaluation()),
    ]

    result = evaluate_hypothesis(spec, records)

    assert result.treatment_values == []
    assert result.treatment_mean is None
    assert result.mean_difference is None
    assert result.direction_supports_hypothesis is None


def test_legacy_control_only_and_failed_records_are_excluded():
    spec = get_spec(HypothesisID.H1)
    records = [
        _record(
            "t-legacy",
            combination_key="kg_historian",
            validity=RunValidity.LEGACY_CONTROL_ONLY,
            evaluation=_evaluation(conclusion_correctness_score=1.0),
        ),
        _record(
            "t-failed",
            combination_key="kg_historian",
            status=ExperimentRunStatus.FAILED,
            evaluation=_evaluation(conclusion_correctness_score=1.0),
        ),
        _record(
            "c1", combination_key="historian_only", evaluation=_evaluation(conclusion_correctness_score=0.0)
        ),
    ]

    result = evaluate_hypothesis(spec, records)

    assert result.treatment_run_ids == []
    assert result.control_run_ids == ["c1"]


def test_records_for_other_combinations_do_not_pollute_either_arm():
    spec = get_spec(HypothesisID.H1)  # kg_historian vs historian_only
    records = [
        _record("t1", combination_key="kg_historian", evaluation=_evaluation(conclusion_correctness_score=0.5)),
        _record("c1", combination_key="historian_only", evaluation=_evaluation(conclusion_correctness_score=0.5)),
        _record("other", combination_key="full", evaluation=_evaluation(conclusion_correctness_score=1.0)),
    ]

    result = evaluate_hypothesis(spec, records)

    assert result.treatment_run_ids == ["t1"]
    assert result.control_run_ids == ["c1"]


def test_evaluate_all_hypotheses_returns_one_result_per_spec():
    results = evaluate_all_hypotheses([])
    assert [r.hypothesis for r in results] == [spec.id for spec in HYPOTHESIS_SPECS]
    for result in results:
        assert result.treatment_values == []
        assert result.control_values == []
        assert result.direction_supports_hypothesis is None
        assert "not" in result.caveat.lower()
