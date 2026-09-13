"""
Shared "held constant" experimental-control checking (M9/M10), used by both
`ExperimentResultStore.write_aggregate` (a flat per-run comparison table)
and `icab.reporting.aggregation` (M12's grouped, multi-dimensional
aggregation) -- factored out here so both enforce the exact same
heterogeneous-controls safeguard rather than two subtly different copies.
"""

from __future__ import annotations

from .models import ExperimentRecord

#: Fields that must be held equal across every run in a comparison for it
#: to be a valid architecture comparison -- i.e. the "everything else held
#: constant" side of "varying only architecture" (see docs/research/
#: experiment-plan.md). `objective` isn't listed separately because it's
#: determined by `scenario_id` (same scenario => same objective).
CONTROL_FIELDS: tuple[str, ...] = (
    "scenario_id",
    "simulation_seed",
    "llm_model",
    "llm_temperature",
    "max_steps",
)


class HeterogeneousControlsError(ValueError):
    """
    Raised when the records being aggregated do not hold `CONTROL_FIELDS`
    constant and heterogeneous controls were not explicitly allowed --
    i.e. this would not be a valid "vary only architecture" comparison.
    The written report still records `controls_consistent`/
    `control_variance` either way, so an explicitly-allowed heterogeneous
    aggregation stays self-documenting rather than silently implying a
    controlled comparison it isn't.
    """


def control_value(record: ExperimentRecord, field: str) -> object:
    if field == "scenario_id":
        return record.config.scenario_id
    if field == "simulation_seed":
        return record.simulation_seed
    if field == "llm_model":
        return record.config.llm_model
    if field == "llm_temperature":
        return record.config.llm_temperature
    if field == "max_steps":
        return record.config.max_steps
    raise ValueError(f"Unknown control field: {field}")  # pragma: no cover


def control_variance(
    records: list[ExperimentRecord],
    fields: tuple[str, ...] = CONTROL_FIELDS,
) -> dict[str, list]:
    """Which of `fields` differ across `records`, and their distinct values."""

    variance: dict[str, list] = {}
    for field in fields:
        values = {control_value(record, field) for record in records}
        if len(values) > 1:
            variance[field] = sorted(values, key=str)
    return variance
