"""
The M9 experiment schema: what to run (`ExperimentConfig`) and what a
completed run produced (`ExperimentRecord`).

Distinct from `icab.experiments.architecture_comparison`
(`ArchitectureComparisonRunner`/`ArchitectureComparisonResult`), which is
unchanged: that module runs `ArchitectureAwareAgent` over an
`InvestigationCase` and stays exactly as it was before M9. This module is
the newer, richer path -- a full experiment record over a
`BenchmarkScenario` (icab.scenarios, M5), covering any agent
(deterministic or LLM) and persisted for later aggregation.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from icab.agent.interface import InvestigationResult
from icab.evaluation.grounded import EvaluationReport


class AgentType(StrEnum):
    """Which agent implementation ran the investigation."""

    DETERMINISTIC = "deterministic"
    LLM = "llm"


class DeterministicAgentKind(StrEnum):
    """
    Which deterministic baseline agent to run when
    ``ExperimentConfig.agent_type == AgentType.DETERMINISTIC``.

    Unlike the LLM agent, none of these support an arbitrary
    ``architectures`` list: ``STRUCTURED_RETRIEVAL``/``CONTEXT_AWARE`` are
    fixed-strategy baselines with a hard-coded tool sequence (their
    ``architectures`` config value is recorded for labeling only, not
    enforced); ``ARCHITECTURE_AWARE`` takes exactly one architecture. This
    is a real, documented limitation of the existing baselines, not an
    oversight in the experiment schema.
    """

    STRUCTURED_RETRIEVAL = "structured_retrieval"
    CONTEXT_AWARE = "context_aware"
    ARCHITECTURE_AWARE = "architecture_aware"


class ExperimentRunStatus(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"


class ExperimentConfig(BaseModel):
    """
    One experiment run's configuration -- everything that determines what
    was run, held explicit rather than left to implicit agent behavior.
    """

    model_config = ConfigDict(extra="forbid")

    scenario_id: str = Field(min_length=1)

    #: Which context architectures' tools the agent is given -- explicit,
    #: not inherited implicitly from the scenario (though it usually
    #: matches `BenchmarkScenario.available_architectures`). Enforced for
    #: the LLM agent via `tools_for_architectures`; see
    #: `DeterministicAgentKind` for the deterministic baselines' caveat.
    architectures: list[str] = Field(min_length=1)

    agent_type: AgentType

    #: Required when agent_type == DETERMINISTIC.
    deterministic_agent: DeterministicAgentKind | None = None

    #: LLM generation config -- recorded regardless of whether it was
    #: explicitly set, so it's auditable even when a default was used.
    #: None when agent_type == DETERMINISTIC.
    llm_model: str | None = None
    llm_temperature: float | None = None

    #: Tool/context budget. LLMInvestigationAgent enforces this as
    #: max_steps; deterministic baselines have no configurable budget (see
    #: DeterministicAgentKind) and always record None here regardless of
    #: what was passed.
    max_steps: int | None = None

    #: Experiment-level seed, independent of the scenario's own
    #: `simulation_seed` -- reserved for any agent-side stochasticity
    #: (e.g. sampling/tie-breaking) distinct from the physical process.
    #: Neither current agent implementation is stochastic beyond LLM
    #: sampling itself (governed by llm_temperature/provider), so this is
    #: currently recorded for forward-compatibility and audit rather than
    #: consumed by anything.
    random_seed: int | None = None


class ExperimentRecord(BaseModel):
    """
    One completed (or failed) experiment run: the config it was run with,
    the scenario conditions that were actually used, the result, the
    evaluation, and enough metadata to reproduce and audit it later.

    The full trace is intentionally NOT embedded here -- see
    `icab.experiments.storage.ExperimentResultStore`, which persists this
    record under `results/raw/`, the trace under `results/traces/`, and
    the evaluation under `results/evaluations/` separately, linked by
    `run_id`.
    """

    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(min_length=1)
    experiment_id: str = Field(
        min_length=1,
        description="Groups related runs (e.g. an architecture sweep) together.",
    )

    config: ExperimentConfig

    scenario_difficulty: str
    simulation_seed: int = Field(
        description="The BenchmarkScenario's own seed -- drives the TEP simulator."
    )

    icab_version: str | None = None

    started_at: datetime
    completed_at: datetime

    status: ExperimentRunStatus
    error: str | None = None

    result: InvestigationResult | None = None
    evaluation: EvaluationReport | None = None
    trace_event_count: int = 0
