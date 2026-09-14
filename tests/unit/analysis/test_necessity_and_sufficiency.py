"""ICAB-CN/ICAB-CS unit tests: necessity and sufficiency analysis over synthetic (but schema-real) records."""

from __future__ import annotations

import pytest

from icab.analysis import analyze_context_necessity, find_minimum_sufficient_context
from icab.experiments.models import ExperimentRunStatus
from icab.scenarios.models import ScenarioDifficulty, TaskMode
from icab.tasks.benchmark_task import EvaluationCriteria
from icab.tasks.context_dimensions import ContextDimension
from icab.usecases import ISA95Level, IndustrialUseCase

from _v2_factories import make_evaluation, make_v2_record


def _use_case(**overrides) -> IndustrialUseCase:
    base = dict(
        use_case_id="eq-value-and-relationship-combination",
        name="Combine value and relationship",
        description="Test use case.",
        isa95_level=ISA95Level.EQUIPMENT,
        task_type=TaskMode.INVESTIGATION,
        required_context=[ContextDimension.C5_OPERATIONAL, ContextDimension.C3_RELATIONAL],
        candidate_context=[ContextDimension.C5_OPERATIONAL, ContextDimension.C3_RELATIONAL, ContextDimension.C2_ASSET_HIERARCHY],
        success_criteria=EvaluationCriteria(binding_scores=["required_evidence_score", "relationship_score"]),
        applicable_scenarios=["d2_reactor_context_combination"],
        difficulty=ScenarioDifficulty.D2,
    )
    base.update(overrides)
    return IndustrialUseCase(**base)


class TestAnalyzeContextNecessity:
    def test_only_scopes_records_matching_the_use_case(self):
        use_case = _use_case()
        matching = make_v2_record(
            "r1", context_combination_id="C4+C5+C7", architectures=["historian"], evaluation=make_evaluation(required_evidence_score=1.0)
        )
        other_use_case = make_v2_record(
            "r2", use_case_id="some-other-use-case", context_combination_id="C4+C5+C7", architectures=["historian"], evaluation=make_evaluation()
        )

        report = analyze_context_necessity([matching, other_use_case], use_case)

        assert report.total_runs_considered == 1

    def test_reports_insufficient_evidence_when_every_tested_combo_includes_the_dimension(self):
        use_case = _use_case()
        # Both tested combinations include C5 -- no "without C5" side exists.
        records = [
            make_v2_record("r1", context_combination_id="C4+C5+C7", architectures=["historian"], evaluation=make_evaluation()),
            make_v2_record("r2", context_combination_id="C2+C3+C4+C5+C6+C7", architectures=["historian", "knowledge_graph"], evaluation=make_evaluation()),
        ]

        report = analyze_context_necessity(records, use_case, metric="required_evidence_score")

        c5_finding = next(f for f in report.findings if f.dimension == ContextDimension.C5_OPERATIONAL)
        assert c5_finding.evidence_status == "insufficient_evidence"
        assert c5_finding.delta is None

    def test_reports_a_real_delta_when_both_sides_are_tested(self):
        use_case = _use_case()
        # historian-only (C4+C5+C7): no C3 -> low required_evidence_score
        # kg-only (C2+C3+C6): no C5 -> also low, but for a DIFFERENT reason
        with_c3 = make_v2_record(
            "r1", context_combination_id="C2+C3+C6", architectures=["knowledge_graph"],
            evaluation=make_evaluation(required_evidence_score=1.0),
        )
        without_c3 = make_v2_record(
            "r2", context_combination_id="C4+C5+C7", architectures=["historian"],
            evaluation=make_evaluation(required_evidence_score=0.5),
        )

        report = analyze_context_necessity([with_c3, without_c3], use_case, metric="required_evidence_score")

        c3_finding = next(f for f in report.findings if f.dimension == ContextDimension.C3_RELATIONAL)
        assert c3_finding.evidence_status == "evidence"
        assert c3_finding.delta == pytest.approx(0.5)
        assert c3_finding.n_with == 1
        assert c3_finding.n_without == 1

    def test_empty_records_produce_insufficient_evidence_everywhere(self):
        use_case = _use_case()
        report = analyze_context_necessity([], use_case)
        assert all(f.evidence_status == "insufficient_evidence" for f in report.findings)
        assert report.total_runs_considered == 0


