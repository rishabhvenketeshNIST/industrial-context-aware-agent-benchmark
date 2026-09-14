"""
Builds a `CIMEnvironment` (entities, relationships, observations) from
`icab.benchmark_context.data`'s synthetic hierarchy/KPI catalog --
loaded through the EXACT SAME `icab.context.environment_loader
.EnvironmentLoader` real TEP data already uses (see
`icab.benchmark_context.seed`), so this controlled data reaches the
agent through the SAME architecture/context mechanisms being evaluated
-- never a special hidden database only the evaluator can see.

`Enterprise`/`Site`/`Area`/`WorkCenter` are the SAME CIM entity classes
`icab.tep.adapter.TEPAdapter` already uses for the real Site/Area
entities -- this module reuses, never redefines, them.
"""

from __future__ import annotations

from datetime import UTC, datetime

from icab.cim import (
    Area,
    CIMEnvironment,
    Enterprise,
    Entity,
    Measurement,
    Observation,
    Relationship,
    RelationshipType,
    Site,
    WorkCenter,
)

from . import data

#: A single, fixed reference timestamp for every synthetic observation
#: -- these are static/rarely-changing KPI-style reference values, not
#: live simulated process data, so there is no meaningful "when" beyond
#: "as of this controlled benchmark context version."
_REFERENCE_TIMESTAMP = datetime(2026, 1, 1, tzinfo=UTC)


def build_hierarchy_entities() -> list[Entity]:
    entities: list[Entity] = [Enterprise(canonical_id=data.ENTERPRISE_ID, name=data.ENTERPRISE_NAME, source=data.BENCHMARK_CONTEXT_SOURCE, source_id="enterprise")]

    for site in data.SITES:
        if site.real:
            continue  # urn:icab:site:tep already exists via icab.tep.adapter.TEPAdapter -- never redefined here.
        entities.append(Site(canonical_id=site.canonical_id, name=site.name, source=data.BENCHMARK_CONTEXT_SOURCE, source_id=site.key))

    for area in data.AREAS:
        if area.real:
            continue  # urn:icab:area:reaction already exists -- never redefined here.
        entities.append(Area(canonical_id=area.canonical_id, name=area.name, source=data.BENCHMARK_CONTEXT_SOURCE, source_id=area.key))

    for wc in data.WORK_CENTERS:
        entities.append(WorkCenter(canonical_id=wc.canonical_id, name=wc.name, source=data.BENCHMARK_CONTEXT_SOURCE, source_id=wc.key))

    return entities


def build_hierarchy_relationships() -> list[Relationship]:
    relationships: list[Relationship] = []

    for site in data.SITES:
        # ADDITIVE only: the real urn:icab:site:tep keeps its own existing
        # real relationships untouched -- this only ADDS a new PART_OF
        # edge to the (new) enterprise, never removing or altering
        # anything already established.
        relationships.append(
            Relationship(subject=site.canonical_id, predicate=RelationshipType.PART_OF, object=data.ENTERPRISE_ID, source=data.BENCHMARK_CONTEXT_SOURCE)
        )

    for area in data.AREAS:
        site = data.site_by_key(area.site_key)
        if area.real:
            continue  # urn:icab:area:reaction PART_OF urn:icab:site:tep already exists as a real relationship.
        relationships.append(
            Relationship(subject=area.canonical_id, predicate=RelationshipType.PART_OF, object=site.canonical_id, source=data.BENCHMARK_CONTEXT_SOURCE)
        )

    for wc in data.WORK_CENTERS:
        area = data.area_by_key(wc.area_key)
        relationships.append(
            Relationship(subject=wc.canonical_id, predicate=RelationshipType.PART_OF, object=area.canonical_id, source=data.BENCHMARK_CONTEXT_SOURCE)
        )

    return relationships


def _kpi_entities_and_observations(kpi_values: list[data.KpiValue]) -> tuple[list[Entity], list[Observation]]:
    entities: list[Entity] = []
    observations: list[Observation] = []

    for kv in kpi_values:
        entities.append(
            Measurement(
                canonical_id=kv.measurement_id,
                name=f"{kv.entity_name}: {kv.kpi.label}",
                description=f"Controlled benchmark KPI ({kv.kpi.unit}) for {kv.entity_id}.",
                source=data.BENCHMARK_CONTEXT_SOURCE,
                source_id=kv.kpi.key,
            )
        )
        observations.append(
            Observation(
                observation_id=f"{kv.measurement_id}:obs",
                measurement_id=kv.measurement_id,
                timestamp=_REFERENCE_TIMESTAMP,
                value=kv.value,
                unit=kv.kpi.unit,
                quality="GOOD",
                source=data.BENCHMARK_CONTEXT_SOURCE,
                source_id=kv.kpi.key,
            )
        )

    return entities, observations


def build_kpi_measurement_relationships(kpi_values: list[data.KpiValue]) -> list[Relationship]:
    """One MEASURES-style ASSOCIATED_WITH relationship per KPI, tying the measurement back to its owning entity (C3 relational discoverability)."""

    return [
        Relationship(subject=kv.entity_id, predicate=RelationshipType.ASSOCIATED_WITH, object=kv.measurement_id, source=data.BENCHMARK_CONTEXT_SOURCE)
        for kv in kpi_values
    ]


def build_benchmark_context_environment() -> CIMEnvironment:
    """
    The complete controlled benchmark context layer as one `CIMEnvironment`
    -- pass to `icab.context.environment_loader.EnvironmentLoader.load()`
    (see `icab.benchmark_context.seed`) to write it into the real
    historian/knowledge_graph, exactly like `icab.tep.adapter.TEPAdapter
    .build_real_environment()` already does for real TEP data.
    """

    entities = build_hierarchy_entities()
    relationships = build_hierarchy_relationships()
    observations: list[Observation] = []

    for kpi_values_fn in (data.enterprise_kpi_values, data.site_kpi_values, data.area_kpi_values, data.work_center_kpi_values):
        kpi_values = kpi_values_fn()
        kpi_entities, kpi_observations = _kpi_entities_and_observations(kpi_values)
        entities.extend(kpi_entities)
        observations.extend(kpi_observations)
        relationships.extend(build_kpi_measurement_relationships(kpi_values))

    return CIMEnvironment(entities=entities, relationships=relationships, observations=observations)
