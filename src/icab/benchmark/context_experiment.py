"""
ICAB v2 (context-requirement experimentation): runs a chosen SET of
context conditions (`icab.tasks.experiment_design`) against ONE task,
resolving each against the task's own `available_architectures`
(`icab.tasks.context_conditions`) and executing only the ones that are
actually realizable -- reusing the exact same execution path
`icab.benchmark.runner.BenchmarkRunner` uses (`icab.benchmark._execution`)
so every run this produces is persisted, aggregated, and analyzable
through the SAME `results/` layout and the SAME `icab.analysis` suites,
with no separate format or code path.

This is deliberately a SEPARATE, narrower entry point from
`BenchmarkRunner` (which sweeps every task in a suite/split against an
architecture spec): here, the caller picks ONE task and a context-
condition DESIGN STRATEGY (single/pairwise/progressive/targeted/
ablation/replay), and this module is responsible for the honest
bookkeeping the ICAB v2 direction requires --

    supported combination   (realizable at all, by SOME architecture arm)
    selected combination     (chosen by the design strategy)
    not_applicable            (outside this use case's own candidate_context)
    not_executed / unrealizable  (no architecture arm can realize it)
    executed                  (a real run was attempted)
    successful / failed        (that run's own ExperimentRunStatus)

"not executed" (NOT_APPLICABLE or UNREALIZABLE, or a realizable-but-
OVERSHOOT condition skipped because `allow_overshoot` was not set) is
NEVER counted or reported as a failure -- see `ContextConditionOutcome`.
"""

from __future__ import annotations

import uuid
from typing import Sequence

from pydantic import BaseModel, ConfigDict, Field

from icab.experiments import ExperimentResultStore, ExperimentRunner, ExperimentRunStatus
from icab.scenarios import BenchmarkScenarioRegistry
from icab.tasks.context_combinations import ContextCombination, combination_for_dimensions, combination_for_id
from icab.tasks.context_conditions import ConditionStatus, resolve_condition_architectures
from icab.tasks.context_dimensions import provided_dimensions
from icab.tasks.experiment_design import DesignStrategy, generate_conditions
from icab.tasks.registry import BenchmarkTaskRegistry
from icab.tasks.splits import load_split_assignment
from icab.tep.faults import FaultCatalog, load_fault_catalog
from icab.usecases import IndustrialUseCase, IndustrialUseCaseRegistry

from ._execution import build_experiment_config, run_one
from .config import get_git_commit, get_suite
from .runner import BenchmarkIdCollisionError

__all__ = [
    "ContextConditionOutcome",
    "ContextExperimentConfig",
    "ContextExperimentResult",
    "ContextExperimentRunner",
]


class ContextExperimentConfig(BaseModel):
    """One `ContextExperimentRunner.run()` invocation's configuration."""

    model_config = ConfigDict(extra="forbid")

    suite: str
    task_id: str

    design: str  # icab.tasks.experiment_design.DesignStrategy value
    #: TARGETED only -- explicit combination ids.
    targets: list[str] | None = None
    #: ABLATION only -- the combination id to ablate from. Defaults (when
    #: None) to the combination this task's OWN `available_architectures`,
    #: used together, actually provides -- the natural "full context this
    #: task can offer" baseline, EXACT by construction.
    baseline: str | None = None
    #: PROGRESSIVE only -- a permutation of C1..C7 as combination-id
    #: dimension values (e.g. ["C4", "C1", ...]). Defaults to canonical order.
    progressive_order: list[str] | None = None

    #: Realizable-but-OVERSHOOT conditions (see icab.tasks.context_conditions)
    #: are skipped (not_executed) unless this is set -- running them
    #: silently would test MORE context than the condition's own id
    #: implies, which is exactly the conflation the ICAB v2 direction
    #: warns against.
    allow_overshoot: bool = False

    agent: str = "llm"
    seeds: list[int] | None = None
    repetitions: int = Field(default=1, ge=1)

    llm_model: str | None = None
    llm_temperature: float | None = None
    max_steps: int | None = Field(default=None, ge=1)
    max_tool_calls: int | None = Field(default=None, ge=1)
    max_context_tokens: int | None = Field(default=None, ge=1)
    max_wall_time_seconds: float | None = Field(default=None, gt=0)

    name: str | None = None
    force: bool = False


