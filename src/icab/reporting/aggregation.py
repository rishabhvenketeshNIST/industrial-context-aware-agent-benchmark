"""
M12: grouped, multi-dimensional aggregation over persisted `ExperimentRecord`s.

Distinct from `ExperimentResultStore.write_aggregate` (M9/M10), which
produces one flat per-run comparison table for a single `experiment_id`.
This module answers a different question: "summarize these runs, grouped
by <dimension(s)>, with mean/median/stdev/min/max/n per core metric" --
across scenario, difficulty, architecture (combination), agent type, LLM
model, or seed/run, per the M12 direction. It operates purely on
already-persisted records (no simulator/gateway/LLM calls) and is
deterministic given the same input.

Reuses, rather than re-implements:
  * `icab.experiments.controls` for the exact same heterogeneous-controls
    safeguard `write_aggregate` enforces ("do not aggregate incompatible
    experimental conditions").
  * `icab.experiments.hypotheses.metric_value`/`is_usable_record` for
    metric resolution and the VALID+COMPLETED usability filter.
  * `icab.reporting.stats.summarize` for the actual statistics.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from icab.experiments.controls import CONTROL_FIELDS, HeterogeneousControlsError, control_variance
from icab.experiments.hypotheses import is_usable_record, metric_value
from icab.experiments.models import ExperimentRecord, ExperimentRunStatus, RunValidity

from .metrics import ALL_METRICS
from .stats import SummaryStats, summarize

__all__ = [
    "DIMENSION_RESOLVERS",
    "AggregationReport",
    "GroupSummary",
    "aggregate_records",
    "list_dimensions",
]

#: One resolver per supported `group_by` dimension name. `None` is a
#: legitimate resolved value (e.g. `deterministic_agent` for an LLM run) --
#: it becomes its own group, not an error.
DIMENSION_RESOLVERS: dict[str, Callable[[ExperimentRecord], Any]] = {
    "scenario_id": lambda r: r.config.scenario_id,
    "difficulty": lambda r: r.scenario_difficulty,
    "architecture": lambda r: "+".join(r.config.architectures),
    "architecture_combination_key": lambda r: r.config.architecture_combination_key,
    "agent_type": lambda r: r.config.agent_type.value,
    "deterministic_agent": lambda r: (
        r.config.deterministic_agent.value if r.config.deterministic_agent else None
    ),
    "llm_model": lambda r: r.config.llm_model,
    "llm_temperature": lambda r: r.config.llm_temperature,
    "max_steps": lambda r: r.config.max_steps,
    "simulation_seed": lambda r: r.simulation_seed,
    "run_id": lambda r: r.run_id,
    "experiment_id": lambda r: r.experiment_id,
    "validity": lambda r: r.validity.value,
    "status": lambda r: r.status.value,
    #: M13-D: benchmark-orchestrator dimensions -- all read directly off
    #: ExperimentConfig (no task-registry lookup needed at aggregation
    #: time; see ExperimentConfig.task_type's own docstring for why it's
    #: recorded as its own field rather than derived here). None for any
    #: run not launched via icab.benchmark (e.g. a bare
    #: ExperimentRunner.run() scenario-only call, pre-M13-D style).
    "task_id": lambda r: r.config.task_id,
    "task_type": lambda r: r.config.task_type,
    "suite": lambda r: r.config.suite,
    "split": lambda r: r.config.split,
    "repetition": lambda r: r.config.repetition,
    #: ICAB v2 dimensions -- see icab.usecases/icab.tasks.context_combinations.
    "isa95_level": lambda r: r.config.isa95_level,
    "use_case_id": lambda r: r.config.use_case_id,
    "context_combination_id": lambda r: r.config.context_combination_id,
    #: ICAB question banks -- see icab.questions.
    "question_id": lambda r: r.config.question_id,
    "question_instance_id": lambda r: r.config.question_instance_id,
    "repetition_mode": lambda r: r.config.repetition_mode,
}


def list_dimensions() -> list[str]:
    return sorted(DIMENSION_RESOLVERS)


def _dimension_value(record: ExperimentRecord, dimension: str) -> Any:
    try:
        resolver = DIMENSION_RESOLVERS[dimension]
    except KeyError:
        raise ValueError(
            f"Unknown aggregation dimension: {dimension!r}. Valid: {list_dimensions()}"
        ) from None
    return resolver(record)


class GroupSummary(BaseModel):
    """One group's run counts and per-metric summary statistics."""

    model_config = ConfigDict(extra="forbid")

    group_key: dict[str, str | int | float | bool | None]
    run_ids: list[str]
    n_runs: int
    n_completed: int
    n_failed: int
    n_valid: int
    n_legacy_control_only: int
    #: metric name -> SummaryStats, computed only over this group's VALID
    #: + COMPLETED records (see `icab.experiments.hypotheses.is_usable_record`) --
    #: n_runs/n_completed/etc. above still count every record in the
    #: group regardless, so a group's full composition stays visible even
    #: when its metrics are computed over a subset of it.
    metrics: dict[str, SummaryStats]


