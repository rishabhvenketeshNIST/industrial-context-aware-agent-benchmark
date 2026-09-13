"""
Shared summary-statistics helper (M12) -- one place computing mean/
median/stdev/min/max/n over a list of metric values, used by both
`icab.reporting.aggregation` (per-group, per-metric) and
`icab.reporting.hypothesis_report` (per-arm), so the two report kinds
never silently disagree about how "average"/"spread" are computed.
"""

from __future__ import annotations

from statistics import mean, median, stdev

from pydantic import BaseModel, ConfigDict


class SummaryStats(BaseModel):
    """
    Descriptive statistics over one list of numeric values. `stdev` is the
    SAMPLE standard deviation (`statistics.stdev`) and is None (not 0.0)
    when fewer than two values are available -- a single observation has
    no meaningful spread, and reporting 0.0 would misleadingly suggest
    "measured and found to be zero variance" rather than "not enough data
    to say."
    """

    model_config = ConfigDict(extra="forbid")

    n: int
    mean: float | None = None
    median: float | None = None
    stdev: float | None = None
    minimum: float | None = None
    maximum: float | None = None


def summarize(values: list[float]) -> SummaryStats:
    if not values:
        return SummaryStats(n=0)

    return SummaryStats(
        n=len(values),
        mean=mean(values),
        median=median(values),
        stdev=stdev(values) if len(values) >= 2 else None,
        minimum=min(values),
        maximum=max(values),
    )
