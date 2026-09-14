"""
Unit tests for `icab.export.metrics.build_campaign_metrics` -- computed
purely from already-built `CanonicalExecutionRecord`s, so these tests
never touch `ExperimentRecord`/ICAB internals directly.
"""

from __future__ import annotations

from icab.export.metrics import build_campaign_metrics
from icab.export.schema import (
    BenchmarkInfo,
    CanonicalExecutionRecord,
    ContextInfo,
    EvaluationInfo,
    EvidenceInfo,
    ExecutionInfo,
    GroundTruthInfo,
    Isa95Info,
    LLMInfo,
    QuestionInfo,
    TraceInfo,
)


def _record(execution_id: str, *, question_id: str, repetition: int, correct: bool | None, success: bool = True, latency_ms: float | None = 100.0) -> CanonicalExecutionRecord:
    return CanonicalExecutionRecord(
        execution_id=execution_id,
        benchmark=BenchmarkInfo(name="b", version="1.0.0", campaign_id="c"),
        isa95=Isa95Info(level="equipment"),
        question=QuestionInfo(id=question_id, text="q", use_case="uc-1", category="cat-1", difficulty="basic", expected_answer_type="numeric_value", tags=["cat-1"], provenance="p"),
        ground_truth=GroundTruthInfo(answer="42", expected_answer_type="numeric_value", root_cause_disturbance=None, affected_measurements=[], affected_equipment=[], expected_relationships=[], expected_evidence=[], source="s", explanation="42"),
        llm=LLMInfo(model="m", agent="llm", answer="42"),
        execution=ExecutionInfo(repetition=repetition, repetition_mode="exact", scenario="s1", architecture="historian", timestamp_started="t0", timestamp_completed="t1", latency_ms=latency_ms, success=success),
        context=ContextInfo(hypothesized_required_dimensions=[], available_dimensions=[], context_acquired=[], context_consumed=[], context_retrieval_events=0),
        evidence=EvidenceInfo(items=[], sources=[]),
        trace=TraceInfo(tool_calls=[], retrievals=[], errors=[]),
        evaluation=EvaluationInfo(
            correct=correct,
            answer_score=1.0 if correct else (0.0 if correct is False else None),
            canonical_id_score=1.0,
            evidence_score=1.0,
            failure_mode=None if correct else "reasoning_failure",
            evaluation_details=None,
        ),
    )


class TestBasicCounts:
    def test_completion_and_correctness_rates(self):
        records = [
            _record("r1", question_id="q1", repetition=1, correct=True),
            _record("r2", question_id="q1", repetition=2, correct=True),
            _record("r3", question_id="q1", repetition=3, correct=False),
            _record("r4", question_id="q2", repetition=1, correct=None, success=False),
        ]

        metrics = build_campaign_metrics(records)

        assert metrics["total_executions"] == 4
        assert metrics["completed_executions"] == 3
        assert metrics["failed_executions"] == 1
        assert metrics["completion_rate"] == 0.75
        assert metrics["correctness_rate"] == 2 / 3  # of the 3 scored (non-null) records

    def test_repetition_consistency_per_question(self):
        records = [
            _record("r1", question_id="q1", repetition=1, correct=True),
            _record("r2", question_id="q1", repetition=2, correct=True),
            _record("r3", question_id="q1", repetition=3, correct=False),
        ]

        metrics = build_campaign_metrics(records)

        q1 = metrics["repetition_consistency"]["q1"]
        assert q1["total_repetitions"] == 3
        assert q1["correct_repetitions"] == 2
        assert q1["consistency_ratio"] == 2 / 3

    def test_failure_mode_counts_include_none_for_successes(self):
        records = [
            _record("r1", question_id="q1", repetition=1, correct=True),
            _record("r2", question_id="q1", repetition=2, correct=False),
        ]

        metrics = build_campaign_metrics(records)

        assert metrics["failure_mode_counts"]["none"] == 1
        assert metrics["failure_mode_counts"]["reasoning_failure"] == 1

    def test_empty_campaign_never_divides_by_zero(self):
        metrics = build_campaign_metrics([])
        assert metrics["total_executions"] == 0
        assert metrics["completion_rate"] is None
        assert metrics["correctness_rate"] is None
        assert metrics["latency_ms_summary"]["mean"] is None

    def test_latency_summary(self):
        records = [
            _record("r1", question_id="q1", repetition=1, correct=True, latency_ms=100.0),
            _record("r2", question_id="q1", repetition=2, correct=True, latency_ms=300.0),
        ]
        metrics = build_campaign_metrics(records)
        assert metrics["latency_ms_summary"]["mean"] == 200.0
        assert metrics["latency_ms_summary"]["min"] == 100.0
        assert metrics["latency_ms_summary"]["max"] == 300.0

    def test_does_not_invent_a_correctness_rate_when_nothing_was_scored(self):
        records = [_record("r1", question_id="q1", repetition=1, correct=None, success=False)]
        metrics = build_campaign_metrics(records)
        assert metrics["correctness_rate"] is None  # never fabricated as 0.0
