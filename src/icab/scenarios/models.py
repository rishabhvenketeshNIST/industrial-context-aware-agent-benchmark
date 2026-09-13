"""
The benchmark investigation scenario model (M5).

Distinct from ``icab.tep.scenarios.TEPScenario`` (a static measurement
snapshot used by the original prototype path): a ``BenchmarkScenario``
drives the *real* TEP simulator (``icab.tep.simulator.TEPSimulator``) over
time, with a deterministic seed, an optional fault schedule, and
structured, checkable ground truth -- so an investigation can require
combining live/historical/relational context rather than being a
keyword-matching exercise over a single static fact.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ScenarioDifficulty(StrEnum):
    """
    ICAB scenario difficulty levels (locked research concept).

    D1 straightforward; D2 requires combining sources; D3 requires
    relationships/history; D4 open-ended investigation.
    """

    D1 = "D1"
    D2 = "D2"
    D3 = "D3"
    D4 = "D4"


class TaskMode(StrEnum):
    """ICAB task modes (locked research concept)."""

    QA = "qa"
    INVESTIGATION = "investigation"
    DIAGNOSIS = "diagnosis"


class FaultSchedule(BaseModel):
    """
    A TEP disturbance (IDV) activated at a specific point in simulated
    time -- the scenario-authoring surface for
    `icab.tep.simulator.TEPSimulator.inject_fault`. This is deliberately
    lean: `disturbance` is the simulator's own real fault identifier (not
    a second, ICAB-invented id), and the disturbance's own name/
    provenance/empirical-verification status live in the separate
    `icab.tep.faults.FaultCatalogEntry` (M13-B) -- one authoritative
    place per concept, not duplicated here.
    """

    model_config = ConfigDict(extra="forbid")

    disturbance: str = Field(min_length=1, description="e.g. 'idv_04'")
    activate_at_hours: float = Field(ge=0.0)
    #: M13-B: how long the fault stays active before being cleared, in
    #: simulated hours. None (default) preserves pre-M13-B behavior: once
    #: activated, a fault is never cleared for the rest of the scenario.
    duration_hours: float | None = Field(default=None, gt=0.0)
    magnitude: float = Field(default=1.0)
    description: str | None = None


class GroundTruth(BaseModel):
    """
    Structured, checkable ground truth for a benchmark scenario.

    Kept as canonical IDs / disturbance names (not free text) wherever
    possible, so scoring can check structured fields rather than relying
    only on keyword matching in a text conclusion (a locked research
    quality rule).
    """

    model_config = ConfigDict(extra="forbid")

    conclusion: str = Field(
        min_length=1,
        description="Reference conclusion an evaluator/human can compare an agent's answer against.",
    )
    root_cause_disturbance: str | None = Field(
        default=None,
        description="The TEP disturbance name (e.g. 'idv_04') actually responsible, if any.",
    )
    affected_measurements: list[str] = Field(
        default_factory=list,
        description="Canonical measurement ids expected to show the effect.",
    )
    affected_equipment: list[str] = Field(
        default_factory=list,
        description="Canonical equipment ids expected to be implicated.",
    )
    expected_relationships: list[tuple[str, str, str]] = Field(
        default_factory=list,
        description="(subject, predicate, object) canonical-id triples the KG should confirm.",
    )
    expected_evidence: list[str] = Field(
        default_factory=list,
        description="Canonical ids/identifiers a grounded answer should reference.",
    )


class BenchmarkScenario(BaseModel):
    """A full ICAB investigation scenario driven by the real TEP simulator."""

    model_config = ConfigDict(extra="forbid")

    scenario_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str | None = None
    difficulty: ScenarioDifficulty
    task_mode: TaskMode = TaskMode.INVESTIGATION

    objective: str = Field(min_length=1)

    seed: int
    warmup_hours: float = Field(default=0.0, ge=0.0)
    duration_hours: float = Field(gt=0.0)
    sync_interval_hours: float = Field(
        default=0.25,
        gt=0.0,
        description=(
            "How often the running simulator's state is pushed into the "
            "historian/knowledge graph/MQTT during the scenario -- this is "
            "what gives D3/D4 scenarios a real historical trend to query, "
            "rather than a single final snapshot."
        ),
    )

    faults: list[FaultSchedule] = Field(default_factory=list)

    available_architectures: list[str] = Field(
        default_factory=lambda: [
            "historian",
            "knowledge_graph",
            "uns",
            "opcua",
            "mqtt",
        ],
        description=(
            "Which context architectures' tools an agent is given for this "
            "scenario -- restricting this is what makes architecture "
            "comparisons meaningful (an agent cannot just use whichever "
            "tool is easiest)."
        ),
    )

    ground_truth: GroundTruth

    @model_validator(mode="after")
    def _objective_must_not_leak_the_fault_schedule(self) -> "BenchmarkScenario":
        """
        M13-B technical safeguard (not just authoring discipline): the
        agent only ever sees `objective` (never `ground_truth`/`faults`
        directly -- see icab.agent.llm.agent.LLMInvestigationAgent and
        icab.experiments.ExperimentRunner, neither of which reads either
        field), so this is the one place a fault id COULD accidentally
        leak into agent-visible text. Reject that at construction time
        rather than relying on scenario authors to remember not to.
        """

        objective_lower = self.objective.lower()

        for fault in self.faults:
            if fault.disturbance.lower() in objective_lower:
                raise ValueError(
                    f"Scenario {self.scenario_id!r}'s objective must not mention its own "
                    f"fault identifier {fault.disturbance!r} -- the agent must discover "
                    "what is wrong, not be told. See GroundTruth.root_cause_disturbance "
                    "for where this belongs instead."
                )

        return self
