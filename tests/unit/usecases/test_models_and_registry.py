"""ICAB v2: tests for IndustrialUseCase/IndustrialUseCaseRegistry, including the REAL, checked-in configs/usecases/ files."""

from __future__ import annotations

import pytest

from icab.scenarios import BenchmarkScenarioRegistry
from icab.scenarios.models import ScenarioDifficulty, TaskMode
from icab.tasks.benchmark_task import EvaluationCriteria
from icab.tasks.context_dimensions import ContextDimension
from icab.usecases import ISA95_LEVEL_COVERAGE_NOTES, ISA95Level, IndustrialUseCase, IndustrialUseCaseRegistry

SCENARIOS_DIR = "configs/benchmark/scenarios"
USECASES_DIR = "configs/usecases"


def _use_case(**overrides) -> IndustrialUseCase:
    base = dict(
        use_case_id="test-use-case",
        name="Test use case",
        description="A test use case.",
        isa95_level=ISA95Level.EQUIPMENT,
        task_type=TaskMode.QA,
        required_context=[ContextDimension.C5_OPERATIONAL],
        candidate_context=[ContextDimension.C5_OPERATIONAL, ContextDimension.C4_TEMPORAL],
        success_criteria=EvaluationCriteria(binding_scores=["required_evidence_score"]),
        applicable_scenarios=["d1_reactor_pressure_reading"],
        difficulty=ScenarioDifficulty.D1,
    )
    base.update(overrides)
    return IndustrialUseCase(**base)


class TestIndustrialUseCaseModel:
    def test_valid_use_case_constructs(self):
        use_case = _use_case()
        assert use_case.use_case_id == "test-use-case"

    def test_required_context_must_be_a_subset_of_candidate_context(self):
        with pytest.raises(ValueError, match="candidate_context"):
            _use_case(
                required_context=[ContextDimension.C3_RELATIONAL],
                candidate_context=[ContextDimension.C5_OPERATIONAL],
            )

    def test_required_context_equal_to_candidate_context_is_fine(self):
        use_case = _use_case(
            required_context=[ContextDimension.C5_OPERATIONAL],
            candidate_context=[ContextDimension.C5_OPERATIONAL],
        )
        assert use_case.required_context == use_case.candidate_context

    def test_empty_required_context_is_rejected(self):
        with pytest.raises(Exception):
            _use_case(required_context=[])

    def test_empty_applicable_scenarios_is_rejected(self):
        with pytest.raises(Exception):
            _use_case(applicable_scenarios=[])

    def test_rejects_unknown_fields(self):
        with pytest.raises(Exception):
            IndustrialUseCase(**{**_use_case().model_dump(), "bogus_field": True})