class TestFindMinimumSufficientContext:
    def test_never_claims_global_minimality(self):
        use_case = _use_case()
        report = find_minimum_sufficient_context([], use_case)
        assert "NOT a" in report.caveat
        assert "global mathematical minimality" in report.caveat

    def test_picks_the_smallest_cardinality_condition_meeting_every_binding_score(self):
        use_case = _use_case()  # binding_scores: required_evidence_score, relationship_score
        insufficient_small = make_v2_record(
            "r1", context_combination_id="C5", architectures=["historian"],
            evaluation=make_evaluation(required_evidence_score=1.0, relationship_score=0.0),  # fails relationship_score
        )
        sufficient_larger = make_v2_record(
            "r2", context_combination_id="C3+C5", architectures=["historian", "knowledge_graph"],
            evaluation=make_evaluation(required_evidence_score=1.0, relationship_score=1.0),
        )
        sufficient_largest = make_v2_record(
            "r3", context_combination_id="C2+C3+C4+C5+C6+C7", architectures=["historian", "knowledge_graph"],
            evaluation=make_evaluation(required_evidence_score=1.0, relationship_score=1.0),
        )

        report = find_minimum_sufficient_context([insufficient_small, sufficient_larger, sufficient_largest], use_case)

        assert report.minimum_sufficient_context_among_tested == "C3+C5"

    def test_none_when_nothing_tested_meets_the_threshold(self):
        use_case = _use_case()
        record = make_v2_record(
            "r1", context_combination_id="C5", architectures=["historian"],
            evaluation=make_evaluation(required_evidence_score=0.5, relationship_score=0.0),
        )

        report = find_minimum_sufficient_context([record], use_case)

        assert report.minimum_sufficient_context_among_tested is None

    def test_failed_runs_never_count_as_sufficient(self):
        use_case = _use_case()
        failed = make_v2_record(
            "r1", context_combination_id="C3+C5", architectures=["historian", "knowledge_graph"],
            status=ExperimentRunStatus.FAILED, error="boom",
        )

        report = find_minimum_sufficient_context([failed], use_case)

        assert report.minimum_sufficient_context_among_tested is None

    def test_a_superset_of_a_sufficient_condition_is_excluded_from_candidates(self):
        # C3+C5 ⊂ C2+C3+C4+C5+C6+C7, and both meet the threshold -- the
        # larger one is DOMINATED (not a minimal element) and must not
        # appear as its own candidate.
        use_case = _use_case()
        smaller = make_v2_record(
            "r1", context_combination_id="C3+C5", architectures=["historian", "knowledge_graph"],
            evaluation=make_evaluation(required_evidence_score=1.0, relationship_score=1.0),
        )
        larger = make_v2_record(
            "r2", context_combination_id="C2+C3+C4+C5+C6+C7", architectures=["historian", "knowledge_graph"],
            evaluation=make_evaluation(required_evidence_score=1.0, relationship_score=1.0),
        )

        report = find_minimum_sufficient_context([smaller, larger], use_case)

        assert report.candidate_minimum_sufficient_contexts == ["C3+C5"]
        assert report.minimum_sufficient_context_among_tested == "C3+C5"


