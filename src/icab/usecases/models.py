"""
ICAB v2: `IndustrialUseCase` -- the industrial OBJECTIVE a benchmark task
serves, kept explicitly separate from the task itself (the exact
question/objective text) and from the scenario (the process/fault
conditions) -- see the module docstring of `icab.usecases.registry` for
the full v2 concept chain (ISA-95 level -> use case -> scenario ->
context requirement -> representation -> architecture -> agent ->
outcome).

Reuses, rather than re-invents: `icab.scenarios.models.TaskMode`/
`ScenarioDifficulty` (the SAME locked task-type/difficulty concepts a
`BenchmarkTask` uses), `icab.tasks.context_dimensions.ContextDimension`
(the seven locked dimensions), and
`icab.tasks.benchmark_task.EvaluationCriteria` (the SAME binding-score
mechanism a task's own pass/fail criteria already use -- a use case's
`success_criteria` is that same object, not a second scoring concept).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from icab.scenarios.models import ScenarioDifficulty, TaskMode
from icab.tasks.benchmark_task import EvaluationCriteria
from icab.tasks.context_dimensions import ContextDimension
from icab.tasks.isa95 import ISA95Level


class IndustrialUseCase(BaseModel):
    """
    One industrial objective at a specific ISA-95 level -- e.g. "identify
    the equipment implicated by an abnormal measurement" at the Equipment
    level. A use case is INTENT, not a specific question: several
    `BenchmarkTask`s (across scenarios/seeds/architectures) can all serve
    the same use case, each asking a concrete, task-specific question in
    service of it (see `BenchmarkTask.use_case_id`).
    """

    model_config = ConfigDict(extra="forbid")

    use_case_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)

    isa95_level: ISA95Level
    task_type: TaskMode

    #: The context dimensions genuinely necessary to accomplish this use
    #: case -- the NARROW set (see `icab.tasks.context_dimensions`
    #: module docstring: derived from actual evidence, never assigned
    #: because a dimension "sounds appropriate").
    required_context: list[ContextDimension] = Field(min_length=1)
    #: A BROADER set worth testing (required_context plus dimensions that
    #: might plausibly help but aren't assumed necessary) -- the
    #: candidate pool the necessity/composition/sufficiency benchmarks
    #: (icab.analysis) draw context-combination conditions from for this
    #: use case. Always a superset of required_context.
    candidate_context: list[ContextDimension] = Field(min_length=1)

    success_criteria: EvaluationCriteria

    #: Real, registered `BenchmarkScenario` ids this use case is actually
    #: evaluated against -- cross-checked by `IndustrialUseCaseRegistry`
    #: (scenario must exist), the same discipline
    #: `BenchmarkTaskRegistry` already applies to `BenchmarkTask.scenario_id`.
    applicable_scenarios: list[str] = Field(min_length=1)

    difficulty: ScenarioDifficulty

    #: Where this use case's design came from -- e.g. which real tasks'
    #: required_context_dimensions it was derived from, or "new" for a
    #: genuinely new (not v1-task-derived) use case.
    provenance: str = Field(default="icab.usecases")
    version: str = Field(default="1.0.0")

    @model_validator(mode="after")
    def _candidate_context_is_a_superset_of_required_context(self) -> "IndustrialUseCase":
        missing = set(self.required_context) - set(self.candidate_context)
        if missing:
            raise ValueError(
                f"Use case {self.use_case_id!r}: required_context {sorted(missing)} "
                "must also be in candidate_context -- candidate_context is the "
                "broader pool required_context is drawn from, not a separate set."
            )
        return self
