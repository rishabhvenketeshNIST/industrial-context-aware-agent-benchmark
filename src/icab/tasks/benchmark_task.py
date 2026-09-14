"""
M13-C: the ICAB benchmark task model -- what an agent is actually asked
to do, kept explicitly separate from `icab.scenarios.models.BenchmarkScenario`
(which defines the process state/fault/time-series conditions a task is
asked ABOUT). Reuses, rather than duplicates: `icab.scenarios.models
.TaskMode`/`ScenarioDifficulty`/`GroundTruth` are the SAME locked enums/
model a scenario uses, not a second copy.

    BenchmarkScenario  (process state / fault / time-series conditions)
         |
         |  scenario_id (a task always resolves to exactly one scenario)
         v
    BenchmarkTask      (the question, required evidence, evaluation criteria)
         |
         |  evaluated via
         v
    GroundedInvestigationEvaluator.evaluate_task(...)  (icab.evaluation.grounded)

Distinct from the older, unused `icab.tasks.models.InvestigationTask`
(prototype-era, tied to the static `icab.tep.scenarios.TEPScenario` path,
left untouched -- see that module's own docstring).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from icab.scenarios.models import GroundTruth, ScenarioDifficulty, TaskMode
from icab.tasks.isa95 import ISA95Level

from .context_dimensions import ContextDimension, unsupported_dimensions

#: The EvaluationReport score fields a task's `EvaluationCriteria.binding_scores`
#: may name -- kept as an explicit, small whitelist (not "any float field")
#: so a typo or a made-up criterion name fails loudly at task-authoring
#: time rather than silently never binding. Cross-checked directly
#: against `icab.evaluation.grounded.EvaluationReport.model_fields` by
#: tests/unit/tasks/test_benchmark_task.py -- if the evaluator ever
#: renames one of these, that test (not a task author) catches the drift.
KNOWN_SCORE_FIELDS: tuple[str, ...] = (
    "required_evidence_score",
    "canonical_id_score",
    "relationship_score",
    "conclusion_correctness_score",
    "grounding_score",
    "completeness_score",
)


class EvaluationCriteria(BaseModel):
    """
    Which of `GroundedInvestigationEvaluator`'s existing, deterministic
    scores are the BINDING pass/fail criteria for one task -- this does
    NOT introduce a new evaluation mechanism; it selects which of the
    evaluator's already-computed scores matter for THIS task's grading,
    since not every task cares about every dimension (e.g. a D1 QA task
    has no relationships to confirm; a D4 diagnosis task's
    `conclusion_correctness_score` is central).
    """

    model_config = ConfigDict(extra="forbid")

    binding_scores: list[str] = Field(min_length=1)
    #: Minimum value each binding score must reach for the task to count
    #: as passed. A single shared threshold, deliberately simple; a task
    #: needing a looser bar for one score than another should split into
    #: two tasks rather than smuggle in per-score thresholds here.
    pass_threshold: float = Field(default=1.0, ge=0.0, le=1.0)
    #: Explicit acknowledgment of anything this task's ground truth would
    #: ideally check but the current GroundedInvestigationEvaluator
    #: cannot verify deterministically (e.g. "the causal NARRATIVE is
    #: sound," not just "the right nouns are present") -- documented
    #: here rather than silently pretended solved. See
    #: docs/benchmark/evaluation.md.
    known_limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _binding_scores_are_known(self) -> "EvaluationCriteria":
        unknown = [name for name in self.binding_scores if name not in KNOWN_SCORE_FIELDS]
        if unknown:
            raise ValueError(
                f"Unknown binding score(s) {unknown} -- must be one of {KNOWN_SCORE_FIELDS}."
            )
        return self


class BenchmarkTask(BaseModel):
    """
    One benchmark task: a concrete question/objective posed against a
    specific `BenchmarkScenario`'s process state, with its own required
    evidence, context-dimension declaration, architecture restriction,
    hidden ground truth, and evaluation criteria.

    A single scenario may have MULTIPLE tasks (a QA task asking for one
    value, a diagnosis task asking for the root cause, etc., all against
    the same underlying process state) -- this is the intended way to
    get task diversity without inflating the scenario count.
    """

    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(min_length=1)
    scenario_id: str = Field(min_length=1, description="FK into BenchmarkScenarioRegistry.")

    task_type: TaskMode
    difficulty: ScenarioDifficulty

    objective: str = Field(min_length=1, description="The agent-visible question/instruction.")

    #: Architectures THIS TASK permits -- must be a subset of the
    #: underlying scenario's own `available_architectures` (checked at
    #: registry load time, where the scenario is available to check
    #: against -- see icab.tasks.registry.BenchmarkTaskRegistry). Never a
    #: superset: a task cannot grant access to an architecture its
    #: scenario never synced into.
    available_architectures: list[str] = Field(min_length=1)

    required_context_dimensions: list[ContextDimension] = Field(min_length=1)

    #: Canonical ids a grounded answer should reference (mirrors
    #: GroundTruth.expected_evidence, but scoped to THIS task's specific
    #: question, which may be a subset of the underlying scenario's own
    #: expected_evidence).
    required_evidence: list[str] = Field(default_factory=list)
    #: Canonical ids (equipment/measurement/actuator) the investigation
    #: is expected to touch/discover -- broader than required_evidence,
    #: which is specifically what the CONCLUSION should cite.
    expected_entities: list[str] = Field(default_factory=list)
    expected_relationships: list[tuple[str, str, str]] = Field(default_factory=list)
    expected_temporal_evidence: bool = False

    ground_truth: GroundTruth
    evaluation_criteria: EvaluationCriteria

    provenance: str = Field(
        default="icab.benchmark",
        description="Where this task's design came from -- e.g. a fault-catalog entry + scenario ground truth.",
    )
    version: str = Field(default="1.0.0")

    #: ICAB v2: which ISA-95 level and industrial use case (icab.usecases)
    #: this task serves -- both OPTIONAL/additive so every existing
    #: tep-v1 task keeps validating unchanged (task_id, in effect,
    #: reused directly for tep-v2 by adding these two fields rather than
    #: duplicating task content -- see scripts/generate_tep_v2_tasks.py).
    #: `use_case_id` is not cross-validated against
    #: IndustrialUseCaseRegistry here (BenchmarkTask has no reference to
    #: one, mirroring how scenario_id is validated by
    #: BenchmarkTaskRegistry rather than by the model itself) -- see
    #: icab.usecases.registry / icab.benchmark.config for where that
    #: cross-check happens for the tep-v2 suite.
    isa95_level: ISA95Level | None = None
    use_case_id: str | None = None

    @model_validator(mode="after")
    def _dimensions_are_architecturally_supportable(self) -> "BenchmarkTask":
        """
        Necessary-condition guard against "assigning dimensions merely
        because they sound appropriate": a task cannot declare a context
        dimension its own `available_architectures` has no way to
        supply. See icab.tasks.context_dimensions module docstring for
        why this is necessary, not sufficient.
        """

        unsupported = unsupported_dimensions(
            self.required_context_dimensions, self.available_architectures
        )
        if unsupported:
            raise ValueError(
                f"Task {self.task_id!r} declares context dimension(s) {unsupported} "
                f"that no architecture in {self.available_architectures} can supply."
            )
        return self

    @model_validator(mode="after")
    def _expected_temporal_evidence_implies_a_temporal_dimension(self) -> "BenchmarkTask":
        if self.expected_temporal_evidence and not (
            ContextDimension.C4_TEMPORAL in self.required_context_dimensions
            or ContextDimension.C7_HISTORICAL in self.required_context_dimensions
        ):
            raise ValueError(
                f"Task {self.task_id!r} sets expected_temporal_evidence=True but declares "
                "neither C4 (Temporal) nor C7 (Historical) in required_context_dimensions."
            )
        return self

    @model_validator(mode="after")
    def _expected_relationships_imply_a_relational_dimension(self) -> "BenchmarkTask":
        if self.expected_relationships and not (
            ContextDimension.C3_RELATIONAL in self.required_context_dimensions
            or ContextDimension.C6_PROCEDURAL in self.required_context_dimensions
        ):
            raise ValueError(
                f"Task {self.task_id!r} declares expected_relationships but neither C3 "
                "(Relational) nor C6 (Procedural) in required_context_dimensions."
            )
        return self
