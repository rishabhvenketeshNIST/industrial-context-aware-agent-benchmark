"""
Discovers and cross-validates `Question`s -- the same discipline
`icab.usecases.registry.IndustrialUseCaseRegistry` already applies to
use cases, extended to also check each `Question.realizations` entry
against a REAL `BenchmarkTaskRegistry` (the task must exist, its own
`scenario_id` must match the realization's key, and -- when the task
declares one -- its `isa95_level` must match the question's).

Layout: one YAML file per ISA-95 level under a question-bank directory,
each holding a `questions:` list, e.g. `configs/questions/equipment.yaml`.
An EMPTY (or missing) `questions:` list is legitimate for a currently-
unsupported level (Enterprise/Site/Work Center) -- not an error.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from icab.tasks.isa95 import ISA95Level
from icab.tasks.registry import BenchmarkTaskRegistry
from icab.usecases import IndustrialUseCaseRegistry

from .models import Question


def load_questions(path: str | Path) -> list[Question]:
    """Load and validate every question in one YAML file's `questions:` list."""

    path = Path(path)

    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}

    return [Question.model_validate(entry) for entry in data.get("questions", [])]


class QuestionBankRegistry:
    """
    Discovers every question under a directory, validating each against a
    `IndustrialUseCaseRegistry` (use_case_id must exist and share this
    question's isa95_level) and a `BenchmarkTaskRegistry` (every
    realization must name a real task, for the scenario the mapping
    claims, at the same ISA-95 level).
    """

    def __init__(
        self,
        directory: str | Path,
        *,
        use_case_registry: IndustrialUseCaseRegistry,
        task_registry: BenchmarkTaskRegistry,
    ) -> None:
        self.directory = Path(directory)
        self.use_case_registry = use_case_registry
        self.task_registry = task_registry

        if not self.directory.exists():
            raise FileNotFoundError(f"Question bank directory does not exist: {self.directory}")
        if not self.directory.is_dir():
            raise NotADirectoryError(f"Question bank path is not a directory: {self.directory}")

        self._questions = self._discover()

    def _discover(self) -> dict[str, Question]:
        questions: dict[str, Question] = {}

        for path in sorted(self.directory.glob("*.yaml")):
            for question in load_questions(path):
                if question.question_id in questions:
                    raise ValueError(f"Duplicate question_id: {question.question_id} (in {path})")

                self._validate(question, source=path)
                questions[question.question_id] = question

        return questions

    def _validate(self, question: Question, *, source: Path) -> None:
        try:
            use_case = self.use_case_registry.get(question.use_case_id)
        except KeyError:
            raise ValueError(
                f"Question {question.question_id!r} (in {source}) references unknown use_case_id "
                f"{question.use_case_id!r}."
            ) from None

        if use_case.isa95_level != question.isa95_level:
            raise ValueError(
                f"Question {question.question_id!r} (in {source}) declares isa95_level="
                f"{question.isa95_level.value!r} but its use case {question.use_case_id!r} is at "
                f"{use_case.isa95_level.value!r}."
            )

        for scenario_id, task_id in question.realizations.items():
            try:
                task = self.task_registry.get(task_id)
            except KeyError:
                raise ValueError(
                    f"Question {question.question_id!r} (in {source}) realization for scenario "
                    f"{scenario_id!r} references unknown task_id {task_id!r}."
                ) from None

            if task.scenario_id != scenario_id:
                raise ValueError(
                    f"Question {question.question_id!r} (in {source}): realization key "
                    f"{scenario_id!r} does not match task {task_id!r}'s own scenario_id "
                    f"{task.scenario_id!r}."
                )

            if task.isa95_level is not None and task.isa95_level != question.isa95_level:
                raise ValueError(
                    f"Question {question.question_id!r} (in {source}): realization task {task_id!r} "
                    f"is at isa95_level={task.isa95_level.value!r}, not {question.isa95_level.value!r}."
                )

    def get(self, question_id: str) -> Question:
        try:
            return self._questions[question_id]
        except KeyError:
            raise KeyError(f"Unknown question_id: {question_id}") from None

    def list_ids(self) -> list[str]:
        return sorted(self._questions)

    def for_level(self, level: ISA95Level) -> list[Question]:
        return [q for q in self._questions.values() if q.isa95_level == level]

    def for_use_case(self, use_case_id: str) -> list[Question]:
        return [q for q in self._questions.values() if q.use_case_id == use_case_id]

    def for_tag(self, tag) -> list[Question]:
        return [q for q in self._questions.values() if tag in q.tags]

    def __len__(self) -> int:
        return len(self._questions)

    def __iter__(self):
        return iter(self._questions.values())
