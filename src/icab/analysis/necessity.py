"""
ICAB-CN: context necessity -- for a given industrial use case, which
context dimensions does removing appear to matter for?

This does NOT assert necessity from expert opinion. For each of the use
case's own `candidate_context` dimensions, it partitions the ACTUALLY
TESTED context-combination conditions (`icab.tasks.context_combinations`)
into "included this dimension" vs. "did not," and reports the difference
in a metric's mean between the two groups. A dimension with NO tested
combinations on one side of that partition gets `insufficient_evidence`
-- never a fabricated necessity claim about an untested condition.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from icab.experiments.models import ExperimentRecord
from icab.reporting.aggregation import aggregate_records
from icab.tasks.context_combinations import combination_for_id
from icab.tasks.context_dimensions import ContextDimension
from icab.usecases import IndustrialUseCase

from ._shared import records_for_use_case, tested_combination_ids

#: Minimum tested-run count on EACH side of a with/without partition
#: before a delta is reported at all -- below this, `insufficient_evidence`
#: is reported instead of a delta computed from too few observations to
#: mean anything.
_MIN_RUNS_PER_SIDE = 1


class DimensionNecessityFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dimension: ContextDimension
    metric: str

    tested_with_dimension: list[str]  # context_combination_ids that included it
    tested_without_dimension: list[str]  # context_combination_ids (within candidate_context) that omitted it

    mean_with: float | None
    mean_without: float | None
    #: mean_with - mean_without, when both sides have evidence -- a
    #: positive value means the tested conditions that included this
    #: dimension scored HIGHER on average; this is a descriptive
    #: comparison over the tested conditions, not a significance claim.
    delta: float | None

    n_with: int
    n_without: int

    #: "evidence" when both sides have >= _MIN_RUNS_PER_SIDE usable runs;
    #: "insufficient_evidence" otherwise -- e.g. every tested combination
    #: happened to include this dimension.
    evidence_status: str


class NecessityReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    use_case_id: str
    metric: str
    tested_combinations: list[str]
    total_runs_considered: int
    findings: list[DimensionNecessityFinding]


def analyze_context_necessity(
    records: list[ExperimentRecord],
    use_case: IndustrialUseCase,
    *,
    metric: str = "required_evidence_score",
) -> NecessityReport:
    scoped = records_for_use_case(records, use_case.use_case_id)
    tested = tested_combination_ids(scoped)

    findings: list[DimensionNecessityFinding] = []

    for dimension in use_case.candidate_context:
        with_ids = [cid for cid in tested if dimension in combination_for_id(cid).dimensions]
        without_ids = [cid for cid in tested if dimension not in combination_for_id(cid).dimensions]

        mean_with = mean_without = delta = None
        n_with = n_without = 0

        if with_ids:
            with_records = [r for r in scoped if r.config.context_combination_id in with_ids]
            n_with = len(with_records)
            report = aggregate_records(
                with_records, group_by=("use_case_id",), metrics=(metric,), allow_heterogeneous_controls=True
            )
            if report.groups:
                mean_with = report.groups[0].metrics[metric].mean

        if without_ids:
            without_records = [r for r in scoped if r.config.context_combination_id in without_ids]
            n_without = len(without_records)
            report = aggregate_records(
                without_records, group_by=("use_case_id",), metrics=(metric,), allow_heterogeneous_controls=True
            )
            if report.groups:
                mean_without = report.groups[0].metrics[metric].mean

        evidence_status = (
            "evidence"
            if (with_ids and without_ids and n_with >= _MIN_RUNS_PER_SIDE and n_without >= _MIN_RUNS_PER_SIDE
                and mean_with is not None and mean_without is not None)
            else "insufficient_evidence"
        )
        if evidence_status == "evidence":
            delta = mean_with - mean_without  # type: ignore[operator]

        findings.append(
            DimensionNecessityFinding(
                dimension=dimension,
                metric=metric,
                tested_with_dimension=with_ids,
                tested_without_dimension=without_ids,
                mean_with=mean_with,
                mean_without=mean_without,
                delta=delta,
                n_with=n_with,
                n_without=n_without,
                evidence_status=evidence_status,
            )
        )

    return NecessityReport(
        use_case_id=use_case.use_case_id,
        metric=metric,
        tested_combinations=tested,
        total_runs_considered=len(scoped),
        findings=findings,
    )