class ContextConditionOutcome(BaseModel):
    """What happened to ONE selected context condition."""

    model_config = ConfigDict(extra="forbid")

    combination_id: str
    dimensions: list[str]
    cardinality: int

    #: "exact" / "overshoot" / "unrealizable" (icab.tasks.context_conditions
    #: .ConditionStatus) / "not_applicable" (outside the use case's own
    #: candidate_context, when a use case is known for this task).
    resolution_status: str
    resolved_architectures: list[str] | None
    reason: str

    #: False for NOT_APPLICABLE/UNREALIZABLE, and for OVERSHOOT when
    #: allow_overshoot was not set -- NEVER treated as a failure (see
    #: module docstring).
    executed: bool
    run_ids: list[str] = Field(default_factory=list)


class ContextExperimentResult(BaseModel):
    """Summary of one campaign: every selected condition's outcome, plus run-level counters."""

    model_config = ConfigDict(extra="forbid")

    campaign_id: str
    suite: str
    task_id: str
    use_case_id: str | None
    isa95_level: str | None
    design: str

    conditions: list[ContextConditionOutcome]

    total_conditions: int
    executed_conditions: int
    not_applicable_conditions: int
    unrealizable_conditions: int
    overshoot_skipped_conditions: int

    total_runs: int
    successful_runs: int
    failed_runs: int
    run_ids: list[str]


