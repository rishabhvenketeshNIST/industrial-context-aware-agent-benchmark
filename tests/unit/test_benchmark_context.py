"""Unit tests for icab.benchmark_context -- the controlled/synthetic Enterprise/Site/Area/Work-Center data layer."""

from __future__ import annotations

from icab.benchmark_context import build_benchmark_context_environment
from icab.benchmark_context.data import (
    AREA_KPIS,
    AREAS,
    BENCHMARK_CONTEXT_SOURCE,
    ENTERPRISE_ID,
    ENTERPRISE_KPIS,
    REAL_TEP_AREA_ID,
    REAL_TEP_SITE_ID,
    SITE_KPIS,
    SITES,
    WORK_CENTER_KPIS,
    WORK_CENTERS,
    _deterministic_value,
    enterprise_kpi_values,
    site_kpi_values,
    work_center_kpi_values,
)


class TestDeterministicValues:
    def test_same_inputs_always_produce_the_same_value(self):
        kpi = ENTERPRISE_KPIS[0]
        a = _deterministic_value(ENTERPRISE_ID, kpi)
        b = _deterministic_value(ENTERPRISE_ID, kpi)
        assert a == b

    def test_different_entities_get_different_values_for_the_same_kpi(self):
        kpi = SITE_KPIS[0]
        values = {_deterministic_value(site.canonical_id, kpi) for site in SITES}
        assert len(values) == len(SITES)  # no accidental collisions across 3 sites

    def test_values_stay_within_the_declared_range(self):
        for kpi in ENTERPRISE_KPIS:
            value = _deterministic_value(ENTERPRISE_ID, kpi)
            assert kpi.low <= value <= kpi.high


class TestRealVsControlledSeparation:
    def test_the_real_tep_site_and_area_are_never_redefined(self):
        env = build_benchmark_context_environment()
        entity_ids = {e.canonical_id for e in env.entities}
        assert REAL_TEP_SITE_ID not in entity_ids  # reused as-is, never redefined here
        assert REAL_TEP_AREA_ID not in entity_ids

    def test_every_synthetic_entity_and_relationship_and_observation_is_tagged(self):
        env = build_benchmark_context_environment()
        assert all(e.source == BENCHMARK_CONTEXT_SOURCE for e in env.entities)
        assert all(r.source == BENCHMARK_CONTEXT_SOURCE for r in env.relationships)
        assert all(o.source == BENCHMARK_CONTEXT_SOURCE for o in env.observations)

    def test_the_real_tep_site_gets_an_additive_link_to_the_enterprise(self):
        env = build_benchmark_context_environment()
        site_to_enterprise = [
            r for r in env.relationships
            if r.subject == REAL_TEP_SITE_ID and r.predicate.value == "PART_OF" and r.object == ENTERPRISE_ID
        ]
        assert len(site_to_enterprise) == 1  # additive: the real site's OWN existing relationships are untouched elsewhere


class TestHierarchyCompleteness:
    def test_every_site_links_to_the_enterprise(self):
        env = build_benchmark_context_environment()
        part_of_enterprise = {r.subject for r in env.relationships if r.predicate.value == "PART_OF" and r.object == ENTERPRISE_ID}
        assert part_of_enterprise == {s.canonical_id for s in SITES}

    def test_every_work_center_links_to_its_declared_area(self):
        env = build_benchmark_context_environment()
        for wc in WORK_CENTERS:
            from icab.benchmark_context.data import area_by_key

            area = area_by_key(wc.area_key)
            assert any(
                r.subject == wc.canonical_id and r.predicate.value == "PART_OF" and r.object == area.canonical_id
                for r in env.relationships
            )


class TestKpiCatalogSizes:
    def test_expected_measurement_counts(self):
        assert len(enterprise_kpi_values()) == len(ENTERPRISE_KPIS) * 1
        assert len(site_kpi_values()) == len(SITE_KPIS) * len(SITES)
        assert len(work_center_kpi_values()) == len(WORK_CENTER_KPIS) * len(WORK_CENTERS)

    def test_every_kpi_value_has_a_unique_measurement_id(self):
        values = enterprise_kpi_values() + site_kpi_values() + work_center_kpi_values()
        ids = [v.measurement_id for v in values]
        assert len(ids) == len(set(ids))


class TestEnvironmentIsReadyToLoad:
    def test_environment_has_no_duplicate_entity_ids(self):
        env = build_benchmark_context_environment()
        ids = [e.canonical_id for e in env.entities]
        assert len(ids) == len(set(ids))

    def test_every_observation_measurement_id_has_a_matching_measurement_entity(self):
        env = build_benchmark_context_environment()
        measurement_ids = {e.canonical_id for e in env.entities}
        for obs in env.observations:
            assert obs.measurement_id in measurement_ids
