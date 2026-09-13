# Automated TEP fault injection and empirical characterization (M13-B)

This documents ICAB's reproducible fault/disturbance injection system for
the real TEP simulator, built on top of the M13-A process-context model.
It answers three distinct questions, kept explicitly separate throughout:
**what the simulator supports**, **what ICAB can inject without
breaking**, and **what has actually been shown, empirically, to do
something** -- existing in the simulator's own registry is not the same
as having been run and observed to matter.

## The real simulator's fault mechanism (inspected, not assumed)

Verified directly against `tep_studio`:

```python
>>> from tep_studio import list_disturbances
>>> len(list_disturbances())
28
```

`TEPSimulator.inject_fault(disturbance, *, active=True, magnitude=1.0)`
sets one entry of the plant's disturbance vector (`idv_01`..`idv_28`,
each independently addressable) and logs a `fault_injected` ICAB
bookkeeping event (`source="icab"`, distinct from real plant events like
`shutdown`, `source="simulator"`). Per the kernel's own schema
(`tep_studio.simulation.schema.TEP_SCHEMA.disturbances`), every
disturbance is bounded `[0.0, 1.0]` -- `magnitude` scales the
disturbance's own built-in perturbation, it is not a free physical unit.
Disturbances are **persistent once activated** (the kernel does not
clear them on its own); M13-B adds ICAB-side scheduled deactivation (see
below). Determinism was verified directly, not assumed: repeated
`reset(seed=X)` + an identical step/inject sequence produce
**bit-identical** measurement trajectories in this environment (not
merely "close" -- see `test_run_and_sample_is_bit_identical_across_repeated_calls`).

