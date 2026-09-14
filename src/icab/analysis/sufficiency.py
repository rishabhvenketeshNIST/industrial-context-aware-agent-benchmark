"""
ICAB-CS: context sufficiency -- the minimum context combination, AMONG
THOSE ACTUALLY TESTED, that meets a use case's own success criteria.

Deliberately never called "the minimum sufficient context" without
qualification: a context combination that was never tested cannot be
ruled either sufficient or insufficient, so the result is always framed
as "Minimum Sufficient Context Among Tested Conditions" (see the ICAB v2
direction's explicit instruction not to claim global mathematical
minimality unless the experimental design actually establishes it -- it
does not here, since only a subset of the 127-combination space is ever
realistically tested).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from icab.experiments.models import ExperimentRecord
from icab.reporting.aggregation import aggregate_records
from icab.tasks.context_combinations import combination_for_id
from icab.usecases import IndustrialUseCase

from ._shared import records_for_use_case, tested_combination_ids


class _ConditionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    context_combination_id: str
    cardinality: int
    n_runs: int
    scores: dict[str, float | None]
    meets_threshold: bool


class SufficiencyReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    use_case_id: str
    binding_scores: list[str]
    pass_threshold: float

    tested_conditions: list[_ConditionResult]

    #: The smallest-cardinality tested condition meeting every binding
    #: score's threshold -- None if NO tested condition met it.
    minimum_sufficient_context_among_tested: str | None
    #: Explicit, honest label distinguishing this from a global claim --
    #: always present in the rendered report/profile.
    caveat: str = (
        "Minimum Sufficient Context Among Tested Conditions -- NOT a "
        "claim of global mathematical minimality. Only context "
        "combinations actually run are considered; an untested, "
        "smaller combination may or may not also be sufficient."
    )


def find_minimum_sufficient_context(
    records: list[ExperimentRecord],
    use_case: IndustrialUseCase,
) -> SufficiencyReport:
    scoped = records_for_use_case(records, use_case.use_case_id)
    tested = tested_combination_ids(scoped)
    binding_scores = list(use_case.success_criteria.binding_scores)
    threshold = use_case.success_criteria.pass_threshold

    conditions: list[_ConditionResult] = []
    for combination_id in tested:
        combination_records = [r for r in scoped if r.config.context_combination_id == combination_id]
        report = aggregate_records(
            combination_records,
            group_by=("context_combination_id",),
            metrics=tuple(binding_scores),
            allow_heterogeneous_controls=True,
        )
        scores: dict[str, float | None] = {}
        meets = True
        if report.groups:
            group = report.groups[0]
            for score_name in binding_scores:
                mean = group.metrics[score_name].mean
                scores[score_name] = mean
                if mean is None or mean < threshold:
                    meets = False
        else:
            meets = False
            scores = {name: None for name in binding_scores}

        conditions.append(
            _ConditionResult(
                context_combination_id=combination_id,
                cardinality=combination_for_id(combination_id).cardinality,
                n_runs=len(combination_records),
                scores=scores,
                meets_threshold=meets,
            )
        )

    sufficient = [condition for condition in conditions if condition.meets_threshold]
    minimum = min(sufficient, key=lambda condition: (condition.cardinality, condition.context_combination_id)).context_combination_id if sufficient else None

    return SufficiencyReport(
        use_case_id=use_case.use_case_id,
        binding_scores=binding_scores,
        pass_threshold=threshold,
        tested_conditions=conditions,
        minimum_sufficient_context_among_tested=minimum,
    )
