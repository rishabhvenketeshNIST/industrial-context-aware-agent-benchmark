"""Unit tests for icab.questions.validation -- the Section 25 formal question-bank validation report."""

from __future__ import annotations

from icab.questions import validate_question_bank
from icab.scenarios import BenchmarkScenarioRegistry
from icab.tasks.registry import BenchmarkTaskRegistry
from icab.usecases import IndustrialUseCaseRegistry

from icab.questions.registry import QuestionBankRegistry

SCENARIOS_DIR = "configs/benchmark/scenarios"
TASKS_V2_DIR = "configs/benchmark/tasks_v2"
USECASES_DIR = "configs/usecases"


def _registries():
    scenario_registry = BenchmarkScenarioRegistry(SCENARIOS_DIR)
    task_registry = BenchmarkTaskRegistry(TASKS_V2_DIR, scenario_registry=scenario_registry)
    use_case_registry = IndustrialUseCaseRegistry(USECASES_DIR, scenario_registry=scenario_registry)
    return task_registry, use_case_registry


class TestValidateQuestionBank:
    def test_every_level_bank_passes_every_check(self):
        task_registry, use_case_registry = _registries()

        for level in ("enterprise", "site", "area", "work_center", "process_cell", "equipment"):
            registry = QuestionBankRegistry(f"configs/questions/{level}", use_case_registry=use_case_registry, task_registry=task_registry)
            report = validate_question_bank(registry, task_registry, level)

            assert report.total_questions == 50
            assert report.validated_count == 50
            assert report.failed_count == 0
            assert report.all_validated is True

    def test_every_individual_check_is_reported_per_question(self):
        task_registry, use_case_registry = _registries()
        registry = QuestionBankRegistry("configs/questions/equipment", use_case_registry=use_case_registry, task_registry=task_registry)
        report = validate_question_bank(registry, task_registry, "equipment")

        expected_checks = {
            "realizations_resolve_to_real_tasks",
            "answer_is_grounded_in_benchmark_data",
            "correct_isa95_level",
            "expected_evidence_documented",
            "answer_is_deterministically_evaluable",
            "compatible_scenario_exists",
            "context_hypothesis_documented",
            "evaluator_can_score_it",
            "not_a_duplicate",
        }
        for result in report.results:
            assert set(result.checks) == expected_checks
            assert all(result.checks.values())
            assert result.passed is True
            assert result.failure_reasons == []

    def test_all_validated_is_false_for_an_empty_bank(self):
        task_registry, _use_case_registry = _registries()

        class _EmptyRegistry:
            def __iter__(self):
                return iter([])

        report = validate_question_bank(_EmptyRegistry(), task_registry, "enterprise")
        assert report.total_questions == 0
        assert report.all_validated is False  # empty is never "complete," even though failed_count == 0
