"""
Question -> Question Instance -> Repetition -> Experiment Run -> Trace.

A `Question` (icab.questions.models) is the semantic task. A
`QuestionInstance` is that question fixed to one concrete: scenario,
architecture arm, and agent configuration -- everything that must be
held constant for repeated EXECUTIONS of it to be comparable at all. A
`Repetition` is not a separate model: it is simply one more
`icab.experiments.models.ExperimentConfig.repetition` value (the same
field M13-D already introduced) run against the SAME `QuestionInstance`
-- reused, not reinvented.
"""

from __future__ import annotations

import hashlib
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class RepetitionMode(StrEnum):
    """
    Why a given batch of runs against the same Question was generated --
    recorded on each resulting `ExperimentConfig.repetition_mode` for
    traceability/filtering, per the ICAB context-requirement direction's
    explicit "record which type was used."
    """

    #: Same question, scenario, context condition, architecture, AND
    #: agent configuration, executed repeatedly -- measures LLM
    #: stochasticity/reproducibility/answer variance, holding the
    #: process condition itself fixed.
    EXACT = "exact"
    #: Same SEMANTIC question, deliberately run against a DIFFERENT
    #: scenario (a different QuestionInstance, same Question) --
    #: measures robustness/generalization/scenario sensitivity, not
    #: agent stochasticity.
    CONTROLLED_VARIATION = "controlled_variation"


class QuestionInstance(BaseModel):
    """
    One concrete realization of a `Question`: a fixed scenario,
    architecture arm, and agent configuration. Repetitions of the SAME
    instance share this exact tuple; a controlled-variation batch
    produces one instance PER varied scenario, each with its own
    `instance_id`.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    question_id: str
    scenario_id: str
    #: Canonical (sorted) architecture arm -- matches
    #: `ExperimentConfig.architectures`, just deduplicated/sorted for a
    #: stable id.
    architectures: tuple[str, ...]
    agent: str  # "llm" | "baseline" | a legacy DeterministicAgentKind value
    llm_model: str | None = None
    llm_temperature: float | None = None

    instance_id: str = Field(min_length=1)

    @staticmethod
    def build(
        *,
        question_id: str,
        scenario_id: str,
        architectures: list[str] | tuple[str, ...],
        agent: str,
        llm_model: str | None = None,
        llm_temperature: float | None = None,
    ) -> "QuestionInstance":
        sorted_archs = tuple(sorted(set(architectures)))
        instance_id = instance_id_for(
            question_id=question_id,
            scenario_id=scenario_id,
            architectures=sorted_archs,
            agent=agent,
            llm_model=llm_model,
            llm_temperature=llm_temperature,
        )
        return QuestionInstance(
            question_id=question_id,
            scenario_id=scenario_id,
            architectures=sorted_archs,
            agent=agent,
            llm_model=llm_model,
            llm_temperature=llm_temperature,
            instance_id=instance_id,
        )


def instance_id_for(
    *,
    question_id: str,
    scenario_id: str,
    architectures: tuple[str, ...],
    agent: str,
    llm_model: str | None,
    llm_temperature: float | None,
) -> str:
    """
    A stable, human-legible-prefix id: the readable parts up front (so a
    `results/<level>/experiments/` filename stays inspectable), a short
    hash suffix to keep it unique and bounded-length even for a long
    architecture arm / model name.
    """

    arch_label = "+".join(sorted(architectures)) or "none"
    readable = f"{question_id}--{scenario_id}--{arch_label}--{agent}"

    digest_input = f"{readable}--{llm_model}--{llm_temperature}"
    digest = hashlib.sha256(digest_input.encode("utf-8")).hexdigest()[:8]

    return f"{readable}--{digest}"
