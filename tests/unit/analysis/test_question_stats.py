"""Unit tests for icab.analysis.question_stats -- Question -> Use Case -> ISA-95 Benchmark macro/micro aggregation."""

from __future__ import annotations

from icab.analysis import benchmark_level_stats, question_stats, use_case_question_stats
from icab.experiments.models import ExperimentRunStatus

from _v2_factories import make_evaluation, make_v2_record


def _record(run_id, *, question_id, use_case_id="eq-value-and-relationship-combination", isa95_level="equipment", required_evidence_score=1.0, status=ExperimentRunStatus.COMPLETED):
    record = make_v2_record(
        run_id,
        use_case_id=use_case_id,
        isa95_level=isa95_level,
        context_combination_id="C3+C5",
        architectures=["historian", "knowledge_graph"],
        status=status,
        evaluation=make_evaluation(required_evidence_score=required_evidence_score) if status == ExperimentRunStatus.COMPLETED else None,
        error=None if status == ExperimentRunStatus.COMPLETED else "boom",
    )
    return record.model_copy(update={"config": record.config.model_copy(update={"question_id": question_id})})


class TestQuestionStats:
    def test_repeated_runs_produce_real_statistics(self):
        records = [
            _record("r1", question_id="Q-1", required_evidence_score=1.0),
            _record("r2", question_id="Q-1", required_evidence_score=1.0),
            _record("r3", question_id="Q-1", required_evidence_score=0.0),
        ]

        stats = question_stats(records, question_id="Q-1", use_case_id="eq-value-and-relationship-combination")

        assert stats.n_repetitions == 3
        assert stats.n_usable == 3
        assert stats.success_rate == 2 / 3
        assert stats.mean == 2 / 3
        assert stats.sample_size_label == "tentative_small_n"
        assert set(stats.run_ids) == {"r1", "r2", "r3"}

    def test_no_records_gives_null_statistics_not_an_error(self):
        stats = question_stats([], question_id="Q-none", use_case_id="eq-value-and-relationship-combination")

        assert stats.n_repetitions == 0
        assert stats.mean is None
        assert stats.success_rate is None
        assert stats.sample_size_label == "no_evidence"

    def test_failed_runs_are_excluded_from_the_metric_but_counted_in_repetitions(self):
        records = [
            _record("r1", question_id="Q-1", required_evidence_score=1.0),
            _record("r2", question_id="Q-1", status=ExperimentRunStatus.FAILED),
        ]

        stats = question_stats(records, question_id="Q-1", use_case_id="eq-value-and-relationship-combination")

        assert stats.n_repetitions == 2
        assert stats.n_usable == 1
        assert stats.mean == 1.0


class TestUseCaseQuestionStats:
    def test_macro_average_is_the_mean_of_question_means_micro_is_pooled(self):
        # Q-1: 1 repetition scoring 1.0 (mean=1.0)
        # Q-2: 3 repetitions scoring 0.0, 0.0, 0.0 (mean=0.0)
        # macro = mean(1.0, 0.0) = 0.5 -- Q-1's single run isn't drowned out
        # micro = mean(1.0, 0.0, 0.0, 0.0) = 0.25 -- pooled, repetition-weighted
        records = [
            _record("r1", question_id="Q-1", required_evidence_score=1.0),
            _record("r2", question_id="Q-2", required_evidence_score=0.0),
            _record("r3", question_id="Q-2", required_evidence_score=0.0),
            _record("r4", question_id="Q-2", required_evidence_score=0.0),
        ]

        stats = use_case_question_stats(records, use_case_id="eq-value-and-relationship-combination", question_ids=["Q-1", "Q-2"])

        assert stats.macro_average == 0.5
        assert stats.micro_average == 0.25
        assert stats.n_questions == 2

    def test_every_question_own_result_is_preserved_even_when_aggregating(self):
        records = [
            _record("r1", question_id="Q-easy", required_evidence_score=1.0),
            _record("r2", question_id="Q-hard", required_evidence_score=0.0),
        ]

        stats = use_case_question_stats(records, use_case_id="eq-value-and-relationship-combination", question_ids=["Q-easy", "Q-hard"])

        by_id = {q.question_id: q for q in stats.questions}
        assert by_id["Q-easy"].mean == 1.0
        assert by_id["Q-hard"].mean == 0.0  # the hard question's poor score is NOT hidden by the easy one


class TestBenchmarkLevelStats:
    def test_rolls_up_across_use_cases_preserving_each_one(self):
        records = [
            _record("r1", question_id="Q-1", use_case_id="uc-a", required_evidence_score=1.0),
            _record("r2", question_id="Q-2", use_case_id="uc-b", required_evidence_score=0.0),
        ]

        stats = benchmark_level_stats(
            records,
            isa95_level="equipment",
            use_case_ids=["uc-a", "uc-b"],
            question_ids_by_use_case={"uc-a": ["Q-1"], "uc-b": ["Q-2"]},
        )

        assert stats.n_use_cases == 2
        assert stats.n_questions == 2
        assert stats.macro_average == 0.5  # mean(1.0, 0.0) across the two use cases
        assert stats.micro_average == 0.5  # same here since n=1 per use case
        assert {uc.use_case_id for uc in stats.use_cases} == {"uc-a", "uc-b"}

    def test_only_records_at_the_requested_level_are_considered(self):
        records = [
            _record("r1", question_id="Q-1", use_case_id="uc-a", isa95_level="equipment", required_evidence_score=1.0),
            _record("r2", question_id="Q-2", use_case_id="uc-b", isa95_level="process_cell", required_evidence_score=0.0),
        ]

        stats = benchmark_level_stats(
            records,
            isa95_level="equipment",
            use_case_ids=["uc-a", "uc-b"],
            question_ids_by_use_case={"uc-a": ["Q-1"], "uc-b": ["Q-2"]},
        )

        # uc-b's process_cell record must not contaminate the equipment-level rollup.
        assert stats.macro_average == 1.0
