from icab.experiments.hypotheses import HypothesisID, get_spec
from icab.reporting.aggregation import aggregate_records
from icab.reporting.hypothesis_report import build_hypothesis_report
from icab.reporting.plotting import (
    plot_effectiveness_vs_efficiency,
    plot_hypothesis_comparison,
    plot_metric_by_group,
)

from _factories import make_evaluation, make_record


def _aggregation_report():
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
    return aggregate_records(records, group_by=("architecture_combination_key",))


def test_plot_metric_by_group_writes_a_nonempty_file(tmp_path):
    report = _aggregation_report()
    output_path = tmp_path / "figure.png"

    result_path = plot_metric_by_group(report, "conclusion_correctness_score", output_path)

    assert result_path == output_path
    assert output_path.exists()
    assert output_path.stat().st_size > 0


def test_plot_metric_by_group_handles_single_data_point_without_stdev(tmp_path):
    """A group with n=1 has stdev=None -- must not crash the error-bar rendering."""

    report = _aggregation_report()
    assert report.groups[0].metrics["conclusion_correctness_score"].n == 1

    output_path = tmp_path / "figure.png"
    plot_metric_by_group(report, "conclusion_correctness_score", output_path)

    assert output_path.exists()


def test_plot_effectiveness_vs_efficiency_writes_a_nonempty_file(tmp_path):
    report = _aggregation_report()
    output_path = tmp_path / "scatter.png"

    plot_effectiveness_vs_efficiency(report, "conclusion_correctness_score", "tool_call_count", output_path)

    assert output_path.exists()
    assert output_path.stat().st_size > 0


def test_plot_hypothesis_comparison_writes_a_nonempty_file(tmp_path):
    spec = get_spec(HypothesisID.H1)
    records = [
        make_record("t1", combination_key="kg_historian", evaluation=make_evaluation(conclusion_correctness_score=0.8)),
        make_record("c1", combination_key="historian_only", evaluation=make_evaluation(conclusion_correctness_score=0.0)),
    ]
    hypothesis_report = build_hypothesis_report(spec, records)
    output_path = tmp_path / "hyp.png"

    plot_hypothesis_comparison(hypothesis_report, output_path)

    assert output_path.exists()
    assert output_path.stat().st_size > 0
