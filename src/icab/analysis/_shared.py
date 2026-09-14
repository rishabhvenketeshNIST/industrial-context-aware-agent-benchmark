"""Shared, private helpers for icab.analysis -- not part of the public API."""

from __future__ import annotations

from icab.experiments.models import ExperimentRecord, ExperimentRunStatus, RunValidity
from icab.tasks.context_combinations import combination_for_id


def records_for_use_case(
    records: list[ExperimentRecord],
    use_case_id: str,
    *,
    question_id: str | None = None,
) -> list[ExperimentRecord]:
    """
    Every record whose `config.use_case_id` matches -- across whatever
    architectures/seeds/combinations were actually run. When
    `question_id` is given, further narrows to that one Question
    (icab.questions) -- the same scoping function serves necessity/
    sufficiency at BOTH the use-case level (question_id=None, the
    original M13-C-era behavior, unchanged) and the question level
    (icab.benchmark.levels' 3-tier ISA-95-benchmark direction).
    """

    scoped = [record for record in records if record.config.use_case_id == use_case_id]
    if question_id is not None:
        scoped = [record for record in scoped if record.config.question_id == question_id]
    return scoped


def usable(records: list[ExperimentRecord]) -> list[ExperimentRecord]:
    """VALID + COMPLETED only -- same rule `icab.experiments.hypotheses.is_usable_record` already uses."""

    return [
        record
        for record in records
        if record.validity == RunValidity.VALID and record.status == ExperimentRunStatus.COMPLETED
    ]


def tested_combination_ids(records: list[ExperimentRecord]) -> list[str]:
    """
    Every DISTINCT `context_combination_id` actually present in `records`
    -- ordered by cardinality then combination id, matching
    `icab.tasks.context_combinations`' own canonical ordering, NOT the
    full 127-combination space (only what was genuinely tested).
    """

    ids = {record.config.context_combination_id for record in records if record.config.context_combination_id}
    return sorted(ids, key=lambda combination_id: (combination_for_id(combination_id).cardinality, combination_id))


#: Phase 15 (repeated-run support): a fixed, documented, deterministic
#: rule for labeling how much weight a sample size can bear -- NEVER a
#: statistical significance/confidence-interval claim (n this small never
#: supports one). Shared by every icab.analysis module that reports a
#: mean over usable runs, so the same n is always described the same way.
def sample_size_label(n: int) -> str:
    if n <= 0:
        return "no_evidence"
    if n == 1:
        return "single_observation"
    if n < 5:
        return "tentative_small_n"
    return "repeated_empirical_result"
