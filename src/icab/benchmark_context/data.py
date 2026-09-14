"""
ICAB's CONTROLLED BENCHMARK CONTEXT LAYER -- a deterministic, versioned,
clearly-labeled synthetic Enterprise/Site/Area/Work-Center hierarchy and
KPI catalog, built ONLY to give the 50-questions-per-ISA-95-level
benchmark milestone something real and grounded to ask about at levels
TEP genuinely has no data for.

This is NEVER presented as real plant data. Every entity/relationship/
observation this module produces is tagged
`source=BENCHMARK_CONTEXT_SOURCE` ("icab_benchmark_context"), sharply
distinct from `source="tep"` (real Tennessee Eastman Process data) --
see `icab.tep.adapter.TEPAdapter` for the real data this layer is
explicitly NOT replacing or altering. The real TEP Site/Area entities
(`urn:icab:site:tep`, `urn:icab:area:reaction`) are reused AS-IS (the
enterprise/work-center layers attach to them via new, ADDITIVE
relationships) -- their own existing real facts/relationships are never
removed or rewritten, so every experiment record collected against them
before this milestone stays valid and interpretable.

Values are DETERMINISTIC (seeded per `(entity_id, kpi_name)` via
`random.Random`, never `random` module state, never wall-clock/host
randomness) and VERSIONED (`BENCHMARK_CONTEXT_VERSION`) -- the same
seed always produces the same synthetic KPI value, so results referring
to a specific version of this layer stay reproducible. They are
labeled, throughout this module's own docstrings/`ARE_SYNTHETIC=True`
markers and every downstream Question's `provenance` field, as
CONTROLLED/SYNTHETIC data -- realistic in shape and magnitude, not
claimed to be empirically measured.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

BENCHMARK_CONTEXT_SOURCE = "icab_benchmark_context"
BENCHMARK_CONTEXT_VERSION = "1.0.0"

REAL_TEP_SITE_ID = "urn:icab:site:tep"
REAL_TEP_AREA_ID = "urn:icab:area:reaction"

ENTERPRISE_ID = "urn:icab:enterprise:northwind-chemical"
ENTERPRISE_NAME = "Northwind Chemical (controlled benchmark enterprise)"


@dataclass(frozen=True)
class SiteDef:
    key: str
    canonical_id: str
    name: str
    real: bool  # True only for urn:icab:site:tep, reused from icab.tep.adapter.TEPAdapter


@dataclass(frozen=True)
class AreaDef:
    key: str
    canonical_id: str
    name: str
    site_key: str
    real: bool  # True only for urn:icab:area:reaction


@dataclass(frozen=True)
class WorkCenterDef:
    key: str
    canonical_id: str
    name: str
    area_key: str


SITES: tuple[SiteDef, ...] = (
    SiteDef("tep", REAL_TEP_SITE_ID, "Tennessee Eastman Process Site", real=True),
    SiteDef("riverside", "urn:icab:site:riverside", "Riverside Site", real=False),
    SiteDef("port_arthur", "urn:icab:site:port-arthur", "Port Arthur Site", real=False),
)

AREAS: tuple[AreaDef, ...] = (
    AreaDef("reaction", REAL_TEP_AREA_ID, "Reaction Area", "tep", real=True),
    AreaDef("riverside_utilities", "urn:icab:area:riverside-utilities", "Riverside Utilities Area", "riverside", real=False),
    AreaDef("port_arthur_processing", "urn:icab:area:port-arthur-processing", "Port Arthur Processing Area", "port_arthur", real=False),
)

WORK_CENTERS: tuple[WorkCenterDef, ...] = (
    WorkCenterDef("reaction_utilities", "urn:icab:workcenter:reaction-utilities", "Reaction Area Utilities Work Center", "reaction"),
    WorkCenterDef("riverside_packaging", "urn:icab:workcenter:riverside-packaging", "Riverside Packaging Work Center", "riverside_utilities"),
    WorkCenterDef("port_arthur_distillation", "urn:icab:workcenter:port-arthur-distillation", "Port Arthur Distillation Work Center", "port_arthur_processing"),
)


@dataclass(frozen=True)
class KpiDef:
    """One KPI TYPE -- realized once per entity at its own ISA-95 level, below."""

    key: str
    label: str
    unit: str
    low: float
    high: float
    ndigits: int = 1


def _deterministic_value(entity_id: str, kpi: KpiDef) -> float:
    """Same (entity_id, kpi.key, BENCHMARK_CONTEXT_VERSION) always yields the same value -- a controlled/synthetic value, not an empirical measurement."""

    rng = random.Random(f"{entity_id}:{kpi.key}:{BENCHMARK_CONTEXT_VERSION}")
    return round(rng.uniform(kpi.low, kpi.high), kpi.ndigits)


ENTERPRISE_KPIS: tuple[KpiDef, ...] = (
    KpiDef("annual_production_target", "Annual production target", "metric_tons", 180000, 320000, 0),
    KpiDef("enterprise_revenue_target", "Enterprise revenue target", "USD_million", 350, 620, 1),
    KpiDef("enterprise_safety_incidents_ytd", "Enterprise safety incidents (YTD)", "count", 0, 12, 0),
    KpiDef("enterprise_headcount", "Enterprise headcount", "count", 3000, 5500, 0),
    KpiDef("enterprise_energy_consumption_target", "Enterprise energy consumption target", "MWh", 90000, 160000, 0),
    KpiDef("enterprise_capital_budget", "Enterprise capital budget", "USD_million", 30, 90, 1),
    KpiDef("enterprise_quality_target", "Enterprise quality target", "percent", 97.0, 99.9, 2),
    KpiDef("enterprise_carbon_intensity_target", "Enterprise carbon intensity target", "kg_CO2_per_ton", 320, 480, 0),
    KpiDef("enterprise_customer_otd_target", "Enterprise on-time-delivery target", "percent", 92.0, 99.0, 1),
    KpiDef("enterprise_rd_budget", "Enterprise R&D budget", "USD_million", 8, 25, 1),
)

SITE_KPIS: tuple[KpiDef, ...] = (
    KpiDef("site_production_output", "Site production output", "metric_tons_per_month", 5000, 30000, 0),
    KpiDef("site_headcount", "Site headcount", "count", 400, 2200, 0),
    KpiDef("site_safety_incidents_ytd", "Site safety incidents (YTD)", "count", 0, 6, 0),
    KpiDef("site_energy_consumption", "Site energy consumption", "MWh_per_month", 4000, 18000, 0),
    KpiDef("site_utilization_rate", "Site utilization rate", "percent", 55.0, 96.0, 1),
    KpiDef("site_maintenance_backlog", "Site maintenance backlog", "hours", 20, 600, 0),
    KpiDef("site_inventory_level", "Site inventory level", "metric_tons", 500, 8000, 0),
    KpiDef("site_shift_count", "Site shift count", "count", 1, 4, 0),
    KpiDef("site_downtime_hours", "Site downtime", "hours_per_month", 5, 250, 1),
    KpiDef("site_water_consumption", "Site water consumption", "cubic_meters_per_month", 2000, 40000, 0),
)

AREA_KPIS: tuple[KpiDef, ...] = (
    KpiDef("area_production_rate", "Area production rate", "metric_tons_per_day", 50, 900, 1),
    KpiDef("area_utilization", "Area utilization", "percent", 50.0, 95.0, 1),
    KpiDef("area_open_workorders", "Area open work orders", "count", 0, 40, 0),
    KpiDef("area_safety_incidents_ytd", "Area safety incidents (YTD)", "count", 0, 4, 0),
    KpiDef("area_equipment_count", "Area equipment count", "count", 3, 25, 0),
    KpiDef("area_last_inspection_days_ago", "Days since area's last inspection", "days", 1, 180, 0),
    KpiDef("area_energy_consumption", "Area energy consumption", "MWh_per_day", 50, 900, 1),
    KpiDef("area_headcount", "Area headcount", "count", 15, 220, 0),
)

WORK_CENTER_KPIS: tuple[KpiDef, ...] = (
    KpiDef("wc_resource_count", "Work center resource count", "count", 2, 30, 0),
    KpiDef("wc_scheduled_jobs", "Work center scheduled jobs", "count", 0, 60, 0),
    KpiDef("wc_utilization", "Work center utilization", "percent", 40.0, 98.0, 1),
    KpiDef("wc_operator_count", "Work center operator count", "count", 1, 20, 0),
    KpiDef("wc_backlog_hours", "Work center backlog", "hours", 0, 300, 0),
    KpiDef("wc_target_throughput", "Work center target throughput", "units_per_shift", 50, 3000, 0),
    KpiDef("wc_changeover_minutes", "Work center changeover time", "minutes", 5, 180, 0),
    KpiDef("wc_active_shift_count", "Work center active shift count", "count", 1, 3, 0),
)


@dataclass(frozen=True)
class KpiValue:
    entity_id: str
    entity_name: str
    kpi: KpiDef
    value: float
    measurement_id: str


def _measurement_id(entity_id: str, kpi_key: str) -> str:
    # entity_id looks like "urn:icab:site:riverside" -> "urn:icab:measurement:site:riverside:site_production_output"
    suffix = entity_id.split(":", 2)[-1]
    return f"urn:icab:measurement:{suffix}:{kpi_key}"


def enterprise_kpi_values() -> list[KpiValue]:
    return [
        KpiValue(ENTERPRISE_ID, ENTERPRISE_NAME, kpi, _deterministic_value(ENTERPRISE_ID, kpi), _measurement_id(ENTERPRISE_ID, kpi.key))
        for kpi in ENTERPRISE_KPIS
    ]


def site_kpi_values() -> list[KpiValue]:
    return [
        KpiValue(site.canonical_id, site.name, kpi, _deterministic_value(site.canonical_id, kpi), _measurement_id(site.canonical_id, kpi.key))
        for site in SITES
        for kpi in SITE_KPIS
    ]


def area_kpi_values() -> list[KpiValue]:
    return [
        KpiValue(area.canonical_id, area.name, kpi, _deterministic_value(area.canonical_id, kpi), _measurement_id(area.canonical_id, kpi.key))
        for area in AREAS
        for kpi in AREA_KPIS
    ]


def work_center_kpi_values() -> list[KpiValue]:
    return [
        KpiValue(wc.canonical_id, wc.name, kpi, _deterministic_value(wc.canonical_id, kpi), _measurement_id(wc.canonical_id, kpi.key))
        for wc in WORK_CENTERS
        for kpi in WORK_CENTER_KPIS
    ]


def area_by_key(key: str) -> AreaDef:
    return next(a for a in AREAS if a.key == key)


def site_by_key(key: str) -> SiteDef:
    return next(s for s in SITES if s.key == key)
