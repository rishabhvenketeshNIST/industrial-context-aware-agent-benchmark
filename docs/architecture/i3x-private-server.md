# Private i3X Server

## What changed

Before this milestone, ICAB's only i3X connection was to
`https://api.i3x.dev/v1`, a public i3X spec conformance/reference server
with fixed, unrelated demo content (a `pump-101`, `tank-201`, generic
sensors -- no TEP, no reactor). It was read-only and stayed that way (see
`docs/architecture/context-architecture.md`'s original M4 write-up).

ICAB now also runs a **private, TEP-backed i3X instance**:

```
TEP simulator (icab.tep.simulator.TEPSimulator, in services/opcua/)
  -> icab.context.opcua.TEPOPCUAServer      (OPC UA address space, live values)
  -> i3xua                                   (CESMII's OPC UA -> i3X wrapper, services/i3x/)
  -> icab.context.i3x.client.I3XClient       (the same client class as before)
  -> ICAB Gateway (icab.gateway.tools.GatewayTools.i3x_get_*)
  -> agent (deterministic or LLM)
```

The public `https://api.i3x.dev/v1` endpoint is untouched and remains
read-only reference infrastructure; ICAB never writes to it. The gateway's
live i3X connection now points at the private instance by default
(`ICAB_I3X_BASE_URL`, default `http://localhost:8090`) --
`icab.context.i3x.client.I3XClient` itself is unchanged; only *which*
server the gateway constructs one against changed.

## Why i3xua, not a custom-built server

Before writing an i3X server from scratch, the CESMII GitHub org (which
also publishes the i3X spec and the `i3x-client` package ICAB already
depends on) was checked for a reference implementation:
[`cesmii/OPCUA-i3X`](https://github.com/cesmii/OPCUA-i3X) ("i3xua") is
exactly that -- an actively maintained, Apache-2.0-licensed OPC UA-to-i3X
wrapper. It mirrors any OPC UA server's address space into real i3X
namespaces/object-types/objects/relationships/values, with an HTTP+JSON
API, a Docker build, and a per-node history ring buffer.

Since ICAB already has a real, TEP-backed OPC UA server
(`icab.context.opcua.TEPOPCUAServer`, from the M4 milestone), pointing
i3xua at it means the private i3X instance exposes **the same underlying
TEP process** the MQTT/Historian/UNS/OPC UA/KG layers already use --
not a second, unrelated dataset. No i3X server had to be written from
scratch, and ICAB gained no new coupling to OPC UA-specific concepts
beyond what M4 already introduced.

`i3xua` is not published as a PyPI package or a tagged/versioned container
image, so `services/i3x/Dockerfile` builds it by cloning
`cesmii/OPCUA-i3X` at a **pinned commit**
(`7df7478bebfedc083b2244428ac9f75e83505166`) rather than tracking `main`,
so the image stays reproducible.

## How TEP data flows into it

1. `scripts/run_tep_opcua_server.py` (containerized as the `opcua_tep`
   compose service) resets a `TEPSimulator`, starts a `TEPOPCUAServer`, and
   loops: step the simulator, `sync_from_simulator` (write current values
   into the OPC UA address space), sleep, repeat. This is a *new*,
   always-on sibling to the M4 `TEPOPCUAServer` integration tests (which
   spin up their own short-lived instance per test) and to
   `scripts/run_opcua_demo_server.py` (a small, static, unrelated demo
   server that `ArchitectureAwareAgent`'s hard-coded OPC UA path still
   uses as-is).
2. `i3xua` (the `i3x_server` compose service) connects to `opcua_tep` over
   the compose network (`opc.tcp://icab-opcua-tep:4841/icab/tep/`,
   `services/i3x/config.yaml`), browses its address space, and mirrors it
   into real i3X objects/types/relationships/values.
3. `icab.context.i3x.client.I3XClient` (unchanged) talks to `i3xua` exactly
   as it would talk to any i3X v1.0 server.
4. `icab.gateway.tools.GatewayTools.i3x_get_*` (unchanged behavior, just a
   different backing server) exposes that to agents.

## i3X capabilities actually exposed (verified, not assumed)

Checked directly against the running stack, not asserted from documentation:

- **Namespaces**: the OPC UA server's namespace array, each suffixed
  `#connection=icab_tep` (`get_namespaces`).
- **Object types**: OPC UA node classes mirrored as i3X object types (347
  observed on first browse).
- **Objects**: one object per `REAL_TEP_EQUIPMENT` item (Reactor,
  Condenser, Separator, Stripper, Compressor, Purge System, Feed System)
  plus one per real measurement (505 objects observed total) --
  `get_objects`/`get_object`.
- **Relationships**: `HasComponent` from each equipment object to its
  measurements (e.g. Reactor -> Reactor pressure) -- `get_related_objects`.
- **Current values**: real, live, moving reactor-pressure-scale values
  (`get_value`) -- confirmed to change across repeated reads
  (`tests/integration/test_i3x_private_server.py::test_private_tep_backed_i3x_value_changes_over_time`).
- **History**: `get_history` returns an empty series until `i3xua` has had
  an active subscription on that node long enough to populate its
  per-node ring buffer (`registry.history_ring_size` in
  `services/i3x/config.yaml`) -- i3xua does not backfill from OPC UA
  server-side history (our `TEPOPCUAServer` doesn't keep one). This is a
  real, current limitation, not a hidden gap: `capabilities.query.history`
  reports `true` (the endpoint exists and is spec-correct), but a caller
  needs a live subscription running first for it to return anything.

## Gateway resilience

`I3XClient` connects **eagerly** at construction (unlike
historian/knowledge-graph, which connect lazily per call) -- this was
already true against the public server, just invisible because that
server is always up. Pointing the gateway at a local, sometimes-not-running
container turned that into a real failure mode: importing
`icab.gateway.app` would previously crash outright if `i3x_server` wasn't
running, taking down *every* gateway test regardless of whether it touched
i3X. Fixed by catching the connection failure at startup (`i3x = None` on
failure, with a printed warning) and adding a `GatewayTools._require_i3x()`
guard (mirroring the existing optional-`mqtt` pattern) to every `i3x_get_*`
method, so a missing private i3X server degrades to a clear `RuntimeError`
from the specific tool call instead of an import-time crash.

## LLM agent tool support

`icab.agent.llm.tools.AGENT_TOOLS` gained `i3x_get_objects`,
`i3x_get_object`, `i3x_get_related_objects`, `i3x_get_value`, and
`i3x_get_history` (architecture key `"i3x"` in
`ARCHITECTURE_TOOL_NAMES`/`tools_for_architectures`). These gateway routes
take individual FastAPI query parameters rather than a Pydantic request
body, so `AgentTool` now accepts either a `request_model` (existing tools,
schema derived from the gateway's own Pydantic model) or a hand-written
`parameters` JSON Schema plus `http_method="GET"` (new i3X tools) --
`icab.agent.client.AgentGatewayClient.call_tool` gained a matching
`method` parameter (`GET` uses query params, default stays `POST` with a
JSON body, so every existing tool call is unaffected).

## Effect on the architecture-comparison experiment design

i3X moves from "excluded, no genuine TEP data available" to a fully
usable, restrictable architecture: a scenario can now set
`available_architectures: [i3x]` (alone or combined) and get a real,
independent access pattern -- object/type/relationship discovery plus
current values, distinct from UNS (name-path browsing), OPC UA (raw
node-id browsing), and the knowledge graph (canonical-id relationships).
None of the four D1-D4 scenarios committed in M5 were changed to use it
(their ground truth was already verified against the historian/KG-based
design); adding an i3X-driven scenario is now straightforward future work
rather than blocked infrastructure.
