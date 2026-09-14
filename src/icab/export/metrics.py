"""
Campaign-level `metrics.json`, computed ONLY from an already-built list
of `CanonicalExecutionRecord`s (not from ICAB's internal
`ExperimentRecord`s directly) -- so the exact same numbers here are
reproducible by an external analyst re-computing them from the plain
`executions.jsonl`/`results.csv` this campaign also exports, with no
ICAB import. Every metric is a straightforward count/rate/mean over
fields the export schema already carries (`execution.success`,
`evaluation.correct`, `evaluation.answer_score`, `execution.latency_ms`,
`evaluation.failure_mode`) -- no new scientific metric is introduced.

Deliberately silent on anything beyond execution/evaluation bookkeeping:
this module does NOT decide "context X was necessary" or "architecture Y
is sufficient" -- those are independent-analysis conclusions
(icab.analysis.necessity/sufficiency), out of scope here by design (see
the ICAB export milestone's "keep ICAB analysis separate" principle).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from .schema import CanonicalExecutionRecord


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _rate(flags: list[bool]) -> float | None:
    return (sum(1 for f in flags if f) / len(flags)) if flags else None


def _group_summary(records: list[CanonicalExecutionRecord]) -> dict[str, Any]:
    scores = [r.evaluation.answer_score for r in records if r.evaluation.answer_score is not None]
    correctness = [r.evaluation.correct for r in records if r.evaluation.correct is not None]
    return {
        "n_executions": len(records),
        "n_scored": len(scores),
        "mean_answer_score": _mean(scores),
        "correctness_rate": _rate(correctness),
    }


def build_campaign_metrics(records: list[CanonicalExecutionRecord]) -> dict[str, Any]:
    """
    `records` should be every canonical record in ONE campaign export
    (one ISA-95 level's campaign, not mixed across campaigns/levels).
    """

    total = len(records)
    completed = [r for r in records if r.execution.success]
    failed = [r for r in records if not r.execution.success]

    all_scores = [r.evaluation.answer_score for r in records if r.evaluation.answer_score is not None]
    all_correct = [r.evaluation.correct for r in records if r.evaluation.correct is not None]

    by_question: dict[str, list[CanonicalExecutionRecord]] = defaultdict(list)
    by_use_case: dict[str, list[CanonicalExecutionRecord]] = defaultdict(list)
    by_category: dict[str, list[CanonicalExecutionRecord]] = defaultdict(list)
    by_answer_type: dict[str, list[CanonicalExecutionRecord]] = defaultdict(list)
    failure_mode_counts: dict[str, int] = defaultdict(int)
    latencies: list[float] = []

    for record in records:
        by_question[record.question.id].append(record)
        if record.question.use_case:
            by_use_case[record.question.use_case].append(record)
        if record.question.category:
            by_category[record.question.category].append(record)
        if record.question.expected_answer_type:
            by_answer_type[record.question.expected_answer_type].append(record)
        mode = record.evaluation.failure_mode or "none"
        failure_mode_counts[mode] += 1
        if record.execution.latency_ms is not None:
            latencies.append(record.execution.latency_ms)

    # macro = mean of each QUESTION's own mean answer_score; micro = mean
    # pooled over every individual execution -- same macro/micro
    # distinction icab.analysis.question_stats already uses, applied here
    # to the exported dataset directly.
    per_question_means = [m for m in (_mean([r.evaluation.answer_score for r in recs if r.evaluation.answer_score is not None]) for recs in by_question.values()) if m is not None]

    repetition_consistency = {
        qid: {
            "total_repetitions": len(recs),
            "successful_executions": sum(1 for r in recs if r.execution.success),
            "correct_repetitions": sum(1 for r in recs if r.evaluation.correct is True),
            "scored_repetitions": sum(1 for r in recs if r.evaluation.correct is not None),
            "consistency_ratio": _rate([r.evaluation.correct for r in recs if r.evaluation.correct is not None]),
        }
        for qid, recs in sorted(by_question.items())
    }

    sorted_latencies = sorted(latencies)

    return {
        "total_executions": total,
        "completed_executions": len(completed),
        "failed_executions": len(failed),
        "completion_rate": len(completed) / total if total else None,
        "correctness_rate": _rate(all_correct),
        "n_scored": len(all_scores),
        "macro_answer_score": _mean(per_question_means),
        "micro_answer_score": _mean(all_scores),
        "by_question": {qid: _group_summary(recs) for qid, recs in sorted(by_question.items())},
        "by_use_case": {uc: _group_summary(recs) for uc, recs in sorted(by_use_case.items())},
        "by_category": {cat: _group_summary(recs) for cat, recs in sorted(by_category.items())},
        "by_answer_type": {t: _group_summary(recs) for t, recs in sorted(by_answer_type.items())},
        "repetition_consistency": repetition_consistency,
        "failure_mode_counts": dict(sorted(failure_mode_counts.items())),
        "latency_ms_summary": {
            "n": len(sorted_latencies),
            "mean": _mean(sorted_latencies),
            "median": sorted_latencies[len(sorted_latencies) // 2] if sorted_latencies else None,
            "min": sorted_latencies[0] if sorted_latencies else None,
            "max": sorted_latencies[-1] if sorted_latencies else None,
        },
    }
