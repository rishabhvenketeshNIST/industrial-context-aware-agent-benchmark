"""
M13-B: the ICAB fault/disturbance catalog -- what is actually usable,
and how well-characterized, for benchmark purposes.

Three explicitly distinct, cumulative tiers (per the M13-B research
direction -- existing merely in the simulator's own registry is NOT the
same as having been actually run and shown to do something):

  1. ``simulator_supported`` -- `tep_studio.list_disturbances()` lists
     it. Trivially true for all 28; recorded for traceability, not as an
     achievement.
  2. ``icab_injectable`` -- `TEPSimulator.inject_fault()` plus actually
     stepping the plant forward completed without raising, in EVERY
     characterization seed tested. Distinguishes "the API accepts the
     name" from "actually running it doesn't break."
  3. ``empirically_verified`` -- REPEATABLY (the same measurements
     affected, or a trip, in EVERY tested seed) produced either a real,
     above-noise-floor measurement deviation or a plant trip. This --
     not (1) or (2) -- is what makes a disturbance eligible for
     benchmark scenario use; see `is_benchmark_ready`.

The characterization run that establishes (2)/(3) lives in
`icab.tep.fault_characterization` (kept separate: that module is the
empirical run, this module is the resulting SPECIFICATION/CATALOG the
run's results populate) and is persisted at
`configs/benchmark/fault_catalog.json`
(`scripts/characterize_tep_disturbances.py` regenerates it) -- the
observed process response, stored separately from the disturbance's own
bare identity/name.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from .fault_characterization import DisturbanceCharacterization

#: Default location of the persisted, empirically-derived fault catalog
#: -- versioned configuration/reference data (like the D1-D4 scenario
#: YAMLs under configs/benchmark/scenarios/), not a per-experiment run
#: result, so it lives under configs/, not results/.
DEFAULT_CATALOG_PATH = Path("configs/benchmark/fault_catalog.json")


class FaultCatalogEntry(BaseModel):
    """One disturbance's aggregated (across every tested seed) empirical status."""

    model_config = ConfigDict(extra="forbid")

    disturbance: str = Field(min_length=1, description="Simulator's own id, e.g. 'idv_06'.")
    name: str = Field(description="tep_studio's own description of this disturbance.")

    simulator_supported: bool
    icab_injectable: bool
    empirically_verified: bool

    #: Canonical measurement/equipment ids affected REPEATABLY -- the
    #: INTERSECTION across every tested seed's affected set, not the
    #: union (a conservative, "this holds up every time we checked"
    #: signal, matching the "repeatability across seeds" requirement).
    affected_measurements: list[str] = Field(default_factory=list)
    affected_equipment: list[str] = Field(default_factory=list)
    #: Tripped the plant in at least one tested seed -- kept even if not
    #: every seed, since a trip is independently notable regardless of
    #: whether it is the repeatable outcome.
    plant_tripped_in_any_seed: bool

    characterization_seeds: list[int]
    warmup_hours: float
    duration_hours: float
    magnitude: float
    deviation_threshold_stdevs: float

    tep_studio_version: str
    characterized_at: str = Field(description="ISO 8601 UTC timestamp of the characterization run.")


class FaultCatalog(BaseModel):
    """The full, persisted characterization catalog for every simulator disturbance."""

    model_config = ConfigDict(extra="forbid")

    entries: list[FaultCatalogEntry]

    def get(self, disturbance: str) -> FaultCatalogEntry:
        for entry in self.entries:
            if entry.disturbance == disturbance:
                return entry
        raise KeyError(f"No fault-catalog entry for {disturbance!r}.")

    def verified(self) -> list[FaultCatalogEntry]:
        """Every entry with `empirically_verified=True` -- the benchmark-ready set."""

        return [entry for entry in self.entries if entry.empirically_verified]


def load_fault_catalog(path: str | Path = DEFAULT_CATALOG_PATH) -> FaultCatalog:
    return FaultCatalog.model_validate_json(Path(path).read_text(encoding="utf-8"))


def write_fault_catalog(catalog: FaultCatalog, path: str | Path = DEFAULT_CATALOG_PATH) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(catalog.model_dump_json(indent=2), encoding="utf-8")
    return path


def build_fault_catalog_entry(
    disturbance: str,
    name: str,
    characterizations: list[DisturbanceCharacterization],
    *,
    tep_studio_version: str,
    characterized_at: str,
) -> FaultCatalogEntry:
    """
    Aggregate one disturbance's per-seed `DisturbanceCharacterization`s
    (see `icab.tep.fault_characterization.characterize_all_disturbances`)
    into a single `FaultCatalogEntry`.

    ``icab_injectable``/``empirically_verified`` require the property to
    hold in EVERY supplied characterization (all tested seeds), not just
    one -- this is the "repeatability across seeds" requirement, applied
    at aggregation time rather than trusted from a single lucky run.
    ``affected_measurements``/``affected_equipment`` are the
    INTERSECTION across seeds for the same reason.
    """

    if not characterizations:
        raise ValueError(f"No characterizations supplied for {disturbance!r}.")

    icab_injectable = all(c.icab_injectable for c in characterizations)
    plant_tripped_in_any_seed = any(c.plant_tripped for c in characterizations)

    if icab_injectable:
        affected_sets = [set(c.affected_measurements) for c in characterizations]
        repeatable_affected_measurements = sorted(set.intersection(*affected_sets))
        empirically_verified = plant_tripped_in_any_seed or bool(repeatable_affected_measurements)
    else:
        repeatable_affected_measurements = []
        empirically_verified = False

    equipment_sets = [set(c.affected_equipment) for c in characterizations]
    repeatable_affected_equipment = (
        sorted(set.intersection(*equipment_sets)) if icab_injectable else []
    )

    first = characterizations[0]

    return FaultCatalogEntry(
        disturbance=disturbance,
        name=name,
        simulator_supported=True,
        icab_injectable=icab_injectable,
        empirically_verified=empirically_verified,
        affected_measurements=repeatable_affected_measurements,
        affected_equipment=repeatable_affected_equipment,
        plant_tripped_in_any_seed=plant_tripped_in_any_seed,
        characterization_seeds=[c.seed for c in characterizations],
        warmup_hours=first.warmup_hours,
        duration_hours=first.duration_hours,
        magnitude=first.magnitude,
        deviation_threshold_stdevs=first.deviation_threshold_stdevs,
        tep_studio_version=tep_studio_version,
        characterized_at=characterized_at,
    )


def is_benchmark_ready(disturbance: str, *, catalog: FaultCatalog | None = None) -> bool:
    """
    Whether ``disturbance`` is empirically verified and therefore safe to
    use in a benchmark scenario's fault schedule. Loads the default
    catalog if one isn't supplied; returns False (not an error) for a
    disturbance the catalog has no entry for, e.g. one added to
    `tep_studio` after the catalog was last regenerated.
    """

    catalog = catalog or load_fault_catalog()

    try:
        entry = catalog.get(disturbance)
    except KeyError:
        return False

    return entry.empirically_verified
