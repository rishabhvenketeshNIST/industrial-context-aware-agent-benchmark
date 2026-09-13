import pytest

from icab.experiments.controls import HeterogeneousControlsError
from icab.experiments.hypotheses import HypothesisID, evaluate_hypothesis, get_spec
from icab.reporting.hypothesis_report import build_hypothesis_report

from _factories import make_evaluation, make_record


def test_build_from_spec_computes_stats_for_both_arms():
    spec = get_spec(HypothesisID.H1)  # kg_historian vs historian_only
    records = [
        make_record(
            "t1", combination_key="kg_historian", evaluation=make_evaluation(conclusion_correctness_score=0.8)
        ),
        make_record(
            "c1", combination_key="historian_only", evaluation=make_evaluation(conclusion_correctness_score=0.0)
        ),
    ]

    report = build_hypothesis_report(spec, records)

    assert report.treatment_stats.n == 1
    assert report.treatment_stats.mean == 0.8
    assert report.control_stats.n == 1
    assert report.control_stats.mean == 0.0
    assert report.result.direction_supports_hypothesis is True


def test_build_from_precomputed_result_reuses_it_unchanged():
    spec = get_spec(HypothesisID.H1)
    records = [
        make_record(
            "t1", combination_key="kg_historian", evaluation=make_evaluation(conclusion_correctness_score=0.8)
        ),
        make_record(
            "c1", combination_key="historian_only", evaluation=make_evaluation(conclusion_correctness_score=0.0)
        ),
    ]
    precomputed = evaluate_hypothesis(spec, records)

    report = build_hypothesis_report(precomputed, records)

    assert report.result is precomputed


def test_limitations_flag_small_sample_size():
    spec = get_spec(HypothesisID.H1)
    records = [
        make_record("t1", combination_key="kg_historian", evaluation=make_evaluation()),
        make_record("c1", combination_key="historian_only", evaluation=make_evaluation()),
    ]

    report = build_hypothesis_report(spec, records)

    assert any("small" in note.lower() for note in report.limitations)


def test_limitations_flag_a_tie_as_not_evidence_either_way():
    spec = get_spec(HypothesisID.H1)
    records = [
        make_record("t1", combination_key="kg_historian", evaluation=make_evaluation(conclusion_correctness_score=0.5)),
        make_record("c1", combination_key="historian_only", evaluation=make_evaluation(conclusion_correctness_score=0.5)),
    ]

    report = build_hypothesis_report(spec, records)

    assert report.result.direction_supports_hypothesis is False
    assert any("tie" in note.lower() for note in report.limitations)


def test_limitations_flag_an_empty_arm():
    spec = get_spec(HypothesisID.H1)
    records = [
        make_record("t1", combination_key="kg_historian", evaluation=make_evaluation()),
        # no historian_only records at all
    ]

    report = build_hypothesis_report(spec, records)

    assert report.control_stats.n == 0
    assert any("no usable" in note.lower() for note in report.limitations)


def test_heterogeneous_controls_among_arm_records_raises_by_default():
    spec = get_spec(HypothesisID.H1)
    records = [
        make_record("t1", combination_key="kg_historian", max_steps=10, evaluation=make_evaluation()),
        make_record("c1", combination_key="historian_only", max_steps=20, evaluation=make_evaluation()),
    ]

    with pytest.raises(HeterogeneousControlsError, match="H1"):
        build_hypothesis_report(spec, records)


def test_allow_heterogeneous_controls_overrides():
    spec = get_spec(HypothesisID.H1)
    records = [
        make_record("t1", combination_key="kg_historian", max_steps=10, evaluation=make_evaluation()),
        make_record("c1", combination_key="historian_only", max_steps=20, evaluation=make_evaluation()),
    ]

    report = build_hypothesis_report(spec, records, allow_heterogeneous_controls=True)

    assert report.controls_consistent is False
    assert "max_steps" in report.control_variance


def test_records_outside_either_arm_do_not_affect_the_report():
    spec = get_spec(HypothesisID.H1)
    records = [
        make_record("t1", combination_key="kg_historian", evaluation=make_evaluation()),
        make_record("c1", combination_key="historian_only", evaluation=make_evaluation()),
        make_record("other", combination_key="full", max_steps=999, evaluation=make_evaluation()),
    ]

    # The "other" (full) record has a wildly different max_steps but is not
    # part of H1's arms -- must not trigger HeterogeneousControlsError.
    report = build_hypothesis_report(spec, records)

    assert report.controls_consistent is True
