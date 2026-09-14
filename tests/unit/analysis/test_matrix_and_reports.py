"""Unit tests for `icab.analysis.matrix` (Phase 8) and `icab.analysis.reports` (Phase 14) over synthetic (schema-real) records."""

from __future__ import annotations

from icab.analysis import (
    architecture_context_matrix,
    build_use_case_experiment_matrix,
    candidate_msc_table,
    context_requirement_matrix,
    failure_mode_matrix,
    isa95_coverage_matrix,
)
from icab.experiments.models import ExperimentRunStatus
from icab.scenarios import BenchmarkScenarioRegistry
from icab.scenarios.models import ScenarioDifficulty, TaskMode
from icab.tasks.benchmark_task import EvaluationCriteria
from icab.tasks.context_dimensions import ContextDimension
from icab.usecases import ISA95Level, IndustrialUseCase, IndustrialUseCaseRegistry

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


class TestUseCaseExperimentMatrix:
    def test_assembles_factor_inventory_and_sub_reports(self):
        use_case = _use_case()
        records = [
            make_v2_record(
                "r1", context_combination_id="C3+C5", architectures=["historian", "knowledge_graph"],
                evaluation=make_evaluation(required_evidence_score=1.0, relationship_score=1.0),
            ),
            make_v2_record(
                "r2", context_combination_id="C4+C5+C7", architectures=["historian"],
                evaluation=make_evaluation(required_evidence_score=0.5, relationship_score=0.0),
            ),
        ]

        matrix = build_use_case_experiment_matrix(records, use_case)

        assert matrix.use_case_id == "eq-value-and-relationship-combination"
        assert matrix.isa95_level == "equipment"
        assert set(matrix.architectures_tested) == {"historian", "knowledge_graph"}
        assert matrix.total_runs == 2
        assert matrix.successful_runs == 2
        assert matrix.sample_size_label == "tentative_small_n"
        assert matrix.sufficiency.minimum_sufficient_context_among_tested == "C3+C5"
        assert matrix.candidate_msc == ["C3", "C5"]
        assert matrix.candidate_msc_combinations == ["C3+C5"]
        assert sum(matrix.discoverability_breakdown.values()) == 2

    def test_exposes_every_incomparable_candidate_msc_not_just_one(self):
        use_case = _use_case()
        records = [
            make_v2_record(
                "r1", context_combination_id="C3+C5", architectures=["historian", "knowledge_graph"],
                evaluation=make_evaluation(required_evidence_score=1.0, relationship_score=1.0),
            ),
            make_v2_record(
                "r2", context_combination_id="C2+C3", architectures=["knowledge_graph"],
                evaluation=make_evaluation(required_evidence_score=1.0, relationship_score=1.0),
            ),
        ]

        matrix = build_use_case_experiment_matrix(records, use_case)

        assert set(matrix.candidate_msc_combinations) == {"C3+C5", "C2+C3"}

    def test_failed_runs_are_never_silently_dropped_from_counters(self):
        use_case = _use_case()
        records = [
            make_v2_record("r1", context_combination_id="C3+C5", architectures=["historian", "knowledge_graph"], status=ExperimentRunStatus.FAILED, error="boom"),
        ]

        matrix = build_use_case_experiment_matrix(records, use_case)

        assert matrix.total_runs == 1
        assert matrix.failed_runs == 1
        assert matrix.successful_runs == 0


class TestContextRequirementMatrix:
    def test_cells_cover_required_sufficient_beneficial_not_demonstrated_not_applicable(self):
        use_case = _use_case()  # required=[C5, C3], candidate=[C5, C3, C2]
        records = [
            make_v2_record(
                "r1", context_combination_id="C3+C5", architectures=["historian", "knowledge_graph"],
                evaluation=make_evaluation(required_evidence_score=1.0, relationship_score=1.0),
            ),
        ]

        matrix = context_requirement_matrix([use_case], records)

        row = matrix.rows[0]
        # C3+C5 is the MSC -> both flip from "required" to the more specific "sufficient".
        assert row.cells["C3"] == "sufficient"
        assert row.cells["C5"] == "sufficient"
        # C2 is in candidate_context but never demonstrated as beneficial or part of an MSC.
        assert row.cells["C2"] == "not_demonstrated"
        # C1/C4/C6/C7 are outside this use case's candidate_context entirely.
        assert row.cells["C1"] == "not_applicable"
        assert row.cells["C4"] == "not_applicable"

    def test_declared_required_dimension_without_sufficiency_evidence_stays_required(self):
        use_case = _use_case()
        matrix = context_requirement_matrix([use_case], [])  # no records at all

        row = matrix.rows[0]
        assert row.cells["C5"] == "required"
        assert row.cells["C3"] == "required"
        assert row.cells["C2"] == "not_demonstrated"


