"""
ICAB v2: tests for the real, checked-in tep-v2 suite -- both that it
loads correctly as a BenchmarkTaskRegistry (mirroring
tests/unit/tasks/test_real_task_inventory.py's discipline for tep-v1),
and that scripts/generate_tep_v2_tasks.py's TASK_TO_USE_CASE mapping
table stays in sync with the real tep-v1 inventory it was derived from.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from icab.benchmark.config import get_suite
from icab.scenarios import BenchmarkScenarioRegistry
from icab.tasks.registry import BenchmarkTaskRegistry
from icab.tasks.splits import load_split_assignment
from icab.usecases import IndustrialUseCaseRegistry

_GENERATOR_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "generate_tep_v2_tasks.py"


def _load_generator_module():
    spec = importlib.util.spec_from_file_location("generate_tep_v2_tasks", _GENERATOR_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def suite():
    return get_suite("tep-v2")


@pytest.fixture(scope="module")
def scenario_registry(suite):
    return BenchmarkScenarioRegistry(suite.scenarios_dir)


@pytest.fixture(scope="module")
def task_registry(suite, scenario_registry):
    return BenchmarkTaskRegistry(suite.tasks_dir, scenario_registry=scenario_registry)


@pytest.fixture(scope="module")
def use_case_registry(scenario_registry):
    return IndustrialUseCaseRegistry("configs/usecases", scenario_registry=scenario_registry)


class TestTepV2SuiteStructure:
    def test_reuses_the_same_scenarios_and_splits_as_tep_v1(self):
        v1 = get_suite("tep-v1")
        v2 = get_suite("tep-v2")
        assert v2.scenarios_dir == v1.scenarios_dir
        assert v2.splits_path == v1.splits_path
        assert v2.tasks_dir != v1.tasks_dir  # only the task inventory differs

    def test_every_task_declares_isa95_level_and_use_case_id(self, task_registry):
        for task in task_registry:
            assert task.isa95_level is not None, task.task_id
            assert task.use_case_id is not None, task.task_id

    def test_every_use_case_id_is_a_real_registered_use_case(self, task_registry, use_case_registry):
        for task in task_registry:
            use_case_registry.get(task.use_case_id)  # raises KeyError if unknown

    def test_every_tasks_isa95_level_matches_its_own_use_cases_isa95_level(self, task_registry, use_case_registry):
        for task in task_registry:
            use_case = use_case_registry.get(task.use_case_id)
            assert task.isa95_level == use_case.isa95_level, task.task_id

    def test_splits_still_cover_every_scenario_tep_v2_tasks_reference(self, task_registry, suite):
        from icab.tasks.splits import validate_split_coverage

        assignment = load_split_assignment(suite.splits_path)
        uncovered = validate_split_coverage(task_registry, assignment)
        assert uncovered == []

    def test_tep_v1_task_content_is_reproduced_byte_for_byte(self, task_registry):
        """
        tep-v2's tasks are supposed to be tep-v1's own tasks PLUS
        isa95_level/use_case_id -- never a re-derivation. Spot-checks
        objective/ground_truth text for one real, known task.
        """

        v1_registry = BenchmarkTaskRegistry("configs/benchmark/tasks", scenario_registry=BenchmarkScenarioRegistry("configs/benchmark/scenarios"))
        v1_task = v1_registry.get("d1-qa-current-pressure")
        v2_task = task_registry.get("d1-qa-current-pressure")

        assert v2_task.objective == v1_task.objective
        assert v2_task.ground_truth == v1_task.ground_truth
        assert v2_task.required_evidence == v1_task.required_evidence

    def test_covers_at_least_equipment_process_cell_and_area_levels(self, task_registry):
        levels = {task.isa95_level.value for task in task_registry}
        assert {"equipment", "process_cell", "area"} <= levels


class TestGeneratorTableStaysInSync:
    """
    Regression guard: if a v1 task is ever added/removed/renamed without
    updating scripts/generate_tep_v2_tasks.py's TASK_TO_USE_CASE table,
    this test fails loudly (the generator script itself also refuses to
    run in that case -- see its own main()).
    """

    def test_task_to_use_case_matches_the_real_tep_v1_inventory_exactly(self):
        module = _load_generator_module()

        v1_registry = BenchmarkTaskRegistry("configs/benchmark/tasks", scenario_registry=BenchmarkScenarioRegistry("configs/benchmark/scenarios"))
        real_task_ids = set(v1_registry.list_ids())
        mapped_task_ids = set(module.TASK_TO_USE_CASE)

        assert real_task_ids == mapped_task_ids

    def test_every_mapped_use_case_id_is_real(self):
        module = _load_generator_module()
        scenario_registry = BenchmarkScenarioRegistry("configs/benchmark/scenarios")
        use_case_registry = IndustrialUseCaseRegistry("configs/usecases", scenario_registry=scenario_registry)

        for use_case_id in set(module.TASK_TO_USE_CASE.values()):
            use_case_registry.get(use_case_id)
