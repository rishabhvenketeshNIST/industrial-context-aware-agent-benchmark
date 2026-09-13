from icab.experiments.hypotheses import HypothesisID, get_spec
from icab.reporting.aggregation import aggregate_records
from icab.reporting.hypothesis_report import build_hypothesis_report
from icab.reporting.markdown import render_aggregation_markdown, render_hypothesis_markdown

from _factories import make_evaluation, make_record


def test_aggregation_markdown_contains_group_and_metric_labels():
    records = [
        make_record(
            "t1", combination_key="kg_historian", evaluation=make_evaluation(conclusion_correctness_score=0.5)
        ),
        make_record(
            "c1", combination_key="historian_only", evaluation=make_evaluation(conclusion_correctness_score=0.0)
        ),
    ]
    report = aggregate_records(records, group_by=("architecture_combination_key",))

    markdown = render_aggregation_markdown(report, title="Test report")

    assert "# Test report" in markdown
    assert "kg_historian" in markdown
    assert "historian_only" in markdown
    assert "Investigation correctness" in markdown  # EFFECTIVENESS_METRICS label
    assert "Tool calls" in markdown  # EFFICIENCY_METRICS label
    assert "no simulator, gateway, or LLM calls" in markdown


def test_hypothesis_markdown_contains_statement_arms_and_limitations():
    spec = get_spec(HypothesisID.H3)
    records = [
        make_record("t1", combination_key="kg_historian", evaluation=make_evaluation(relationship_score=1.0)),
        make_record("c1", combination_key="historian_only", evaluation=make_evaluation(relationship_score=0.0)),
    ]
    report = build_hypothesis_report(spec, records)

    markdown = render_hypothesis_markdown(report)

    assert "H3" in markdown
    assert spec.statement in markdown
    assert "kg_historian" in markdown
    assert "historian_only" in markdown
    assert "## Limitations" in markdown
    assert "not a significance test" in markdown
