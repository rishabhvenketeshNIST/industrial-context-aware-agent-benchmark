"""
Runs a selected slice of ONE ISA-95 level's question bank against real
infrastructure -- Question -> Question Instance -> Repetition -> real
Experiment Run, reusing the SAME execution path (`icab.benchmark
._execution`) `BenchmarkRunner`/`ContextExperimentRunner` already use, so
every run lands through the exact same `ExperimentRunner.run_task` /
`GroundedInvestigationEvaluator.evaluate_task` path as every other ICAB
v2 run.

The one thing genuinely new here: results are written to a LEVEL-SCOPED
`ExperimentResultStore` (`definition.results_root`, e.g. `results/equipment/`)
with a hard guard -- a run whose own `ExperimentConfig.isa95_level`
disagrees with the benchmark definition it is being saved under fails
loudly rather than silently writing an Equipment result into
`results/process_cell/` or vice versa.
"""

from __future__ import annotations

import uuid
from typing import Sequence

from pydantic import BaseModel, ConfigDict, Field

from icab.experiments import ExperimentResultStore, ExperimentRunner, ExperimentRunStatus
from icab.questions import Question, QuestionBankRegistry, QuestionInstance, RepetitionMode
from icab.scenarios import BenchmarkScenarioRegistry
from icab.tasks.context_combinations import ContextCombination, combination_for_id, combination_id_for
from icab.tasks.context_conditions import ConditionStatus, resolve_condition_architectures
from icab.tasks.registry import BenchmarkTaskRegistry
from icab.tep.faults import FaultCatalog, load_fault_catalog
from icab.usecases import IndustrialUseCaseRegistry

from ._execution import build_experiment_config, run_one
from .config import get_git_commit
from .levels import ISA95BenchmarkDefinition
from .manifest import write_manifest
from .runner import BenchmarkIdCollisionError

__all__ = [
    "IsaLevelMismatchError",
    "QuestionBenchmarkConfig",
    "QuestionBenchmarkResult",
    "QuestionBenchmarkRunner",
    "QuestionRunOutcome",
]


class IsaLevelMismatchError(ValueError):
    """
    Raised when a run's own `ExperimentConfig.isa95_level` disagrees with
    the `ISA95BenchmarkDefinition` it was about to be saved under --
    never silently written to the wrong level's results/ tree.
    """


class QuestionBenchmarkConfig(BaseModel):
    """One `QuestionBenchmarkRunner.run()` invocation's configuration."""

    model_config = ConfigDict(extra="forbid")

    #: Restrict to these question ids -- None means every question in
    #: the level's bank (still further narrowed by use_case_ids/tags
    #: below, if given).
    question_ids: list[str] | None = None
    use_case_ids: list[str] | None = None
    tags: list[str] | None = None

    #: Context combination ids to test PER selected question -- resolved
    #: against each question's realized task's own available
    #: architectures (icab.tasks.context_conditions), exactly like
    #: icab.benchmark.context_experiment. None means: just use the
    #: question's own hypothesized_required_context combination.
    context_combination_ids: list[str] | None = None
    allow_overshoot: bool = False

    #: Scenario selection PER question -- None means every scenario the
    #: question has a real realization for (question.realizations).
    scenario_ids: list[str] | None = None

    agent: str = "llm"
    llm_model: str | None = None
    llm_temperature: float | None = None
    max_steps: int | None = Field(default=None, ge=1)
    max_tool_calls: int | None = Field(default=None, ge=1)
    max_context_tokens: int | None = Field(default=None, ge=1)
    max_wall_time_seconds: float | None = Field(default=None, gt=0)

    #: Repetitions PER (question, scenario, context condition,
    #: architecture arm) instance -- configurable, never hard-coded.
    repetitions: int = Field(default=1, ge=1)
    seeds: list[int] | None = None
    repetition_mode: str = RepetitionMode.EXACT.value

    name: str | None = None
    force: bool = False


class QuestionRunOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: str
    scenario_id: str
    context_combination_id: str
    resolution_status: str
    resolved_architectures: list[str] | None
    instance_id: str | None
    executed: bool
    run_ids: list[str] = Field(default_factory=list)
    reason: str


class QuestionBenchmarkResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    campaign_id: str
    benchmark_id: str
    isa95_level: str

    outcomes: list[QuestionRunOutcome]

    total_selected_instances: int
    executed_instances: int
    total_runs: int
    successful_runs: int
    failed_runs: int

    manifest_path: str | None = None


