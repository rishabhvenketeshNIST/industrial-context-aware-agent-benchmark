"""ICAB v2 failure taxonomy + Context Design Profile unit tests."""

from __future__ import annotations

from icab.analysis import build_context_design_profile, classify_failures
from icab.analysis.failure_taxonomy import FailureCategory
from icab.experiments.models import ExperimentRunStatus
from icab.scenarios.models import ScenarioDifficulty, TaskMode
from icab.tasks.benchmark_task import EvaluationCriteria
from icab.tasks.context_dimensions import ContextDimension
from icab.usecases import ISA95Level, IndustrialUseCase

from _v2_factories import make_evaluation, make_v2_record


def _use_case() -> IndustrialUseCase:
    return IndustrialUseCase(
        use_case_id="eq-value-and-relationship-combination",
        name="Combine value and relationship",
        description="Test use case.",
        isa95_level=ISA95Level.EQUIPMENT,
        task_type=TaskMode.INVESTIGATION,
        required_context=[ContextDimension.C5_OPERATIONAL],
        candidate_context=[ContextDimension.C5_OPERATIONAL],
        success_criteria=EvaluationCriteria(binding_scores=["required_evidence_score"]),
        applicable_scenarios=["d2_reactor_context_combination"],
        difficulty=ScenarioDifficulty.D2,
    )


class TestFailureTaxonomy:
    def test_infrastructure_shaped_error_is_architecture_connectivity_failure(self):
        record = make_v2_record(
            "r1", context_combination_id="C5", architectures=["historian"],
            status=ExperimentRunStatus.FAILED, error="ConnectError: [WinError 10061] refused",
        )

        [classification] = classify_failures([record])

        assert classification.category == FailureCategory.ARCHITECTURE_CONNECTIVITY_FAILURE

    def test_no_context_acquired_at_all_is_context_not_discoverable(self):
        record = make_v2_record(
            "r1", context_combination_id="C5", architectures=["historian"],
            evaluation=make_evaluation(required_evidence_score=0.0, context_acquired=[]),
        )

        [classification] = classify_failures([record])

        assert classification.category == FailureCategory.CONTEXT_NOT_DISCOVERABLE

    def test_context_acquired_but_missing_required_evidence_is_context_not_retrieved(self):
        record = make_v2_record(
            "r1", context_combination_id="C5", architectures=["historian"],
            evaluation=make_evaluation(required_evidence_score=0.5, context_acquired=["urn:icab:measurement:x"]),
        )

        [classification] = classify_failures([record])

        assert classification.category == FailureCategory.CONTEXT_NOT_RETRIEVED

    def test_budget_exceeded_is_efficiency_failure_regardless_of_other_scores(self):
        record = make_v2_record(
            "r1", context_combination_id="C5", architectures=["historian"],
            evaluation=make_evaluation(required_evidence_score=1.0, terminated_properly=False),
        )

        [classification] = classify_failures([record])

        assert classification.category == FailureCategory.EFFICIENCY_FAILURE

    def test_wrong_canonical_id_is_representation_failure(self):
        record = make_v2_record(
            "r1", context_combination_id="C5", architectures=["historian"],
            evaluation=make_evaluation(required_evidence_score=1.0, canonical_id_score=0.5),
        )

        [classification] = classify_failures([record])

        assert classification.category == FailureCategory.REPRESENTATION_FAILURE

    def test_unsupported_numeric_claim_is_grounding_failure(self):
        record = make_v2_record(
            "r1", context_combination_id="C5", architectures=["historian"],
            evaluation=make_evaluation(required_evidence_score=1.0, canonical_id_score=1.0, grounding_score=0.5),
        )

        [classification] = classify_failures([record])

        assert classification.category == FailureCategory.GROUNDING_FAILURE

    def test_wrong_conclusion_despite_good_evidence_is_reasoning_failure_not_context_failure(self):
        """
        The exact distinction the ICAB v2 direction insists on: a
        missing context dimension must never be blamed on the agent, and
        symmetrically, a genuine reasoning mistake must not be
        misclassified as a context/architecture problem.
        """

        record = make_v2_record(
            "r1", context_combination_id="C5", architectures=["historian"],
            evaluation=make_evaluation(
                required_evidence_score=1.0, canonical_id_score=1.0, grounding_score=1.0,
                conclusion_correctness_score=0.0,
            ),
        )

        [classification] = classify_failures([record])

        assert classification.category == FailureCategory.REASONING_FAILURE

    def test_fully_successful_run_is_category_none(self):
        record = make_v2_record("r1", context_combination_id="C5", architectures=["historian"], evaluation=make_evaluation())

        [classification] = classify_failures([record])

        assert classification.category == FailureCategory.NONE

    def test_every_record_gets_classified_including_successful_ones(self):
        records = [
            make_v2_record("r1", context_combination_id="C5", architectures=["historian"], evaluation=make_evaluation()),
            make_v2_record("r2", context_combination_id="C5", architectures=["historian"], status=ExperimentRunStatus.FAILED, error="boom"),
        ]

        classifications = classify_failures(records)

        assert len(classifications) == 2


class TestContextDesignProfile:
    def test_profile_reflects_real_evidence_counts(self):
        use_case = _use_case()
        records = [
            make_v2_record("r1", context_combination_id="C5", architectures=["historian"], evaluation=make_evaluation()),
            make_v2_record("r2", context_combination_id="C5", architectures=["historian"], evaluation=make_evaluation()),
        ]

        profile = build_context_design_profile(records, use_case)

        assert profile.use_case == use_case.use_case_id
        assert profile.isa95_level == "equipment"
        assert profile.evidence["runs"] == 2
        assert "NOT a" in profile.sufficiency_caveat

    def test_confidence_is_low_with_a_single_run(self):
        use_case = _use_case()
        record = make_v2_record("r1", context_combination_id="C5", architectures=["historian"], evaluation=make_evaluation())

        profile = build_context_design_profile([record], use_case)

        assert profile.confidence == "low"

    def test_representation_recommendation_only_uses_architectures_capable_of_the_dimension(self):
        """
        Regression test for a real bug found during development: the
        profile must never recommend an architecture for a dimension it
        cannot actually supply (e.g. historian for C3 Relational).
        """

        use_case = IndustrialUseCase(
            use_case_id="eq-value-and-relationship-combination",
            name="test",
            description="test",
            isa95_level=ISA95Level.EQUIPMENT,
            task_type=TaskMode.INVESTIGATION,
            required_context=[ContextDimension.C3_RELATIONAL, ContextDimension.C5_OPERATIONAL],
            candidate_context=[ContextDimension.C3_RELATIONAL, ContextDimension.C5_OPERATIONAL],
            success_criteria=EvaluationCriteria(binding_scores=["required_evidence_score"]),
            applicable_scenarios=["d2_reactor_context_combination"],
            difficulty=ScenarioDifficulty.D2,
        )
        records = [
            make_v2_record("r1", context_combination_id="C5", architectures=["historian"], evaluation=make_evaluation(conclusion_correctness_score=1.0)),
            make_v2_record("r2", context_combination_id="C3", architectures=["knowledge_graph"], evaluation=make_evaluation(conclusion_correctness_score=1.0)),
        ]

        profile = build_context_design_profile(records, use_case)

        assert "historian" in profile.representations["C5"]
        assert "knowledge_graph" in profile.representations["C3"]
        assert "historian" not in profile.representations["C3"]
