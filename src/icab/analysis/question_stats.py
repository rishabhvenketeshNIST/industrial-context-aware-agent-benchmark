"""
ICAB question-bank statistics: Question -> Use Case -> ISA-95 Benchmark
aggregation, with BOTH macro-average (mean of each question's own mean --
an easy question with many repetitions can never drown out a hard
question with few) and micro-average (mean pooled over every individual
run) reported side by side, per the explicit "do not allow easy
questions to completely hide difficult questions" / "preserve question-
level results even when aggregating" direction.

Every function here is a thin wrapper over the EXISTING
`icab.reporting.aggregation.aggregate_records` (grouping/statistics) and
`icab.analysis.failure_taxonomy`/`.discoverability` (per-run
classification) -- no new score, no new statistical method.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from icab.experiments.models import ExperimentRecord
from icab.reporting.aggregation import aggregate_records
from icab.reporting.metrics import EFFICIENCY_METRICS

from ._shared import sample_size_label
from .discoverability import discoverability_breakdown
from .failure_taxonomy import classify_failures


class QuestionStats(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: str
    use_case_id: str
    metric: str

    n_repetitions: int
    n_usable: int
    success_rate: float | None  # fraction of usable runs with metric >= 1.0 (unchanged pass_threshold semantics live at the sufficiency layer; this is a simple per-run rate)
    mean: float | None
    median: float | None
    stdev: float | None
    sample_size_label: str

    failure_breakdown: dict[str, int]
    discoverability_breakdown: dict[str, int]
    #: {efficiency-metric-name: mean} -- tool_call_count/latency/context
    #: acquired-consumed, whatever icab.reporting.metrics.EFFICIENCY_METRICS
    #: already tracks, reused as-is.
    efficiency: dict[str, float | None]

    run_ids: list[str]


class UseCaseQuestionStats(BaseModel):
    """Every question's own stats, PRESERVED (never collapsed away), plus the use case's macro/micro rollup."""

    model_config = ConfigDict(extra="forbid")

    use_case_id: str
    metric: str
    n_questions: int
    #: Mean of each question's own mean -- an easy, heavily-repeated
    #: question cannot outweigh a hard, thinly-tested one.
    macro_average: float | None
    #: Mean pooled over every individual run across every question --
    #: the traditional, repetition-weighted average.
    micro_average: float | None
    questions: list[QuestionStats]


class BenchmarkLevelStats(BaseModel):
    """Every use case's own rollup, PRESERVED, plus the whole ISA-95-level benchmark's macro/micro rollup."""

    model_config = ConfigDict(extra="forbid")

    isa95_level: str
    metric: str
    n_use_cases: int
    n_questions: int
    macro_average: float | None  # mean of each USE CASE's own macro_average
    micro_average: float | None  # mean pooled over every individual run at this level
    use_cases: list[UseCaseQuestionStats]


def _metric_values(records: list[ExperimentRecord], metric: str) -> list[float]:
    from icab.experiments.hypotheses import is_usable_record, metric_value

    values = []
    for record in records:
        if not is_usable_record(record):
            continue
        value = metric_value(record, metric)
        if value is not None:
            values.append(value)
    return values


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def question_stats(
    records: list[ExperimentRecord],
    *,
    question_id: str,
    use_case_id: str,
    metric: str = "required_evidence_score",
) -> QuestionStats:
    scoped = [r for r in records if r.config.question_id == question_id]
    values = _metric_values(scoped, metric)

    efficiency_names = tuple(name for name, _label in EFFICIENCY_METRICS)
    efficiency: dict[str, float | None] = {}
    if scoped:
        report = aggregate_records(scoped, group_by=("question_id",), metrics=efficiency_names, allow_heterogeneous_controls=True)
        if report.groups:
            efficiency = {name: report.groups[0].metrics[name].mean for name in efficiency_names}
    else:
        efficiency = {name: None for name in efficiency_names}

    success_rate = (sum(1 for v in values if v >= 1.0) / len(values)) if values else None
    mean = _mean(values)
    median = sorted(values)[len(values) // 2] if values else None
    stdev = None
    if len(values) >= 2:
        variance = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
        stdev = variance**0.5

    return QuestionStats(
        question_id=question_id,
        use_case_id=use_case_id,
        metric=metric,
        n_repetitions=len(scoped),
        n_usable=len(values),
        success_rate=success_rate,
        mean=mean,
        median=median,
        stdev=stdev,
        sample_size_label=sample_size_label(len(values)),
        failure_breakdown=_count_by(classify_failures(scoped), key="category"),
        discoverability_breakdown=discoverability_breakdown(scoped),
        efficiency=efficiency,
        run_ids=sorted(r.run_id for r in scoped),
    )


def use_case_question_stats(
    records: list[ExperimentRecord],
    *,
    use_case_id: str,
    question_ids: list[str],
    metric: str = "required_evidence_score",
) -> UseCaseQuestionStats:
    scoped = [r for r in records if r.config.use_case_id == use_case_id]

    per_question = [
        question_stats(scoped, question_id=qid, use_case_id=use_case_id, metric=metric)
        for qid in sorted(question_ids)
    ]
    question_means = [q.mean for q in per_question if q.mean is not None]
    macro = _mean(question_means)
    micro = _mean(_metric_values(scoped, metric))

    return UseCaseQuestionStats(
        use_case_id=use_case_id,
        metric=metric,
        n_questions=len(per_question),
        macro_average=macro,
        micro_average=micro,
        questions=per_question,
    )


def benchmark_level_stats(
    records: list[ExperimentRecord],
    *,
    isa95_level: str,
    use_case_ids: list[str],
    question_ids_by_use_case: dict[str, list[str]],
    metric: str = "required_evidence_score",
) -> BenchmarkLevelStats:
    level_records = [r for r in records if r.config.isa95_level == isa95_level]

    per_use_case = [
        use_case_question_stats(
            level_records, use_case_id=uc_id, question_ids=question_ids_by_use_case.get(uc_id, []), metric=metric
        )
        for uc_id in sorted(use_case_ids)
    ]
    use_case_macros = [uc.macro_average for uc in per_use_case if uc.macro_average is not None]
    macro = _mean(use_case_macros)
    micro = _mean(_metric_values(level_records, metric))

    return BenchmarkLevelStats(
        isa95_level=isa95_level,
        metric=metric,
        n_use_cases=len(per_use_case),
        n_questions=sum(uc.n_questions for uc in per_use_case),
        macro_average=macro,
        micro_average=micro,
        use_cases=per_use_case,
    )


def _count_by(classifications: list, *, key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in classifications:
        value = getattr(item, key)
        counts[value] = counts.get(value, 0) + 1
    return counts