`idv_01`-`idv_20` are the documented Downs & Vogel step-change/drift/
sticking faults; `idv_21`-`idv_28` are the Bathelt/Ricker/Jelali kernel's
additional documented random-variation disturbances (per
`icab.tep.simulator`'s own module docstring, unchanged).

## Three explicit tiers -- not conflated

| Tier | What it means | Result |
|---|---|---|
| `simulator_supported` | `tep_studio.list_disturbances()` lists it | **28 / 28** (trivial by construction) |
| `icab_injectable` | `TEPSimulator.inject_fault()` + actually stepping the plant forward completed without raising, in EVERY characterization seed | **28 / 28** |
| `empirically_verified` | REPEATABLY (same result in every tested seed) produced a real, above-noise-floor measurement deviation, or a plant trip | **7 / 28** |

No disturbance failed to inject or crashed the simulator -- all 28 are
mechanically usable. But **only 7 of 28 have been shown, empirically, to
produce a repeatable, measurement-visible effect** under the
characterization parameters below. The other 21 are not "broken"; most
are the kernel's small-magnitude *random-variation* disturbances
(`idv_08`-`idv_28`, aside from the few that verified), designed to
perturb the plant subtly rather than step it -- see Limitations for two
informative, specific non-verified cases.

## Empirical characterization methodology

`icab.tep.fault_characterization` -- a PAIRED, same-seed comparison, not
a bare "did a number change" check:

1. For one seed, run a no-fault baseline and (separately) a faulted run,
   each: reset -> warm up 1.0h -> (faulted run only: inject at
   magnitude 1.0) -> step+sample every 0.05h for 4.0h.
2. For every one of the 41 measurements, compute the baseline's own
   mean and sample stdev over that window, and the faulted run's mean
   over the LAST 20% of the window (a sustained shift, not one noisy
   sample).
3. A measurement counts as "affected" only if that sustained deviation
   is **>= 4 standard deviations** of the measurement's own baseline
   noise -- its own observed noise floor under otherwise identical
   conditions, not an arbitrary percent-of-value threshold.
4. Repeated at **two seeds (101, 202)**; a disturbance's catalog entry
   uses the **intersection** of affected measurements/equipment across
   both seeds (repeatable in every tested seed, not merely one lucky
   run) -- see `build_fault_catalog_entry`.

Same-seed baseline reuse is valid because of the verified determinism
above: one baseline per seed is computed once and reused across all 28
disturbances at that seed (29 simulations per seed, not 56).

Persisted at `configs/benchmark/fault_catalog.json`
(`scripts/characterize_tep_disturbances.py` regenerates it) -- the
**observed process response**, stored separately from the disturbance's
bare identity (`icab.tep.faults.FaultCatalogEntry` vs.
`icab.tep.fault_characterization.DisturbanceCharacterization`, itself
distinct from the scenario-level `icab.scenarios.models.FaultSchedule`):

```
simulator fault (tep_studio.list_disturbances)
    |  icab.tep.fault_characterization.characterize_disturbance
    v
observed process response (DisturbanceCharacterization, per seed)
    |  icab.tep.faults.build_fault_catalog_entry (intersect across seeds)
    v
fault catalog entry (FaultCatalogEntry -- "empirically verified?")
    |  referenced by (not duplicated into) a scenario's
    |  icab.scenarios.models.FaultSchedule + GroundTruth
    v
benchmark ground truth (hidden from the agent -- see below)
```

## The 7 empirically verified disturbances, and why each belongs in the initial suite

Selected from real characterization data (seeds 101/202, 1h warmup, 4h
duration, magnitude 1.0), not arbitrarily:

| Disturbance | Name | Behavioral pattern demonstrated | Evidence |
|---|---|---|---|
| `idv_17` | Random reactor heat transfer deviation | **Obvious single-variable response** | Only `reactor_cooling_water_outlet_temperature_meas` affected, on the reactor -- name and effect align directly. |
| `idv_24` | Random D feed pressure/flow | **Affected equipment not obvious from the fault name** | Named after the D-feed/feed-system, but its only repeatable effect lands on the REACTOR's cooling water temperature -- nothing in the feed system itself clears the threshold. |
| `idv_02` | B composition of stream 4, A/C ratio constant | **Multi-variable response** (moderate) | 8 measurements across 3 equipment (compressor, purge system, reactor). |
| `idv_20` | Unknown random disturbance | **Cross-unit response**, even though undocumented | 2 measurements spanning reactor + separator, despite the kernel's own description offering no clue what it represents -- empirical characterization works without a clean textual spec. |
| `idv_08` | Random A/B/C composition of stream 4 | **Requires historical reasoning / delayed response** | A stochastic (not step) disturbance -- e.g. `PURGE_FLOW`'s deviation grows ~150x from early-window to late-window; a single current-value snapshot would likely miss it, a historical trend would not. |
| `idv_01` | A/C ratio of stream 4, B composition constant | **Cross-unit / requires relational-context discovery**; also a strong delayed-response example | The widest footprint of all 28: 26 measurements, all 7 equipment. Already D3's own fault choice (confirmed empirically here, not merely trusted). `PURGE_F_CONCENTRATION` shows a ~570x early-to-late deviation growth. |
| `idv_06` | A feed loss | **Affected equipment not obvious from LOCAL (reactor) measurements** -- the flagship case | Already D4's own fault choice. Empirically confirmed quantitatively: reactor's own measurements show the SMALLEST deviations of everything affected (`reactor_pressure` 4.6σ, `reactor_level` 4.2σ) while downstream equipment shows dramatically larger ones (`compressor_work` 63σ, `stripper_temperature` 26σ) -- exactly the D4 scenario's own narrative, now backed by numbers rather than only asserted. |

Two of the seven (`idv_01`, `idv_06`) are the disturbances D3/D4 already
use -- this characterization independently confirms, rather than merely
assumes, that those pre-existing scenario choices were empirically
sound. The other five are new candidates that were NOT turned into new
scenarios in this milestone (that is explicitly M13-C/D territory, out
of scope here) -- they are documented, empirically-grounded options for
whoever builds the next scenario.

### Example observed response (real output, `idv_06`, seed 101)

```
FEED_A_FLOW:   62.2 sigma deviation (collapses toward ~0 -- feed cut off)
REACTOR_PRESSURE:   4.6 sigma  (barely moves -- see above)
STRIPPER_TEMPERATURE: 25.8 sigma
COMPRESSOR_WORK:      63.2 sigma
plant_tripped: False
```

## Fault specification: scenario-level vs. catalog-level

Per "avoid duplicating simulator definitions unnecessarily," the
specification is split across the two layers that already existed for
other things, extended rather than replaced:

- **`icab.scenarios.models.FaultSchedule`** (a scenario's own choice of
  *when*/*how long*/*how strong*): `disturbance` (the simulator's own
  id -- never a second, ICAB-invented id), `activate_at_hours`,
  **`duration_hours`** (NEW in M13-B: `None` = persistent for the rest
  of the scenario, pre-M13-B behavior, unchanged; a number = the fault
  is cleared -- `inject_fault(active=False)` -- at
  `activate_at_hours + duration_hours`), `magnitude`, `description`.
- **`icab.tep.faults.FaultCatalogEntry`** (the disturbance's own,
  scenario-independent identity/provenance): `name` (from
  `tep_studio`'s own description), `simulator_supported`/
  `icab_injectable`/`empirically_verified`, `affected_measurements`/
  `affected_equipment`, `tep_studio_version`, `characterized_at`.

Nothing is duplicated: a scenario's `FaultSchedule.disturbance` is the
join key into the catalog (`icab.tep.faults.is_benchmark_ready`), not a
second copy of the disturbance's name/description.

### Scheduled deactivation (`duration_hours`)

`ScenarioRunner.prepare()` now tracks pending deactivations the same way
it already tracked pending activations -- sorted by time, checked once
per simulation-time-step iteration -- and calls
`simulator.inject_fault(disturbance, active=False)` when a fault's
`duration_hours` elapses. Existing D3/D4 scenarios (`duration_hours`
unset on their `FaultSchedule`) are completely unaffected: `None` was
already, and remains, "never cleared."

## Hidden ground-truth separation

Structural, not merely disciplined: `grep -rl ground_truth src/` finds
exactly two files -- `icab.scenarios.models` (the definition) and
`icab.evaluation.grounded` (which reads it only AFTER an agent has
already submitted its conclusion, purely for scoring). Neither
`icab.agent.llm.agent.LLMInvestigationAgent` nor
`icab.experiments.ExperimentRunner` ever reads `ground_truth` or
`.faults` -- `ExperimentRunner` passes the agent only `scenario.objective`
and a bare `{scenario_id, difficulty}` dict.

M13-B adds one ENFORCED technical safeguard on top of that structural
fact: `BenchmarkScenario` now has a model validator
(`_objective_must_not_leak_the_fault_schedule`) that rejects, AT
CONSTRUCTION TIME, a scenario whose free-text `objective` mentions its
own `FaultSchedule.disturbance` id -- e.g. authoring a D-level scenario
whose objective says "investigate the idv_06 disturbance" is now a
`ValidationError`, not merely bad practice a reviewer might miss. This
existed nowhere before M13-B; every current D1-D4 scenario already
passes it (verified by the full test suite still loading them).

Verified end to end, against the REAL stack (`tests/integration/test_tep_fault_injection.py`):
inject a real, verified disturbance through the full
`ScenarioRunner` -> real Historian + real Neo4j + real MQTT path, then
confirm the fault id string appears in NONE of: the synced `CIMEnvironment`
entities/relationships/observations, the real KG's own relationship read
path, the real historian's current-value row, or the real MQTT message --
while separately confirming (via `simulator.get_events()`, itself never
agent-visible) that the fault genuinely was injected and genuinely
changed the synced measurement value.

## Generation/provenance

Unaffected, by construction: fault injection only changes *what the
simulator's process state is* at sync time -- `ScenarioRunner.prepare()`
still calls `self.context_sync.sync(simulator, generation_id=generation_id)`
exactly as before M13-B, so every observation a fault-bearing scenario
run produces still carries the correct `generation_id` (verified
directly in the integration test above). Faults themselves are never KG
entities or relationships, so the M9 generation_id read-path regression
test and legacy-baseline validity mechanism are untouched.

## Determinism and reproducibility

A benchmark run's `(scenario_id, seed, fault schedule, injection time,
warmup, duration)` reproduces **bit-identical** measurement trajectories
in this environment -- empirically verified directly (not merely
claimed), both at the raw `TEPSimulator` level and through the
characterization mechanism itself (same seed -> same
`DisturbanceCharacterization`). This is a stronger claim than "subject
to numerical behavior" precisely because it was checked, not assumed --
if a future `tep-studio` version introduces any source of
non-determinism (parallelism, uninitialized memory, etc.), this
guarantee would need re-verifying, not re-assuming.

## Validated with

- `tests/unit/tep/test_fault_characterization.py` -- the characterization
  mechanism against the real simulator (short windows, fast): detects a
  known strong effect, is deterministic, correctly reports "not
  injectable" for a bad name, reuses a supplied baseline correctly, and
  confirms a real "no measurement effect, but still injectable" case
  (`idv_04` -- see Limitations).
- `tests/unit/tep/test_faults.py` -- catalog model, persistence
  round-trip, and the cross-seed aggregation/repeatability logic
  (intersection of affected sets; injectable/verified require every
  seed to agree; a repeatable trip is independently sufficient).
- `tests/unit/scenarios/test_runner.py` -- `duration_hours` scheduled
  deactivation (and pre-M13-B "never cleared" behavior preserved).
- `tests/unit/scenarios/test_hidden_ground_truth.py` -- the objective-leak
  validator, and that neither `ExperimentRunner`'s `initial_state` nor
  a real `LLMInvestigationAgent` run's actual LLM messages ever contain
  the fault id or ground truth.
- `tests/unit/scenarios/test_fault_catalog_integration.py` -- D3/D4's
  existing fault choices cross-checked against the real, checked-in
  catalog.
- `tests/integration/test_tep_fault_injection.py` -- against the REAL
  simulator, REAL Neo4j, REAL Historian, and REAL MQTT broker (not an
  in-memory KG): real process-behavior change, fault metadata recorded
  separately, and no leakage into any agent-visible surface.

## Remaining limitations

- **Only 2 characterization seeds (101, 202).** Sufficient to establish
  "repeatable across at least a couple of seeds," not a large-sample
  statistical claim. `scripts/characterize_tep_disturbances.py --seeds`
  accepts more.
- **The tail-mean-vs-baseline-stdev statistic is not equally sensitive
  to every response shape.** `idv_01`'s effect on `reactor_pressure`
  (a real, gradual decline -- D3's own scenario premise) clears the
  threshold at seed 101 (6.5σ) but not at seed 202, so it is correctly
  excluded from the cross-seed-repeatable catalog entry even though the
  underlying physical effect is real (D3's own historical-trend-based
  investigation is a better-suited detection method than this
  characterization's single tail-window average -- a slope/trend
  statistic would likely be more robust for gradually-declining
  measurements and is a natural follow-up, not implemented here).
- **`idv_04`/`idv_05` (reactor/separator cooling water INLET
  temperature) show no measurement-level effect at all**, at either
  seed -- a genuine, informative finding, not a gap: the reactor/
  separator temperature control loops (see
  `docs/architecture/tep-context-model.md`'s `CONTROLS` relationships)
  specifically manipulate the cooling water VALVE to hold the
  temperature MEASUREMENT at setpoint, and valve positions are not
  observed anywhere in ICAB yet (M13-A limitation, unchanged) -- so a
  well-compensated disturbance is, correctly, invisible to a
  measurement-only characterization.
- **Manipulated-variable (actuator) values remain unobserved** (M13-A's
  limitation, unchanged by M13-B) -- characterization can only see what
  the 41 measurements show, not the controller's compensating actions.
- **Magnitude scaling beyond 1.0 is untested.** Every characterization
  run used `magnitude=1.0` (full nominal activation); the API accepts
  other values (clamped by the kernel's own `[0.0, 1.0]` schema bounds
  in practice), but no empirical claim is made here about intermediate
  magnitudes' effects.
- **No new BenchmarkScenario YAML files were authored** for the five
  newly-identified candidate faults -- selecting/documenting the
  empirically-grounded fault suite was this milestone's job; turning
  them into full scenarios (objectives, ground truth, difficulty
  placement) is explicitly M13-C/D territory.
