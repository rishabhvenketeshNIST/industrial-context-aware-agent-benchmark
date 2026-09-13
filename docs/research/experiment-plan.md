# Experiment Infrastructure (M9)

## What this is, and isn't

`icab.experiments` (M9) is a Python-first, locally reproducible experiment
runner: one `ExperimentConfig` in, one `ExperimentRecord` out, persisted
under `results/`. It is not a distributed/cloud platform, and does not try
to be one -- a researcher runs it from the command line
(`scripts/run_experiment.py`) against a gateway they started themselves.

It is additive: `icab.experiments.architecture_comparison`
(`ArchitectureComparisonRunner`) is unchanged and still works exactly as
before, for its own `InvestigationCase`-based path. M9's `ExperimentRunner`
is the newer, richer path built on the M5 `BenchmarkScenario`/
`ScenarioRunner` and the M8 `GroundedInvestigationEvaluator`.

## Schema

`ExperimentConfig` (what to run):

| Field | Meaning |
|---|---|
| `scenario_id` | Which `BenchmarkScenario` (configs/benchmark/scenarios/) |
| `architectures` | Explicit tool-availability list -- e.g. `["historian"]` or `["historian", "knowledge_graph"]`. Never inherited implicitly from the scenario. |
| `agent_type` | `deterministic` or `llm` |
| `deterministic_agent` | `structured_retrieval` / `context_aware` / `architecture_aware` (legacy, control-only -- see "Resolved" below) or `scenario_aware` (real-data-aware, benchmark-eligible), when `agent_type == deterministic` |
| `deterministic_equipment_key` | Only for `scenario_aware`: which `REAL_TEP_EQUIPMENT` item to inspect (default `"reactor"`) |
| `llm_model`, `llm_temperature` | LLM generation config, recorded even when a default was used |
| `max_steps` | Tool/context budget (LLM only; see "Budgets" below) |
| `random_seed` | Reserved for agent-side stochasticity, distinct from the scenario's own simulation seed (see "Seeds" below) |

`ExperimentRecord` (what happened) adds: `run_id`, `experiment_id` (groups
related runs, e.g. an architecture sweep), `scenario_difficulty`,
`simulation_seed`, `generation_id` (the scenario-preparation provenance
tag -- see "Resolved" below), `icab_version`, `started_at`/`completed_at`,
`status` (`completed`/`failed`), `validity`/`validity_reason` (whether this
run is eligible for the main benchmark -- see "Resolved" below), `error`,
`result` (the full `InvestigationResult`), `evaluation` (the full
`EvaluationReport`), and `trace_event_count`.

## Storage layout

Reuses the existing `results/` directory (not a new storage system) with
the requested separation:

```
results/
  raw/<run_id>.json          ExperimentRecord (trace not embedded)
  traces/<run_id>.jsonl      the run's TraceEvent list (icab.trace.storage.JsonlTraceStorage)
  evaluations/<run_id>.json  the run's EvaluationReport alone
  aggregate/<experiment_id>.{json,csv}   cross-run comparison table
```

`raw` and `evaluations` are separate files (not one blob) so a report can
load just the scores for many runs without pulling in every full
`InvestigationResult`; `traces` are separate again since they are the
largest artifact and least often needed for aggregate analysis.

## CLI / workflow

```bash
uv run uvicorn icab.gateway.app:app --reload     # separately, as with the other scripts

# one run
uv run python scripts/run_experiment.py \
    --scenario d1_reactor_pressure_reading --architectures historian --agent-type llm

# deterministic baseline
uv run python scripts/run_experiment.py \
    --scenario d1_reactor_pressure_reading --architectures historian \
    --agent-type deterministic --deterministic-agent structured_retrieval

# architecture comparison -- same scenario/seed/fault, only tools vary
uv run python scripts/run_experiment.py --compare \
    --scenario d2_reactor_context_combination \
    --architectures historian --architectures historian,knowledge_graph \
    --agent-type llm

# scenario-aware deterministic baseline (real data, benchmark-eligible)
uv run python scripts/run_experiment.py \
    --scenario d1_reactor_pressure_reading --architectures historian,knowledge_graph,uns \
    --agent-type deterministic --deterministic-agent scenario_aware
```

`--compare` (or passing `--architectures` more than once) calls
`ExperimentRunner.compare_architectures`, which prepares the scenario
**once** and runs every architecture group against that one preparation,
then writes `results/aggregate/<experiment_id>.{json,csv}` -- excluding
`LEGACY_CONTROL_ONLY` runs by default (pass
`--include-invalid-in-aggregate` to include them, clearly labeled, if you
specifically want to compare against a control baseline).

## Research design decisions (as requested, explicitly)

**How identical process conditions are guaranteed across architecture
comparisons.** `ExperimentRunner.compare_architectures` calls
`ScenarioRunner.prepare(scenario)` exactly once per comparison, before
looping over architecture configs -- every architecture variant
investigates the same already-synced historian/knowledge-graph/MQTT state.
This is airtight for **historian, knowledge_graph, uns, mqtt** (all
written by that one `TEPContextSync.sync()` call chain). **It is NOT
airtight for opcua/i3x**: those are backed by the always-on
`opcua_tep`/`i3x_server` compose services (private i3X milestone), which
run their own independent `TEPSimulator(seed=42)` continuously, with no
fault schedule, decoupled from any given experiment's `scenario.seed`/
fault timing. An architecture comparison that includes `opcua` or `i3x`
alongside `historian`/`knowledge_graph` is therefore comparing "the same
kind of real TEP process" but **not** a bit-identical run. This was known
from the private i3X milestone and is restated here because M9 is where
it actually matters for experimental validity. Fixing it properly (a
per-experiment, freshly-seeded OPC UA/i3X pair) is future work, not
attempted here to keep M9 Python-first and simple.

