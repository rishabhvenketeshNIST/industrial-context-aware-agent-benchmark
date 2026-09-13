"""
M13-C: split integrity -- every scenario assigned to exactly one split,
no leakage (two tasks sharing a scenario always land in the same split),
and the real checked-in configs/benchmark/splits.yaml covers every real
scenario a real task references.
"""

import pytest
from pydantic import ValidationError

from icab.scenarios import BenchmarkScenarioRegistry
from icab.tasks import (
    BenchmarkTaskRegistry,
    SplitAssignment,
    TaskSplit,
    load_split_assignment,
    tasks_in_split,
    validate_split_coverage,
)

SCENARIOS_DIR = "configs/benchmark/scenarios"
TASKS_DIR = "configs/benchmark/tasks"
SPLITS_PATH = "configs/benchmark/splits.yaml"


def _registry() -> BenchmarkTaskRegistry:
    return BenchmarkTaskRegistry(TASKS_DIR, scenario_registry=BenchmarkScenarioRegistry(SCENARIOS_DIR))


def test_split_assignment_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        SplitAssignment(development=["s1"], validation=[], test=[], not_a_real_field="x")


def test_scenario_in_two_splits_resolves_to_the_first_checked_not_silently_both():
    assignment = SplitAssignment(development=["s1"], validation=["s1"], test=[])

    # This is exactly why the real splits.yaml must be authored carefully
    # (see the next test group) -- split_for_scenario has no way to
    # detect the duplication itself, it just returns the first match.
    assert assignment.split_for_scenario("s1") == TaskSplit.DEVELOPMENT


def test_real_splits_file_assigns_every_scenario_to_at_most_one_split():
    assignment = load_split_assignment(SPLITS_PATH)

    all_ids = [*assignment.development, *assignment.validation, *assignment.test]
    assert len(all_ids) == len(set(all_ids)), "a scenario appears in more than one split"


def test_real_splits_file_covers_every_scenario_a_real_task_references():
    registry = _registry()
    assignment = load_split_assignment(SPLITS_PATH)

    assert validate_split_coverage(registry, assignment) == []


def test_two_tasks_sharing_a_scenario_always_land_in_the_same_split():
    """The actual leakage-prevention property: no scenario with more than
    one real task has its tasks split across development/validation/test."""

    registry = _registry()
    assignment = load_split_assignment(SPLITS_PATH)

    for scenario_id in {task.scenario_id for task in registry}:
        tasks_for_scenario = registry.for_scenario(scenario_id)
        splits = {assignment.split_for_scenario(task.scenario_id) for task in tasks_for_scenario}
        assert len(splits) == 1, f"{scenario_id}'s tasks span multiple splits: {splits}"


def test_tasks_in_split_partitions_the_whole_registry_with_no_overlap():
    registry = _registry()
    assignment = load_split_assignment(SPLITS_PATH)

    development = {t.task_id for t in tasks_in_split(registry, TaskSplit.DEVELOPMENT, assignment=assignment)}
    validation = {t.task_id for t in tasks_in_split(registry, TaskSplit.VALIDATION, assignment=assignment)}
    test_split = {t.task_id for t in tasks_in_split(registry, TaskSplit.TEST, assignment=assignment)}

    assert development & validation == set()
    assert development & test_split == set()
    assert validation & test_split == set()
    assert development | validation | test_split == {task.task_id for task in registry}


def test_split_for_unassigned_scenario_raises():
    assignment = SplitAssignment(development=["s1"], validation=[], test=[])

    with pytest.raises(KeyError):
        assignment.split_for_scenario("not_assigned_anywhere")
