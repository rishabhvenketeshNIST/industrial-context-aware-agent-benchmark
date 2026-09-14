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

import hashlib
import json
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from icab.agent.interface import InvestigationResult
from icab.evaluation.grounded import EvaluationReport
from icab.evaluation.information_flow import InformationFlowReport


class AgentType(StrEnum):
    """Which agent implementation ran the investigation."""

    DETERMINISTIC = "deterministic"
    LLM = "llm"


class DeterministicAgentKind(StrEnum):
    """
    Which deterministic baseline agent to run when
    ``ExperimentConfig.agent_type == AgentType.DETERMINISTIC``.

    ``STRUCTURED_RETRIEVAL``/``CONTEXT_AWARE``/``ARCHITECTURE_AWARE`` are
    the pre-M5 *legacy* baselines: hard-coded to the static-prototype
    canonical ids/paths (and, for ARCHITECTURE_AWARE's OPC UA path, a
    different OPC UA server entirely), so they do not see a real
    BenchmarkScenario's own data. Verified live during M9: a legacy-baseline
    run against a real scenario concluded with the OLD static fixture value,
    not the scenario's actual simulated state. Kept unchanged (regression/
    control value only -- see RunValidity.LEGACY_CONTROL_ONLY) rather than
    updated, per an explicit decision not to modify these agents.

    ``SCENARIO_AWARE`` is the M9 real-data-aware baseline
    (icab.agent.baseline.scenario_aware.ScenarioAwareBaselineAgent): fixed,
    deterministic tool sequence like the legacy baselines, but built on
    real canonical ids discovered from the live scenario/UNS tree, so it IS
    eligible for the main benchmark comparison.
    """

    STRUCTURED_RETRIEVAL = "structured_retrieval"
    CONTEXT_AWARE = "context_aware"
    ARCHITECTURE_AWARE = "architecture_aware"
    SCENARIO_AWARE = "scenario_aware"


#: The legacy, pre-M5 deterministic baselines -- not benchmark-eligible
#: against a real BenchmarkScenario (see DeterministicAgentKind, RunValidity).
LEGACY_DETERMINISTIC_AGENT_KINDS = frozenset(
    {
        DeterministicAgentKind.STRUCTURED_RETRIEVAL,
        DeterministicAgentKind.CONTEXT_AWARE,
        DeterministicAgentKind.ARCHITECTURE_AWARE,
    }
)


