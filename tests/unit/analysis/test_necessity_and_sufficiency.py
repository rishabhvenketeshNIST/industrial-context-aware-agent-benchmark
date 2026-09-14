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
