"""
Unit tests for icab.benchmark.completeness -- the Sections 19-20
3,000-execution invariant checker and completeness report.
"""

from __future__ import annotations

from datetime import UTC, datetime

from icab.benchmark.completeness import (
    TARGET_EXECUTIONS_PER_LEVEL,
    TARGET_QUESTIONS_PER_LEVEL,
    TARGET_REPETITIONS_PER_QUESTION,
    TARGET_TOTAL_EXECUTIONS,
    SuiteCompletenessReport,
    check_level_completeness,
)
from icab.experiments.models import AgentType, ExperimentConfig, ExperimentRecord, ExperimentRunStatus, RunValidity


class _FakeQuestionRegistry:
    def __init__(self, ids: list[str]) -> None:
        self._ids = ids

    def list_ids(self) -> list[str]:
        return self._ids


def _record(run_id: str, *, question_id: str, instance_id: str, repetition: int, isa95_level: str = "equipment", status=ExperimentRunStatus.COMPLETED) -> ExperimentRecord:
    now = datetime.now(UTC)
    return ExperimentRecord(
        run_id=run_id,
        experiment_id="campaign-1",
        config=ExperimentConfig(
            scenario_id="d1_reactor_pressure_reading",
            isa95_level=isa95_level,
            question_id=question_id,
            question_instance_id=instance_id,
            repetition=repetition,
            architectures=["historian"],
            agent_type=AgentType.LLM,
        ),
        scenario_difficulty="D1",
        simulation_seed=1,
        started_at=now,
        completed_at=now,
        status=status,
        validity=RunValidity.VALID,
        trace_event_count=3,
    )


class TestTargets:
    def test_target_math(self):
        assert TARGET_QUESTIONS_PER_LEVEL == 50
        assert TARGET_REPETITIONS_PER_QUESTION == 10
        assert TARGET_EXECUTIONS_PER_LEVEL == 500
        assert TARGET_TOTAL_EXECUTIONS == 3000


class TestCheckLevelCompleteness:
    def test_a_question_with_all_ten_repetitions_is_complete(self):
        registry = _FakeQuestionRegistry(["Q-1"] + [f"Q-{i}" for i in range(2, 51)])
        records = [_record(f"r{i}", question_id="Q-1", instance_id="inst-1", repetition=i) for i in range(1, 11)]

        report = check_level_completeness("equipment", registry, records)

        q1 = next(q for q in report.questions if q.question_id == "Q-1")
        assert q1.repetitions_completed == 10
        assert q1.complete is True
        assert report.is_complete is False  # the other 49 questions have zero repetitions

    def test_fewer_than_ten_repetitions_is_incomplete(self):
        registry = _FakeQuestionRegistry(["Q-1"])
        records = [_record(f"r{i}", question_id="Q-1", instance_id="inst-1", repetition=i) for i in range(1, 6)]  # only 5

        report = check_level_completeness("equipment", registry, records)

        q1 = report.questions[0]
        assert q1.repetitions_completed == 5
        assert q1.complete is False
        assert "5/10" in q1.issues[0]

    def test_fewer_than_fifty_questions_in_the_bank_is_flagged(self):
        registry = _FakeQuestionRegistry(["Q-1", "Q-2"])  # only 2, not 50

        report = check_level_completeness("equipment", registry, [])

        assert any("expected exactly 50" in issue for issue in report.issues)
        assert report.is_complete is False

    def test_wrong_isa95_level_contamination_is_detected(self):
        registry = _FakeQuestionRegistry([f"Q-{i}" for i in range(1, 51)])
        contaminated = _record("bad-1", question_id="Q-1", instance_id="inst-1", repetition=1, isa95_level="process_cell")

        report = check_level_completeness("equipment", registry, [contaminated])

        assert any("mismatched isa95_level" in issue for issue in report.issues)
        assert report.is_complete is False
        # The contaminated record must not be counted toward THIS level's executions.
        assert report.n_executions_actual == 0

    def test_failed_runs_never_count_toward_completed_repetitions(self):
        registry = _FakeQuestionRegistry(["Q-1"])
        records = [_record(f"r{i}", question_id="Q-1", instance_id="inst-1", repetition=i, status=ExperimentRunStatus.FAILED) for i in range(1, 11)]

        report = check_level_completeness("equipment", registry, records)

        q1 = report.questions[0]
        assert q1.repetitions_completed == 0
        assert q1.complete is False

    def test_duplicate_repetition_indices_are_flagged(self):
        registry = _FakeQuestionRegistry(["Q-1"])
        records = [
            _record("r1", question_id="Q-1", instance_id="inst-1", repetition=1),
            _record("r1-dup", question_id="Q-1", instance_id="inst-1", repetition=1),  # same instance+repetition index, run twice
        ]

        report = check_level_completeness("equipment", registry, records)

        assert any("duplicate" in issue.lower() for issue in report.issues)

    def test_a_fully_complete_level_reports_true(self):
        ids = [f"Q-{i}" for i in range(1, 51)]
        registry = _FakeQuestionRegistry(ids)
        records = [
            _record(f"r-{qid}-{rep}", question_id=qid, instance_id=f"inst-{qid}", repetition=rep)
            for qid in ids
            for rep in range(1, 11)
        ]

        report = check_level_completeness("equipment", registry, records)

        assert report.n_executions_successful == 500
        assert all(q.complete for q in report.questions)
        assert not report.issues
        assert report.is_complete is True
        assert report.completion_fraction == 1.0


class TestSuiteCompletenessReport:
    def test_never_complete_with_fewer_than_six_levels(self):
        registry = _FakeQuestionRegistry([f"Q-{i}" for i in range(1, 51)])
        level_report = check_level_completeness("equipment", registry, [])
        suite = SuiteCompletenessReport(levels=[level_report])

        assert suite.is_complete is False  # only 1 of 6 levels present

    def test_total_executions_actual_sums_across_levels(self):
        registry = _FakeQuestionRegistry(["Q-1"])
        records_a = [_record("a1", question_id="Q-1", instance_id="i1", repetition=1, isa95_level="equipment")]
        records_b = [_record("b1", question_id="Q-1", instance_id="i1", repetition=1, isa95_level="area")]

        suite = SuiteCompletenessReport(
            levels=[
                check_level_completeness("equipment", registry, records_a),
                check_level_completeness("area", registry, records_b),
            ]
        )

        assert suite.total_executions_actual == 2
