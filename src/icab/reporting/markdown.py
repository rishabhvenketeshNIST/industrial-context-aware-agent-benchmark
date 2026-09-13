"""
M12: renders `AggregationReport`/`HypothesisReport` as human-readable
Markdown. Purely a text-formatting layer over already-computed reports --
computes nothing itself, so it can't introduce a different number than
the JSON/CSV/figures derived from the same report.
"""

from __future__ import annotations

from .aggregation import AggregationReport, GroupSummary
from .hypothesis_report import HypothesisReport
from .metrics import ALL_METRICS, EFFECTIVENESS_METRICS
from .stats import SummaryStats

_METRIC_LABELS: dict[str, str] = dict(ALL_METRICS)
_EFFECTIVENESS_NAMES: frozenset[str] = frozenset(name for name, _label in EFFECTIVENESS_METRICS)


def _fmt(value: float | None, digits: int = 3) -> str:
    if value is None:
        return "n/a"
    # Large values (latency ms, token counts) read better with thousands
    # separators than in general/scientific notation; small ones (scores,
    # ratios) keep significant-figure formatting.
    if abs(value) >= 1000:
        return f"{value:,.0f}"
    return f"{value:.{digits}g}"


def _stats_row(metric: str, stats: SummaryStats) -> str:
    label = _METRIC_LABELS.get(metric, metric)
    return (
        f"| {label} | {stats.n} | {_fmt(stats.mean)} | {_fmt(stats.median)} | "
        f"{_fmt(stats.stdev)} | {_fmt(stats.minimum)} | {_fmt(stats.maximum)} |"
    )


_METRICS_TABLE_HEADER = (
    "| Metric | n | Mean | Median | Stdev | Min | Max |\n"
    "|---|---|---|---|---|---|---|"
)


def _group_heading(group: GroupSummary) -> str:
    return ", ".join(f"{key}={value}" for key, value in group.group_key.items())


def render_aggregation_markdown(report: AggregationReport, *, title: str = "Aggregation report") -> str:
    lines = [
        f"# {title}",
        "",
        f"- **Grouped by**: {', '.join(report.group_by)}",
        f"- **Held constant**: {', '.join(report.hold_constant) or '(none)'}",
        f"- **Controls consistent**: {report.controls_consistent}"
        + ("" if report.controls_consistent else f" -- varies: {report.control_variance}"),
        f"- **Invalid runs included**: {report.include_invalid} "
        f"({report.excluded_invalid_runs} excluded from metrics)",
        f"- **Source runs considered**: {len(report.source_run_ids)}",
        "",
        "Computed entirely from persisted `results/{raw,traces,evaluations}/` "
        "artifacts -- no simulator, gateway, or LLM calls were made to produce "
        "this report. This is a benchmark-measurement summary "
        "(mean/median/stdev/min/max over recorded metrics), not a statistical "
        "inference about any hypothesis.",
        "",
    ]

    for group in report.groups:
        lines.append(f"## {_group_heading(group) or '(all runs)'}")
        lines.append("")
        lines.append(
            f"- runs: {group.n_runs} (completed={group.n_completed}, failed={group.n_failed}, "
            f"valid={group.n_valid}, legacy_control_only={group.n_legacy_control_only})"
        )
        lines.append(f"- run_ids: {', '.join(group.run_ids)}")
        lines.append("")

        effectiveness = [m for m in group.metrics if m in _EFFECTIVENESS_NAMES]
        efficiency = [m for m in group.metrics if m not in _EFFECTIVENESS_NAMES]

        lines.append("**Effectiveness**")
        lines.append("")
        lines.append(_METRICS_TABLE_HEADER)
        for metric in effectiveness:
            lines.append(_stats_row(metric, group.metrics[metric]))
        lines.append("")

        lines.append("**Efficiency**")
        lines.append("")
        lines.append(_METRICS_TABLE_HEADER)
        for metric in efficiency:
            lines.append(_stats_row(metric, group.metrics[metric]))
        lines.append("")

    return "\n".join(lines)


def render_hypothesis_markdown(report: HypothesisReport) -> str:
    result = report.result

    lines = [
        f"# {result.hypothesis.value}: {result.statement}",
        "",
        f"- **Metric**: {result.metric} (higher supports H: {result.higher_is_better})",
        f"- **Treatment**: {'+'.join(result.treatment_combinations)}",
        f"- **Control**: {'+'.join(result.control_combinations)}",
        f"- **Controls consistent across arm records**: {report.controls_consistent}"
        + ("" if report.controls_consistent else f" -- varies: {report.control_variance}"),
        "",
        _METRICS_TABLE_HEADER,
        _stats_row_named("Treatment", report.treatment_stats),
        _stats_row_named("Control", report.control_stats),
        "",
        f"- **Observed difference (treatment - control)**: {_fmt(result.mean_difference)}",
        f"- **Direction supports hypothesis**: {result.direction_supports_hypothesis}",
        f"- **Runs**: treatment n={len(result.treatment_run_ids)} ({', '.join(result.treatment_run_ids) or '(none)'}), "
        f"control n={len(result.control_run_ids)} ({', '.join(result.control_run_ids) or '(none)'})",
        "",
        "## Limitations",
        "",
    ]
    lines.extend(f"- {note}" for note in report.limitations)
    lines.append("")
    lines.append(f"> {result.caveat}")

    return "\n".join(lines)


def _stats_row_named(name: str, stats: SummaryStats) -> str:
    return (
        f"| {name} | {stats.n} | {_fmt(stats.mean)} | {_fmt(stats.median)} | "
        f"{_fmt(stats.stdev)} | {_fmt(stats.minimum)} | {_fmt(stats.maximum)} |"
    )
