from icab.experiments.hypotheses import HypothesisID, get_spec
from icab.reporting.aggregation import aggregate_records
from icab.reporting.hypothesis_report import build_hypothesis_report
from icab.reporting.store import ReportStore

from _factories import make_evaluation, make_record


def test_write_and_load_aggregation_report_round_trips(tmp_path):
    store = ReportStore(root=tmp_path / "results")
    records = [
        make_record(
            "t1", combination_key="kg_historian", evaluation=make_evaluation(conclusion_correctness_score=0.5)
        ),
    ]
    report = aggregate_records(records, group_by=("architecture_combination_key",))

    path = store.write_aggregation_report(report, "test-agg")

    assert path.exists()
    assert path == store.reports_dir / "test-agg.json"

    loaded = store.load_aggregation_report("test-agg")
    assert loaded.groups[0].group_key == report.groups[0].group_key


def test_write_and_load_hypothesis_report_round_trips(tmp_path):
    store = ReportStore(root=tmp_path / "results")
    spec = get_spec(HypothesisID.H1)
    records = [
        make_record("t1", combination_key="kg_historian", evaluation=make_evaluation()),
        make_record("c1", combination_key="historian_only", evaluation=make_evaluation()),
    ]
    report = build_hypothesis_report(spec, records)

    path = store.write_hypothesis_report(report, "test-hyp-H1")

    assert path.exists()

    loaded = store.load_hypothesis_report("test-hyp-H1")
    assert loaded.result.hypothesis == report.result.hypothesis
    assert loaded.limitations == report.limitations


def test_write_markdown_writes_a_file(tmp_path):
    store = ReportStore(root=tmp_path / "results")

    path = store.write_markdown("# hello", "test-md")

    assert path.exists()
    assert path.read_text(encoding="utf-8") == "# hello"
    assert path == store.reports_dir / "test-md.md"


def test_figure_path_creates_figures_dir(tmp_path):
    store = ReportStore(root=tmp_path / "results")

    path = store.figure_path("plot.png")

    assert path.parent.exists()
    assert path == store.figures_dir / "plot.png"