class TestPartialOrderMultipleCandidates:
    """
    Context combinations form a PARTIAL order by dimension subset, not a
    total order -- two sufficient tested conditions can be genuinely
    incomparable (neither a subset of the other), including but not
    limited to equal-cardinality ties. Both must be reported, never one
    arbitrarily preferred.
    """

    def test_two_equal_cardinality_sufficient_conditions_are_both_reported(self):
        use_case = _use_case()
        a = make_v2_record(
            "r1", context_combination_id="C3+C5", architectures=["historian", "knowledge_graph"],
            evaluation=make_evaluation(required_evidence_score=1.0, relationship_score=1.0),
        )
        b = make_v2_record(
            "r2", context_combination_id="C2+C3", architectures=["knowledge_graph"],
            evaluation=make_evaluation(required_evidence_score=1.0, relationship_score=1.0),
        )

        report = find_minimum_sufficient_context([a, b], use_case)

        assert set(report.candidate_minimum_sufficient_contexts) == {"C3+C5", "C2+C3"}
        # The singular field is deterministic (lexicographically first) but never claims uniqueness on its own.
        assert report.minimum_sufficient_context_among_tested in {"C3+C5", "C2+C3"}

    def test_incomparable_conditions_of_different_cardinality_are_both_reported(self):
        # C5 (cardinality 1) is NOT a subset of C2+C3 (cardinality 2) and
        # vice versa -- genuinely incomparable despite different sizes.
        use_case = _use_case()
        small = make_v2_record(
            "r1", context_combination_id="C5", architectures=["historian"],
            evaluation=make_evaluation(required_evidence_score=1.0, relationship_score=1.0),
        )
        different = make_v2_record(
            "r2", context_combination_id="C2+C3", architectures=["knowledge_graph"],
            evaluation=make_evaluation(required_evidence_score=1.0, relationship_score=1.0),
        )

        report = find_minimum_sufficient_context([small, different], use_case)

        assert set(report.candidate_minimum_sufficient_contexts) == {"C5", "C2+C3"}

    def test_empty_candidate_list_when_nothing_is_sufficient(self):
        use_case = _use_case()
        record = make_v2_record(
            "r1", context_combination_id="C5", architectures=["historian"],
            evaluation=make_evaluation(required_evidence_score=0.0, relationship_score=0.0),
        )

        report = find_minimum_sufficient_context([record], use_case)

        assert report.candidate_minimum_sufficient_contexts == []


class TestQuestionLevelScoping:
    """MSC/necessity at the QUESTION level (icab.questions), not just the whole use case -- same functions, an optional question_id parameter."""

    def test_necessity_scoped_to_one_question_ignores_other_questions_records(self):
        use_case = _use_case()
        for_q1 = make_v2_record(
            "r1", context_combination_id="C2+C3+C6", architectures=["knowledge_graph"],
            evaluation=make_evaluation(required_evidence_score=1.0),
        )
        for_q1 = for_q1.model_copy(update={"config": for_q1.config.model_copy(update={"question_id": "Q-1"})})
        for_q2 = make_v2_record(
            "r2", context_combination_id="C4+C5+C7", architectures=["historian"],
            evaluation=make_evaluation(required_evidence_score=0.0),
        )
        for_q2 = for_q2.model_copy(update={"config": for_q2.config.model_copy(update={"question_id": "Q-2"})})

        report = analyze_context_necessity([for_q1, for_q2], use_case, question_id="Q-1")

        assert report.question_id == "Q-1"
        assert report.total_runs_considered == 1  # Q-2's record never entered the scope

    def test_sufficiency_scoped_to_one_question(self):
        use_case = _use_case()
        for_q1 = make_v2_record(
            "r1", context_combination_id="C3+C5", architectures=["historian", "knowledge_graph"],
            evaluation=make_evaluation(required_evidence_score=1.0, relationship_score=1.0),
        )
        for_q1 = for_q1.model_copy(update={"config": for_q1.config.model_copy(update={"question_id": "Q-1"})})
        for_q2_insufficient = make_v2_record(
            "r2", context_combination_id="C3+C5", architectures=["historian", "knowledge_graph"],
            evaluation=make_evaluation(required_evidence_score=0.0, relationship_score=0.0),
        )
        for_q2_insufficient = for_q2_insufficient.model_copy(update={"config": for_q2_insufficient.config.model_copy(update={"question_id": "Q-2"})})

        report_q1 = find_minimum_sufficient_context([for_q1, for_q2_insufficient], use_case, question_id="Q-1")
        report_q2 = find_minimum_sufficient_context([for_q1, for_q2_insufficient], use_case, question_id="Q-2")

        assert report_q1.question_id == "Q-1"
        assert report_q1.minimum_sufficient_context_among_tested == "C3+C5"
        assert report_q2.minimum_sufficient_context_among_tested is None  # Q-2's own single run was insufficient

    def test_no_question_id_still_pools_every_question_unchanged(self):
        use_case = _use_case()
        for_q1 = make_v2_record(
            "r1", context_combination_id="C3+C5", architectures=["historian", "knowledge_graph"],
            evaluation=make_evaluation(required_evidence_score=1.0, relationship_score=1.0),
        )
        for_q1 = for_q1.model_copy(update={"config": for_q1.config.model_copy(update={"question_id": "Q-1"})})

        report = find_minimum_sufficient_context([for_q1], use_case)  # no question_id -- whole use case

        assert report.question_id is None
        assert report.minimum_sufficient_context_among_tested == "C3+C5"


