"""
ICAB-CC: context composition -- does combining context dimensions enable
what individual dimensions alone cannot, among the conditions actually
tested for a use case?

Purely descriptive: groups tested combinations by cardinality and
reports each cardinality's mean metric, plus which specific combination
scored highest/lowest among those tested -- no claim about combinations
never run.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from icab.experiments.models import ExperimentRecord
from icab.reporting.aggregation import aggregate_records
from icab.tasks.context_combinations import combination_for_id
from icab.usecases import IndustrialUseCase

from ._shared import records_for_use_case, tested_combination_ids


class CompositionFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    context_combination_id: str
    cardinality: int
    n_runs: int
    mean: float | None


class CompositionReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    use_case_id: str
    metric: str
    findings: list[CompositionFinding]
    #: The tested combination with the highest mean (ties broken by
    #: smallest cardinality, then combination id) -- None if nothing
    #: was tested.
    best_tested_combination: str | None


def analyze_context_composition(
    records: list[ExperimentRecord],
    use_case: IndustrialUseCase,
    *,
    metric: str = "conclusion_correctness_score",
) -> CompositionReport:
    scoped = records_for_use_case(records, use_case.use_case_id)
    tested = tested_combination_ids(scoped)

    findings: list[CompositionFinding] = []
    for combination_id in tested:
        combination_records = [r for r in scoped if r.config.context_combination_id == combination_id]
        report = aggregate_records(
            combination_records, group_by=("context_combination_id",), metrics=(metric,), allow_heterogeneous_controls=True
        )
        mean = report.groups[0].metrics[metric].mean if report.groups else None
        findings.append(
            CompositionFinding(
                context_combination_id=combination_id,
                cardinality=combination_for_id(combination_id).cardinality,
                n_runs=len(combination_records),
                mean=mean,
            )
        )

    scored = [finding for finding in findings if finding.mean is not None]
    best = (
        max(scored, key=lambda finding: (finding.mean, -finding.cardinality)).context_combination_id
        if scored
        else None
    )

    return CompositionReport(use_case_id=use_case.use_case_id, metric=metric, findings=findings, best_tested_combination=best)
