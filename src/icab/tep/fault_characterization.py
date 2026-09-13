"""
M13-B: empirical characterization of the real TEP simulator's 28
disturbances.

Distinct from `icab.tep.faults` (the ICAB-level fault catalog/
specification that this module's results POPULATE): this module is what
actually PRODUCES the empirical evidence -- for a given disturbance, does
injecting it actually, measurably change the plant's behavior (not
merely "the simulator accepted the call without raising"), which
measurements move, and does the plant trip. Never invents an effect from
the disturbance's name/documentation -- every claim here comes from
actually running the simulator.

Methodology: a PAIRED, same-seed comparison, not a bare "did the value
change" check. For one seed, a no-fault baseline and a faulted run are
both stepped through the same warmup+duration, sampling every
measurement at regular checkpoints during the post-fault window in both.
A measurement counts as "affected" only if the faulted run's LAST
`_TAIL_FRACTION` of the window (a sustained shift, not a single noisy
sample) deviates from the baseline's own mean, in the baseline's own
observed sample-stdev units over the identical window -- i.e. the
deviation must clear that measurement's own noise floor under otherwise
identical conditions (same seed, same duration), not an arbitrary
percentage-of-value threshold.

Same-seed determinism was verified directly (see
tests/unit/tep/test_fault_characterization.py): repeated
reset(seed=X) + identical step/inject sequences produce bit-identical
measurement trajectories in this environment, so a single baseline run
per seed is valid to reuse across every disturbance tested at that seed
(no need to re-run a fresh baseline per disturbance).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean, stdev

from pydantic import BaseModel, ConfigDict

from .measurements import build_real_tep_variables, derive_real_equipment_id
from .simulator import TEPSimulator

DEFAULT_WARMUP_HOURS = 1.0
DEFAULT_DURATION_HOURS = 4.0
DEFAULT_SAMPLE_INTERVAL_HOURS = 0.05
DEFAULT_DEVIATION_THRESHOLD_STDEVS = 4.0

#: Fraction (from the end) of the post-fault sampling window averaged
#: when checking for a SUSTAINED deviation, rather than reacting to one
#: transient/noisy sample.
_TAIL_FRACTION = 0.2
#: Guards against a division by zero for a baseline series with (near)
#: zero observed variance -- not a claim that such a floor is itself
#: meaningful noise.
_MIN_STDEV_FLOOR = 1e-9


@dataclass(frozen=True)
class Trajectory:
    """One run's sampled measurement history over its post-warmup/post-fault window."""

    samples: dict[str, list[float]] = field(default_factory=dict)


def _run_and_sample(
    *,
    seed: int,
    warmup_hours: float,
    duration_hours: float,
    sample_interval_hours: float,
    disturbance: str | None,
    magnitude: float,
) -> tuple[Trajectory, bool]:
    """
    Reset + warm up, optionally inject one disturbance right after
    warmup, then step+sample for `duration_hours`. Returns
    ``(trajectory, plant_tripped)``. Uses ONLY `TEPSimulator`'s public
    API (`reset`/`step`/`inject_fault`/`get_measurements`/`terminated`) --
    no reach into simulator internals.
    """

    simulator = TEPSimulator()
    simulator.reset(seed=seed)
    simulator.step(duration=warmup_hours)

    if disturbance is not None:
        simulator.inject_fault(disturbance, magnitude=magnitude)

    samples: dict[str, list[float]] = {name: [] for name in simulator.get_measurements()}
    elapsed = 0.0
    tripped = False

    while elapsed < duration_hours - 1e-9:
        step = min(sample_interval_hours, duration_hours - elapsed)
        simulator.step(duration=step)
        elapsed += step

        if simulator.terminated:
            tripped = True
            break  # nothing meaningful to sample once the plant has shut down

        for name, value in simulator.get_measurements().items():
            samples[name].append(value)

    return Trajectory(samples=samples), tripped


class DisturbanceCharacterization(BaseModel):
    """
    One (disturbance, seed) pair's empirical characterization -- the
    OBSERVED PROCESS RESPONSE, kept separate from the disturbance's own
    static identity/specification (`icab.tep.faults.FaultCatalogEntry`,
    which several of these are aggregated into).
    """

    model_config = ConfigDict(extra="forbid")

    disturbance: str
    seed: int
    magnitude: float
    warmup_hours: float
    duration_hours: float
    deviation_threshold_stdevs: float

    #: `TEPSimulator.inject_fault()` + the subsequent step/sample loop
    #: completed without raising. False only on an actual exception --
    #: NOT on the plant tripping (a trip is an expected, informative
    #: outcome of some disturbances, not a failure of the injection).
    icab_injectable: bool
    plant_tripped: bool
    #: Canonical measurement ids whose sustained (tail-window) deviation
    #: cleared `deviation_threshold_stdevs`.
    affected_measurements: list[str] = []
    #: Canonical equipment ids derived from `affected_measurements` via
    #: the existing M13-A equipment-assignment heuristic.
    affected_equipment: list[str] = []
    #: variable_id -> observed deviation, in baseline-stdev units, for
    #: every measurement in `affected_measurements` (not all 41).
    max_deviation_stdevs: dict[str, float] = {}
    error: str | None = None


