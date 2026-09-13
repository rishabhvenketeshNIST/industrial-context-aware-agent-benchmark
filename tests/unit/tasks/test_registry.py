"""
M13-C: BenchmarkTaskRegistry -- discovery, uniqueness, scenario/task
linkage validation, and deterministic loading, against a small synthetic
task-directory fixture (NOT the real configs/benchmark/tasks/ -- that is
covered by tests/unit/tasks/test_real_task_inventory.py, which loads the
actual checked-in tasks).
"""

from pathlib import Path

import pytest
import yaml

from icab.scenarios import BenchmarkScenarioRegistry
from icab.tasks.registry import BenchmarkTaskRegistry, load_benchmark_tasks

SCENARIOS_DIR = "configs/benchmark/scenarios"


def _write_tasks_file(directory: Path, filename: str, tasks: list[dict]) -> None:
    (directory / filename).write_text(yaml.safe_dump({"tasks": tasks}), encoding="utf-8")


def _minimal_task(task_id: str, *, scenario_id: str = "d1_reactor_pressure_reading", architectures=None) -> dict:
    return {
        "task_id": task_id,
        "scenario_id": scenario_id,
        "task_type": "qa",
        "difficulty": "D1",
        "objective": "What is x?",
        "available_architectures": architectures or ["historian"],
        "required_context_dimensions": ["C5"],
        "ground_truth": {"conclusion": "x is normal."},
        "evaluation_criteria": {"binding_scores": ["required_evidence_score"]},
    }


def test_registry_discovers_tasks_across_multiple_files(tmp_path):
    _write_tasks_file(tmp_path, "a.yaml", [_minimal_task("t1"), _minimal_task("t2")])
    _write_tasks_file(tmp_path, "b.yaml", [_minimal_task("t3")])

    registry = BenchmarkTaskRegistry(tmp_path, scenario_registry=BenchmarkScenarioRegistry(SCENARIOS_DIR))

    assert len(registry) == 3
    assert registry.list_ids() == ["t1", "t2", "t3"]


def test_registry_rejects_duplicate_task_ids_across_files(tmp_path):
    _write_tasks_file(tmp_path, "a.yaml", [_minimal_task("dup")])
    _write_tasks_file(tmp_path, "b.yaml", [_minimal_task("dup")])

    with pytest.raises(ValueError, match="Duplicate task ID"):
        BenchmarkTaskRegistry(tmp_path, scenario_registry=BenchmarkScenarioRegistry(SCENARIOS_DIR))


def test_registry_rejects_a_task_referencing_an_unknown_scenario(tmp_path):
    _write_tasks_file(tmp_path, "a.yaml", [_minimal_task("t1", scenario_id="not_a_real_scenario")])

    with pytest.raises(ValueError, match="unknown scenario"):
        BenchmarkTaskRegistry(tmp_path, scenario_registry=BenchmarkScenarioRegistry(SCENARIOS_DIR))


def test_registry_rejects_a_task_granting_more_architectures_than_its_scenario():
    """d1_reactor_pressure_reading only ever makes `historian` available --
    a task claiming `knowledge_graph` too would grant access to an
    architecture the scenario never synced into."""

    scenario_registry = BenchmarkScenarioRegistry(SCENARIOS_DIR)

    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_tasks_file(
            tmp_path, "a.yaml",
            [_minimal_task("t1", architectures=["historian", "knowledge_graph"])],
        )

        with pytest.raises(ValueError, match="never makes available"):
            BenchmarkTaskRegistry(tmp_path, scenario_registry=scenario_registry)


def test_registry_get_and_lookup_helpers(tmp_path):
    _write_tasks_file(
        tmp_path, "a.yaml",
        [_minimal_task("t1"), _minimal_task("t2", scenario_id="d2_reactor_context_combination", architectures=["historian", "knowledge_graph"])],
    )

    registry = BenchmarkTaskRegistry(tmp_path, scenario_registry=BenchmarkScenarioRegistry(SCENARIOS_DIR))

    assert registry.get("t1").task_id == "t1"
    with pytest.raises(KeyError):
        registry.get("not_a_real_task")

    assert [task.task_id for task in registry.for_scenario("d1_reactor_pressure_reading")] == ["t1"]
    assert [task.task_id for task in registry] == ["t1", "t2"]


def test_registry_loading_is_deterministic(tmp_path):
    """Same directory contents -> same list_ids() order across repeated loads."""

    _write_tasks_file(tmp_path, "z.yaml", [_minimal_task("t3")])
    _write_tasks_file(tmp_path, "a.yaml", [_minimal_task("t1"), _minimal_task("t2")])

    scenario_registry = BenchmarkScenarioRegistry(SCENARIOS_DIR)
    first = BenchmarkTaskRegistry(tmp_path, scenario_registry=scenario_registry).list_ids()
    second = BenchmarkTaskRegistry(tmp_path, scenario_registry=scenario_registry).list_ids()

    assert first == second == ["t1", "t2", "t3"]


def test_load_benchmark_tasks_reads_the_tasks_list_from_one_file(tmp_path):
    _write_tasks_file(tmp_path, "only.yaml", [_minimal_task("t1"), _minimal_task("t2")])

    tasks = load_benchmark_tasks(tmp_path / "only.yaml")

    assert [task.task_id for task in tasks] == ["t1", "t2"]
