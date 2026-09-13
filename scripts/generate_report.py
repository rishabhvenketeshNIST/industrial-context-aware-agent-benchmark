"""
Command-line entry point for M12 grouped aggregation reports.

Operates ENTIRELY on already-persisted `results/{raw,traces,evaluations}/`
artifacts (via `icab.experiments.ExperimentResultStore`) -- makes no
simulator, gateway, or LLM calls, and produces the same output every time
given the same persisted input records.

Usage::

    # summarize every persisted run, grouped by architecture combination
    uv run python scripts/generate_report.py \\
        --all --group-by architecture_combination_key --name d4-by-combination

    # restrict to specific runs (e.g. one experiment_id's sweep)
    uv run python scripts/generate_report.py \\
        --experiment-id m10-d4-combo-validation-v2 \\
        --group-by architecture_combination_key --name d4-v2-by-combination \\
        --plot-metric conclusion_correctness_score --plot-metric tool_call_count

    # group by more than one dimension at once
    uv run python scripts/generate_report.py --all \\
        --group-by scenario_id --group-by architecture_combination_key \\
        --name by-scenario-and-combination

Writes `results/reports/<name>.json` (the full `AggregationReport`),
`results/reports/<name>.md` (a human-readable summary), and, for each
`--plot-metric`, `results/figures/<name>-<metric>.png`.
"""

from __future__ import annotations

import argparse
import sys

from icab.experiments import ExperimentResultStore
from icab.experiments.controls import HeterogeneousControlsError
from icab.reporting.aggregation import aggregate_records, list_dimensions
from icab.reporting.markdown import render_aggregation_markdown
from icab.reporting.metrics import ALL_METRICS
from icab.reporting.plotting import plot_metric_by_group
from icab.reporting.store import ReportStore


def _load_records(store: ExperimentResultStore, args: argparse.Namespace):
    if args.run_id:
        return [store.load_record(run_id) for run_id in args.run_id]

    all_run_ids = store.list_run_ids()
    if not all_run_ids:
        raise SystemExit("No persisted runs found under --results-root; nothing to aggregate.")

    records = [store.load_record(run_id) for run_id in all_run_ids]

    if args.experiment_id:
        wanted = set(args.experiment_id)
        records = [record for record in records if record.experiment_id in wanted]

    return records


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--run-id", action="append", help="Explicit run_id(s) to aggregate.")
    selection.add_argument(
        "--experiment-id",
        action="append",
        help="Aggregate every persisted run whose experiment_id is one of these.",
    )
    selection.add_argument("--all", action="store_true", help="Aggregate every persisted run.")

    parser.add_argument(
        "--group-by",
        action="append",
        required=True,
        choices=list_dimensions(),
        help="Dimension(s) to group by -- pass more than once for a multi-dimensional grouping.",
    )
    parser.add_argument(
        "--metric",
        action="append",
        choices=[name for name, _label in ALL_METRICS],
        help="Restrict to specific metric(s) -- default: every core metric.",
    )
    parser.add_argument("--include-invalid", action="store_true")
    parser.add_argument("--allow-heterogeneous-controls", action="store_true")
    parser.add_argument("--name", required=True, help="Output basename under results/reports/ and results/figures/.")
    parser.add_argument(
        "--plot-metric",
        action="append",
        default=[],
        choices=[name for name, _label in ALL_METRICS],
        help="Also render a bar-chart figure for this metric across groups (pass more than once).",
    )
    parser.add_argument("--results-root", default="results")

    args = parser.parse_args()

    store = ExperimentResultStore(root=args.results_root)
    report_store = ReportStore(root=args.results_root)

    records = _load_records(store, args)

    try:
        report = aggregate_records(
            records,
            group_by=tuple(args.group_by),
            metrics=tuple(args.metric) if args.metric else None,
            include_invalid=args.include_invalid,
            allow_heterogeneous_controls=args.allow_heterogeneous_controls,
        )
    except HeterogeneousControlsError as error:
        print(f"error: {error}", file=sys.stderr)
        print("Pass --allow-heterogeneous-controls to aggregate anyway.", file=sys.stderr)
        return 1

    json_path = report_store.write_aggregation_report(report, args.name)
    markdown_path = report_store.write_markdown(
        render_aggregation_markdown(report, title=args.name.replace("-", " ")), args.name
    )

    print(f"Grouped by: {', '.join(report.group_by)}")
    print(f"Controls consistent: {report.controls_consistent}" + (f" (varies: {report.control_variance})" if not report.controls_consistent else ""))
    print(f"Groups: {len(report.groups)}  Source runs: {len(report.source_run_ids)}  Excluded invalid: {report.excluded_invalid_runs}")
    print(f"Report written to: {json_path}")
    print(f"                   {markdown_path}")

    for metric in args.plot_metric:
        figure_path = plot_metric_by_group(report, metric, report_store.figure_path(f"{args.name}-{metric}.png"))
        print(f"Figure written to: {figure_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
