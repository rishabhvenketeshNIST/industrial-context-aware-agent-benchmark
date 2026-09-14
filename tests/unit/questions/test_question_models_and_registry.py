"""Unit tests for icab.questions: the Question model, taxonomy, and QuestionBankRegistry."""

from __future__ import annotations

import pytest

from icab.questions import (
    DifficultyFactors,
    ExpectedAnswerType,
    Question,
    QuestionBankRegistry,
    QuestionCategory,
    QuestionDifficulty,
    ValidationStatus,
)
from icab.scenarios import BenchmarkScenarioRegistry
from icab.scenarios.models import TaskMode
from icab.tasks.context_dimensions import ContextDimension
from icab.tasks.isa95 import ISA95Level
from icab.tasks.registry import BenchmarkTaskRegistry
from icab.usecases import IndustrialUseCaseRegistry

SCENARIOS_DIR = "configs/benchmark/scenarios"
TASKS_V2_DIR = "configs/benchmark/tasks_v2"
USECASES_DIR = "configs/usecases"


def _question(**overrides) -> Question:
    base = dict(
        question_id="Q-TEST-1",
        benchmark_id="icab-equipment-v1",
        use_case_id="eq-current-value-interpretation",
        isa95_level=ISA95Level.EQUIPMENT,
        question_text="What is the current reactor pressure?",
        task_type=TaskMode.QA,
        objective="Report the reactor pressure value.",
        hypothesized_required_context=[ContextDimension.C5_OPERATIONAL],
        expected_evidence_description="A recent pressure reading.",
        expected_answer_type=ExpectedAnswerType.NUMERIC_VALUE,
        compatible_scenarios=["d1_reactor_pressure_reading"],
        realizations={"d1_reactor_pressure_reading": "d1-qa-current-pressure"},
        difficulty=QuestionDifficulty.BASIC,
        difficulty_factors=DifficultyFactors(n_sources=1),
        tags=[QuestionCategory.MEASUREMENT_INTERPRETATION],
    )
    base.update(overrides)
    return Question(**base)


class TestQuestionModel:
    def test_valid_question_constructs(self):
        question = _question()
        assert question.version == "1.0.0"
        assert question.validation_status == ValidationStatus.DRAFT

    def test_realization_must_be_a_declared_compatible_scenario(self):
        with pytest.raises(ValueError, match="not listed in compatible_scenarios"):
            _question(
                compatible_scenarios=["d1_reactor_pressure_reading"],
                realizations={"some_other_scenario": "some-task"},
            )

    def test_compatible_scenarios_may_be_a_superset_of_realizations(self):
        # Framework-ready: a scenario can be declared compatible before a
        # concrete task realization exists for it.
        question = _question(
            compatible_scenarios=["d1_reactor_pressure_reading", "d2_reactor_context_combination"],
            realizations={"d1_reactor_pressure_reading": "d1-qa-current-pressure"},
        )
        assert set(question.realizations) < set(question.compatible_scenarios)


