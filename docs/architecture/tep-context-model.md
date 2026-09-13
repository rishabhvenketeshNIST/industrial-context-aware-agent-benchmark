# The complete TEP process-context model (M13-A)

Before M13-A, the knowledge graph represented the 41 published TEP
measurements and a flat 7-item equipment hierarchy (`PART_OF` +
`MONITORS` only) -- correct, but far from a complete representation of
the real TEP process/control structure. This documents what M13-A added:
the full set of process variables ICAB actually has access to, how they
are identified, which relationships are now represented and why each one
is defensible, and what is deliberately still absent.

## How many TEP process variables ICAB represents, and how that number was obtained

Verified directly against the `tep-studio` dependency (never assumed):

```python
>>> from tep_studio import list_measurements, list_manipulated_variables, list_disturbances
>>> len(list_measurements()), len(list_manipulated_variables()), len(list_disturbances())
(41, 12, 28)
```

- **41 measurements** (`XMEAS`-equivalent) -- process OUTPUTS the plant
  reports. Already fully represented pre-M13-A
  (`icab.tep.measurements.build_real_tep_variables`); M13-A adds a
  `category` to each (below).
- **12 manipulated variables** (`XMV`-equivalent) -- process INPUTS the
  control system writes (valve positions, agitator speed). **Not
  represented at all before M13-A.** Now modeled as `Actuator` entities
  (`icab.tep.measurements.build_real_tep_manipulated_variables`).
- **28 disturbances** (`IDV` 1-28) -- fault-injection switches
  (`icab.tep.simulator.TEPSimulator.inject_fault`). Out of scope for
  M13-A (see Limitations) -- these are scenario/fault-injection concerns,
  not process-context entities, and M13-A is explicitly not a
  fault-injection milestone.

**53 total process variables now have a canonical ICAB identity**
(41 + 12).

## Single authoritative identity source

Per the explicit M13-A requirement not to duplicate variable definitions
across architectures: **every** consumer -- `TEPAdapter` (KG),
`icab.context.uns.tep_builder` (UNS), `icab.context.mqtt.publisher`
(MQTT), `icab.context.opcua.tep_server` (OPC UA, and the private i3X
instance riding on top of it) -- calls
`icab.tep.measurements.build_real_tep_variables()` /
`build_real_tep_manipulated_variables()` directly. There is no second,
independently maintained list anywhere; a unit test
(`test_measurement_canonical_ids_agree_across_kg_uns_and_mqtt`,
`test_actuator_canonical_ids_agree_between_kg_entities_and_uns_nodes` in
`tests/unit/tep/test_real_adapter.py`) asserts the id sets returned by
each consumer are identical, not merely "probably the same."

Canonical id scheme (unchanged, just now covering actuators too):

| Kind | Canonical id pattern | Example |
|---|---|---|
| Measurement | `urn:icab:measurement:<name>` | `urn:icab:measurement:reactor_pressure` |
| Actuator | `urn:icab:actuator:<name>` | `urn:icab:actuator:reactor_cooling_water_valve` |
| Equipment | `urn:icab:equipment:<key>` | `urn:icab:equipment:reactor` |
| Alarm | `urn:icab:alarm:<override-name>` | `urn:icab:alarm:high-pressure-to-production` |

## Required metadata, per variable

Every measurement (`TEPVariable`) and manipulated variable
(`ManipulatedVariable`, both in `icab.tep.measurements`) carries:
canonical id, stable `variable_id`, human-readable `name`, `unit`,
`equipment_id` (process/equipment location), `category` (physical
quantity type), and, once turned into a CIM `Entity` by `TEPAdapter`,
`source="tep"` + `source_id=<variable_id>` (provenance) and an
`entity_type` of `Measurement` or `Actuator`.

**`category`** (new in M13-A) is derived from the measurement's own
published UNIT (`icab.tep.measurements._category_for_unit`), not a
per-variable judgment call -- a unit not in the lookup table raises
rather than silently guessing:

| Unit | Category | Count |
|---|---|---|
| `kscmh`, `kg/h`, `m3/h` | flow | 10 |
| `kPa gauge` | pressure | 3 |
| `%` | level | 3 |
| `degC` | temperature | 5 |
| `kW` | work | 1 |
| `mol %` | composition | 19 |

Manipulated variables get a `category` of `"valve"` (11) or `"speed"`
(1, the reactor agitator), from their own name.

## Equipment/process hierarchy

Unchanged from pre-M13-A: `Site` (`urn:icab:site:tep`) -> `Area` -> one
flat `ProcessCell` -> 7 `Equipment` entities (reactor, condenser,
separator, stripper, compressor, purge system, feed system), all
`PART_OF` their parent. Equipment assignment for measurements uses a
documented prefix heuristic on the simulator's own naming convention
(`_EQUIPMENT_PREFIXES`); M13-A adds the equivalent for actuators
(`_ACTUATOR_EQUIPMENT_KEYWORDS`, a keyword-containment check since MV
names put the identifying word mid-string, e.g. `separator_cooling_water_valve`).