class ContextExperimentRunner:
    """Resolves and executes a context-condition design strategy against one task."""

    def __init__(
        self,
        *,
        experiment_runner: ExperimentRunner,
        experiment_store: ExperimentResultStore,
        use_case_registry: IndustrialUseCaseRegistry | None = None,
    ) -> None:
        self.experiment_runner = experiment_runner
        self.experiment_store = experiment_store
        self.use_case_registry = use_case_registry

    def run(self, config: ContextExperimentConfig) -> ContextExperimentResult:
        suite = get_suite(config.suite)
        scenario_registry = BenchmarkScenarioRegistry(suite.scenarios_dir)
        task_registry = BenchmarkTaskRegistry(suite.tasks_dir, scenario_registry=scenario_registry)
        split_assignment = load_split_assignment(suite.splits_path)

        try:
            task = task_registry.get(config.task_id)
        except KeyError:
            raise ValueError(
                f"Unknown --task {config.task_id!r} for suite {config.suite!r}. "
                f"Valid task ids: {task_registry.list_ids()}"
            ) from None

        split = split_assignment.split_for_scenario(task.scenario_id)

        use_case: IndustrialUseCase | None = None
        if task.use_case_id and self.use_case_registry is not None:
            try:
                use_case = self.use_case_registry.get(task.use_case_id)
            except KeyError:
                use_case = None  # best-effort classification only -- never blocks a run

        conditions = self._select_conditions(config, task)

        campaign_id = config.name or f"ctxexp-{config.suite}-{config.task_id}-{uuid.uuid4().hex[:8]}"
        self._check_no_existing_campaign(campaign_id, force=config.force)
        git_commit = get_git_commit()
        fault_catalog = self._load_fault_catalog_best_effort()
        seed_values: list[int | None] = list(config.seeds) if config.seeds else [None]

        outcomes: list[ContextConditionOutcome] = []
        all_run_ids: list[str] = []
        successful = failed = 0

        for combo in conditions:
            if use_case is not None and not (set(combo.dimensions) <= set(use_case.candidate_context)):
                outcomes.append(
                    ContextConditionOutcome(
                        combination_id=combo.combination_id,
                        dimensions=[d.value for d in combo.dimensions],
                        cardinality=combo.cardinality,
                        resolution_status="not_applicable",
                        resolved_architectures=None,
                        reason=(
                            f"{combo.combination_id} includes a dimension outside use case "
                            f"{use_case.use_case_id!r}'s own candidate_context "
                            f"{[d.value for d in use_case.candidate_context]} -- not a meaningful "
                            "condition for this use case, regardless of realizability."
                        ),
                        executed=False,
                    )
                )
                continue

            resolution = resolve_condition_architectures(combo, task.available_architectures)

            if resolution.status == ConditionStatus.UNREALIZABLE:
                outcomes.append(
                    ContextConditionOutcome(
                        combination_id=combo.combination_id,
                        dimensions=[d.value for d in combo.dimensions],
                        cardinality=combo.cardinality,
                        resolution_status=resolution.status.value,
                        resolved_architectures=None,
                        reason=resolution.reason,
                        executed=False,
                    )
                )
                continue

            if resolution.status == ConditionStatus.OVERSHOOT and not config.allow_overshoot:
                outcomes.append(
                    ContextConditionOutcome(
                        combination_id=combo.combination_id,
                        dimensions=[d.value for d in combo.dimensions],
                        cardinality=combo.cardinality,
                        resolution_status=resolution.status.value,
                        resolved_architectures=list(resolution.architectures) if resolution.architectures else None,
                        reason=resolution.reason + " Pass allow_overshoot=True to run it anyway (labeled as overshoot, not as this exact combination).",
                        executed=False,
                    )
                )
                continue

            run_ids = self._execute_condition(
                task=task,
                scenario_registry=scenario_registry,
                architectures=resolution.architectures,
                combination_id=combo.combination_id,
                split=split,
                config=config,
                campaign_id=campaign_id,
                git_commit=git_commit,
                fault_catalog=fault_catalog,
                seed_values=seed_values,
            )
            all_run_ids.extend(run_id for run_id, _status in run_ids)
            for _run_id, status in run_ids:
                if status == ExperimentRunStatus.COMPLETED:
                    successful += 1
                else:
                    failed += 1

            outcomes.append(
                ContextConditionOutcome(
                    combination_id=combo.combination_id,
                    dimensions=[d.value for d in combo.dimensions],
                    cardinality=combo.cardinality,
                    resolution_status=resolution.status.value,
                    resolved_architectures=list(resolution.architectures),
                    reason=resolution.reason,
                    executed=True,
                    run_ids=[run_id for run_id, _status in run_ids],
                )
            )

        return ContextExperimentResult(
            campaign_id=campaign_id,
            suite=config.suite,
            task_id=task.task_id,
            use_case_id=task.use_case_id,
            isa95_level=task.isa95_level.value if task.isa95_level is not None else None,
            design=config.design,
            conditions=outcomes,
            total_conditions=len(outcomes),
            executed_conditions=sum(1 for o in outcomes if o.executed),
            not_applicable_conditions=sum(1 for o in outcomes if o.resolution_status == "not_applicable"),
            unrealizable_conditions=sum(1 for o in outcomes if o.resolution_status == ConditionStatus.UNREALIZABLE.value),
            overshoot_skipped_conditions=sum(
                1 for o in outcomes if o.resolution_status == ConditionStatus.OVERSHOOT.value and not o.executed
            ),
            total_runs=len(all_run_ids),
            successful_runs=successful,
            failed_runs=failed,
            run_ids=all_run_ids,
        )

    # -- condition selection ----------------------------------------------

    def _select_conditions(
        self, config: ContextExperimentConfig, task
    ) -> tuple[ContextCombination, ...]:
        if config.design == DesignStrategy.REPLAY.value:
            return self._replay_conditions(task)

        baseline: ContextCombination | None = None
        if config.design == DesignStrategy.ABLATION.value:
            baseline_id = config.baseline or self._default_ablation_baseline(task).combination_id
            baseline = combination_for_id(baseline_id)

        progressive_order = None
        if config.progressive_order:
            from icab.tasks.context_dimensions import ContextDimension

            progressive_order = [ContextDimension(value) for value in config.progressive_order]

        return generate_conditions(
            config.design,
            targets=config.targets,
            baseline=baseline,
            progressive_order=progressive_order,
        )

    @staticmethod
    def _default_ablation_baseline(task) -> ContextCombination:
        """The combination this task's OWN architectures, all used together, actually provide -- EXACT by construction."""

        return combination_for_dimensions(provided_dimensions(list(task.available_architectures)))

    def _replay_conditions(self, task) -> tuple[ContextCombination, ...]:
        """
        Every DISTINCT `context_combination_id` already persisted for this
        exact task -- Phase 4E "existing-condition replay": preserves
        compatibility with whatever combinations earlier runs already
        established, without re-deriving them from scratch.
        """

        ids: set[str] = set()
        for run_id in self.experiment_store.list_run_ids():
            record = self.experiment_store.load_record(run_id)
            if record.config.task_id == task.task_id and record.config.context_combination_id:
                ids.add(record.config.context_combination_id)

        return tuple(sorted((combination_for_id(cid) for cid in ids), key=lambda c: (c.cardinality, c.combination_id)))

    # -- execution ----------------------------------------------------------

    def _execute_condition(
        self,
        *,
        task,
        scenario_registry: BenchmarkScenarioRegistry,
        architectures: tuple[str, ...],
        combination_id: str,
        split,
        config: ContextExperimentConfig,
        campaign_id: str,
        git_commit: str | None,
        fault_catalog: FaultCatalog | None,
        seed_values: Sequence[int | None],
    ) -> list[tuple[str, ExperimentRunStatus]]:
        results: list[tuple[str, ExperimentRunStatus]] = []

        exp_config = build_experiment_config(
            task=task,
            arm_architectures=architectures,
            combination_key=None,
            split=split,
            agent=config.agent,
            suite=config.suite,
            llm_model=config.llm_model,
            llm_temperature=config.llm_temperature,
            max_steps=config.max_steps,
            max_tool_calls=config.max_tool_calls,
            max_context_tokens=config.max_context_tokens,
            max_wall_time_seconds=config.max_wall_time_seconds,
        )

        for seed in seed_values:
            for repetition in range(1, config.repetitions + 1):
                run_id = (
                    f"{campaign_id}-{combination_id}-{'+'.join(architectures)}"
                    f"-seed{seed if seed is not None else 'default'}-rep{repetition}"
                )
                run_config = exp_config.model_copy(update={"repetition": repetition})

                run_id, record, trace = run_one(
                    experiment_runner=self.experiment_runner,
                    task=task,
                    scenario_registry=scenario_registry,
                    exp_config=run_config,
                    run_id=run_id,
                    experiment_id=campaign_id,
                    seed=seed,
                    benchmark_version=None,
                    git_commit=git_commit,
                    fault_catalog=fault_catalog,
                )
                self.experiment_store.save(record, trace)
                results.append((run_id, record.status))

        return results

    # -- misc ---------------------------------------------------------------

    def _check_no_existing_campaign(self, campaign_id: str, *, force: bool) -> None:
        if force:
            return
        existing_raw = list(self.experiment_store.raw_dir.glob(f"{campaign_id}-*.json"))
        if existing_raw:
            raise BenchmarkIdCollisionError(
                f"A context experiment campaign with id {campaign_id!r} already has persisted "
                f"results under {self.experiment_store.root}/ -- refusing to overwrite it. Pass "
                "a different name (or omit it for a fresh auto-generated id), or force=True."
            )

    @staticmethod
    def _load_fault_catalog_best_effort() -> FaultCatalog | None:
        try:
            return load_fault_catalog()
        except Exception:  # noqa: BLE001 -- audit metadata only, never fatal
            return None
