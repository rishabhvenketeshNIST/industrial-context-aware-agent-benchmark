"""
M12: reproducible plotting utilities over already-computed `AggregationReport`/
`HypothesisReport` objects -- computes no new numbers itself (every value
plotted comes straight from the report passed in) and asserts no
conclusion in a title/label beyond the metric/dimension names and the
hypothesis's own statement text (which is data, not a verdict this module
adds). Kept separate from `icab.experiments` (benchmark execution) and
from `icab.reporting.aggregation` (the actual analysis) on purpose.

Uses matplotlib's non-interactive "Agg" backend so this works headless
(CI, no display) -- set before any other matplotlib import.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

from pathlib import Path  # noqa: E402

import matplotlib.pyplot as plt  # noqa: E402

from .aggregation import AggregationReport  # noqa: E402
from .hypothesis_report import HypothesisReport  # noqa: E402
from .metrics import ALL_METRICS  # noqa: E402

_METRIC_LABELS: dict[str, str] = dict(ALL_METRICS)


def _group_label(group_key: dict) -> str:
    # A single group_by dimension: just the value (the dimension name is
    # already in the plot title/axis label, no need to repeat it per bar).
    if len(group_key) == 1:
        return str(next(iter(group_key.values())))
    return ", ".join(f"{k}={v}" for k, v in group_key.items())


def plot_metric_by_group(
    report: AggregationReport,
    metric: str,
    output_path: str | Path,
) -> Path:
    """Bar chart of one metric's mean (error bars: stdev, where n>=2) across every group in `report`."""

    output_path = Path(output_path)
    label = _METRIC_LABELS.get(metric, metric)

    groups = [group for group in report.groups if metric in group.metrics]
    labels = [_group_label(group.group_key) for group in groups]
    means = [group.metrics[metric].mean for group in groups]
    errors = [group.metrics[metric].stdev or 0.0 for group in groups]
    ns = [group.metrics[metric].n for group in groups]

    fig, ax = plt.subplots(figsize=(max(4.5, 1.6 * len(groups)), 4.5))
    positions = range(len(groups))
    bar_heights = [m if m is not None else 0 for m in means]
    ax.bar(positions, bar_heights, yerr=errors, capsize=4)
    ax.set_xticks(list(positions))
    ax.set_xticklabels(labels, rotation=20, ha="right", fontsize=9)
    ax.set_ylabel(label)
    ax.set_title(f"{label} by {', '.join(report.group_by)}")
    top = max([h + e for h, e in zip(bar_heights, errors, strict=True)] + [0]) or 1.0
    ax.set_ylim(0, top * 1.15)
    for position, n, height, error in zip(positions, ns, bar_heights, errors, strict=True):
        ax.annotate(f"n={n}", (position, height + error), textcoords="offset points", xytext=(0, 4), ha="center", fontsize=8)
    fig.tight_layout()
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)

    return output_path


def plot_effectiveness_vs_efficiency(
    report: AggregationReport,
    effectiveness_metric: str,
    efficiency_metric: str,
    output_path: str | Path,
) -> Path:
    """Scatter of one effectiveness metric against one efficiency metric, one point per group."""

    output_path = Path(output_path)
    x_label = _METRIC_LABELS.get(efficiency_metric, efficiency_metric)
    y_label = _METRIC_LABELS.get(effectiveness_metric, effectiveness_metric)

    groups = [
        group
        for group in report.groups
        if effectiveness_metric in group.metrics and efficiency_metric in group.metrics
    ]

    fig, ax = plt.subplots(figsize=(6, 5))
    for group in groups:
        x = group.metrics[efficiency_metric].mean
        y = group.metrics[effectiveness_metric].mean
        if x is None or y is None:
            continue
        ax.scatter(x, y)
        ax.annotate(_group_label(group.group_key), (x, y), fontsize=7, xytext=(4, 4), textcoords="offset points")

    ax.set_xlabel(x_label)
    ax.set_ylabel(y_label)
    ax.set_title(f"{y_label} vs {x_label}")
    fig.tight_layout()
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)

    return output_path


def plot_hypothesis_comparison(report: HypothesisReport, output_path: str | Path) -> Path:
    """Bar chart of treatment vs control mean (error bars: stdev where n>=2) for one hypothesis's metric."""

    output_path = Path(output_path)
    result = report.result
    label = _METRIC_LABELS.get(result.metric, result.metric)

    arms = ["+".join(result.treatment_combinations), "+".join(result.control_combinations)]
    means = [report.treatment_stats.mean, report.control_stats.mean]
    errors = [report.treatment_stats.stdev or 0.0, report.control_stats.stdev or 0.0]
    ns = [report.treatment_stats.n, report.control_stats.n]
    bar_heights = [m if m is not None else 0 for m in means]

    fig, ax = plt.subplots(figsize=(5.5, 4.5))
    positions = range(len(arms))
    ax.bar(positions, bar_heights, yerr=errors, capsize=4)
    ax.set_xticks(list(positions))
    ax.set_xticklabels(arms, fontsize=9)
    ax.set_ylabel(label)
    ax.set_title(f"{result.hypothesis.value}: {label}")
    top = max([h + e for h, e in zip(bar_heights, errors, strict=True)] + [0]) or 1.0
    ax.set_ylim(0, top * 1.15)
    for position, n, height, error in zip(positions, ns, bar_heights, errors, strict=True):
        ax.annotate(f"n={n}", (position, height + error), textcoords="offset points", xytext=(0, 4), ha="center", fontsize=8)
    fig.tight_layout()
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)

    return output_path
