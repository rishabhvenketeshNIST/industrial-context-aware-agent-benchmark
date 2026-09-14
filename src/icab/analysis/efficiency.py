"""
ICAB-CE: context efficiency -- for a use case, how much tool usage/
context volume did each TESTED condition actually cost, using the
EXISTING efficiency metrics (`icab.reporting.metrics.EFFICIENCY_METRICS`)
-- no new measure invented, just grouped by context combination/
architecture instead of by architecture alone.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from icab.experiments.models import ExperimentRecord
from icab.reporting.aggregation import aggregate_records
from icab.reporting.metrics import EFFICIENCY_METRICS
from icab.usecases import IndustrialUseCase

from ._shared import records_for_use_case


class EfficiencyReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    use_case_id: str
    group_by: tuple[str, ...]
    #: group_key (as rendered by aggregate_records) -> {metric: mean}
    groups: list[dict]


def analyze_context_efficiency(
    records: list[ExperimentRecord],
    use_case: IndustrialUseCase,
    *,
    group_by: tuple[str, ...] = ("context_combination_id", "architecture"),
) -> EfficiencyReport:
    scoped = records_for_use_case(records, use_case.use_case_id)
    metric_names = tuple(name for name, _label in EFFICIENCY_METRICS)

    if not scoped:
        return EfficiencyReport(use_case_id=use_case.use_case_id, group_by=group_by, groups=[])

    report = aggregate_records(scoped, group_by=group_by, metrics=metric_names, allow_heterogeneous_controls=True)

    groups = [
        {
            "group_key": group.group_key,
            "n_runs": group.n_runs,
            "metrics": {name: group.metrics[name].mean for name in metric_names},
        }
        for group in report.groups
    ]

    return EfficiencyReport(use_case_id=use_case.use_case_id, group_by=group_by, groups=groups)
