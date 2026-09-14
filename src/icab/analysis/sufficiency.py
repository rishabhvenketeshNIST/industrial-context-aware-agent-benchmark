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
    #: Every run_id that fed this condition's scores -- traceability from
    #: a sufficiency/MSC conclusion back to the exact persisted
    #: ExperimentRecord(s) (results/raw/<run_id>.json) it rests on.
    run_ids: list[str] = []


class SufficiencyReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    use_case_id: str
    #: None when scoped to the whole use case; set when scoped to one
    #: Question (icab.questions) -- see `find_minimum_sufficient_context`'s
    #: own `question_id` parameter.
    question_id: str | None = None
    binding_scores: list[str]
    pass_threshold: float

    tested_conditions: list[_ConditionResult]

    #: The smallest-cardinality tested condition meeting every binding
    #: score's threshold -- None if NO tested condition met it. Kept for
    #: backward compatibility (e.g. icab.analysis.profile); when several
    #: conditions tie for smallest/incomparable, this is simply the
    #: first of `candidate_minimum_sufficient_contexts` (lexicographically
    #: smallest id) -- prefer that field when the full picture matters.
    minimum_sufficient_context_among_tested: str | None
    #: EVERY tested sufficient condition that is not a proper superset of
    #: another tested sufficient condition -- i.e. the minimal elements of
    #: the sufficient conditions under the DIMENSION-SUBSET partial order,
    #: not merely "smallest cardinality." Context combinations do not form
    #: a total order: two sufficient conditions of equal cardinality (or
    #: of different cardinality, if neither's dimensions are a subset of
    #: the other's) are INCOMPARABLE, and both are reported here rather
    #: than one being arbitrarily preferred. Empty when nothing tested met
    #: the threshold.
    candidate_minimum_sufficient_contexts: list[str] = []
    #: Explicit, honest label distinguishing this from a global claim --
    #: always present in the rendered report/profile.
    caveat: str = (
        "Minimum Sufficient Context Among Tested Conditions -- NOT a "
        "claim of global mathematical minimality. Only context "
        "combinations actually run are considered; an untested, "
        "smaller combination may or may not also be sufficient. Context "
        "combinations form a partial order (by dimension subset), not a "
        "total order -- see candidate_minimum_sufficient_contexts for "
        "every incomparable minimal candidate, not just one arbitrarily "
        "chosen among ties."
    )


def find_minimum_sufficient_context(
    records: list[ExperimentRecord],
    use_case: IndustrialUseCase,
    *,
    question_id: str | None = None,
) -> SufficiencyReport:
    """
    `question_id=None` (default): scoped to the whole use case, unchanged
    M13-C-era/ICAB-v2 behavior. Pass `question_id` to scope this SAME
    sufficiency/candidate-MSC determination to one Question
    (icab.questions) -- the ICAB question-bank direction's "MSC at the
    question level."
    """

    scoped = records_for_use_case(records, use_case.use_case_id, question_id=question_id)
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
                run_ids=sorted(r.run_id for r in combination_records),
            )
        )

    candidates = _minimal_sufficient_conditions(conditions)
    minimum = candidates[0] if candidates else None

    return SufficiencyReport(
        use_case_id=use_case.use_case_id,
        question_id=question_id,
        binding_scores=binding_scores,
        pass_threshold=threshold,
        tested_conditions=conditions,
        minimum_sufficient_context_among_tested=minimum,
        candidate_minimum_sufficient_contexts=candidates,
    )


def _minimal_sufficient_conditions(conditions: list[_ConditionResult]) -> list[str]:
    """
    Every sufficient (meets_threshold) tested condition whose dimensions
    are NOT a proper superset of another sufficient tested condition's
    dimensions -- the minimal elements of the sufficient set under the
    dimension-SUBSET partial order. Two sufficient conditions of equal
    cardinality are always incomparable (neither's dimensions can be a
    proper subset of the other's when they have the same size), so BOTH
    are always included -- this generalizes "smallest cardinality" to the
    partial order context combinations actually form, per the ICAB v2
    direction: "If two incomparable conditions have the same number of
    dimensions, do not arbitrarily choose one."
    """

    sufficient = [condition for condition in conditions if condition.meets_threshold]
    dimension_sets = {
        condition.context_combination_id: set(combination_for_id(condition.context_combination_id).dimensions)
        for condition in sufficient
    }

    minimal_ids = [
        condition_id
        for condition_id, dims in dimension_sets.items()
        if not any(
            other_dims < dims  # a strictly smaller sufficient condition's dimensions are a proper subset
            for other_id, other_dims in dimension_sets.items()
            if other_id != condition_id
        )
    ]

    return sorted(minimal_ids, key=lambda condition_id: (combination_for_id(condition_id).cardinality, condition_id))
