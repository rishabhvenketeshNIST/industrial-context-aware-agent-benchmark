import pytest

from icab.experiments.controls import HeterogeneousControlsError
from icab.experiments.models import AgentType, ExperimentRunStatus, RunValidity
from icab.reporting.aggregation import aggregate_records, list_dimensions

from _factories import make_evaluation, make_information_flow, make_record


def test_unknown_dimension_raises_with_valid_list():
    records = [make_record("r1")]

    with pytest.raises(ValueError, match="scenario_id"):
        aggregate_records(records, group_by=("not_a_real_dimension",))


def test_list_dimensions_includes_every_spec_named_dimension():
    dims = list_dimensions()
    for expected in (
        "scenario_id",
        "difficulty",
        "architecture",
        "architecture_combination_key",
        "agent_type",
        "llm_model",
        "simulation_seed",
        "run_id",
    ):
        assert expected in dims


def test_groups_by_architecture_combination_key_and_computes_metrics():
    records = [
        make_record(
            "t1",
            combination_key="kg_historian",
            evaluation=make_evaluation(conclusion_correctness_score=0.5, tool_call_count=10),
        ),
        make_record(
            "c1",
            combination_key="historian_only",
            evaluation=make_evaluation(conclusion_correctness_score=0.0, tool_call_count=20),
        ),
    ]

    report = aggregate_records(records, group_by=("architecture_combination_key",))

    assert report.controls_consistent is True
    assert len(report.groups) == 2

    by_key = {group.group_key["architecture_combination_key"]: group for group in report.groups}
    assert by_key["kg_historian"].metrics["conclusion_correctness_score"].mean == 0.5
    assert by_key["kg_historian"].metrics["tool_call_count"].mean == 10.0
    assert by_key["historian_only"].metrics["conclusion_correctness_score"].mean == 0.0


def test_source_run_ids_include_every_record_considered_even_if_excluded():
    records = [
        make_record("valid1", evaluation=make_evaluation()),
        make_record("legacy1", validity=RunValidity.LEGACY_CONTROL_ONLY, evaluation=make_evaluation()),
    ]

    report = aggregate_records(records, group_by=("scenario_id",))

    assert set(report.source_run_ids) == {"valid1", "legacy1"}
    assert report.excluded_invalid_runs == 1
    # the legacy run is excluded from groups/metrics by default
    assert report.groups[0].run_ids == ["valid1"]


def test_include_invalid_keeps_legacy_runs_in_group_composition_but_not_in_metrics():
    records = [
        make_record("valid1", evaluation=make_evaluation(conclusion_correctness_score=1.0)),
        make_record(
            "legacy1",
            validity=RunValidity.LEGACY_CONTROL_ONLY,
            evaluation=make_evaluation(conclusion_correctness_score=1.0),
        ),
    ]

    report = aggregate_records(records, group_by=("scenario_id",), include_invalid=True)

    assert report.excluded_invalid_runs == 0
    group = report.groups[0]
    assert group.n_runs == 2
    assert group.n_valid == 1
    assert group.n_legacy_control_only == 1
    # metrics still only computed over the usable (VALID + COMPLETED) record
    assert group.metrics["conclusion_correctness_score"].n == 1


def test_failed_runs_are_counted_but_excluded_from_metrics():
    records = [
        make_record("ok1", evaluation=make_evaluation(conclusion_correctness_score=1.0)),
        make_record(
            "failed1",
            status=ExperimentRunStatus.FAILED,
            evaluation=make_evaluation(conclusion_correctness_score=1.0),
        ),
    ]

    report = aggregate_records(records, group_by=("scenario_id",))

    group = report.groups[0]
    assert group.n_runs == 2
    assert group.n_completed == 1
    assert group.n_failed == 1
    assert group.metrics["conclusion_correctness_score"].n == 1


def test_heterogeneous_max_steps_raises_by_default():
    records = [
        make_record("a", combination_key="kg_historian", max_steps=10, evaluation=make_evaluation()),
        make_record("b", combination_key="historian_only", max_steps=20, evaluation=make_evaluation()),
    ]

    with pytest.raises(HeterogeneousControlsError, match="max_steps"):
        aggregate_records(records, group_by=("architecture_combination_key",))


def test_allow_heterogeneous_controls_overrides_and_reports_variance():
    records = [
        make_record("a", combination_key="kg_historian", max_steps=10, evaluation=make_evaluation()),
        make_record("b", combination_key="historian_only", max_steps=20, evaluation=make_evaluation()),
    ]

    report = aggregate_records(
        records, group_by=("architecture_combination_key",), allow_heterogeneous_controls=True
    )

    assert report.controls_consistent is False
    assert "max_steps" in report.control_variance
    assert len(report.groups) == 2


def test_grouping_by_scenario_id_does_not_require_seed_to_match():
    """Different scenarios legitimately have different simulation_seed values -- see
    aggregate_records's docstring on the scenario_id/simulation_seed special case."""

    records = [
        make_record(
            "a",
            scenario_id="d3_reactor_pressure_deviation",
            simulation_seed=103,
            evaluation=make_evaluation(),
        ),
        make_record(
            "b",
            scenario_id="d4_plant_wide_investigation",
            simulation_seed=104,
            evaluation=make_evaluation(),
        ),
    ]

    # Should NOT raise, even though simulation_seed differs, because
    # scenario_id is the group_by dimension and seed is intrinsic to it.
    report = aggregate_records(records, group_by=("scenario_id",))

    assert report.controls_consistent is True
    assert len(report.groups) == 2


def test_information_flow_metrics_are_resolved_per_group():
    records = [
        make_record(
            "a",
            combination_key="full",
            evaluation=make_evaluation(),
            information_flow=make_information_flow(redundant_acquisition_count=5, tool_error_count=1),
        ),
        make_record(
            "b",
            combination_key="kg_historian",
            evaluation=make_evaluation(),
            information_flow=make_information_flow(redundant_acquisition_count=2, tool_error_count=0),
        ),
    ]

    report = aggregate_records(records, group_by=("architecture_combination_key",))

    by_key = {group.group_key["architecture_combination_key"]: group for group in report.groups}
    assert by_key["full"].metrics["information_flow.redundant_acquisition_count"].mean == 5.0
    assert by_key["kg_historian"].metrics["information_flow.tool_error_count"].mean == 0.0


def test_deterministic_agent_dimension_groups_llm_runs_as_none():
    records = [make_record("a", agent_type=AgentType.LLM, evaluation=make_evaluation())]

    report = aggregate_records(records, group_by=("deterministic_agent",))

    assert report.groups[0].group_key["deterministic_agent"] is None