def characterize_disturbance(
    disturbance: str,
    *,
    seed: int,
    warmup_hours: float = DEFAULT_WARMUP_HOURS,
    duration_hours: float = DEFAULT_DURATION_HOURS,
    sample_interval_hours: float = DEFAULT_SAMPLE_INTERVAL_HOURS,
    magnitude: float = 1.0,
    deviation_threshold_stdevs: float = DEFAULT_DEVIATION_THRESHOLD_STDEVS,
    baseline: Trajectory | None = None,
) -> DisturbanceCharacterization:
    """
    Empirically characterize one disturbance at one seed, against a
    same-seed, no-fault baseline.

    ``baseline``, when given, must be a `Trajectory` produced by
    ``_run_and_sample(seed=seed, disturbance=None, ...)`` with the SAME
    seed/warmup/duration/sample_interval as this call -- reused across
    every disturbance tested at that seed rather than re-run each time
    (see `characterize_all_disturbances`). When omitted, this function
    computes it itself.
    """

    if baseline is None:
        baseline, _ = _run_and_sample(
            seed=seed,
            warmup_hours=warmup_hours,
            duration_hours=duration_hours,
            sample_interval_hours=sample_interval_hours,
            disturbance=None,
            magnitude=0.0,
        )

    try:
        faulted, tripped = _run_and_sample(
            seed=seed,
            warmup_hours=warmup_hours,
            duration_hours=duration_hours,
            sample_interval_hours=sample_interval_hours,
            disturbance=disturbance,
            magnitude=magnitude,
        )
    except Exception as error:  # noqa: BLE001 -- any simulator failure means "not injectable"
        return DisturbanceCharacterization(
            disturbance=disturbance,
            seed=seed,
            magnitude=magnitude,
            warmup_hours=warmup_hours,
            duration_hours=duration_hours,
            deviation_threshold_stdevs=deviation_threshold_stdevs,
            icab_injectable=False,
            plant_tripped=False,
            error=f"{type(error).__name__}: {error}",
        )

    affected: dict[str, float] = {}

    for name, faulted_series in faulted.samples.items():
        baseline_series = baseline.samples.get(name, [])
        if len(baseline_series) < 2 or not faulted_series:
            continue

        baseline_mean = mean(baseline_series)
        baseline_stdev = stdev(baseline_series) or _MIN_STDEV_FLOOR

        tail_length = max(1, int(len(faulted_series) * _TAIL_FRACTION))
        tail_mean = mean(faulted_series[-tail_length:])

        deviation = abs(tail_mean - baseline_mean) / baseline_stdev

        if deviation >= deviation_threshold_stdevs:
            affected[name] = deviation

    canonical_ids = {
        variable.variable_id: variable.canonical_id for variable in build_real_tep_variables()
    }
    affected_measurement_ids = sorted(canonical_ids[name] for name in affected)
    affected_equipment_ids = sorted({derive_real_equipment_id(name.lower()) for name in affected})

    return DisturbanceCharacterization(
        disturbance=disturbance,
        seed=seed,
        magnitude=magnitude,
        warmup_hours=warmup_hours,
        duration_hours=duration_hours,
        deviation_threshold_stdevs=deviation_threshold_stdevs,
        icab_injectable=True,
        plant_tripped=tripped,
        affected_measurements=affected_measurement_ids,
        affected_equipment=affected_equipment_ids,
        max_deviation_stdevs={
            canonical_ids[name]: round(value, 2) for name, value in affected.items()
        },
    )


def characterize_all_disturbances(
    *,
    seeds: tuple[int, ...],
    warmup_hours: float = DEFAULT_WARMUP_HOURS,
    duration_hours: float = DEFAULT_DURATION_HOURS,
    sample_interval_hours: float = DEFAULT_SAMPLE_INTERVAL_HOURS,
    magnitude: float = 1.0,
    deviation_threshold_stdevs: float = DEFAULT_DEVIATION_THRESHOLD_STDEVS,
) -> dict[str, list[DisturbanceCharacterization]]:
    """
    Characterize every disturbance `tep_studio.list_disturbances()`
    publishes, at every seed in ``seeds`` -- one no-fault baseline
    computed per seed (not per disturbance) and reused across all 28.

    Returns ``{disturbance_id: [characterization_per_seed, ...]}`` --
    the per-seed results, for `icab.tep.faults` to aggregate into a
    single `FaultCatalogEntry` per disturbance (repeatability across
    seeds is a property of that aggregation, not of any one run).
    """

    from tep_studio import list_disturbances

    disturbance_ids = [name for name, _ in list_disturbances()]

    results: dict[str, list[DisturbanceCharacterization]] = {
        disturbance_id: [] for disturbance_id in disturbance_ids
    }

    for seed in seeds:
        baseline, _ = _run_and_sample(
            seed=seed,
            warmup_hours=warmup_hours,
            duration_hours=duration_hours,
            sample_interval_hours=sample_interval_hours,
            disturbance=None,
            magnitude=0.0,
        )

        for disturbance_id in disturbance_ids:
            characterization = characterize_disturbance(
                disturbance_id,
                seed=seed,
                warmup_hours=warmup_hours,
                duration_hours=duration_hours,
                sample_interval_hours=sample_interval_hours,
                magnitude=magnitude,
                deviation_threshold_stdevs=deviation_threshold_stdevs,
                baseline=baseline,
            )
            results[disturbance_id].append(characterization)

    return results