class TestArchitectureContextMatrix:
    def test_only_single_architecture_runs_count_toward_a_row(self):
        records = [
            make_v2_record("r1", context_combination_id="C5", architectures=["historian"], evaluation=make_evaluation(conclusion_correctness_score=1.0)),
            make_v2_record("r2", context_combination_id="C3+C5", architectures=["historian", "knowledge_graph"], evaluation=make_evaluation()),
        ]

        matrix = architecture_context_matrix(records)

        historian_row = next(r for r in matrix.rows if r.architecture == "historian")
        assert historian_row.n_single_architecture_runs == 1
        assert historian_row.mean_conclusion_correctness_score == 1.0
        assert "C4" in historian_row.claims_to_expose
        assert "C5" in historian_row.claims_to_expose
        assert "C3" not in historian_row.claims_to_expose  # historian cannot supply C3

        # knowledge_graph never ran alone in this record set.
        kg_row = next(r for r in matrix.rows if r.architecture == "knowledge_graph")
        assert kg_row.n_single_architecture_runs == 0
        assert kg_row.mean_conclusion_correctness_score is None


class TestFailureModeMatrix:
    def test_tallies_across_every_record(self):
        records = [
            make_v2_record("r1", context_combination_id="C5", architectures=["historian"], evaluation=make_evaluation()),
            make_v2_record(
                "r2", context_combination_id="C5", architectures=["historian"],
                evaluation=make_evaluation(context_acquired=[], required_evidence_score=0.0),
            ),
        ]

        breakdown = failure_mode_matrix(records)

        assert breakdown["none"] == 1
        assert breakdown["context_not_discoverable"] == 1


class TestISA95CoverageMatrix:
    def test_every_level_present_with_honest_coverage_notes(self):
        registry = IndustrialUseCaseRegistry(
            "configs/usecases", scenario_registry=BenchmarkScenarioRegistry("configs/benchmark/scenarios")
        )
        records = [
            make_v2_record("r1", context_combination_id="C5", architectures=["historian"], isa95_level="equipment", evaluation=make_evaluation()),
        ]

        matrix = isa95_coverage_matrix(registry, records)

        by_level = {row.level: row for row in matrix.rows}
        assert set(by_level) == {"enterprise", "site", "area", "work_center", "process_cell", "equipment"}
        # ICAB v3: every level now has real use-case-backed content (real
        # TEP data at Process Cell/Equipment, a controlled/mixed
        # synthetic benchmark context layer elsewhere -- see
        # icab.benchmark_context / docs/benchmark/specification-v3.md).
        assert by_level["enterprise"].use_case_count > 0
        assert by_level["equipment"].use_case_count > 0
        assert by_level["equipment"].experiment_coverage == 1
        assert by_level["enterprise"].experiment_coverage == 0
        assert all(row.framework_support for row in matrix.rows)
        assert by_level["enterprise"].coverage_note  # non-empty, explains controlled-synthetic provenance


class TestCandidateMscTable:
    def test_only_use_cases_with_evidence_appear(self):
        use_case = _use_case()
        other = _use_case(use_case_id="some-other-use-case")
        records = [
            make_v2_record(
                "r1", context_combination_id="C3+C5", architectures=["historian", "knowledge_graph"], use_case_id="eq-value-and-relationship-combination",
                evaluation=make_evaluation(required_evidence_score=1.0, relationship_score=1.0),
            ),
        ]

        rows = candidate_msc_table([use_case, other], records)

        assert len(rows) == 1
        assert rows[0]["use_case_id"] == "eq-value-and-relationship-combination"
        assert rows[0]["candidate_msc"] == "C3+C5"
        assert rows[0]["candidate_msc_combinations"] == ["C3+C5"]