## Relationship types represented, and their provenance

Per the M13-A direction to separate **structural** / **process-control**
/ **causal-diagnostic** relationships and give every nontrivial one a
defensible source -- six of the fifteen suggested relationship types are
populated; the rest are deliberately absent (see Limitations). **None are
causal or diagnostic** -- nothing here is inferred from observing the
simulator run; every non-hierarchy edge is read from a citable, static
source that exists independently of any particular simulation.

| Predicate | Subject -> Object | Count | Kind | Source |
|---|---|---|---|---|
| `PART_OF` | Area/ProcessCell/Equipment -> parent | 9 | structural | ISA-95 hierarchy convention (unchanged, pre-M13-A) |
| `MONITORS` | Equipment -> Measurement | 41 | structural | Simulator's own measurement-naming convention (unchanged, pre-M13-A) |
| `ACTUATES` | Equipment -> Actuator | 12 | structural | Simulator's own MV-naming convention (M13-A, same heuristic style as MONITORS) |
| `CONTROLS` | Actuator -> Measurement | 9 | **process/control** | `tep_studio.control.registry.RICKER_MODE1` -- Ricker (1996), the SAME decentralized controller `TEPSimulator` runs closed-loop by default (M13-A) |
| `HAS_LIMIT` | Measurement -> Alarm | 2 | **process/control** | `RICKER_MODE1.overrides` -- Ricker (1996) sec. 4 documented constraint overrides (M13-A) |
| `ASSOCIATED_WITH` | Alarm -> Actuator | 1 | **process/control** | Same override registry, only where the override's target is itself a real actuator (M13-A) |

**74 relationships total** in one real-path `TEPAdapter.build_real_environment()`
call, up from 50 pre-M13-A (9 hierarchy `PART_OF` + 41 `MONITORS`). The
separate, untouched static 4-variable prototype path
(`TEPAdapter.build_environment()`) still produces its own unrelated 8
(4 hierarchy + 4 `MONITORS`) -- not affected by any M13-A change.

### Why `CONTROLS` only covers 9 of the real controller's ~10 loops

`RICKER_MODE1` (the exact registry `TEPSimulator`'s
`RickerMultiLoopController` executes) defines more control loops than
that. `icab.tep.measurements.real_control_loop_pairs()` derives the 9
DIRECT pv->mv pairs *programmatically* (checking each loop's target
against the real 12 manipulated-variable names), not by hand-picking
which loops "count" -- production, reactor_level, separator_level,
stripper_level, reactor_pressure, `%G` composition, and the two velocity
reactant loops (`ya`/`yac`) all drive an INTERNAL signal instead
(`production_index`, a cascaded setpoint, an internal ratio, a
composition trim) that is not itself a first-class ICAB entity. Rather
than invent a relationship to something that doesn't exist as an entity,
those loops are left unrepresented. This is exactly the "leave absent
rather than invent" instruction in practice, not an oversight --
`test_control_loop_pairs_exclude_loops_that_drive_an_internal_signal`
pins this down as intended behavior.

### The two `HAS_LIMIT` overrides

`RICKER_MODE1.overrides` documents two Mode-1 constraint overrides, each
with its own `confirmed_source` citation:

- `high_pressure_to_production`: reactor pressure crossing 2900 kPa cuts
  the production index. The target (`production_index`) is an internal
  signal, not a real actuator -- gets a `HAS_LIMIT` edge (reactor_pressure
  -> the alarm) but no further `ASSOCIATED_WITH` edge to a nonexistent
  entity.
- `high_level_to_recycle`: reactor level crossing 90% adjusts the
  compressor recycle valve -- a REAL actuator, so this one gets both the
  `HAS_LIMIT` edge and an `ASSOCIATED_WITH` edge to
  `urn:icab:actuator:compressor_recycle_valve`.

Both are modeled as `Alarm` entities (not `Fault`): they are protective
CONTROL actions the plant takes on its own measurements, not a diagnosed
process fault.

## Provenance and `generation_id`

Every M13-A relationship-building method (`get_real_actuator_relationships`,
`get_real_control_relationships`, `get_real_limit_relationships`) accepts
the same `generation_id` parameter the pre-existing `MONITORS`/`PART_OF`
methods do, and `TEPAdapter.build_real_environment()` threads it through
unchanged -- so the M9 provenance mechanism (distinguishing one scenario
run's own relationships from a shared, persistent Neo4j's historical
accumulation) applies to every new relationship kind automatically, not
just the ones that existed before M13-A. Every `Relationship` also
carries `source`/`source_id` distinguishing exactly which of the three
provenance kinds (structural / process-control / -- causal is never used
here) it came from; see the table above.