class TestQuestionBankRegistry:
    def _registry(self, level: str) -> QuestionBankRegistry:
        scenario_registry = BenchmarkScenarioRegistry(SCENARIOS_DIR)
        task_registry = BenchmarkTaskRegistry(TASKS_V2_DIR, scenario_registry=scenario_registry)
        use_case_registry = IndustrialUseCaseRegistry(USECASES_DIR, scenario_registry=scenario_registry)
        return QuestionBankRegistry(f"configs/questions/{level}", use_case_registry=use_case_registry, task_registry=task_registry)

    def test_equipment_bank_loads_real_validated_questions(self):
        registry = self._registry("equipment")
        assert len(registry) >= 30  # real target: ~30, met via reuse of the real tep-v2 task inventory
        for question in registry:
            assert question.isa95_level == ISA95Level.EQUIPMENT
            assert question.validation_status == ValidationStatus.VALIDATED

    def test_process_cell_and_area_banks_load_without_fabrication(self):
        # Explicitly smaller than the ~30/~15 targets -- TEP's real
        # scenario/entity diversity at these levels does not support
        # more without inventing content (see docs/benchmark/specification-v3.md).
        process_cell = self._registry("process_cell")
        area = self._registry("area")
        assert len(process_cell) >= 1
        assert len(area) >= 1

    def test_for_level_and_for_use_case_and_for_tag_filter_correctly(self):
        registry = self._registry("equipment")
        for question in registry.for_level(ISA95Level.EQUIPMENT):
            assert question.isa95_level == ISA95Level.EQUIPMENT

        one_use_case = next(iter(registry)).use_case_id
        for question in registry.for_use_case(one_use_case):
            assert question.use_case_id == one_use_case

        one_tag = next(iter(registry)).tags[0]
        for question in registry.for_tag(one_tag):
            assert one_tag in question.tags

    def test_get_unknown_question_id_raises_a_clear_error(self):
        registry = self._registry("equipment")
        with pytest.raises(KeyError):
            registry.get("not-a-real-question")

    def test_unsupported_levels_have_empty_but_valid_banks(self, tmp_path):
        scenario_registry = BenchmarkScenarioRegistry(SCENARIOS_DIR)
        task_registry = BenchmarkTaskRegistry(TASKS_V2_DIR, scenario_registry=scenario_registry)
        use_case_registry = IndustrialUseCaseRegistry(USECASES_DIR, scenario_registry=scenario_registry)

        for level in ("enterprise", "site", "work_center"):
            registry = QuestionBankRegistry(f"configs/questions/{level}", use_case_registry=use_case_registry, task_registry=task_registry)
            assert len(registry) == 0  # legitimate, not an error

    def test_duplicate_question_id_across_files_is_rejected(self, tmp_path):
        import yaml

        payload = {
            "questions": [
                {
                    "question_id": "Q-DUP",
                    "benchmark_id": "icab-equipment-v1",
                    "use_case_id": "eq-current-value-interpretation",
                    "isa95_level": "equipment",
                    "question_text": "x",
                    "task_type": "qa",
                    "objective": "x",
                    "hypothesized_required_context": ["C5"],
                    "expected_evidence_description": "x",
                    "expected_answer_type": "numeric_value",
                    "compatible_scenarios": ["d1_reactor_pressure_reading"],
                    "realizations": {"d1_reactor_pressure_reading": "d1-qa-current-pressure"},
                    "difficulty": "basic",
                    "difficulty_factors": {"n_sources": 1},
                    "tags": ["measurement_interpretation"],
                }
            ]
        }
        (tmp_path / "one.yaml").write_text(yaml.safe_dump(payload), encoding="utf-8")
        (tmp_path / "two.yaml").write_text(yaml.safe_dump(payload), encoding="utf-8")

        scenario_registry = BenchmarkScenarioRegistry(SCENARIOS_DIR)
        task_registry = BenchmarkTaskRegistry(TASKS_V2_DIR, scenario_registry=scenario_registry)
        use_case_registry = IndustrialUseCaseRegistry(USECASES_DIR, scenario_registry=scenario_registry)

        with pytest.raises(ValueError, match="Duplicate question_id"):
            QuestionBankRegistry(tmp_path, use_case_registry=use_case_registry, task_registry=task_registry)

    def test_realization_referencing_unknown_task_is_rejected(self, tmp_path):
        import yaml

        payload = {
            "questions": [
                {
                    "question_id": "Q-BAD-TASK",
                    "benchmark_id": "icab-equipment-v1",
                    "use_case_id": "eq-current-value-interpretation",
                    "isa95_level": "equipment",
                    "question_text": "x",
                    "task_type": "qa",
                    "objective": "x",
                    "hypothesized_required_context": ["C5"],
                    "expected_evidence_description": "x",
                    "expected_answer_type": "numeric_value",
                    "compatible_scenarios": ["d1_reactor_pressure_reading"],
                    "realizations": {"d1_reactor_pressure_reading": "not-a-real-task"},
                    "difficulty": "basic",
                    "difficulty_factors": {"n_sources": 1},
                    "tags": ["measurement_interpretation"],
                }
            ]
        }
        (tmp_path / "bad.yaml").write_text(yaml.safe_dump(payload), encoding="utf-8")

        scenario_registry = BenchmarkScenarioRegistry(SCENARIOS_DIR)
        task_registry = BenchmarkTaskRegistry(TASKS_V2_DIR, scenario_registry=scenario_registry)
        use_case_registry = IndustrialUseCaseRegistry(USECASES_DIR, scenario_registry=scenario_registry)

        with pytest.raises(ValueError, match="unknown task_id"):
            QuestionBankRegistry(tmp_path, use_case_registry=use_case_registry, task_registry=task_registry)
