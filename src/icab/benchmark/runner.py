"""
M13-D: one-command ICAB benchmark orchestration.

This module ONLY orchestrates existing components -- it introduces no new
scientific methodology, no new evaluation logic, and no new persistence
format:

    BenchmarkConfig (this package)
        -> BenchmarkTaskRegistry / BenchmarkScenarioRegistry (M13-C/M5)
        -> SplitAssignment (M13-C)
        -> resolve_architecture_arms (this package, M13-D)
        -> ExperimentConfig (M9, extended M13-D)
        -> ExperimentRunner.run_task (M9, extended M13-D)
            -> ScenarioRunner.prepare (M5) -- real TEP simulator + fault injection
            -> Agent (deterministic baseline or LLMInvestigationAgent, M6/M9)
            -> GroundedInvestigationEvaluator.evaluate_task (M8/M13-C)
        -> ExperimentResultStore.save (M9) -- per-run persistence
        -> ExperimentResultStore.write_aggregate (M9/M12)
        -> icab.reporting.aggregate_records / render_aggregation_markdown / plotting (M12)
        -> icab.reporting.build_qa_report / render_qa_report_markdown (M13-D follow-up)
           -- a researcher-facing question/answer report, built purely
           from already-persisted records (no additional agent/gateway/
           LLM call, so it cannot leak ground truth back to an agent)

Execution is strictly sequential -- no distributed workers, no task
queue. A failure in one (task, architecture arm, seed, repetition) run is
caught, persisted as a FAILED record, and does not stop the remaining
runs (see `BenchmarkRunner._run_one`).
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field

from icab.experiments import (
    AgentType,
    DeterministicAgentKind,
    ExperimentConfig,
    ExperimentRecord,
    ExperimentResultStore,
    ExperimentRunner,
    ExperimentRunStatus,
)
from icab.reporting import aggregate_records, build_qa_report, render_aggregation_markdown, render_qa_report_markdown
from icab.reporting.plotting import plot_metric_by_group
from icab.reporting.store import ReportStore
from icab.scenarios import BenchmarkScenarioRegistry
from icab.tasks.benchmark_task import BenchmarkTask
from icab.tep.faults import FaultCatalog, load_fault_catalog
from icab.tasks.registry import BenchmarkTaskRegistry
from icab.tasks.splits import SplitAssignment, TaskSplit, load_split_assignment, tasks_in_split
from icab.trace.models import TraceEvent

from ._execution import LEGACY_AGENT_VALUES, PRIMARY_AGENTS, build_experiment_config, run_one
from .config import (
    BENCHMARK_SUITE_VERSION,
    BenchmarkConfig,
    get_git_commit,
    get_suite,
    resolve_architecture_arms,
    validate_architectures_spec,
)

class BenchmarkIdCollisionError(ValueError):
    """
    Raised when `results/` already contains artifacts for the requested
    `benchmark_id` and `BenchmarkConfig.force` was not set -- production
    data-collection safeguard: a benchmark invocation must never silently
    overwrite a previous one's raw records/traces/evaluations/aggregate/
    reports. Only reachable when `--name` is explicitly reused (the
    default, auto-generated `benchmark-<suite>-<uuid>` id is never
    reused in practice).
    """


#: Agent-selector strings that map to a benchmark-eligible (non-legacy)
#: agent -- the only two ever run without an explicit legacy opt-in.
#: (Defined in `icab.benchmark._execution`, shared with
#: `ContextExperimentRunner`; re-bound here under their original names so
#: nothing else in this file needs to change.)
_PRIMARY_AGENTS = PRIMARY_AGENTS

#: `--agent` values that name an M9 legacy deterministic baseline
#: directly -- an explicit, separate opt-in (never `_PRIMARY_AGENTS`'
#: default), always excluded from normal benchmark aggregates via
#: `RunValidity.LEGACY_CONTROL_ONLY` (see `ExperimentRunner._validity_for`).
_LEGACY_AGENT_VALUES = LEGACY_AGENT_VALUES


class BenchmarkRunResult(BaseModel):
    """Summary counters and output locations from one `BenchmarkRunner.run()` invocation."""

    model_config = ConfigDict(extra="forbid")

    benchmark_id: str
    suite: str
    split: str | None
    task_ids: list[str]
    scenario_ids: list[str]
    architectures: list[str]
    agent: str
    seeds: list[int]
    repetitions: int

    total_runs: int
    successful_runs: int
    failed_runs: int
    skipped_runs: int
    skipped_reasons: list[str]

    run_ids: list[str]

    aggregate_json_path: str | None = None
    aggregate_csv_path: str | None = None
    report_json_path: str | None = None
    report_markdown_path: str | None = None
    figure_paths: list[str] = Field(default_factory=list)

    #: The M13-D follow-up researcher-facing question/answer report --
    #: one entry per run (question/agent answer/ground truth/evidence/
    #: metrics) plus an overall summary. See icab.reporting.qa_report.
    qa_report_json_path: str | None = None
    qa_report_markdown_path: str | None = None


class BenchmarkRunner:
    """
    Orchestrates a full `--suite`/`--split`/`--task` benchmark invocation:
    task selection x architecture-arm expansion x seeds x repetitions,
    each run executed via `ExperimentRunner.run_task` and persisted via
    `ExperimentResultStore`, followed by automatic aggregation/reporting.
    """

    def __init__(
        self,
        *,
        experiment_runner: ExperimentRunner,
        experiment_store: ExperimentResultStore,
        report_store: ReportStore | None = None,
    ) -> None:
        self.experiment_runner = experiment_runner
        self.experiment_store = experiment_store
        self.report_store = report_store or ReportStore(root=experiment_store.root)

    def run(self, config: BenchmarkConfig) -> BenchmarkRunResult:
        if config.agent not in _PRIMARY_AGENTS and config.agent not in _LEGACY_AGENT_VALUES:
            # A bad --agent value is a CONFIGURATION error, not a per-run
            # failure -- fail the whole invocation immediately rather
            # than recording every expanded run as FAILED (which would
            # still burn a full scenario-preparation attempt per run).
            raise ValueError(
                f"Unknown --agent {config.agent!r}. Valid: "
                f"{sorted(_PRIMARY_AGENTS | _LEGACY_AGENT_VALUES)}"
            )

        # Also a configuration error, not a per-run failure -- an
        # architecture name ICAB doesn't know about at all (a typo) is
        # never valid for ANY task, so this is checked once, up front,
        # rather than letting every expanded run independently discover
        # it as a SKIP with a confusing "not available for this task"
        # reason (that reason is reserved for a KNOWN architecture the
        # task just doesn't grant).
        validate_architectures_spec(config.architectures)

        suite = get_suite(config.suite)
        scenario_registry = BenchmarkScenarioRegistry(suite.scenarios_dir)
        task_registry = BenchmarkTaskRegistry(suite.tasks_dir, scenario_registry=scenario_registry)
        split_assignment = load_split_assignment(suite.splits_path)

        tasks = self._select_tasks(task_registry, split_assignment, config)

        if not tasks:
            raise ValueError(
                f"No tasks matched suite={config.suite!r}, split={config.split!r}, "
                f"scenario={config.scenario_id!r}, task={config.task_id!r} -- check "
                "these for typos (e.g. via BenchmarkTaskRegistry.list_ids())."
            )

        benchmark_id = config.name or f"benchmark-{config.suite}-{uuid.uuid4().hex[:8]}"
        self._check_no_existing_benchmark(benchmark_id, force=config.force)
        git_commit = get_git_commit()
        fault_catalog = self._load_fault_catalog_best_effort()
        seed_values: list[int | None] = list(config.seeds) if config.seeds else [None]

        records: list[ExperimentRecord] = []
        run_ids: list[str] = []
        architectures_used: set[str] = set()
        successful = failed = skipped = 0
        skipped_reasons: list[str] = []

        for task in tasks:
            arms = resolve_architecture_arms(config.architectures, task)

            if not arms:
                count = len(seed_values) * config.repetitions
                skipped += count
                skipped_reasons.append(
                    f"{task.task_id}: architecture spec {config.architectures!r} is not "
                    f"available for this task (task permits: {task.available_architectures})"
                    f" -- {count} run(s) skipped"
                )
                continue

            scenario_split = split_assignment.split_for_scenario(task.scenario_id)

            for arm in arms:
                architectures_used.update(arm.architectures)

                for seed in seed_values:
                    for repetition in range(1, config.repetitions + 1):
                        run_id, record, trace = self._run_one(
                            task=task,
                            scenario_registry=scenario_registry,
                            arm_architectures=arm.architectures,
                            combination_key=arm.combination_key,
                            seed=seed,
                            repetition=repetition,
                            split=scenario_split,
                            config=config,
                            benchmark_id=benchmark_id,
                            benchmark_version=BENCHMARK_SUITE_VERSION,
                            git_commit=git_commit,
                            fault_catalog=fault_catalog,
                        )

                        self.experiment_store.save(record, trace)
                        records.append(record)
                        run_ids.append(run_id)

                        if record.status == ExperimentRunStatus.COMPLETED:
                            successful += 1
                        else:
                            failed += 1

        aggregate_json_path = aggregate_csv_path = None
        report_json_path = report_markdown_path = None
        qa_report_json_path = qa_report_markdown_path = None
        figure_paths: list[str] = []

        if records:
            aggregate_json_path, aggregate_csv_path = self.experiment_store.write_aggregate(
                benchmark_id,
                records,
                # A full benchmark invocation necessarily spans many
                # different scenarios/tasks (that is the whole point of
                # running a suite, not a single controlled comparison) --
                # so heterogeneous scenario_id/seed/etc. across records is
                # EXPECTED here, not an error. The written JSON's own
                # controls_consistent/control_variance fields still make
                # this fully auditable.
                allow_heterogeneous_controls=True,
            )

            aggregation_report = aggregate_records(
                records,
                group_by=("task_type", "difficulty", "architecture"),
                allow_heterogeneous_controls=True,
            )
            report_json_path = str(
                self.report_store.write_aggregation_report(aggregation_report, benchmark_id)
            )
            report_markdown_path = str(
                self.report_store.write_markdown(
                    render_aggregation_markdown(
                        aggregation_report, title=f"ICAB benchmark: {benchmark_id}"
                    ),
                    benchmark_id,
                )
            )

            for metric in ("conclusion_correctness_score", "tool_call_count"):
                if any(metric in group.metrics for group in aggregation_report.groups):
                    figure_path = plot_metric_by_group(
                        aggregation_report,
                        metric,
                        self.report_store.figure_path(f"{benchmark_id}-{metric}.png"),
                    )
                    figure_paths.append(str(figure_path))

            # Researcher-facing question/answer report (M13-D follow-up):
            # `tasks`/`scenario_registry` are already loaded above for
            # this exact invocation -- no second registry load, and
            # nothing here makes an agent/gateway/LLM call, so it cannot
            # leak ground truth back to an agent (see
            # icab.reporting.qa_report module docstring).
            tasks_by_id = {task.task_id: task for task in tasks}
            scenarios_by_id = {
                task.scenario_id: scenario_registry.get(task.scenario_id) for task in tasks
            }
            qa_report = build_qa_report(
                records,
                benchmark_id=benchmark_id,
                successful_runs=successful,
                failed_runs=failed,
                skipped_runs=skipped,
                tasks_by_id=tasks_by_id,
                scenarios_by_id=scenarios_by_id,
            )
            qa_report_json_path = str(self.report_store.write_qa_report(qa_report, benchmark_id))
            qa_report_markdown_path = str(
                self.report_store.write_markdown(render_qa_report_markdown(qa_report), f"{benchmark_id}-qa")
            )

        return BenchmarkRunResult(
            benchmark_id=benchmark_id,
            suite=config.suite,
            split=config.split,
            task_ids=sorted({task.task_id for task in tasks}),
            scenario_ids=sorted({task.scenario_id for task in tasks}),
            architectures=sorted(architectures_used),
            agent=config.agent,
            seeds=[seed for seed in seed_values if seed is not None],
            repetitions=config.repetitions,
            total_runs=successful + failed + skipped,
            successful_runs=successful,
            failed_runs=failed,
            skipped_runs=skipped,
            skipped_reasons=skipped_reasons,
            run_ids=run_ids,
            aggregate_json_path=str(aggregate_json_path) if aggregate_json_path else None,
            aggregate_csv_path=str(aggregate_csv_path) if aggregate_csv_path else None,
            report_json_path=report_json_path,
            report_markdown_path=report_markdown_path,
            figure_paths=figure_paths,
            qa_report_json_path=qa_report_json_path,
            qa_report_markdown_path=qa_report_markdown_path,
        )

    # -- production-safety: never silently overwrite a prior benchmark ----

    def _check_no_existing_benchmark(self, benchmark_id: str, *, force: bool) -> None:
        """
        Refuses to proceed if `results/` already has ANY artifact for
        `benchmark_id` -- checked before a single scenario is prepared,
        so a collision is a fast, clear configuration error rather than
        a benchmark invocation that silently overwrites/interleaves with
        a previous one. Checks both the aggregate file (written once, at
        the END of a completed invocation) AND individual raw run files
        (written incrementally, per run) -- a prior invocation that
        crashed before reaching its own aggregate step would otherwise
        leave raw/trace/evaluation files this check must still catch.
        """

        if force:
            return

        aggregate_path = self.experiment_store.aggregate_dir / f"{benchmark_id}.json"
        existing_raw = list(self.experiment_store.raw_dir.glob(f"{benchmark_id}-*.json"))

        if aggregate_path.exists() or existing_raw:
            raise BenchmarkIdCollisionError(
                f"A benchmark with id {benchmark_id!r} already has persisted results "
                f"under {self.experiment_store.root}/ -- refusing to overwrite it. "
                "Pass a different --name (or omit --name for a fresh auto-generated "
                "id), or pass --force to deliberately overwrite."
            )

    # -- fault-version metadata (production hardening) --------------------

    @staticmethod
    def _load_fault_catalog_best_effort() -> FaultCatalog | None:
        """
        Loads `configs/benchmark/fault_catalog.json` once per invocation
        for `ExperimentRecord.fault_version` lookups -- best-effort only:
        a missing/corrupt catalog file must never block a benchmark run,
        since M13-B's catalog is reference/audit data, not something the
        orchestration layer depends on to function.
        """

        try:
            return load_fault_catalog()
        except Exception:  # noqa: BLE001 -- audit metadata only, never fatal
            return None

    # -- task/split selection --------------------------------------------

    @staticmethod
    def _select_tasks(
        task_registry: BenchmarkTaskRegistry,
        split_assignment: SplitAssignment,
        config: BenchmarkConfig,
    ) -> list[BenchmarkTask]:
        """
        Loads the suite's ACTUAL registered task inventory (never a
        hard-coded list) and narrows it by `--split`/`--scenario`/`--task`
        -- in a fixed, deterministic order (`sorted` by task_id), never
        reshuffled at runtime.
        """

        if config.task_id:
            # An explicit --task always wins outright, regardless of
            # --split -- the smoke-test path (`--split development
            # --task <id>`) is expected to name a task that's already in
            # that split, but this makes an explicit --task unambiguous
            # either way rather than silently dropping it if it doesn't
            # match --split.
            try:
                return [task_registry.get(config.task_id)]
            except KeyError:
                raise ValueError(
                    f"Unknown --task {config.task_id!r} for suite {config.suite!r}. "
                    f"Valid task ids: {task_registry.list_ids()}"
                ) from None

        tasks = (
            tasks_in_split(task_registry, TaskSplit(config.split), assignment=split_assignment)
            if config.split
            else list(task_registry)
        )

        if config.scenario_id:
            tasks = [task for task in tasks if task.scenario_id == config.scenario_id]

        return sorted(tasks, key=lambda task: task.task_id)

    # -- agent/config construction ----------------------------------------

    @staticmethod
    def _build_experiment_config(
        *,
        task: BenchmarkTask,
        arm_architectures: tuple[str, ...],
        combination_key: str | None,
        split: TaskSplit,
        config: BenchmarkConfig,
    ) -> ExperimentConfig:
        return build_experiment_config(
            task=task,
            arm_architectures=arm_architectures,
            combination_key=combination_key,
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

    def _run_one(
        self,
        *,
        task: BenchmarkTask,
        scenario_registry: BenchmarkScenarioRegistry,
        arm_architectures: tuple[str, ...],
        combination_key: str | None,
        seed: int | None,
        repetition: int,
        split: TaskSplit,
        config: BenchmarkConfig,
        benchmark_id: str,
        benchmark_version: str,
        git_commit: str | None,
        fault_catalog: FaultCatalog | None,
    ) -> tuple[str, ExperimentRecord, list[TraceEvent]]:
        """
        Runs exactly one (task, architecture arm, seed, repetition)
        combination. Never raises: a failure anywhere in this method
        (scenario preparation, agent execution, evaluation) is caught and
        turned into a persisted FAILED `ExperimentRecord` so the rest of
        the benchmark invocation can continue (see module docstring).
        """

        run_id = (
            f"{benchmark_id}-{task.task_id}-{'+'.join(arm_architectures)}"
            f"-seed{seed if seed is not None else 'default'}-rep{repetition}"
        )

        exp_config = self._build_experiment_config(
            task=task,
            arm_architectures=arm_architectures,
            combination_key=combination_key,
            split=split,
            config=config,
        )
        exp_config = exp_config.model_copy(update={"repetition": repetition})

        return run_one(
            experiment_runner=self.experiment_runner,
            task=task,
            scenario_registry=scenario_registry,
            exp_config=exp_config,
            run_id=run_id,
            experiment_id=benchmark_id,
            seed=seed,
            benchmark_version=benchmark_version,
            git_commit=git_commit,
            fault_catalog=fault_catalog,
        )
