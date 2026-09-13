# Connecting the Simulator to the Industrial Context Layer (M4)

This documents how `icab.tep.simulator.TEPSimulator`'s real, dynamic state
reaches each ICAB context architecture, and why each architecture's view of
that state is deliberately *not* identical -- preserving real architectural
differences is a locked research principle, not an oversight.

```
TEP simulator (icab.tep.simulator.TEPSimulator)
 |
 +--> MQTT           icab.context.mqtt.TEPMeasurementPublisher
 +--> Historian       icab.tep.context_sync.TEPContextSync -> EnvironmentLoader
 +--> Knowledge Graph icab.tep.context_sync.TEPContextSync -> EnvironmentLoader
 +--> UNS             icab.context.uns.tep_builder.build_real_uns_nodes (static tree)
 +--> OPC UA          icab.context.opcua.TEPOPCUAServer
 +--> i3X             not wired -- see "i3X" below
```

## The shared source of truth: `TEPAdapter.build_real_environment`

Historian and Knowledge Graph both derive from exactly one call:
`TEPAdapter.build_real_environment(state)`, which turns a `TEPProcessState`
snapshot into a `CIMEnvironment` (entities + relationships + observations)
using the real-measurement registry introduced in M2
(`icab.tep.measurements.build_real_tep_variables` /
`REAL_TEP_EQUIPMENT`). `icab.tep.context_sync.TEPContextSync` loads that one
environment into both the historian and the knowledge graph via the
existing `EnvironmentLoader` (unchanged from before M4), and optionally
publishes it to MQTT via the existing M3 `TEPMeasurementPublisher` -- so
canonical IDs, units, timestamps, and `source="tep"` provenance are
identical across Historian/KG/MQTT for the same observation. This is
verified directly in
`tests/integration/test_tep_context_sync.py::test_tep_context_sync_reaches_historian_kg_and_mqtt`.

## Why each architecture's *view* still differs

Per-architecture information shape is deliberately preserved rather than
flattened into one shared dictionary:

| Architecture | What it actually exposes | What it does NOT expose |
|---|---|---|
| **Historian** | Time-series values by canonical measurement id (`get_current_value`, `get_historical_values`) | No hierarchy, no relationships |
| **Knowledge Graph** | Explicit entities + typed relationships (`PART_OF`, `MONITORS`) for multi-hop traversal | No time series |
| **UNS** | A browsable site/equipment/measurement namespace tree for *discovery* (`browse_uns`) -- canonical IDs are attached to leaf nodes, but browsing doesn't hand back a value | No current/historical values, no relationships beyond the tree shape |
| **MQTT** | The same observation, but reached by subscribing/discovering on a topic namespace (`icab/tep/<equipment>/<measurement>`) with retained last-value semantics -- a streaming/pub-sub access pattern, not a query API | No history, no relationship traversal |
| **OPC UA** | A live, node-addressed address space grouped by equipment Object, discoverable via `browse`/`read` | No relationships, no history (this server does not persist a history buffer) |

An agent restricted to one architecture therefore genuinely has to work
within that architecture's access pattern -- e.g. a UNS-only agent must
browse to discover measurement IDs before it can ask another tool for a
value; a KG-only agent gets relationships but no time series. This is what
makes architecture-comparison experiments (H1-H4) meaningful instead of
trivial.

## UNS

`icab.context.uns.tep_builder.build_real_uns_nodes()` builds a static
`site/tep/<equipment-key>/<measurement>` tree (e.g.
`site/tep/reactor/reactor_pressure`) from the same `REAL_TEP_EQUIPMENT`
registry the MQTT topic namespace uses, so UNS and MQTT agree on equipment
grouping. It is loaded into the gateway's `InMemoryUNSRepository` once, at
process startup, alongside (not replacing) the original 6-node static
prototype tree under `site/tep/reaction/...` -- the two trees' shared
`site/tep` root node is identical, so merging them is safe. The UNS tree
itself does not need re-syncing as the simulator steps (the hierarchy is
static; only measurement *values*, which live in the historian/MQTT, change).

## OPC UA

`icab.context.opcua.TEPOPCUAServer` is a real, self-hosted `asyncua` server
(distinct from `scripts/run_opcua_demo_server.py`'s small static 3-variable
demo, which is left untouched since `ArchitectureAwareAgent`'s hard-coded
demo node id and `scripts/test_opcua_client.py` still depend on it). It
builds one Object per `REAL_TEP_EQUIPMENT` entry and one Variable per real
measurement, and `sync_from_simulator(simulator)` writes the simulator's
current values into that address space. Verified end-to-end (real server,
real OPC UA client, real socket) in
`tests/integration/test_opcua_tep_server.py`, including that values
actually change across simulator steps/fault injection.

## i3X -- deliberately not wired (needs your attention)

`I3XClient` talks to `https://api.i3x.dev/v1`, a public i3X spec
conformance/reference server this project does not own or control.
Inspecting it directly (read-only) during M4 showed it serves a **fixed,
unrelated demo plant** (`pump-101`, `tank-201`, generic sensors) -- there is
no TEP/reactor object on it. The `i3x` client package does support
*writing* current values to existing objects (`update_value`/
`update_values`), but not creating new objects/types, so there is no way to
add TEP-shaped objects to it even if writing to shared public infrastructure
were otherwise appropriate.

**Decision made without asking:** do not write ICAB's simulator data into
that shared external server's unrelated demo objects (semantically wrong,
and mutates infrastructure ICAB doesn't own). i3X therefore stays read-only
against its existing (non-TEP) demo content -- functionally equivalent to
before M4.

**What would change this:** if a self-hostable i3X reference server
implementation becomes available (the `i3x-client` PyPI package is
client-only), or if you can point `I3XClient` at a private/sandboxed i3X
instance ICAB controls, wiring the real simulator into i3X the same way as
OPC UA (one object per equipment item, values kept in sync) is
straightforward future work. Flagging this rather than silently leaving it
implicit.
