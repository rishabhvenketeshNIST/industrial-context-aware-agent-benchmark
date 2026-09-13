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