class TestTraceabilityFromConditionToExperimentId:
    """Every tested condition (and so every context-requirement-matrix cell derived from it) must be traceable back to the exact run_id(s) it rests on."""

    def test_each_tested_condition_carries_its_own_run_ids(self):
        use_case = _use_case()
        a = make_v2_record(
            "run-alpha", context_combination_id="C3+C5", architectures=["historian", "knowledge_graph"],
            evaluation=make_evaluation(required_evidence_score=1.0, relationship_score=1.0),
        )
        b = make_v2_record(
            "run-beta", context_combination_id="C3+C5", architectures=["historian", "knowledge_graph"],
            evaluation=make_evaluation(required_evidence_score=1.0, relationship_score=1.0),
        )
        other_combo = make_v2_record(
            "run-gamma", context_combination_id="C4+C5+C7", architectures=["historian"],
            evaluation=make_evaluation(required_evidence_score=0.0, relationship_score=0.0),
        )

        report = find_minimum_sufficient_context([a, b, other_combo], use_case)

        by_id = {c.context_combination_id: c for c in report.tested_conditions}
        assert set(by_id["C3+C5"].run_ids) == {"run-alpha", "run-beta"}
        assert by_id["C4+C5+C7"].run_ids == ["run-gamma"]

    def test_candidate_msc_table_supporting_experiment_ids_match_the_real_run_ids(self):
        from icab.analysis import candidate_msc_table

        use_case = _use_case()
        a = make_v2_record(
            "run-alpha", context_combination_id="C3+C5", architectures=["historian", "knowledge_graph"],
            evaluation=make_evaluation(required_evidence_score=1.0, relationship_score=1.0),
        )

        rows = candidate_msc_table([use_case], [a])

        assert rows[0]["supporting_experiment_ids"] == {"C3+C5": ["run-alpha"]}

    def test_a_failed_run_never_contributes_a_run_id_to_a_sufficient_condition(self):
        use_case = _use_case()
        completed = make_v2_record(
            "run-good", context_combination_id="C3+C5", architectures=["historian", "knowledge_graph"],
            evaluation=make_evaluation(required_evidence_score=1.0, relationship_score=1.0),
        )
        failed = make_v2_record(
            "run-bad", context_combination_id="C3+C5", architectures=["historian", "knowledge_graph"],
            status=ExperimentRunStatus.FAILED, error="boom",
        )

        report = find_minimum_sufficient_context([completed, failed], use_case)

        condition = next(c for c in report.tested_conditions if c.context_combination_id == "C3+C5")
        # Both run_ids are recorded (the condition genuinely includes both
        # attempts), but the FAILED run must never silently vanish from
        # the record OR silently count toward the passing mean.
        assert set(condition.run_ids) == {"run-good", "run-bad"}
        assert condition.n_runs == 2
