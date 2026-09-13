"""
M13-B: icab.tep.faults -- the fault catalog model, its persistence, and
the seed-aggregation logic that turns several per-seed
DisturbanceCharacterizations into one FaultCatalogEntry (the
"repeatability across seeds" requirement, enforced at aggregation time).
"""

import pytest

from icab.tep.fault_characterization import DisturbanceCharacterization
from icab.tep.faults import (
    FaultCatalog,
    FaultCatalogEntry,
    build_fault_catalog_entry,
    is_benchmark_ready,
    load_fault_catalog,
    write_fault_catalog,
)


def _characterization(**overrides) -> DisturbanceCharacterization:
    base = dict(
        disturbance="idv_06",
        seed=101,
        magnitude=1.0,
        warmup_hours=1.0,
        duration_hours=4.0,
        deviation_threshold_stdevs=4.0,
        icab_injectable=True,
        plant_tripped=False,
        affected_measurements=[],
        affected_equipment=[],
        max_deviation_stdevs={},
    )
    base.update(overrides)
    return DisturbanceCharacterization(**base)


def test_build_fault_catalog_entry_requires_the_effect_in_every_seed():
    """The 'repeatability across seeds' requirement: a measurement only
    counts as affected if it cleared the threshold in EVERY tested seed
    -- the intersection, not the union."""

    seed_a = _characterization(
        seed=101,
        affected_measurements=["urn:icab:measurement:reactor_pressure", "urn:icab:measurement:stripper_level"],
        affected_equipment=["urn:icab:equipment:reactor", "urn:icab:equipment:stripper"],
    )
    seed_b = _characterization(
        seed=202,
        affected_measurements=["urn:icab:measurement:reactor_pressure"],  # stripper_level didn't repeat
        affected_equipment=["urn:icab:equipment:reactor"],
    )

    entry = build_fault_catalog_entry(
        "idv_06", "A feed loss", [seed_a, seed_b],
        tep_studio_version="0.1.1", characterized_at="2026-01-01T00:00:00+00:00",
    )

    assert entry.affected_measurements == ["urn:icab:measurement:reactor_pressure"]
    assert entry.affected_equipment == ["urn:icab:equipment:reactor"]
    assert entry.empirically_verified is True
    assert entry.characterization_seeds == [101, 202]


def test_build_fault_catalog_entry_not_verified_when_no_seed_agrees():
    seed_a = _characterization(seed=101, affected_measurements=["urn:icab:measurement:reactor_pressure"])
    seed_b = _characterization(seed=202, affected_measurements=["urn:icab:measurement:stripper_level"])

    entry = build_fault_catalog_entry(
        "idv_20", "Unknown random disturbance", [seed_a, seed_b],
        tep_studio_version="0.1.1", characterized_at="2026-01-01T00:00:00+00:00",
    )

    assert entry.affected_measurements == []
    assert entry.empirically_verified is False


def test_build_fault_catalog_entry_verified_via_trip_even_with_no_measurement_overlap():
    """A repeatable plant trip is independently sufficient for
    'empirically verified' -- it need not also show an overlapping
    affected-measurement set."""

    seed_a = _characterization(seed=101, plant_tripped=True, affected_measurements=[])
    seed_b = _characterization(seed=202, plant_tripped=True, affected_measurements=[])

    entry = build_fault_catalog_entry(
        "idv_07", "C header pressure loss", [seed_a, seed_b],
        tep_studio_version="0.1.1", characterized_at="2026-01-01T00:00:00+00:00",
    )

    assert entry.plant_tripped_in_any_seed is True
    assert entry.empirically_verified is True


def test_build_fault_catalog_entry_not_injectable_if_any_seed_failed():
    seed_a = _characterization(seed=101, icab_injectable=True)
    seed_b = _characterization(seed=202, icab_injectable=False, error="RuntimeError: boom")

    entry = build_fault_catalog_entry(
        "idv_13", "Reaction kinetics drift", [seed_a, seed_b],
        tep_studio_version="0.1.1", characterized_at="2026-01-01T00:00:00+00:00",
    )

    assert entry.icab_injectable is False
    assert entry.empirically_verified is False
    assert entry.affected_measurements == []


def test_build_fault_catalog_entry_requires_at_least_one_characterization():
    with pytest.raises(ValueError, match="idv_01"):
        build_fault_catalog_entry(
            "idv_01", "A/C ratio", [], tep_studio_version="0.1.1", characterized_at="now"
        )


def test_catalog_round_trips_through_json(tmp_path):
    entry = FaultCatalogEntry(
        disturbance="idv_06",
        name="A feed loss",
        simulator_supported=True,
        icab_injectable=True,
        empirically_verified=True,
        affected_measurements=["urn:icab:measurement:stripper_level"],
        affected_equipment=["urn:icab:equipment:stripper"],
        plant_tripped_in_any_seed=False,
        characterization_seeds=[101, 202],
        warmup_hours=1.0,
        duration_hours=4.0,
        magnitude=1.0,
        deviation_threshold_stdevs=4.0,
        tep_studio_version="0.1.1",
        characterized_at="2026-01-01T00:00:00+00:00",
    )
    catalog = FaultCatalog(entries=[entry])

    path = write_fault_catalog(catalog, tmp_path / "fault_catalog.json")
    loaded = load_fault_catalog(path)

    assert loaded.get("idv_06").affected_measurements == ["urn:icab:measurement:stripper_level"]
    assert loaded.verified() == loaded.entries


def test_catalog_get_raises_for_unknown_disturbance():
    catalog = FaultCatalog(entries=[])

    with pytest.raises(KeyError, match="idv_99"):
        catalog.get("idv_99")


def test_is_benchmark_ready_reflects_the_supplied_catalog():
    verified_entry = FaultCatalogEntry(
        disturbance="idv_06", name="A feed loss", simulator_supported=True,
        icab_injectable=True, empirically_verified=True,
        plant_tripped_in_any_seed=False, characterization_seeds=[101],
        warmup_hours=1.0, duration_hours=4.0, magnitude=1.0,
        deviation_threshold_stdevs=4.0, tep_studio_version="0.1.1",
        characterized_at="2026-01-01T00:00:00+00:00",
    )
    unverified_entry = FaultCatalogEntry(
        disturbance="idv_04", name="Reactor cooling water inlet temperature", simulator_supported=True,
        icab_injectable=True, empirically_verified=False,
        plant_tripped_in_any_seed=False, characterization_seeds=[101],
        warmup_hours=1.0, duration_hours=4.0, magnitude=1.0,
        deviation_threshold_stdevs=4.0, tep_studio_version="0.1.1",
        characterized_at="2026-01-01T00:00:00+00:00",
    )
    catalog = FaultCatalog(entries=[verified_entry, unverified_entry])

    assert is_benchmark_ready("idv_06", catalog=catalog) is True
    assert is_benchmark_ready("idv_04", catalog=catalog) is False
    assert is_benchmark_ready("idv_99", catalog=catalog) is False  # no entry at all
