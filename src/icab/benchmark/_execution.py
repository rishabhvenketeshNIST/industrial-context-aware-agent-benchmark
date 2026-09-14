"""
Shared "run one (task, architecture arm, seed, repetition) combination"
execution logic, factored out of `icab.benchmark.runner.BenchmarkRunner`
so `icab.benchmark.context_experiment.ContextExperimentRunner` (the
context-condition experiment orchestrator) can reuse the EXACT SAME
execution/error-handling semantics rather than re-implementing them --
same run_id scheme, same "never raise, always persist a FAILED record"
behavior, same fault-version lookup.

Pure refactor: `BenchmarkRunner` calls these same two functions with the
same arguments it always did; behavior is unchanged (see
tests/unit/benchmark/test_benchmark_runner.py, which exercises it only
through the public `BenchmarkRunner.run()` API and is unaffected by this
extraction).
"""

from __future__ import annotations

from datetime import UTC, datetime

from icab.experiments import (
    AgentType,
    DeterministicAgentKind,
    ExperimentConfig,
    ExperimentRecord,
    ExperimentRunner,
    ExperimentRunStatus,
    RunValidity,
    compute_configuration_hash,
)
from icab.experiments.runner import _icab_version
from icab.scenarios import BenchmarkScenarioRegistry
from icab.tasks.benchmark_task import BenchmarkTask
from icab.tasks.context_combinations import combination_id_for
from icab.tasks.context_dimensions import provided_dimensions
from icab.tasks.splits import TaskSplit
from icab.tep.faults import FaultCatalog
from icab.trace.models import TraceEvent

#: Agent-selector strings that map to a benchmark-eligible (non-legacy) agent.
PRIMARY_AGENTS = {"baseline", "llm"}

#: `--agent` values naming an M9 legacy deterministic baseline directly.
LEGACY_AGENT_VALUES = {kind.value for kind in DeterministicAgentKind} - {
    DeterministicAgentKind.SCENARIO_AWARE.value
}


def build_experiment_config(
    *,
    task: BenchmarkTask,
    arm_architectures: tuple[str, ...],
    combination_key: str | None,
    split: TaskSplit,
    agent: str,
    suite: str | None = None,
    llm_model: str | None = None,
    llm_temperature: float | None = None,
    max_steps: int | None = None,
    max_tool_calls: int | None = None,
    max_context_tokens: int | None = None,
    max_wall_time_seconds: float | None = None,
) -> ExperimentConfig:
    if agent in PRIMARY_AGENTS:
        agent_type = AgentType.DETERMINISTIC if agent == "baseline" else AgentType.LLM
        deterministic_agent = DeterministicAgentKind.SCENARIO_AWARE if agent == "baseline" else None
    elif agent in LEGACY_AGENT_VALUES:
        agent_type = AgentType.DETERMINISTIC
        deterministic_agent = DeterministicAgentKind(agent)
    else:
        raise ValueError(f"Unknown --agent {agent!r}. Valid: {sorted(PRIMARY_AGENTS | LEGACY_AGENT_VALUES)}")

    return ExperimentConfig(
        scenario_id=task.scenario_id,
        task_id=task.task_id,
        task_type=task.task_type.value,
        isa95_level=task.isa95_level.value if task.isa95_level is not None else None,
        use_case_id=task.use_case_id,
        # PROVIDED context (this arm's own architectures), not the task's
        # fixed required_context_dimensions -- see
        # ExperimentConfig.context_combination_id's own docstring.
        context_combination_id=combination_id_for(provided_dimensions(list(arm_architectures))),
        suite=suite,
        split=split.value,
        architectures=list(arm_architectures),
        architecture_combination_key=combination_key,
        agent_type=agent_type,
        deterministic_agent=deterministic_agent,
        llm_model=llm_model,
        llm_temperature=llm_temperature,
        max_steps=max_steps,
        max_tool_calls=max_tool_calls,
        max_context_tokens=max_context_tokens,
        max_wall_time_seconds=max_wall_time_seconds,
    )


def fault_version_for(fault_id: str | None, fault_catalog: FaultCatalog | None) -> str | None:
    if fault_id is None or fault_catalog is None:
        return None
    try:
        return fault_catalog.get(fault_id).tep_studio_version
    except KeyError:
        return None


def run_one(
    *,
    experiment_runner: ExperimentRunner,
    task: BenchmarkTask,
    scenario_registry: BenchmarkScenarioRegistry,
    exp_config: ExperimentConfig,
    run_id: str,
    experiment_id: str,
    seed: int | None,
    benchmark_version: str | None,
    git_commit: str | None,
    fault_catalog: FaultCatalog | None,
) -> tuple[str, ExperimentRecord, list[TraceEvent]]:
    """
    Runs exactly one already-built `ExperimentConfig` against its task.
    Never raises: a failure anywhere (scenario preparation, agent
    execution) is caught and turned into a persisted FAILED
    `ExperimentRecord` so the caller's larger invocation can continue.
    """

    try:
        scenario = scenario_registry.get(task.scenario_id)
        if seed is not None:
            scenario = scenario.model_copy(update={"seed": seed})

        record, trace = experiment_runner.run_task(
            task,
            exp_config,
            scenario=scenario,
            run_id=run_id,
            experiment_id=experiment_id,
            benchmark_version=benchmark_version,
            git_commit=git_commit,
        )
        fault_version = fault_version_for(record.fault_id, fault_catalog)
        if fault_version is not None:
            record = record.model_copy(update={"fault_version": fault_version})
        return run_id, record, trace
    except Exception as error:  # noqa: BLE001 -- orchestration-level continue-on-error
        now = datetime.now(UTC)
        fault_id = None
        scenario_version = None
        try:
            fault_id = scenario.faults[0].disturbance if scenario.faults else None
            scenario_version = scenario.version
            simulation_seed = scenario.seed
            scenario_difficulty = scenario.difficulty.value
        except NameError:
            simulation_seed = seed if seed is not None else 0
            scenario_difficulty = task.difficulty.value

        record = ExperimentRecord(
            run_id=run_id,
            experiment_id=experiment_id,
            config=exp_config,
            scenario_difficulty=scenario_difficulty,
            simulation_seed=simulation_seed,
            generation_id=None,
            icab_version=_icab_version(),
            benchmark_version=benchmark_version,
            git_commit=git_commit,
            fault_id=fault_id,
            fault_version=fault_version_for(fault_id, fault_catalog),
            scenario_version=scenario_version,
            task_version=task.version,
            configuration_hash=compute_configuration_hash(exp_config),
            started_at=now,
            completed_at=now,
            status=ExperimentRunStatus.FAILED,
            error=f"{type(error).__name__}: {error}",
            validity=RunValidity.VALID,
            result=None,
            evaluation=None,
            information_flow=None,
            trace_event_count=0,
        )
        return run_id, record, []
