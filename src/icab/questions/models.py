"""
ICAB question banks: `Question` is the SEMANTIC task -- "what is being
asked, in principle" -- kept explicitly separate from the concrete,
scenario-specific `icab.tasks.benchmark_task.BenchmarkTask` that already
carries a fixed ground truth/evaluation criteria for ONE scenario's real
values.

This is deliberately NOT a second execution/evaluation path: a
`Question` is realized, per compatible scenario, by an EXISTING,
unmodified `BenchmarkTask` (see `Question.realizations`) -- when a
`QuestionInstance` (icab.questions.instance) is actually run, it resolves
to that real `BenchmarkTask` and goes through the exact same
`ExperimentRunner.run_task` / `GroundedInvestigationEvaluator.evaluate_task`
path every other ICAB v2 task already uses. `Question` only adds the
catalog-level metadata a single `BenchmarkTask` doesn't carry: which
OTHER scenarios the same semantic question could, in principle, also be
asked under (`compatible_scenarios`, a superset of `realizations`'
keys), a design-time (not yet experimentally checked) context hypothesis,
an expected-answer-type classification, a reusable taxonomy tag set, and
its own independent version/validation-status lifecycle.

    empirically_demonstrated_required_context (what necessity analysis
    concludes, per icab.analysis.necessity) is DELIBERATELY NOT a field
    on this model -- it is a derived ANALYSIS OUTPUT, computed only from
    already-persisted experiment records, never a static catalog
    property. Conflating the two is exactly the mistake this model
    exists to prevent (see module docstring of
    icab.tasks.context_dimensions for the same principle applied to
    BenchmarkTask.required_context_dimensions).
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from icab.scenarios.models import TaskMode
from icab.tasks.context_dimensions import ContextDimension
from icab.tasks.isa95 import ISA95Level

from .taxonomy import QuestionCategory


class QuestionDifficulty(StrEnum):
    """
    Reasoning/information-requirement difficulty -- ORTHOGONAL to
    `icab.scenarios.models.ScenarioDifficulty` (D1-D4, which describes
    the underlying PROCESS/FAULT condition's own complexity, not the
    question's). A `basic` question can be asked against a `D4` scenario
    and vice versa.
    """

    BASIC = "basic"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class ExpectedAnswerType(StrEnum):
    """What SHAPE of answer this question expects -- informs which evaluator scores are meaningful, not a new scoring mechanism."""

    NUMERIC_VALUE = "numeric_value"
    ENTITY_ID = "entity_id"
    ENTITY_LIST = "entity_list"
    BOOLEAN = "boolean"
    ROOT_CAUSE_CATEGORY = "root_cause_category"
    RELATIONSHIP_CONFIRMATION = "relationship_confirmation"
    FREE_TEXT_EXPLANATION = "free_text_explanation"


class ValidationStatus(StrEnum):
    """
    Where a question is in its own authoring lifecycle -- distinct from
    whether an individual EXPERIMENT RUN against it succeeded.
    `VALIDATED` means at least one real, real-stack integration run has
    exercised it end to end (mirrors the pre-existing M13-C convention
    of representative-task integration verification); `DRAFT` means it
    passes model validation but has not yet been run for real.
    """

    DRAFT = "draft"
    VALIDATED = "validated"
    DEPRECATED = "deprecated"


class DifficultyFactors(BaseModel):
    """
    Why a question was assigned its `QuestionDifficulty` -- recorded
    factors, not a formula (the ICAB v2 direction is explicit: base
    difficulty on actual information/reasoning requirements, but this is
    a documented judgment call per question, not an automated score).
    """

    model_config = ConfigDict(extra="forbid")

    n_sources: int = Field(ge=1, description="How many distinct architectures/context dimensions this question genuinely draws on.")
    relationship_depth: int = Field(default=0, ge=0, description="How many relationship hops the answer requires (0 = none).")
    requires_temporal_reasoning: bool = False
    requires_cross_source_reasoning: bool = False
    evidence_requirement_count: int = Field(default=1, ge=0, description="How many distinct pieces of evidence the ground truth requires.")


class Question(BaseModel):
    """One semantic question -- see module docstring for how it relates to `BenchmarkTask`."""

    model_config = ConfigDict(extra="forbid")

    question_id: str = Field(min_length=1)
    benchmark_id: str = Field(min_length=1, description="Which icab.benchmark.levels.ISA95BenchmarkDefinition.benchmark_id this belongs to.")
    use_case_id: str = Field(min_length=1)
    isa95_level: ISA95Level

    question_text: str = Field(min_length=1, description="The agent-visible question/instruction, scenario-independent phrasing.")
    task_type: TaskMode
    objective: str = Field(min_length=1, description="A human-readable restatement of what a correct answer must accomplish.")

    #: Design-time HYPOTHESIS about which context dimensions this
    #: question needs -- see module docstring: never conflated with
    #: empirically-demonstrated necessity, which is a separate, derived
    #: analysis output (icab.analysis.necessity), not a field here.
    hypothesized_required_context: list[ContextDimension] = Field(min_length=1)

    expected_evidence_description: str = Field(
        min_length=1, description="What kind of evidence a grounded answer should cite, in general terms (concrete canonical ids live on the per-scenario BenchmarkTask, not here)."
    )
    expected_answer_type: ExpectedAnswerType

    #: Every scenario this question is, IN PRINCIPLE, meaningful under --
    #: a superset of `realizations`' keys. A scenario can be listed here
    #: before a concrete BenchmarkTask realization exists for it (framework-
    #: ready for future extension), but every KEY in `realizations` must
    #: appear here too (checked by `QuestionBankRegistry`).
    compatible_scenarios: list[str] = Field(min_length=1)
    #: scenario_id -> the real, existing BenchmarkTask.task_id that
    #: concretely realizes this question for that scenario (its actual
    #: ground_truth/evaluation_criteria/available_architectures) --
    #: cross-validated by QuestionBankRegistry against a real
    #: BenchmarkTaskRegistry.
    realizations: dict[str, str] = Field(min_length=1)

    difficulty: QuestionDifficulty
    difficulty_factors: DifficultyFactors

    tags: list[QuestionCategory] = Field(min_length=1)

    version: str = Field(default="1.0.0")
    validation_status: ValidationStatus = ValidationStatus.DRAFT

    provenance: str = Field(default="icab.questions", description="Where this question's design came from -- e.g. which real task(s) it was derived from, or 'new' for a genuinely new question.")

    @model_validator(mode="after")
    def _realizations_are_a_subset_of_compatible_scenarios(self) -> "Question":
        extra = set(self.realizations) - set(self.compatible_scenarios)
        if extra:
            raise ValueError(
                f"Question {self.question_id!r}: realizations {sorted(extra)} are not listed in "
                f"compatible_scenarios {self.compatible_scenarios} -- every realized scenario must "
                "also be declared compatible."
            )
        return self