The existing Neo4j read/write path (`icab.context.knowledge_graph.repository
.Neo4jKnowledgeGraphRepository`) needed **no changes** for any of this --
it already stores every entity under one generic `:Entity` label
(`entity_type` as a property) and every relationship under one generic
`:RELATIONSHIP` type (`predicate` as a property), so `Actuator`/`Alarm`
entities and `CONTROLS`/`ACTUATES`/`HAS_LIMIT`/`ASSOCIATED_WITH`
relationships work through the exact same read/write Cypher as
`Equipment`/`Measurement`/`MONITORS` always have. The M9 generation_id
read-path regression test
(`test_neo4j_relationship_generation_id_round_trips`) and the legacy
deterministic-baseline validity mechanism are both untouched.

## Cross-architecture consistency

The same 41 measurement canonical ids are recognizable in KG, UNS, MQTT,
OPC UA, and (through OPC UA) the private i3X instance -- unchanged from
pre-M13-A, just now additionally verified by a dedicated identity test.
The 12 actuator canonical ids are recognizable in KG and UNS (added in
M13-A) but **not yet** in MQTT/OPC UA/i3X/Historian -- see Limitations.
Per the M13-A direction, this is not a requirement that every
architecture expose identical content; it is a requirement that the
*same identity*, where an architecture does expose something, is
recognizable as referring to the same real process variable.

## What is deliberately NOT represented (left absent rather than invented)

- **`CONNECTED_TO` (equipment-to-equipment process-flow topology)**:
  the repository does not bundle a machine-readable P&ID/stream-routing
  table, and reconstructing the Downs & Vogel (1993) flow diagram from
  memory risked asserting a specific stream routing that could not be
  checked against an in-repo source. Left absent per the "leave absent
  rather than invent" instruction, not fabricated from general knowledge
  of the process.
- **Manipulated-variable CURRENT VALUES / time series**: `TEPSimulator`
  exposes `get_measurements()` (the 41 outputs) but no public getter for
  MV positions. Actuators are represented structurally (identity +
  `ACTUATES`/`CONTROLS`) with no `Observation` history on the
  historian/MQTT/OPC UA/i3X side -- extending the simulator wrapper's own
  API was out of scope for this milestone ("do not redesign the existing
  architecture").
  - Corollary: actuators are the one place cross-architecture
    consistency (above) is intentionally partial -- KG/UNS only.
- **Cascaded/ratio/composition-trim control loops** (production,
  reactor_level, separator_level, stripper_level, reactor_pressure,
  `%G`, `ya`, `yac`): real per `RICKER_MODE1`, but their targets
  (`production_index`, an internal setpoint, `r5`/`r6`/`r7` ratios,
  `Eadj`, `r1_trim`/`r4_trim`) are not first-class ICAB entities. Adding
  them would require inventing new entity types beyond this milestone's
  scope; left unrepresented rather than asserting a relationship to
  something that doesn't exist as a node.
- **`HAS_STATE`, `GENERATES`, `CAUSED_BY`, `DESCRIBED_BY`, `LOCATED_IN`,
  `DEPENDS_ON`, `AFFECTS`, `MEASURES`**: no relationship of these kinds
  currently has a source distinct from what `PART_OF`/`MONITORS`/
  `ACTUATES`/`CONTROLS`/`HAS_LIMIT`/`ASSOCIATED_WITH` already cover.
  `MEASURES` specifically is not introduced as a second predicate
  competing with the already-established `MONITORS` for the same
  equipment->measurement edge (existing D1-D4 scenario ground truth and
  the grounded evaluator's relationship scoring both key on `MONITORS`;
  introducing a duplicate predicate for the same fact would be
  redundant, not additive). `DESCRIBED_BY` would need a `Document`
  entity/citation corpus ICAB does not model; the existing
  `Relationship.source`/`source_id` string fields already serve the
  provenance role a `DESCRIBED_BY` edge to a literature citation would.
  None of these is a causal/diagnostic claim waiting to be added --
  they simply have no defensible source yet.

## Validated with

- `tests/unit/tep/test_measurements_registry.py` -- registry identity/
  metadata/category derivation, control-loop-pair/override extraction.
- `tests/unit/tep/test_real_adapter.py` -- CIM entity/relationship
  construction, generation_id threading, cross-architecture identity
  (KG/UNS/MQTT).
- `tests/unit/context/test_environment_loader.py` -- full model syncs
  into an in-memory KG (fast regression).
- `tests/unit/context/test_uns_tep_builder.py` -- actuators appear in the
  UNS tree and are browsable.
- `tests/integration/test_tep_context_model_completeness.py` -- the
  above, but against the REAL TEP simulator, REAL Neo4j, and REAL MQTT
  broker (not an in-memory KG).

## Where the 28 disturbances (IDV 1-28) fit

Out of scope for this document -- the 28 disturbances are process
*perturbations*, not the static context model this document describes.
See [`docs/architecture/tep-fault-injection.md`](tep-fault-injection.md)
(M13-B) for their empirical characterization, injection mechanism, and
the fault catalog.