class AggregationReport(BaseModel):
    """
    A full grouped aggregation: which dimensions were grouped on, which
    were held constant (and whether they actually were), and one
    `GroupSummary` per distinct combination of `group_by` values observed.
    """

    model_config = ConfigDict(extra="forbid")

    group_by: tuple[str, ...]
    hold_constant: tuple[str, ...]
    controls_consistent: bool
    control_variance: dict[str, list]
    include_invalid: bool
    excluded_invalid_runs: int
    groups: list[GroupSummary]
    #: Every run_id considered (included or excluded), for traceability
    #: back to the underlying results/{raw,traces,evaluations}/ files.
    source_run_ids: list[str] = Field(default_factory=list)


def aggregate_records(
    records: list[ExperimentRecord],
    *,
    group_by: tuple[str, ...],
    metrics: tuple[str, ...] | None = None,
    hold_constant: tuple[str, ...] | None = None,
    include_invalid: bool = False,
    allow_heterogeneous_controls: bool = False,
) -> AggregationReport:
    """
    Group `records` by `group_by` (dimension names from `DIMENSION_RESOLVERS`)
    and compute `icab.reporting.stats.summarize` for each of `metrics`
    (default: every `icab.reporting.metrics.ALL_METRICS` name) within each
    group.

    By default, excludes non-`RunValidity.VALID` records (same as
    `ExperimentResultStore.write_aggregate`) -- pass `include_invalid=True`
    to include them (still separately counted in each group's
    `n_legacy_control_only`, never silently blended into `metrics`, since
    `is_usable_record` always excludes them from metric computation
    regardless of `include_invalid`).

    By default, also refuses (`HeterogeneousControlsError`) to aggregate
    records whose `hold_constant` fields (default: `CONTROL_FIELDS` minus
    whatever's in `group_by` -- and minus `simulation_seed` specifically
    when `scenario_id` is being grouped on, since seed is intrinsic to the
    scenario, not an independent factor) are not identical -- "do not
    aggregate incompatible experimental conditions." Pass
    `allow_heterogeneous_controls=True` to override explicitly; the
    returned report always carries `controls_consistent`/`control_variance`.
    """

    if not group_by:
        raise ValueError("group_by must name at least one dimension")

    for dimension in group_by:
        if dimension not in DIMENSION_RESOLVERS:
            raise ValueError(
                f"Unknown aggregation dimension: {dimension!r}. Valid: {list_dimensions()}"
            )

    resolved_metrics = metrics or tuple(name for name, _label in ALL_METRICS)

    included = [
        record for record in records if include_invalid or record.validity == RunValidity.VALID
    ]
    excluded_count = len(records) - len(included)

    if hold_constant is None:
        hold_constant = tuple(field for field in CONTROL_FIELDS if field not in group_by)
        if "scenario_id" in group_by and "simulation_seed" in hold_constant:
            hold_constant = tuple(field for field in hold_constant if field != "simulation_seed")

    variance = control_variance(included, hold_constant) if included and hold_constant else {}
    if variance and not allow_heterogeneous_controls:
        raise HeterogeneousControlsError(
            f"Records being aggregated by {group_by} do not hold constant: "
            f"{variance}. Pass allow_heterogeneous_controls=True to aggregate "
            "anyway -- see docs/research/experiment-plan.md."
        )

    groups: dict[tuple[Any, ...], list[ExperimentRecord]] = {}
    for record in included:
        key = tuple(_dimension_value(record, dimension) for dimension in group_by)
        groups.setdefault(key, []).append(record)

    group_summaries: list[GroupSummary] = []
    for key in sorted(groups, key=lambda k: [str(part) for part in k]):
        group_records = groups[key]
        usable = [record for record in group_records if is_usable_record(record)]

        metric_summaries: dict[str, SummaryStats] = {}
        for metric_name in resolved_metrics:
            values = [
                value
                for value in (metric_value(record, metric_name) for record in usable)
                if value is not None
            ]
            metric_summaries[metric_name] = summarize(values)

        group_summaries.append(
            GroupSummary(
                group_key=dict(zip(group_by, key, strict=True)),
                run_ids=[record.run_id for record in group_records],
                n_runs=len(group_records),
                n_completed=sum(
                    1 for record in group_records if record.status == ExperimentRunStatus.COMPLETED
                ),
                n_failed=sum(
                    1 for record in group_records if record.status == ExperimentRunStatus.FAILED
                ),
                n_valid=sum(
                    1 for record in group_records if record.validity == RunValidity.VALID
                ),
                n_legacy_control_only=sum(
                    1
                    for record in group_records
                    if record.validity == RunValidity.LEGACY_CONTROL_ONLY
                ),
                metrics=metric_summaries,
            )
        )

    return AggregationReport(
        group_by=group_by,
        hold_constant=hold_constant,
        controls_consistent=not variance,
        control_variance=variance,
        include_invalid=include_invalid,
        excluded_invalid_runs=excluded_count,
        groups=group_summaries,
        source_run_ids=sorted(record.run_id for record in records),
    )