class QuestionBenchmarkRunner:
    """Selects, resolves, and executes a slice of one ISA-95 level's question bank."""

    def __init__(
        self,
        *,
        definition: ISA95BenchmarkDefinition,
        experiment_runner: ExperimentRunner,
        question_registry: QuestionBankRegistry,
        use_case_registry: IndustrialUseCaseRegistry,
        task_registry: BenchmarkTaskRegistry,
        scenario_registry: BenchmarkScenarioRegistry,
        experiment_store: ExperimentResultStore | None = None,
    ) -> None:
        if not definition.executable:
            raise ValueError(
                f"{definition.benchmark_id} ({definition.isa95_level.value}) is not executable: "
                f"{definition.coverage_note}"
            )

        self.definition = definition
        self.experiment_runner = experiment_runner
        self.question_registry = question_registry
        self.use_case_registry = use_case_registry
        self.task_registry = task_registry
        self.scenario_registry = scenario_registry
        self.experiment_store = experiment_store or ExperimentResultStore(root=definition.results_root)

    def run(self, config: QuestionBenchmarkConfig) -> QuestionBenchmarkResult:
        questions = self._select_questions(config)
        if not questions:
            raise ValueError(
                f"No questions matched the given filters for {self.definition.benchmark_id} -- "
                f"check question_ids/use_case_ids/tags against {self.question_registry.list_ids()}."
            )

        campaign_id = config.name or f"{self.definition.benchmark_id}-{uuid.uuid4().hex[:8]}"
        self._check_no_existing_campaign(campaign_id, force=config.force)

        git_commit = get_git_commit()
        fault_catalog = self._load_fault_catalog_best_effort()
        seed_values: list[int | None] = list(config.seeds) if config.seeds else [None]

        outcomes: list[QuestionRunOutcome] = []
        all_run_ids: list[str] = []
        successful = failed = 0

        for question in questions:
            scenario_ids = config.scenario_ids or list(question.realizations.keys())
            for scenario_id in scenario_ids:
                if scenario_id not in question.realizations:
                    outcomes.append(
                        QuestionRunOutcome(
                            question_id=question.question_id,
                            scenario_id=scenario_id,
                            context_combination_id="(n/a)",
                            resolution_status="not_applicable",
                            resolved_architectures=None,
                            instance_id=None,
                            executed=False,
                            reason=f"{question.question_id} has no realization for scenario {scenario_id!r}.",
                        )
                    )
                    continue

                task_id = question.realizations[scenario_id]
                task = self.task_registry.get(task_id)

                combos = self._select_combinations(config, question)

                for combo in combos:
                    resolution = resolve_condition_architectures(combo, task.available_architectures)

                    if resolution.status == ConditionStatus.UNREALIZABLE:
                        outcomes.append(self._skip_outcome(question, scenario_id, combo, resolution))
                        continue
                    if resolution.status == ConditionStatus.OVERSHOOT and not config.allow_overshoot:
                        outcomes.append(self._skip_outcome(question, scenario_id, combo, resolution))
                        continue

                    instance = QuestionInstance.build(
                        question_id=question.question_id,
                        scenario_id=scenario_id,
                        architectures=resolution.architectures,
                        agent=config.agent,
                        llm_model=config.llm_model,
                        llm_temperature=config.llm_temperature,
                    )

                    run_ids = self._execute_instance(
                        task=task,
                        question=question,
                        instance=instance,
                        combo=combo,
                        config=config,
                        campaign_id=campaign_id,
                        git_commit=git_commit,
                        fault_catalog=fault_catalog,
                        seed_values=seed_values,
                    )
                    all_run_ids.extend(rid for rid, _status in run_ids)
                    for _rid, status in run_ids:
                        if status == ExperimentRunStatus.COMPLETED:
                            successful += 1
                        else:
                            failed += 1

                    outcomes.append(
                        QuestionRunOutcome(
                            question_id=question.question_id,
                            scenario_id=scenario_id,
                            context_combination_id=combo.combination_id,
                            resolution_status=resolution.status.value,
                            resolved_architectures=list(resolution.architectures),
                            instance_id=instance.instance_id,
                            executed=True,
                            run_ids=[rid for rid, _status in run_ids],
                            reason=resolution.reason,
                        )
                    )

        manifest_path = None
        if all_run_ids:
            records = [self.experiment_store.load_record(run_id) for run_id in self.experiment_store.list_run_ids()]
            level_records = [r for r in records if r.config.isa95_level == self.definition.isa95_level.value]
            # Explicit root=self.experiment_store.root -- NEVER
            # write_manifest's own default (definition.results_root),
            # which would silently target the real production results/
            # tree even when this runner was constructed against a
            # different (e.g. test tmp_path) store.
            manifest_path = str(write_manifest(self.definition, level_records, root=self.experiment_store.root))

        return QuestionBenchmarkResult(
            campaign_id=campaign_id,
            benchmark_id=self.definition.benchmark_id,
            isa95_level=self.definition.isa95_level.value,
            outcomes=outcomes,
            total_selected_instances=len(outcomes),
            executed_instances=sum(1 for o in outcomes if o.executed),
            total_runs=len(all_run_ids),
            successful_runs=successful,
            failed_runs=failed,
            manifest_path=manifest_path,
        )

    # -- selection -----------------------------------------------------

    def _select_questions(self, config: QuestionBenchmarkConfig) -> list[Question]:
        questions = list(self.question_registry)

        if config.question_ids:
            wanted = set(config.question_ids)
            questions = [q for q in questions if q.question_id in wanted]
        if config.use_case_ids:
            wanted_uc = set(config.use_case_ids)
            questions = [q for q in questions if q.use_case_id in wanted_uc]
        if config.tags:
            wanted_tags = set(config.tags)
            questions = [q for q in questions if wanted_tags & {t.value for t in q.tags}]

        return sorted(questions, key=lambda q: q.question_id)

    def _select_combinations(self, config: QuestionBenchmarkConfig, question: Question) -> list[ContextCombination]:
        if config.context_combination_ids:
            return [combination_for_id(cid) for cid in config.context_combination_ids]
        return [combination_for_id(combination_id_for(question.hypothesized_required_context))]

    # -- execution -------------------------------------------------------

    def _execute_instance(
        self,
        *,
        task,
        question: Question,
        instance: QuestionInstance,
        combo: ContextCombination,
        config: QuestionBenchmarkConfig,
        campaign_id: str,
        git_commit: str | None,
        fault_catalog: FaultCatalog | None,
        seed_values: Sequence[int | None],
    ) -> list[tuple[str, ExperimentRunStatus]]:
        from icab.tasks.splits import TaskSplit

        results: list[tuple[str, ExperimentRunStatus]] = []

        exp_config = build_experiment_config(
            task=task,
            arm_architectures=instance.architectures,
            combination_key=None,
            split=TaskSplit.DEVELOPMENT,  # question banks are not split-partitioned -- see module docstring
            agent=config.agent,
            suite=self.definition.benchmark_id,
            llm_model=config.llm_model,
            llm_temperature=config.llm_temperature,
            max_steps=config.max_steps,
            max_tool_calls=config.max_tool_calls,
            max_context_tokens=config.max_context_tokens,
            max_wall_time_seconds=config.max_wall_time_seconds,
        )
        exp_config = exp_config.model_copy(
            update={
                "question_id": question.question_id,
                "question_instance_id": instance.instance_id,
                "repetition_mode": config.repetition_mode,
            }
        )

        if exp_config.isa95_level != self.definition.isa95_level.value:
            raise IsaLevelMismatchError(
                f"Refusing to run {question.question_id!r} (task {task.task_id!r}, isa95_level="
                f"{exp_config.isa95_level!r}) under the {self.definition.isa95_level.value!r} benchmark "
                f"({self.definition.benchmark_id}) -- its own isa95_level disagrees. This would have "
                f"written an Equipment/Process-Cell/Area result under the wrong level's results/ tree."
            )

        for seed in seed_values:
            for repetition in range(1, config.repetitions + 1):
                run_id = f"{campaign_id}-{instance.instance_id}-seed{seed if seed is not None else 'default'}-rep{repetition}"
                run_config = exp_config.model_copy(update={"repetition": repetition})

                run_id, record, trace = run_one(
                    experiment_runner=self.experiment_runner,
                    task=task,
                    scenario_registry=self.scenario_registry,
                    exp_config=run_config,
                    run_id=run_id,
                    experiment_id=campaign_id,
                    seed=seed,
                    benchmark_version=self.definition.question_bank_version,
                    git_commit=git_commit,
                    fault_catalog=fault_catalog,
                )

                if record.config.isa95_level != self.definition.isa95_level.value:
                    raise IsaLevelMismatchError(
                        f"Refusing to persist run {run_id!r} under {self.definition.results_root} -- "
                        f"its own ExperimentConfig.isa95_level={record.config.isa95_level!r} disagrees "
                        f"with this benchmark's {self.definition.isa95_level.value!r}."
                    )

                self.experiment_store.save(record, trace)
                results.append((run_id, record.status))

        return results

    def _skip_outcome(self, question: Question, scenario_id: str, combo: ContextCombination, resolution) -> QuestionRunOutcome:
        return QuestionRunOutcome(
            question_id=question.question_id,
            scenario_id=scenario_id,
            context_combination_id=combo.combination_id,
            resolution_status=resolution.status.value,
            resolved_architectures=list(resolution.architectures) if resolution.architectures else None,
            instance_id=None,
            executed=False,
            reason=resolution.reason,
        )

    # -- misc -------------------------------------------------------------

    def _check_no_existing_campaign(self, campaign_id: str, *, force: bool) -> None:
        if force:
            return
        existing_raw = list(self.experiment_store.raw_dir.glob(f"{campaign_id}-*.json"))
        if existing_raw:
            raise BenchmarkIdCollisionError(
                f"A question-benchmark campaign with id {campaign_id!r} already has persisted results "
                f"under {self.experiment_store.root}/ -- refusing to overwrite it. Pass a different "
                "name (or omit it for a fresh auto-generated id), or force=True."
            )

    @staticmethod
    def _load_fault_catalog_best_effort() -> FaultCatalog | None:
        try:
            return load_fault_catalog()
        except Exception:  # noqa: BLE001 -- audit metadata only, never fatal
            return None
