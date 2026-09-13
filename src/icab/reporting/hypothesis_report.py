"""
M12: a richer, still strictly descriptive report around one M11
`HypothesisTestResult` -- adds per-arm median/stdev/min/max (not just
mean), an explicit `controls_consistent` check over the specific records
used, and plain-language `limitations` derived from the data itself
(small sample size, a tie, an empty arm) rather than hard-coded per
hypothesis.

`HypothesisTestResult` (M11) itself is UNCHANGED and remains the
authoritative descriptive core -- this module only adds statistics and
narrative framing on top of it, never a significance test or a "proven"
verdict. See `icab.experiments.hypotheses` module docstring and
docs/research/hypotheses.md.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from icab.experiments.controls import CONTROL_FIELDS, HeterogeneousControlsError, control_variance
from icab.experiments.hypotheses import (
    HypothesisSpec,
    HypothesisTestResult,
    evaluate_hypothesis,
    is_usable_record,
)
from icab.experiments.models import ExperimentRecord

from .stats import SummaryStats, summarize

__all__ = ["HypothesisReport", "build_hypothesis_report"]

_MIN_SAMPLE_SIZE_FOR_ANY_INFERENCE = 5


class HypothesisReport(BaseModel):
    """
    `result` (the M11 core comparison) plus per-arm `SummaryStats` and
    explicit, data-derived `limitations` -- never a verdict, never a
    p-value.
    """

    model_config = ConfigDict(extra="forbid")

    result: HypothesisTestResult
    treatment_stats: SummaryStats
    control_stats: SummaryStats
    controls_consistent: bool
    control_variance: dict[str, list]
    limitations: list[str]


def _limitations(result: HypothesisTestResult, treatment: SummaryStats, control: SummaryStats) -> list[str]:
    notes = [
        "Descriptive comparison only -- not a significance test, and not "
        "proof or disproof of the hypothesis."
    ]

    if treatment.n == 0 or control.n == 0:
        notes.append(
            "One or both arms have no usable (VALID + COMPLETED) records -- "
            "no comparison is possible from the data supplied."
        )
        return notes

    smaller_n = min(treatment.n, control.n)
    if smaller_n < _MIN_SAMPLE_SIZE_FOR_ANY_INFERENCE:
        notes.append(
            f"Sample size is small (treatment n={treatment.n}, control n={control.n}) "
            "-- far too small for statistical inference. Treat this as a single (or a "
            "handful of) real observation(s), not a validated effect."
        )

    if result.mean_difference == 0:
        notes.append(
            "The observed difference is exactly zero (a tie) -- this is not evidence "
            "for OR against the hypothesis on this data."
        )

    return notes


def build_hypothesis_report(
    spec_or_result: HypothesisSpec | HypothesisTestResult,
    records: list[ExperimentRecord],
    *,
    allow_heterogeneous_controls: bool = False,
) -> HypothesisReport:
    """
    Build a `HypothesisReport` either from a `HypothesisSpec` (computes
    the underlying `HypothesisTestResult` via `evaluate_hypothesis` first)
    or an already-computed `HypothesisTestResult` (e.g. one loaded via
    `ExperimentResultStore.load_hypothesis_result`) plus the records that
    fed it, for the richer per-arm statistics.

    Raises `HeterogeneousControlsError` if the records actually used in
    either arm don't hold `CONTROL_FIELDS` constant, unless
    `allow_heterogeneous_controls=True` -- the same safeguard
    `aggregate_records`/`write_aggregate` enforce, checked here over just
    the arm-relevant records.
    """

    if isinstance(spec_or_result, HypothesisTestResult):
        result = spec_or_result
    else:
        result = evaluate_hypothesis(spec_or_result, records)

    treatment_stats = summarize(result.treatment_values)
    control_stats = summarize(result.control_values)

    arm_combinations = (*result.treatment_combinations, *result.control_combinations)
    arm_records = [
        record
        for record in records
        if is_usable_record(record) and record.config.architecture_combination_key in arm_combinations
    ]
    variance = control_variance(arm_records, CONTROL_FIELDS) if arm_records else {}
    if variance and not allow_heterogeneous_controls:
        raise HeterogeneousControlsError(
            f"Records feeding hypothesis {result.hypothesis.value} do not hold "
            f"controls constant: {variance}. Pass allow_heterogeneous_controls=True "
            "to report anyway -- see docs/research/experiment-plan.md."
        )

    return HypothesisReport(
        result=result,
        treatment_stats=treatment_stats,
        control_stats=control_stats,
        controls_consistent=not variance,
        control_variance=variance,
        limitations=_limitations(result, treatment_stats, control_stats),
    )