class TestIndustrialUseCaseRegistry:
    def test_real_registered_use_cases_load_and_cross_validate(self):
        scenario_registry = BenchmarkScenarioRegistry(SCENARIOS_DIR)
        registry = IndustrialUseCaseRegistry(USECASES_DIR, scenario_registry=scenario_registry)

        assert len(registry) > 0
        for use_case in registry:
            assert use_case.use_case_id in registry.list_ids()

    def test_every_applicable_scenario_is_a_real_registered_scenario(self):
        scenario_registry = BenchmarkScenarioRegistry(SCENARIOS_DIR)
        registry = IndustrialUseCaseRegistry(USECASES_DIR, scenario_registry=scenario_registry)

        for use_case in registry:
            for scenario_id in use_case.applicable_scenarios:
                scenario_registry.get(scenario_id)  # raises KeyError if not real

    def test_duplicate_use_case_id_across_files_is_rejected(self, tmp_path):
        scenario_registry = BenchmarkScenarioRegistry(SCENARIOS_DIR)
        (tmp_path / "a.yaml").write_text(
            "use_cases:\n"
            "  - use_case_id: dup\n"
            "    name: A\n"
            "    description: A.\n"
            "    isa95_level: equipment\n"
            "    task_type: qa\n"
            "    required_context: [C5]\n"
            "    candidate_context: [C5]\n"
            "    success_criteria:\n"
            "      binding_scores: [required_evidence_score]\n"
            "    applicable_scenarios: [d1_reactor_pressure_reading]\n"
            "    difficulty: D1\n",
            encoding="utf-8",
        )
        (tmp_path / "b.yaml").write_text(
            "use_cases:\n"
            "  - use_case_id: dup\n"
            "    name: B\n"
            "    description: B.\n"
            "    isa95_level: equipment\n"
            "    task_type: qa\n"
            "    required_context: [C5]\n"
            "    candidate_context: [C5]\n"
            "    success_criteria:\n"
            "      binding_scores: [required_evidence_score]\n"
            "    applicable_scenarios: [d1_reactor_pressure_reading]\n"
            "    difficulty: D1\n",
            encoding="utf-8",
        )

        with pytest.raises(ValueError, match="Duplicate use_case_id"):
            IndustrialUseCaseRegistry(tmp_path, scenario_registry=scenario_registry)

    def test_unknown_applicable_scenario_is_rejected(self, tmp_path):
        scenario_registry = BenchmarkScenarioRegistry(SCENARIOS_DIR)
        (tmp_path / "bad.yaml").write_text(
            "use_cases:\n"
            "  - use_case_id: bad-scenario-ref\n"
            "    name: Bad\n"
            "    description: Bad.\n"
            "    isa95_level: equipment\n"
            "    task_type: qa\n"
            "    required_context: [C5]\n"
            "    candidate_context: [C5]\n"
            "    success_criteria:\n"
            "      binding_scores: [required_evidence_score]\n"
            "    applicable_scenarios: [not_a_real_scenario]\n"
            "    difficulty: D1\n",
            encoding="utf-8",
        )

        with pytest.raises(ValueError, match="unknown"):
            IndustrialUseCaseRegistry(tmp_path, scenario_registry=scenario_registry)

    def test_for_level_filters_correctly(self):
        scenario_registry = BenchmarkScenarioRegistry(SCENARIOS_DIR)
        registry = IndustrialUseCaseRegistry(USECASES_DIR, scenario_registry=scenario_registry)

        for level in ISA95Level:
            for use_case in registry.for_level(level):
                assert use_case.isa95_level == level

    def test_unknown_use_case_id_raises(self):
        scenario_registry = BenchmarkScenarioRegistry(SCENARIOS_DIR)
        registry = IndustrialUseCaseRegistry(USECASES_DIR, scenario_registry=scenario_registry)

        with pytest.raises(KeyError):
            registry.get("not-a-real-use-case")


class TestHonestCoverageReporting:
    """
    The core ICAB v2/v3 discipline this milestone repeatedly demands: do
    not fabricate use cases to fill the ISA-95 matrix. Since the ICAB v3
    50-question milestone, Enterprise/Site/Work Center are covered by a
    CONTROLLED, clearly-labeled synthetic benchmark context layer
    (icab.benchmark_context) rather than left at zero -- these tests
    assert the ACTUAL, current, honestly-reported coverage and its
    provenance, not that those levels stay empty forever.
    """

    def test_every_level_now_has_real_use_case_coverage(self):
        scenario_registry = BenchmarkScenarioRegistry(SCENARIOS_DIR)
        registry = IndustrialUseCaseRegistry(USECASES_DIR, scenario_registry=scenario_registry)

        for level in ISA95Level:
            assert len(registry.for_level(level)) > 0, f"{level} has zero use cases"

    def test_equipment_and_process_cell_have_real_coverage(self):
        scenario_registry = BenchmarkScenarioRegistry(SCENARIOS_DIR)
        registry = IndustrialUseCaseRegistry(USECASES_DIR, scenario_registry=scenario_registry)

        assert len(registry.for_level(ISA95Level.EQUIPMENT)) > 0
        assert len(registry.for_level(ISA95Level.PROCESS_CELL)) > 0

    def test_every_isa95_level_has_a_coverage_note(self):
        for level in ISA95Level:
            assert level in ISA95_LEVEL_COVERAGE_NOTES
            assert ISA95_LEVEL_COVERAGE_NOTES[level]  # non-empty
