"""
Command-line entry point for M12 hypothesis reports.

Like `scripts/generate_report.py`, operates ENTIRELY on already-persisted
`results/{raw,traces,evaluations}/` artifacts -- makes no simulator,
gateway, or LLM calls. Distinct from `scripts/run_hypothesis_experiment.py`
(M11), which actually RUNS a hypothesis's combinations; this script only
builds a `HypothesisReport` from runs that already exist on disk (e.g.
from a prior `run_hypothesis_experiment.py`/`run_experiment.py` call).

Usage::

    uv run python scripts/generate_hypothesis_report.py \\
        --hypothesis H3 \\
        --experiment-id m10-d4-combo-validation-v2 --experiment-id m11-h2-uns_historian_kg \\
        --name h3-report --plot

Writes `results/reports/<name>.json` (the full `HypothesisReport`),
`results/reports/<name>.md`, and (with `--plot`)
`results/figures/<name>.png`.
"""

from __future__ import annotations

import argparse
import sys

from icab.experiments import ExperimentResultStore
from icab.experiments.controls import HeterogeneousControlsError
from icab.experiments.hypotheses import HypothesisID, get_spec
from icab.reporting.hypothesis_report import build_hypothesis_report
from icab.reporting.markdown import render_hypothesis_markdown
from icab.reporting.plotting import plot_hypothesis_comparison
from icab.reporting.store import ReportStore


def _load_records(store: ExperimentResultStore, args: argparse.Namespace):
    if args.run_id:
        return [store.load_record(run_id) for run_id in args.run_id]

    all_run_ids = store.list_run_ids()
    if not all_run_ids:
        raise SystemExit("No persisted runs found under --results-root; nothing to report on.")

    records = [store.load_record(run_id) for run_id in all_run_ids]

    if args.experiment_id:
        wanted = set(args.experiment_id)
        records = [record for record in records if record.experiment_id in wanted]

    return records


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--hypothesis", required=True, choices=[h.value for h in HypothesisID])

    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--run-id", action="append", help="Explicit run_id(s) to consider.")
    selection.add_argument(
        "--experiment-id",
        action="append",
        help="Consider every persisted run whose experiment_id is one of these.",
    )
    selection.add_argument("--all", action="store_true", help="Consider every persisted run.")

    parser.add_argument("--allow-heterogeneous-controls", action="store_true")
    parser.add_argument("--name", required=True, help="Output basename under results/reports/ and results/figures/.")
    parser.add_argument("--plot", action="store_true", help="Also render a treatment-vs-control figure.")
    parser.add_argument("--results-root", default="results")

    args = parser.parse_args()

    store = ExperimentResultStore(root=args.results_root)
    report_store = ReportStore(root=args.results_root)

    records = _load_records(store, args)
    spec = get_spec(args.hypothesis)

    try:
        report = build_hypothesis_report(
            spec, records, allow_heterogeneous_controls=args.allow_heterogeneous_controls
        )
    except HeterogeneousControlsError as error:
        print(f"error: {error}", file=sys.stderr)
        print("Pass --allow-heterogeneous-controls to report anyway.", file=sys.stderr)
        return 1

    json_path = report_store.write_hypothesis_report(report, args.name)
    markdown_path = report_store.write_markdown(render_hypothesis_markdown(report), args.name)

    print(render_hypothesis_markdown(report))
    print(f"Report written to: {json_path}")
    print(f"                   {markdown_path}")

    if args.plot:
        figure_path = plot_hypothesis_comparison(report, report_store.figure_path(f"{args.name}.png"))
        print(f"Figure written to: {figure_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