class ExperimentRunStatus(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"


class RunValidity(StrEnum):
    """
    Whether a run is eligible for the main architecture-comparison
    benchmark, independent of whether it completed successfully.

    A run can be ``status=COMPLETED`` and still be
    ``LEGACY_CONTROL_ONLY`` -- it ran fine, but its agent is known not to
    access the scenario's actual data, so its scores must not be presented
    alongside real benchmark comparisons. See
    docs/research/experiment-plan.md for the incident that motivated this.
    """

    VALID = "valid"
    LEGACY_CONTROL_ONLY = "legacy_control_only"


class ExperimentConfig(BaseModel):
    """
    One experiment run's configuration -- everything that determines what
    was run, held explicit rather than left to implicit agent behavior.
    """

    model_config = ConfigDict(extra="forbid")

    scenario_id: str = Field(min_length=1)

    #: M13-D: which BenchmarkTask (icab.tasks) this run answers, when run
    #: via the benchmark orchestrator rather than a bare scenario -- None
    #: preserves the original M9-M12 scenario-only path unchanged.
    task_id: str | None = None
    #: The task's own task_type (icab.scenarios.models.TaskMode value),
    #: recorded directly (not looked up from a registry at aggregation
    #: time) so `icab.reporting.aggregation` can group by it without
    #: needing task-registry access.
    task_type: str | None = None
    #: ICAB v2: the ISA-95 level (icab.tasks.isa95.ISA95Level) and
    #: industrial use case (icab.usecases) this run's task serves, and
    #: the canonical id (icab.tasks.context_combinations) of the context
    #: dimensions this run's ARCHITECTURE ARM actually PROVIDED
    #: (icab.tasks.context_dimensions.provided_dimensions(architectures)
    #: -- NOT the task's fixed required_context_dimensions, which stays
    #: the same regardless of which architecture arm ran it. This is
    #: deliberate: running the SAME task with progressively fewer
    #: architectures changes what was PROVIDED, which is exactly the
    #: variable icab.analysis's necessity/sufficiency/composition suites
    #: need to group by. All recorded directly (same convention as
    #: task_type above: no task-registry lookup needed at aggregation
    #: time). None for a tep-v1-only run (no v2 metadata) or any run
    #: made outside the benchmark orchestrator.
    isa95_level: str | None = None
    use_case_id: str | None = None
    context_combination_id: str | None = None
    #: Which named benchmark suite (icab.benchmark) this run belongs to,
    #: e.g. "tep-v1".
    suite: str | None = None
    #: Which split (development/validation/test) the run's task's
    #: scenario is assigned to (icab.tasks.splits) -- recorded, not
    #: re-derived, so a persisted record is self-describing even if
    #: splits.yaml later changes.
    split: str | None = None
    #: Which repetition (1-based) of this exact (task, architecture,
    #: seed) configuration this run is -- see icab.benchmark.runner.
    repetition: int | None = None

    #: Which context architectures' tools the agent is given -- explicit,
    #: not inherited implicitly from the scenario (though it usually
    #: matches `BenchmarkScenario.available_architectures`). Enforced for
    #: the LLM agent via `tools_for_architectures`; see
    #: `DeterministicAgentKind` for the deterministic baselines' caveat.
    architectures: list[str] = Field(min_length=1)

    #: Which named preset (icab.experiments.architecture_combinations,
    #: M10) `architectures` came from, if any -- a label for aggregate
    #: reporting, not a second enforcement path; `architectures` above is
    #: still what's actually enforced.
    architecture_combination_key: str | None = None

    agent_type: AgentType

    #: Required when agent_type == DETERMINISTIC.
    deterministic_agent: DeterministicAgentKind | None = None

    #: Only meaningful for deterministic_agent == SCENARIO_AWARE -- which
    #: real equipment item (icab.tep.measurements.REAL_TEP_EQUIPMENT key,
    #: e.g. "reactor", "stripper") ScenarioAwareBaselineAgent inspects.
    #: Defaults to that agent's own default ("reactor") when unset.
    deterministic_equipment_key: str | None = None

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

    #: M13-D: three additional, optional budgets LLMInvestigationAgent
    #: can enforce (see its own docstring) -- None (the default) means
    #: unbounded, same as pre-M13-D behavior. Deterministic baselines
    #: have no configurable budget of any kind and always record all
    #: three as None regardless of what was passed (same convention as
    #: max_steps above).
    max_tool_calls: int | None = None
    max_context_tokens: int | None = None
    max_wall_time_seconds: float | None = None

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
    generation_id: str | None = Field(
        default=None,
        description=(
            "The scenario-preparation provenance tag this run's data was "
            "written under (icab.scenarios.runner.ScenarioRunner); used to "
            "scope this run's own evidence in the evaluator. See "
            "icab.cim.Relationship/Observation.generation_id."
        ),
    )

    icab_version: str | None = None

    #: M13-D: the icab.benchmark package's own BENCHMARK_SUITE_VERSION,
    #: distinct from icab_version (the installed icab package version) --
    #: None when this run was produced outside the benchmark orchestrator
    #: (e.g. a bare ExperimentRunner.run() call, pre-M13-D style).
    benchmark_version: str | None = None
    #: `git rev-parse HEAD` at the time the run was launched, when
    #: available -- None if not run inside a git repository or the
    #: command could not be resolved. Captured for audit, not enforced.
    git_commit: str | None = None
    #: The TEP disturbance actually scheduled on the scenario that was
    #: run (BenchmarkScenario.faults[0].disturbance), or None for a
    #: scenario with no fault schedule. Mirrors
    #: GroundTruth.root_cause_disturbance but derived from the scenario's
    #: own fault schedule rather than duplicated authoring.
    fault_id: str | None = None
    #: Production-hardening addition: the fault catalog
    #: (configs/benchmark/fault_catalog.json, icab.tep.faults)
    #: entry's own `tep_studio_version` for `fault_id`, when the catalog
    #: has an entry for it -- the closest existing analog to a "fault
    #: version" (M13-B never defined a separate per-fault version
    #: scheme). Best-effort/auditability only: None if `fault_id` is
    #: None, or if the catalog has no matching entry, or if the catalog
    #: file itself could not be loaded -- never blocks a run.
    fault_version: str | None = None
    #: BenchmarkScenario.version (M13-D) of the scenario actually run --
    #: recorded so a persisted record stays self-describing even if the
    #: scenario's own YAML is later revised.
    scenario_version: str | None = None
    #: BenchmarkTask.version (M13-C) of the task actually run, when this
    #: run answers a task -- None when config.task_id is None.
    task_version: str | None = None
    #: sha256 hex digest over a canonical JSON serialization of this
    #: run's ExperimentConfig -- see
    #: icab.experiments.models.compute_configuration_hash. Lets two
    #: persisted records be checked for "same configuration" without
    #: comparing every field by hand.
    configuration_hash: str | None = None

    started_at: datetime
    completed_at: datetime

    status: ExperimentRunStatus
    error: str | None = None

    validity: RunValidity = RunValidity.VALID
    validity_reason: str | None = Field(
        default=None,
        description="Why this run is not VALID, when it isn't -- see RunValidity.",
    )

    result: InvestigationResult | None = None
    evaluation: EvaluationReport | None = None
    information_flow: InformationFlowReport | None = Field(
        default=None,
        description=(
            "Discoverability/acquisition/redundancy analysis of this run's "
            "trace (M10) -- which architecture supplied each piece of "
            "information, and whether the same measurement was acquired "
            "redundantly through more than one. See "
            "icab.evaluation.information_flow."
        ),
    )
    trace_event_count: int = 0
    total_latency_ms: float | None = Field(
        default=None,
        description="Sum of every recorded tool call's latency_ms, when available.",
    )
    total_tokens: int | None = Field(
        default=None,
        description="Sum of every recorded LLM generation call's total_tokens, when available.",
    )


def compute_configuration_hash(config: ExperimentConfig) -> str:
    """
    M13-D: a stable sha256 hex digest of `config`'s own fields, for
    `ExperimentRecord.configuration_hash`.

    Uses Pydantic's own JSON serialization (`model_dump_json`) with sorted
    keys so the hash is stable across field-declaration-order changes and
    across process runs, not over Python's own (unstable) `hash()`/`repr()`.
    This is an audit aid ("did two runs share a configuration?"), not a
    security digest.
    """

    canonical = config.model_dump_json(exclude_none=False)
    # model_dump_json doesn't sort keys itself; re-serialize through
    # json.dumps(..., sort_keys=True) over the already-JSON-safe dict so
    # the digest doesn't depend on Pydantic's field-declaration order.
    canonical_sorted = json.dumps(json.loads(canonical), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical_sorted.encode("utf-8")).hexdigest()