**How simulation time is handled.** Each scenario run gets its own
wall-clock-independent epoch (`_EPOCH_BASE + timedelta(days=scenario.seed)`,
from M5) so historian/MQTT timestamps never collide across scenarios
sharing the same shared, persistent Postgres/MQTT. Re-running the same
scenario (same seed) reproduces the same timestamps and, given the
simulator's own determinism, the same values -- `ExperimentRunner.run()`
re-preparing a scenario is idempotent, not a fresh/different run.

**How LLM stochasticity is handled.** Not pretended away: `llm_temperature`
is recorded in every `ExperimentConfig` (defaulted to `0.0`, i.e. greedy
decoding, when unset, and that resolved value -- not `None` -- is what gets
persisted), and `llm_model` is always recorded. This makes the *experimental
conditions* auditable and repeatable (same scenario, same seed, same model,
same temperature) without claiming the model's own output is
deterministic -- a temperature-0 run against most providers is *usually*
stable but is not guaranteed bit-identical the way the TEP simulator is.
`random_seed` is reserved on the schema for future agent-side
stochasticity (neither current agent samples beyond the LLM call itself).

**How budgets are enforced.** `max_steps` is `LLMInvestigationAgent`'s
existing tool-call budget (M6/M7, unchanged) -- resolved to
`DEFAULT_MAX_STEPS` when unset, and the resolved value is what's recorded.
Deterministic baselines have no configurable budget: they run a fixed,
short, hard-coded tool sequence, so `max_steps` is always recorded as
`None` for them regardless of what was passed in (a real limitation of the
existing baselines, not something this milestone's schema can enforce
around).

**How failed/tool-error runs are represented.** `ExperimentRunner._run_prepared`
wraps scenario preparation and the agent's `run()` call in one try/except:
any exception (a malformed config, e.g. `architecture_aware` given more
than one architecture, or a real tool/network error) sets
`status=failed`, `error=f"{type}: {message}"`, `result=None`,
`evaluation=None` -- but the trace collected up to the failure point is
still returned/persisted, so a failed run is still debuggable. A
tool-level error *within* a successful agent run (e.g. a single gateway
call raising) is different and already handled inside
`LLMInvestigationAgent._execute_tool`: it's caught and fed back to the LLM
as an observed `{"error": ...}` result rather than crashing the whole
investigation -- that run still completes normally.

**How partial investigations are scored.** An LLM run that exhausts its
step budget (`TerminationReason.STEP_BUDGET_EXCEEDED`) still produces a
valid `InvestigationResult` and is evaluated normally --
`GroundedInvestigationEvaluator.completeness_score` factors in
`terminated_properly` (false for a budget-exceeded run) alongside
required-evidence and relationship scores, so a partial investigation
scores lower without being excluded from aggregation.

**How raw traces are associated with aggregate results.** Every artifact
sharing a `run_id` (`results/raw/<run_id>.json`,
`results/traces/<run_id>.jsonl`, `results/evaluations/<run_id>.json`) is
the same run; `results/aggregate/<experiment_id>.{json,csv}` rows carry
`run_id` as their first column specifically so a row in an aggregate table
can always be traced back to its full record and trace.

## Resolved: legacy-baseline contamination (research-design decision)

Running the deterministic-baseline experiment configuration against a
real `BenchmarkScenario` surfaced two compounding problems, verified live
against the running stack, not hypothesized. Both are now resolved,
following an explicit decision (recorded here) rather than a silent fix:

1. **The pre-M5 deterministic baselines don't see real scenario data.**
   `StructuredRetrievalAgent`/`ContextAwareAgent`/`ArchitectureAwareAgent`
   (built before M2's real simulator) are hard-coded to the *legacy*
   static-prototype canonical ids (`urn:icab:measurement:tep_pv_*`), UNS
   path (`site/tep/reaction/reactor`), and a *different* OPC UA server
   (the static demo on port 4840, not the TEP-backed one on port 4841).
   Running the legacy baseline against `d1_reactor_pressure_reading`
   produced the conclusion *"Current reactor pressure is 2834.0 kPa"* --
   the old static fixture value, not the scenario's actual simulated
   pressure (~2705-2708 kPa). The deterministic baseline "ran successfully"
   but investigated the wrong data entirely.

2. **`required_evidence` scoring could be satisfied by shared, cumulative
   knowledge-graph state.** That same run still scored
   `required_evidence_score == 1.0`. Why: `urn:icab:equipment:reactor` is
   intentionally shared between the legacy and real canonical-id
   namespaces (M2's design decision), and Neo4j is shared, persistent
   infrastructure across every run this benchmark has ever executed --
   so `get_entity_relationships("urn:icab:equipment:reactor")` returned
   *all 15* relationships ever written for that entity (confirmed via a
   direct query), including the real `MONITORS -> reactor_pressure` edge
   from unrelated prior scenario runs. The ground truth's required
   canonical id string was present in the response purely because of that
   unrelated side effect -- not because the agent retrieved or grounded on
   that measurement's value.

### Decision (as directed)

The deterministic baseline agents were **not modified** -- their
implementation and existing tests are untouched. Instead:

**1. Legacy vs. scenario-aware baselines are now a first-class
distinction.** `DeterministicAgentKind` splits into the three *legacy*
kinds (`structured_retrieval`/`context_aware`/`architecture_aware`,
`LEGACY_DETERMINISTIC_AGENT_KINDS`) and a new `scenario_aware` kind. Every
`ExperimentRecord` carries `validity: RunValidity` (`VALID` or
`LEGACY_CONTROL_ONLY`) computed purely from the agent kind requested --
`ExperimentRunner._validity_for` marks a run `LEGACY_CONTROL_ONLY`
whenever `deterministic_agent` is one of the three legacy kinds,
regardless of whether it completes successfully. Legacy runs still
execute in full (preserving their regression/control value) and are still
fully persisted (`raw`/`traces`/`evaluations`); they are simply labeled.

**2. The benchmark cannot accidentally include them.**
`ExperimentResultStore.write_aggregate` excludes non-`VALID` runs from the
comparison table **by default** (`excluded_invalid_runs` in the JSON
output records how many); an explicit `include_invalid=True`
(`--include-invalid-in-aggregate` on the CLI) is required to see them
alongside real comparisons, and even then their `validity`/
`validity_reason` columns keep them clearly labeled rather than blending
in with valid results.

**3. A new, separate, scenario-aware baseline was added.**
`icab.agent.baseline.scenario_aware.ScenarioAwareBaselineAgent` (a new
file, not a modification of any existing agent) is deterministic and
fixed like the legacy baselines, but built entirely on real data: it
resolves its target equipment's canonical id from
`icab.tep.measurements.REAL_TEP_EQUIPMENT`, discovers that equipment's
real measurements by actually browsing the live UNS tree
(`browse_uns("site/tep/<equipment_key>")`), retrieves each one's current
value from the gateway, and confirms relationships via
`get_entity_relationships` -- no legacy id or value appears anywhere in
it. `DeterministicAgentKind.SCENARIO_AWARE` is `RunValidity.VALID`, same
as the LLM agent.

**4. `required_evidence` scoring was independently tightened** (this is
the fix that directly closes the false-positive, and the reason the fix
holds even for a legacy baseline run, not only once agents are updated):
`GroundedInvestigationEvaluator` no longer credits a canonical id as
"found" merely because it appears somewhere in a raw
`get_entity_relationships`/other structural tool response. A hit now
requires one of: the id was the `measurement_id`/`element_id` of an
*actual value retrieval* (`get_current_value`/`get_historical_values`/
`i3x_get_value`/`i3x_get_history`), the agent's own structured
`evidence[].identifier`, or literal mention in the agent's own
`conclusion` text. Verified against the real, already-contaminated
Neo4j instance: the SAME legacy-baseline run that previously scored
`required_evidence_score == 1.0` now scores `0.0` --
see "Validation" below.

### Provenance mechanism (the general fix requested)

Beyond the specific `required_evidence` bug, a run/experiment provenance
tag was added so relationship-based ground truth checks (and any future
use) can tell current-run data apart from other runs'/static reference
data, **without clearing the shared historian/knowledge graph** (kept, per
instruction, since historical accumulation may be useful for future ICAB
experiments):

- `icab.cim.Observation`/`Relationship` gained an additive
  `generation_id: str | None` field (`None` = written outside this
  mechanism, e.g. the legacy static-prototype loader -- i.e. "static/
  reference data").
- `icab.scenarios.runner.ScenarioRunner.prepare()` mints **one**
  `generation_id` (a fresh UUID) per scenario preparation and threads it
  through every `TEPContextSync.sync()` call in that preparation --
  `ScenarioRunResult.generation_id` exposes it.
- `TEPAdapter.build_real_environment(..., generation_id=...)` tags every
  observation/relationship it builds; the Postgres `observations` table
  and Neo4j `RELATIONSHIP` edges both persist and return it (the
  historian via a non-destructive `ALTER TABLE ... ADD COLUMN
  generation_id`, not a drop/recreate, to preserve existing data).
- `ExperimentRunner` passes the current run's `generation_id` into
  `GroundedInvestigationEvaluator.evaluate(..., generation_id=...)`, which
  uses it to scope `expected_relationships` confirmation: a matching
  relationship only counts if it was tagged with *this* generation.
  Passing no `generation_id` (existing M8 callers) preserves the original,
  ungated behavior.
- **A bug in this mechanism was itself caught by live validation, not
  just unit tests**: the Neo4j read query's `RETURN` clause initially
  omitted `generation_id` (only the write path's `SET` clause included
  it), so every read silently came back `null` despite correct writes.
  Unit tests using `InMemoryKnowledgeGraphRepository`/mocks never
  exercised the real Cypher query and did not catch this; a live
  architecture-comparison run against the actual Neo4j instance did
  (`relationship_score` stayed `0.0` when it should have been `1.0`).
  Fixed, and now covered by a dedicated real-Neo4j regression test
  (`tests/integration/test_knowledge_graph_neo4j.py::
  test_neo4j_relationship_generation_id_round_trips`). Recorded here as a
  reminder that this class of bug (a real backend integration silently
  dropping a field) is exactly what unit tests with in-memory fakes
  cannot catch -- the live validation step is not optional.

Note on why relationships needed generation-scoping but a similar
"historian value contamination" concern did not: historian rows are
timestamp+measurement_id keyed and immutable, and scenario epochs are
already seed-distinct (M5) so a `get_current_value` query is already
correctly scoped by construction -- there was never a cross-run value
leak, only mis-attribution of relationship-listing (structural) data as
value evidence, which item 4 above closes directly. Relationship edges,
by contrast, are `MERGE`d (one edge per subject/predicate/object,
overwritten on every write) -- generation-scoping is what lets a query
tell "this run's own knowledge graph state" apart from an edge some
*other* run's preparation last touched.

## Validation: real runs against the live stack

**Single run** (`d1_reactor_pressure_reading`, `historian`, LLM):
conclusion *"The current reactor pressure is 2708.37 kPa gauge, which is
within the normal safe operating range..."* --
`required_evidence=1.00 relationship=1.00 conclusion_correctness=1.00
grounding=1.00 completeness=1.00`.

**Architecture comparison** (`d2_reactor_context_combination`, same seed
102, same objective, same model/temperature, only tools varied):

| architectures | termination | required_evidence | relationship | completeness |
|---|---|---|---|---|
| `historian` | `step_budget_exceeded` | 0.00 | 0.00 | 0.00 |
| `historian+knowledge_graph` | `submitted` | 1.00 | 1.00 | 1.00 |

Restricted to `historian` alone, the LLM agent could not satisfy the
objective (which explicitly asks for a knowledge-graph relationship) and
ran out of its step budget; given `historian`+`knowledge_graph` under
otherwise identical conditions, it answered correctly and grounded the
relationship in a real KG response. This is exactly the research property
ICAB is meant to measure -- the same underlying process, the same
objective, differing only in which architecture's tools the agent had.

`results/aggregate/compare-d2_reactor_context_combination-*.csv` has the
full row-per-run comparison.

### Post-hardening re-validation (legacy contamination fix)

Re-run against the actual, already-contaminated Neo4j instance (the same
one with the 15-relationship "reactor" entity from the original incident)
after the fix above:

| Run | agent | validity | required_evidence | relationship | completeness | conclusion |
|---|---|---|---|---|---|---|
| legacy control (`structured_retrieval`, `d1`) | deterministic (legacy) | `legacy_control_only` | **0.00** (was 1.00) | 1.00 (vacuous -- D1 has no expected_relationships) | 0.67 | *"Current reactor pressure is 2834.0 kPa"* (still the wrong, legacy value -- unchanged, as expected, since the agent itself was not touched) |
| scenario-aware (`scenario_aware`, `d1`) | deterministic (new) | `valid` | 1.00 | 1.00 | 1.00 | *"...urn:icab:measurement:reactor_pressure=2708.37... kPa gauge..."* (the real value) |
| architecture comparison, `historian` only (`d2`) | llm | `valid` | 1.00 | 0.00 (tool not available) | 0.33 | ran out of step budget |
| architecture comparison, `historian+knowledge_graph` (`d2`) | llm | `valid` | 1.00 | **1.00** (generation-scoped confirmation, once the Neo4j read-query bug above was also fixed) | 1.00 | correct, grounded |

The legacy-baseline run's `required_evidence_score` dropping from the
original `1.0` to `0.0` -- against the exact same real, contaminated
knowledge graph, with the legacy agent completely unmodified -- is the
direct, live confirmation that an old/contaminated relationship can no
longer cause a benchmark score to pass accidentally. It is also correctly
excluded from `write_aggregate`'s comparison table by default
(`validity=legacy_control_only`).

## M10: Architecture combinations as a first-class experimental variable

M9 already let `ExperimentConfig.architectures` be any list of architecture
names, and `compare_architectures` already ran the same scenario
preparation once per architecture list. What M10 adds is: (1) a named,
documented *registry* of combinations so a comparison doesn't require
hand-typing tool lists, (2) a way to tell which architecture an agent
*actually used* for a given piece of information (not just which
architectures it *had*), and (3) a check that a set of runs being
compared actually held everything but architecture constant.

### The eight named combinations

`icab.experiments.architecture_combinations.ARCHITECTURE_COMBINATIONS` --
`historian_only`, `uns_mqtt`, `opcua_historian`, `i3x_historian`,
`kg_historian`, `uns_historian_kg`, `mqtt_uns_historian`, `full`. These are
explicitly **not** claimed to be the scientifically optimal set (per the
research direction that requested them) -- they are documented starting
points, each chosen to isolate a different question (a single-architecture
floor; discovery+streaming with no query layer; each non-historian
architecture paired with historian; a discovery+query+relational triple;
a triple deliberately chosen to force redundant acquisition without a KG
to explain it; and the full set, to test whether "more architectures" is
strictly better once redundancy/overhead are counted). Full rationale for
each is in the module docstring and per-entry `rationale` field, not
duplicated here to avoid the two drifting apart.

A combination is a *label*, not a second enforcement mechanism: what
actually restricts the LLM agent's tools is still
`icab.agent.llm.tools.tools_for_architectures(config.architectures)`
(unchanged from M9/M6). `ExperimentConfig.architecture_combination_key`
just records which named preset (if any) `architectures` came from, so
aggregate tables can group by it. `ExperimentRunner.compare_combinations`
is the entry point that resolves keys to combinations and runs them
against one shared scenario preparation, exactly like
`compare_architectures` does for raw architecture lists.

The agent is never told which combination or architecture is "better," or
even which architectures it has beyond what `tools_for_architectures`
exposes to it as callable tools -- it discovers what it can do the same
way for every combination (its tool list), and the scenario's objective
never names a combination.

### Discoverability, acquisition, and redundancy (`icab.evaluation.information_flow`)

Having the historian tool *available* is not the same as the agent
*using* it, and having both MQTT and historian available is not the same
as the agent retrieving the same value from both. `InformationFlowAnalyzer`
is a separate, additive analysis (not part of `GroundedInvestigationEvaluator`,
which stays the deterministic scoring path) over one run's recorded trace
that distinguishes:

- **discoverability** -- the agent learned *what exists* (a measurement's
  canonical id) via a browse/relationship-listing tool
  (`browse_uns`, `get_entity_relationships`, `opcua_browse`,
  `i3x_get_objects`/`i3x_get_related_objects`), without a value.
- **acquisition** -- the agent retrieved an actual *value*, via
  `get_current_value`/`get_historical_values` (historian), `read_mqtt`,
  `opcua_read`, or `i3x_get_value`/`i3x_get_history`.
- **redundancy** -- the same measurement's value acquired via more than
  one *distinct architecture* within one investigation (an agent reading
  the same historian value twice is two acquisitions but not
  cross-architecture redundancy; reading it via both MQTT and the
  historian is).

This is what lets an aggregate row answer "which source did the agent
actually use," not just "which sources were available" --
`ExperimentRecord.information_flow` on every run, and
`redundant_acquisition_count`/`unresolved_acquisition_count`/
`tool_error_count`/`discovered_canonical_id_count`/`acquisition_count` as
aggregate CSV columns.

**Cross-architecture identity resolution caveat**: each architecture
names a measurement its own way, so recognizing "this OPC UA read and
that historian read are the same measurement" requires resolving each
architecture's own identifier back to one canonical id.
Historian/MQTT responses carry the canonical id directly. OPC UA's
`opcua_read` only returns a `node_id`; it is resolved by matching a
*prior* `opcua_browse` response *in the same trace* that reported that
node_id's display name, then matching that name against the real TEP
variable registry -- an `opcua_read` with no matching prior browse in the
trace is counted as `unresolved_acquisition_count`, never guessed at. i3X
element ids are parsed from the wrapper's own
`<connection>!<equipment>.<measurement>` format. This mirrors the same
independent-container limitation already documented above for OPC UA/i3X
comparability (M9): resolution depends on what happened to be in *this*
trace, not on a persistent cross-architecture id registry, so
`unresolved_acquisition_count` is a real, expected outcome in some runs,
not a bug to be silently patched over.

### Cost accounting: latency and tokens

`AgentGatewayClient.call_tool` now times every tool call
(`TraceEvent.latency_ms`); `OpenAICompatibleLLMClient.generate` now
returns `LLMResponse.token_usage` from the provider's own `usage` field,
and `LLMInvestigationAgent` records it as a separate `action="llm_generate"`
trace event (distinct from `"tool_call"` events -- it is not a Gateway
tool call). `ExperimentRunner._run_prepared` sums both onto
`ExperimentRecord.total_latency_ms`/`total_tokens`. `MockLLMClient` never
sets `token_usage`, so unit tests correctly see `total_tokens=None` rather
than a fabricated number -- this is intentionally not backfilled from
some estimate.

### Control-consistency validation

An architecture comparison is only a valid "vary only architecture"
comparison if the scenario, simulation seed, LLM model/temperature, and
step budget are identical across the runs being compared --
`ExperimentResultStore.write_aggregate` now checks exactly that
(`_CONTROL_FIELDS = scenario_id, simulation_seed, llm_model,
llm_temperature, max_steps`) and raises `HeterogeneousControlsError` if
they differ, rather than silently producing a comparison table that looks
controlled but isn't. `allow_heterogeneous_controls=True` overrides this
for a deliberately mixed sweep; the written JSON always records
`controls_consistent`/`control_variance` either way, so even an allowed
heterogeneous aggregate is self-documenting rather than silently implying
a controlled comparison it isn't.

### Validation: real multi-combination run against the live stack

`d4_plant_wide_investigation` (D4) was chosen deliberately for this
validation run: its ground truth requires identifying that the Stripper,
Compressor, Separator, and Condenser are affected, *not* the Reactor --
an agent that only ever looks at the reactor cannot answer it correctly,
regardless of which architecture it uses to look. Combinations compared,
one shared scenario preparation per run (seed 104, real RChat
`gemma-4-31B-it`, identical objective; `controls_consistent: true` in
both aggregate JSONs -- scenario/seed/model/temperature/max_steps were
verified identical across each run's three combinations).

**First pass, `max_steps=10`** (`results/aggregate/m10-d4-combo-validation.{json,csv}`)
-- too tight a budget for D4: all three combinations hit
`step_budget_exceeded` before submitting:

| combination | architectures | termination | required_evidence | relationship | completeness | discovered | acquired | redundant | unresolved |
|---|---|---|---|---|---|---|---|---|---|
| `historian_only` | historian | `step_budget_exceeded` | 0.00 | 0.00 | 0.00 | 0 | 6 | 0 | 35 |
| `kg_historian` | knowledge_graph+historian | `step_budget_exceeded` | 0.00 | 0.50 | 0.17 | 28 | 5 | 0 | 0 |
| `full` | mqtt+uns+opcua+i3x+historian+knowledge_graph | `step_budget_exceeded` | 0.50 | 0.00 | 0.17 | 17 | 9 | 0 | 0 |

Already informative even unsubmitted: `historian_only` has no discovery
tool at all, so the LLM resorted to *guessing* plausible canonical ids
from domain knowledge (`get_current_value` calls to things like
`urn:icab:measurement:product_purity`) -- 35 of 41 acquisition attempts
came back with no matching measurement (`{"observation": null}`, not an
`{"error": ...}`, so correctly counted as `unresolved_acquisition_count`
rather than `tool_error_count`) and it never found any of the actually
affected equipment.

**Second pass, `max_steps=20`** (`results/aggregate/m10-d4-combo-validation-v2.{json,csv}`)
-- same scenario/seed/model, only the step budget raised, run as a
separate, equally-valid experiment (not a retry that discarded the
first):

| combination | termination | required_evidence | relationship | conclusion_correctness | completeness | discovered | acquired | redundant | conclusion (truncated) |
|---|---|---|---|---|---|---|---|---|---|
| `historian_only` | `step_budget_exceeded` | 0.00 | 0.00 | 0.00 | 0.00 | 0 | 6 | 0 | still never located the affected equipment (75 unresolved guesses this time) |
| `kg_historian` | **submitted** | 0.50 | 0.50 | 0.17 | 0.67 | 28 | 12 | 2 | *"...significant drop in the stripper level...peak of 50.757%...decline to 9.940%..."* -- correctly identifies the Stripper |
| `full` | **submitted** | 1.00 | 0.00 | 0.22 | 0.67 | 27 | 18 | 5 | *"...separator temperature decreased...stripper temperature decreased...affected equipment are the separator and the stripper"* -- correctly identifies Separator + Stripper (misses Compressor/Condenser) |

This is direct, real evidence for the research property M10 exists to
measure:

- **Architecture availability changes whether the task is solvable at
  all**, not just how well it's solved: `historian_only` could not
  complete the investigation in either budget -- with no discovery tool,
  an agent restricted to historian alone cannot learn *what equipment
  exists* in a plant-wide, no-equipment-named objective, so it never gets
  past guessing ids. `kg_historian` and `full` both completed once given
  enough budget.
- **"More architectures" is not simply "better," once redundancy is
  counted**: `full` scored higher on `required_evidence` (it happened to
  retrieve more of the specific expected canonical ids) but `redundant_acquisition_count`
  rose from 2 (`kg_historian`) to 5 (`full`) -- with six architectures
  available the agent fetched some of the same measurements' values more
  than once, exactly the tool-call/redundancy cost `full` was included in
  the registry to surface (see its rationale above). Neither combination
  found the complete ground-truth equipment set (Stripper, Compressor,
  Separator, Condenser) within budget -- `kg_historian` found only the
  Stripper, `full` found Separator+Stripper but not Compressor/Condenser
  -- so `conclusion_correctness` stayed low (0.17/0.22) for both despite
  reasonable partial completeness (0.67 each).
- **The evaluator's scores track real, distinguishable agent behavior,
  not noise**: three different architecture configurations, same
  scenario/seed/objective/model, produced three different termination
  outcomes and three different score profiles -- not a flat, uninformative
  comparison.

See `results/aggregate/m10-d4-combo-validation{,-v2}.{json,csv}` for the
full per-run rows (this table is a pointer to them, not a duplicate
source of truth), and `results/raw/`, `results/traces/`,
`results/evaluations/` for each run's full record/trace/evaluation.

## M11: H1-H5 hypothesis-testing infrastructure

`icab.experiments.hypotheses` is a comparison LAYER over already-persisted
`ExperimentRecord`s (M9) and the M10 architecture-combination registry --
it adds no new experiment mechanics, benchmark metric, or ground truth.
It maps each locked hypothesis (`docs/research/hypotheses.md`) to a
specific treatment/control architecture-combination pair and an existing
metric already computed by `GroundedInvestigationEvaluator`/
`InformationFlowAnalyzer`:

| Hypothesis | Treatment | Control | Metric | Direction supporting H |
|---|---|---|---|---|
| H1 -- structured context improves accuracy | `kg_historian` | `historian_only` | `conclusion_correctness_score` | higher |
| H2 -- structured semantics reduce context/tool usage | `uns_historian_kg` | `kg_historian` | `tool_call_count` | lower |
| H3 -- KG relationships improve causal reasoning | `kg_historian` | `historian_only` | `relationship_score` | higher |
| H4 -- selective retrieval beats undifferentiated context | `kg_historian` | `full` | `information_flow.redundant_acquisition_count` | lower |
| H5 -- grounded data/relationships reduce unsupported claims | `kg_historian` | `historian_only` | `unsupported_numeric_claims_count` (synthetic: `len(evaluation.unsupported_numeric_claims)`) | lower |

`evaluate_hypothesis`/`evaluate_all_hypotheses` produce a
`HypothesisTestResult`: arm means, their difference, and
`direction_supports_hypothesis` -- a **descriptive** statement about
which way the observed means point on the records supplied, never a
significance test or a proof/disproof claim (every result carries a
plain-language `caveat` saying exactly that). Records are filtered to
`RunValidity.VALID` and `ExperimentRunStatus.COMPLETED` before being
placed in either arm; an arm with no matching, usable records reports
`None` rather than a fabricated value. `scripts/run_hypothesis_experiment.py
--scenario <id> --hypothesis H<n>` runs a hypothesis's combinations via
`ExperimentRunner.compare_combinations` and persists the result to
`results/hypotheses/<experiment_id>-H<n>.json`; `evaluate_hypothesis` can
equally be pointed at records from **different** prior experiment ids
(only the actual controls -- scenario/seed/model/temperature/max_steps --
need to match, which is exactly `write_aggregate`'s
`HeterogeneousControlsError` check, run separately as a sanity check
below), so an existing comparison need not be re-run from scratch just to
evaluate a hypothesis against it.

### Two measurement bugs caught by this validation (both fixed)

Running `evaluate_all_hypotheses` against the real M10 D4 records
surfaced two real, narrow evaluator bugs -- caught the same way the M9
Neo4j read-path bug was: by real data producing an implausible number,
not by a unit test (both bugs are invisible to the existing unit tests,
which construct traces that don't happen to exercise either path). Both
are fixed in `icab.evaluation.grounded`, covered by new regression tests,
and the affected persisted evaluations/aggregates were recomputed from
their already-saved traces (no new LLM calls needed).

1. **`tool_call_count` silently doubled.** `EvaluationReport.tool_call_count`
   was computed as `len(trace)`. That was correct back when a trace only
   ever contained `action="tool_call"` events -- but M10 added a second
   kind of trace event, `action="llm_generate"` (token-usage accounting,
   `LLMInvestigationAgent`), into the SAME trace. From then on,
   `len(trace)` silently counted both, roughly doubling every reported
   tool-call count (`kg_historian`'s D4 v2 run: 18 real tool calls
   reported as 37). Fixed to
   `sum(1 for event in trace if event.action == "tool_call")`.
   `unique_tools_used` was unaffected (`llm_generate` events carry
   `tool=None`, already filtered out). This directly affects RQ3
   (efficiency) and H2 specifically -- H2's real comparison changed from
   29-vs-37 to the corrected 14-vs-18, same direction either way, but the
   uncorrected numbers were simply wrong.
2. **A cited timestamp's year misread as an unsupported claim.** The
   unsupported-numeric-claims scan (`_NUMBER_PATTERN`) matches any bare
   3+-digit integer in the conclusion. A conclusion that correctly cited
   an ISO-8601 timestamp echoed from a real `get_historical_values`
   observation (e.g. "...50.757% at 2026-04-15T01:15:00Z...") had "2026"
   extracted as a claimed measurement value -- which never matches any
   real process reading, so it was flagged unsupported even though the
   agent's actual claim (50.757%) was fully grounded. This produced the
   D4 `kg_historian` run's `grounding_score=0.5` (real value: 1.0). Fixed
   by stripping ISO-8601 timestamp substrings from the conclusion/objective
   text before the numeric scan (`_strip_timestamps`), so a timestamp's
   digits are never treated as a candidate value claim in the first
   place.

### Real hypothesis comparison against the live stack

Records used: the M10 D4 (`d4_plant_wide_investigation`, seed 104,
`max_steps=20`) `historian_only`/`kg_historian`/`full` runs
(`m10-d4-combo-validation-v2-*`) plus one additional real run,
`uns_historian_kg`, under the same scenario/seed/model/temperature/
max_steps (`m11-h2-uns_historian_kg-uns_historian_kg`) -- run specifically
to complete real coverage of H2's treatment arm. `write_aggregate` over
all four (spanning two different `experiment_id`s) reports
`controls_consistent: true`, confirming they are in fact a valid
"vary only architecture" set to compare. Corrected (post-bugfix) result,
`results/hypotheses/m11-hypotheses-consolidated-H{1..5}.json`:

| Hypothesis | Treatment value | Control value | Difference | Supports? |
|---|---|---|---|---|
| H1 | 0.17 | 0.00 | +0.17 | **yes** |
| H2 | 14 | 18 | -4 | **yes** |
| H3 | 0.50 | 0.00 | +0.50 | **yes** |
| H4 | 2 | 5 | -3 | **yes** |
| H5 | 0.00 | 0.00 | 0 | **no** (tie) |

Read honestly, not as confirmation: this is **one real scenario, one
real run per arm** (n=1) -- exactly the "descriptive, not inferential"
comparison the module promises, nothing more. H1-H4 happen to point in
the predicted direction on this data. H5 is a genuine tie, not a
supporting result: both arms produced a fully grounded conclusion (zero
unsupported numeric claims) on this run, so there is no directional
evidence for H5 either way here -- reported as such rather than omitted
or rounded up. A single D4 run is also the hardest, most open-ended
scenario in the suite; nothing here should be read as evidence about
D1-D3, and repeating this with `--repeat` (crude, since only one real
scenario per difficulty currently exists -- see
`docs/benchmark/tasks.md`) or against additional scenarios once a larger
scenario suite exists would be needed before treating any of these
directions as more than a single data point.

## M12: result aggregation and reporting

`icab.reporting` turns the M9-M11 persisted artifacts
(`results/{raw,traces,evaluations}/`) into grouped summaries, hypothesis
reports, and figures. It reads via `ExperimentResultStore` and writes its
own outputs under `results/reports/` (JSON + Markdown) and
`results/figures/` (the latter already anticipated by the original M9
spec's `results/{raw,traces,evaluations,aggregate,figures}` layout). It
makes no simulator/gateway/LLM calls and is fully deterministic given the
same persisted input records -- `scripts/generate_report.py` and
`scripts/generate_hypothesis_report.py` are the CLI entry points, distinct
from `scripts/run_experiment.py`/`run_hypothesis_experiment.py` (M9/M11),
which actually execute runs.

### Three kinds of claim -- kept explicitly distinct

1. **Benchmark measurements** -- a single run's recorded scores/counts
   (`EvaluationReport`, `InformationFlowReport`, latency/tokens). Not
   touched by this milestone; M12 only reads them.
2. **Descriptive observations** -- what M12 adds: means/medians/
   stdev/min/max across a group of runs (`AggregationReport`), and
   treatment-vs-control comparisons (`HypothesisReport`). A description
   of what the recorded data says, nothing more.
3. **Statistical inference** -- a significance test, a confidence
   interval, a claim that an effect is real and not noise. **ICAB does
   not currently produce (3) anywhere**, including in M12. Every
   `HypothesisReport` carries an explicit, data-derived `limitations`
   list and the M11 `HypothesisTestResult.caveat`; nothing in this
   codebase is permitted to render a hypothesis as "proven," "validated,"
   or "significant."

### Aggregation methodology (`icab.reporting.aggregation.aggregate_records`)

Groups a list of `ExperimentRecord`s by one or more named dimensions
(`icab.reporting.aggregation.DIMENSION_RESOLVERS` --
`scenario_id`, `difficulty`, `architecture`, `architecture_combination_key`,
`agent_type`, `deterministic_agent`, `llm_model`, `llm_temperature`,
`max_steps`, `simulation_seed`, `run_id`, `experiment_id`, `validity`,
`status`) and computes `icab.reporting.stats.summarize`
(n/mean/median/stdev/min/max) per `icab.reporting.metrics.ALL_METRICS`
name within each group.

**Aggregation rule -- do not aggregate incompatible experimental
conditions.** Reuses the exact same safeguard `ExperimentResultStore
.write_aggregate` (M9/M10) already enforces, factored out to
`icab.experiments.controls` so both call sites share one implementation:
`CONTROL_FIELDS` (`scenario_id`, `simulation_seed`, `llm_model`,
`llm_temperature`, `max_steps`) must be held constant across every
record being aggregated, except whichever of them is itself a `group_by`
dimension (that's the deliberate independent variable) -- and
`simulation_seed` specifically is dropped from the check when
`scenario_id` is a `group_by` dimension, since a scenario's seed is
intrinsic to it, not a second independent factor. A violation raises
`HeterogeneousControlsError` unless `allow_heterogeneous_controls=True`
is passed explicitly, in which case the report still records
`controls_consistent`/`control_variance` so an intentionally mixed
aggregation stays self-documenting.

By default, non-`RunValidity.VALID` records (legacy deterministic
baselines -- see the M9 section above) are excluded entirely
(`excluded_invalid_runs`); `include_invalid=True` keeps them **visible**
in each group's composition (`n_legacy_control_only`) without ever
letting them into a metric's statistics -- `is_usable_record`
(VALID + COMPLETED) gates metric computation unconditionally, regardless
of `include_invalid`. Validated directly against the repo's real,
already-mixed `results/`: `uv run python scripts/generate_report.py --all
--group-by scenario_id --group-by architecture_combination_key
--allow-heterogeneous-controls --include-invalid --name ...` reports one
D1 group with `n_runs=6, n_valid=4, n_legacy_control_only=2` and
`conclusion_correctness_score` computed over exactly the 4 valid runs --
the 2 legacy runs are counted, never blended in.

### Metric definitions -- effectiveness kept distinct from efficiency

`icab.reporting.metrics` -- two explicit tuples, never collapsed into one
score:

| Effectiveness (quality of the investigation) | Efficiency (cost of reaching it) |
|---|---|
| Investigation correctness (`conclusion_correctness_score`) | Tool calls (`tool_call_count`) |
| Evidence score (`required_evidence_score`) | Context acquired (`context_acquired_count`) |
| Grounded evidence (`grounding_score`) | Context consumed (`context_consumed_count`) |
| Context completeness (`completeness_score`) | Redundant acquisition (`information_flow.redundant_acquisition_count`) |
| Relationship/causal reasoning (`relationship_score`) | Tool errors (`information_flow.tool_error_count`) |
| Temporal reasoning (`temporal_reasoning_score` -- new synthetic metric, M12) | Latency ms (`total_latency_ms`) |
| Unsupported claims (`unsupported_numeric_claims_count`, lower is better) | Token usage (`total_tokens`) |

`temporal_reasoning_score` is a new M12 synthetic metric (alongside the
pre-existing `unsupported_numeric_claims_count`/`context_acquired_count`/
`context_consumed_count`, all resolved by `icab.experiments.hypotheses
.metric_value`, the single metric-resolution function both M11 hypothesis
testing and M12 aggregation share): `None` (not 0.0) when the scenario
didn't require temporal evidence at all (vacuous, same handling as
`relationship_score`'s "nothing expected" case), else `1.0`/`0.0` for
whether it was acquired.

### Treatment/control (hypothesis) reporting

`icab.reporting.hypothesis_report.build_hypothesis_report` wraps the M11
`HypothesisTestResult` (UNCHANGED -- still the authoritative descriptive
core) with per-arm `SummaryStats` and explicit `limitations` derived from
the data itself:

- an empty arm ("no usable records"),
- a small sample size (either arm's n below 5 -- "far too small for
  statistical inference"),
- an exact tie (`mean_difference == 0` -- "not evidence either for or
  against").

Every `HypothesisReport`/rendered Markdown explicitly states: treatment,
control, the observed difference, its direction, the number of runs in
each arm, whether controls were held constant across the records that
fed the two arms specifically (checked separately from -- and can differ
from -- the aggregation-level check above, since a hypothesis's arms are
usually a subset of all persisted records), and the limitations list.
Nothing is ever labeled "proven," "validated," or "significant" --
grepping the entire `icab/reporting` and `icab/experiments/hypotheses.py`
source confirms none of those words appear as a verdict this codebase
asserts.

### Outputs and reproducibility

`results/reports/<name>.json` (machine-readable, the full
`AggregationReport`/`HypothesisReport`) + `results/reports/<name>.md`
(human-readable) + `results/figures/<name>[-<metric>].png` (plots,
`icab.reporting.plotting`, matplotlib `Agg` backend, headless). Every
`AggregationReport.source_run_ids` and every `HypothesisTestResult`'s
`treatment_run_ids`/`control_run_ids` name the exact underlying run_ids,
traceable back to `results/{raw,traces,evaluations}/<run_id>.*` --
an aggregate number is never presented without a path back to the raw
runs it came from.

Given the same persisted `results/` tree, `aggregate_records`/
`build_hypothesis_report` are pure functions of their input records --
running `scripts/generate_report.py`/`generate_hypothesis_report.py`
twice with the same arguments reproduces byte-identical JSON (modulo
key ordering, which pydantic keeps stable). No simulator/gateway/LLM call
is made by either script.

### Validation: reproduced entirely from already-persisted M10/M11 runs

No new LLM calls were spent on M12 -- every example below reuses the
real `m10-d4-combo-validation-v2-*` and `m11-h2-uns_historian_kg-*`
records already on disk from M10/M11:

- `scripts/generate_report.py --experiment-id m10-d4-combo-validation-v2
  --group-by architecture_combination_key --name m12-d4-v2-by-combination
  --plot-metric conclusion_correctness_score --plot-metric tool_call_count
  --plot-metric total_tokens` reproduces the exact M10 per-combination
  numbers (e.g. `kg_historian` `conclusion_correctness_score` mean 0.167,
  `tool_call_count` mean 18 -- matching the corrected M11 values exactly)
  as a grouped `AggregationReport` with figures, not just a flat CSV row.
- `scripts/generate_hypothesis_report.py --hypothesis H<n>
  --experiment-id m10-d4-combo-validation-v2 --experiment-id
  m11-h2-uns_historian_kg --name m12-H<n>-report --plot`, run for all five
  hypotheses, reproduces the exact M11 descriptive results (H1-H4 point in
  their predicted direction, n=1 per arm; H5 is a tie) with the added
  per-arm median/stdev/min/max and explicit limitations.
- `scripts/generate_report.py --all --group-by scenario_id --group-by
  architecture_combination_key` against the repo's real, already-mixed
  `results/` (spanning legacy-baseline runs, deterministic
  scenario-aware runs, and several LLM configs across M9-M11) correctly
  **raises `HeterogeneousControlsError`** listing exactly which controls
  vary (`llm_model`, `llm_temperature`, `max_steps`) -- confirming the
  safeguard works on real historical data, not just synthetic test
  fixtures. `--allow-heterogeneous-controls` overrides it and the
  resulting report honestly records `controls_consistent: false`.
  `--include-invalid` alongside it further confirms the 2 real legacy
  runs present in the repo are counted (`n_legacy_control_only=2`) but
  excluded from every metric (`n=4`, not 6).

### Reproducing these reports

```
uv run python scripts/generate_report.py \
    --experiment-id m10-d4-combo-validation-v2 \
    --group-by architecture_combination_key --name my-report \
    --plot-metric conclusion_correctness_score

uv run python scripts/generate_hypothesis_report.py \
    --hypothesis H3 \
    --experiment-id m10-d4-combo-validation-v2 \
    --name my-h3-report --plot
```

### Remaining limitations (carried forward, not solved by M12)

- Every real hypothesis comparison remains n=1 per arm (one D4 scenario
  run per architecture combination) -- M12 reports this honestly
  (`limitations`) rather than smoothing it over; it does not itself
  generate more data.
- Only one real scenario exists per difficulty level (D1-D4) -- grouping
  by `difficulty` across genuinely different scenarios of the same
  difficulty is not yet possible.
- No inferential statistics (significance tests, confidence intervals,
  effect sizes) exist anywhere in ICAB -- by design, given the current
  sample sizes; adding them prematurely would manufacture false
  precision.
