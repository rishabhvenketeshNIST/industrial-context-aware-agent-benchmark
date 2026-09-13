"""
M13-C: discovers and validates `BenchmarkTask`s, cross-checked against a
`BenchmarkScenarioRegistry` -- the checks a single `BenchmarkTask`
cannot make on its own (it has no reference to the scenario registry),
kept here rather than smuggled into the model itself.

Layout: one YAML file per scenario under a tasks directory, each holding
a `tasks:` list (not one file per task -- keeps a scenario's several
tasks visibly grouped), e.g.
`configs/benchmark/tasks/d1_reactor_pressure_reading.yaml`.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from icab.scenarios import BenchmarkScenarioRegistry

from .benchmark_task import BenchmarkTask


def load_benchmark_tasks(path: str | Path) -> list[BenchmarkTask]:
    """Load and validate every task in one YAML file's `tasks:` list."""

    path = Path(path)

    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file)

    return [BenchmarkTask.model_validate(entry) for entry in data.get("tasks", [])]


class BenchmarkTaskRegistry:
    """
    Discovers every task under a directory, validating each against a
    `BenchmarkScenarioRegistry`:

      * `task.scenario_id` must name a real, loadable scenario;
      * `task.available_architectures` must be a SUBSET of that
        scenario's own `available_architectures` (a task may further
        RESTRICT what the underlying scenario permits, never grant more
        than the scenario itself was ever synced into).

    Task IDs must be unique across all files in the directory.
    """

    def __init__(self, directory: str | Path, *, scenario_registry: BenchmarkScenarioRegistry):
        self.directory = Path(directory)
        self.scenario_registry = scenario_registry

        if not self.directory.exists():
            raise FileNotFoundError(f"Task directory does not exist: {self.directory}")
        if not self.directory.is_dir():
            raise NotADirectoryError(f"Task path is not a directory: {self.directory}")

        self._tasks = self._discover()

    def _discover(self) -> dict[str, BenchmarkTask]:
        tasks: dict[str, BenchmarkTask] = {}

        for path in sorted(self.directory.glob("*.yaml")):
            for task in load_benchmark_tasks(path):
                if task.task_id in tasks:
                    raise ValueError(f"Duplicate task ID: {task.task_id} (in {path})")

                self._validate_against_scenario(task, source=path)
                tasks[task.task_id] = task

        return tasks

    def _validate_against_scenario(self, task: BenchmarkTask, *, source: Path) -> None:
        try:
            scenario = self.scenario_registry.get(task.scenario_id)
        except KeyError:
            raise ValueError(
                f"Task {task.task_id!r} (in {source}) references unknown scenario "
                f"{task.scenario_id!r}."
            ) from None

        extra = set(task.available_architectures) - set(scenario.available_architectures)
        if extra:
            raise ValueError(
                f"Task {task.task_id!r} (in {source}) declares architecture(s) {sorted(extra)} "
                f"its own scenario {task.scenario_id!r} never makes available "
                f"({scenario.available_architectures})."
            )

    def get(self, task_id: str) -> BenchmarkTask:
        try:
            return self._tasks[task_id]
        except KeyError:
            raise KeyError(f"Unknown task ID: {task_id}") from None

    def list_ids(self) -> list[str]:
        return sorted(self._tasks)

    def for_scenario(self, scenario_id: str) -> list[BenchmarkTask]:
        return [task for task in self._tasks.values() if task.scenario_id == scenario_id]

    def for_difficulty(self, difficulty) -> list[BenchmarkTask]:
        return [task for task in self._tasks.values() if task.difficulty == difficulty]

    def for_task_type(self, task_type) -> list[BenchmarkTask]:
        return [task for task in self._tasks.values() if task.task_type == task_type]

    def __len__(self) -> int:
        return len(self._tasks)

    def __iter__(self):
        return iter(self._tasks.values())
