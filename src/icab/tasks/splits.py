"""
M13-C: benchmark task splits (development / validation / test).

Grouped by SCENARIO (not randomly per task), specifically to prevent
leakage: two tasks against the same scenario share the exact same
underlying process trajectory (same seed, same fault, same synced
historian/KG/MQTT state) -- if one such task were used to develop/tune an
agent or evaluator and a near-duplicate sibling task from the SAME
scenario ended up in the test split, "unseen" test performance would
partly reflect memorized/tuned familiarity with that specific process
trajectory, not genuine generalization. Assigning by scenario_id makes
that structurally impossible: every task for a given scenario is always
in the same split.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from .registry import BenchmarkTaskRegistry

DEFAULT_SPLITS_PATH = Path("configs/benchmark/splits.yaml")


class TaskSplit(StrEnum):
    DEVELOPMENT = "development"
    VALIDATION = "validation"
    TEST = "test"


class SplitAssignment(BaseModel):
    """Which split each SCENARIO (not task) belongs to -- see module docstring."""

    model_config = ConfigDict(extra="forbid")

    development: list[str] = Field(default_factory=list)
    validation: list[str] = Field(default_factory=list)
    test: list[str] = Field(default_factory=list)

    def split_for_scenario(self, scenario_id: str) -> TaskSplit:
        if scenario_id in self.development:
            return TaskSplit.DEVELOPMENT
        if scenario_id in self.validation:
            return TaskSplit.VALIDATION
        if scenario_id in self.test:
            return TaskSplit.TEST
        raise KeyError(f"Scenario {scenario_id!r} is not assigned to any split.")

    def scenario_ids(self) -> set[str]:
        return {*self.development, *self.validation, *self.test}


def load_split_assignment(path: str | Path = DEFAULT_SPLITS_PATH) -> SplitAssignment:
    with Path(path).open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file)
    return SplitAssignment.model_validate(data)


def tasks_in_split(
    registry: BenchmarkTaskRegistry,
    split: TaskSplit,
    *,
    assignment: SplitAssignment | None = None,
):
    """Every task in `registry` whose scenario is assigned to `split`."""

    assignment = assignment or load_split_assignment()
    scenario_ids = {
        TaskSplit.DEVELOPMENT: assignment.development,
        TaskSplit.VALIDATION: assignment.validation,
        TaskSplit.TEST: assignment.test,
    }[split]

    return [task for task in registry if task.scenario_id in scenario_ids]


def validate_split_coverage(
    registry: BenchmarkTaskRegistry,
    assignment: SplitAssignment,
) -> list[str]:
    """
    Scenario ids referenced by tasks in `registry` but not assigned to
    ANY split -- should be empty; a non-empty result means some task's
    evidence would never be exercised by any split-scoped experiment.
    """

    task_scenario_ids = {task.scenario_id for task in registry}
    return sorted(task_scenario_ids - assignment.scenario_ids())
