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
| `deterministic_agent` | `structured_retrieval` / `context_aware` / `architecture_aware`, when `agent_type == deterministic` |
| `llm_model`, `llm_temperature` | LLM generation config, recorded even when a default was used |
| `max_steps` | Tool/context budget (LLM only; see "Budgets" below) |
| `random_seed` | Reserved for agent-side stochasticity, distinct from the scenario's own simulation seed (see "Seeds" below) |

`ExperimentRecord` (what happened) adds: `run_id`, `experiment_id` (groups
related runs, e.g. an architecture sweep), `scenario_difficulty`,
`simulation_seed`, `icab_version`, `started_at`/`completed_at`, `status`
(`completed`/`failed`), `error`, `result` (the full `InvestigationResult`),
`evaluation` (the full `EvaluationReport`), and `trace_event_count`.

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
```

`--compare` (or passing `--architectures` more than once) calls
`ExperimentRunner.compare_architectures`, which prepares the scenario
**once** and runs every architecture group against that one preparation,
then writes `results/aggregate/<experiment_id>.{json,csv}`.

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

## A discovered, unresolved research-design issue (needs your decision)

Running the deterministic-baseline experiment configuration against a
real `BenchmarkScenario` surfaced two compounding problems, verified live
against the running stack, not hypothesized:

1. **The pre-M5 deterministic baselines don't see real scenario data.**
   `StructuredRetrievalAgent`/`ContextAwareAgent`/`ArchitectureAwareAgent`
   (built before M2's real simulator) are hard-coded to the *legacy*
   static-prototype canonical ids (`urn:icab:measurement:tep_pv_*`), UNS
   path (`site/tep/reaction/reactor`), and a *different* OPC UA server
   (the static demo on port 4840, not the TEP-backed one on port 4841).
   Running `scripts/run_experiment.py --agent-type deterministic
   --deterministic-agent structured_retrieval` against `d1_reactor_pressure_reading`
   produced the conclusion *"Current reactor pressure is 2834.0 kPa"* --
   the old static fixture value, not the scenario's actual simulated
   pressure (~2705-2708 kPa). The deterministic baseline "ran successfully"
   but investigated the wrong data entirely.

2. **`required_evidence` keyword-substring scoring can be fooled by
   shared, cumulative knowledge-graph state.** That same run still scored
   `required_evidence_score == 1.0`. Why: `urn:icab:equipment:reactor` is
   intentionally shared between the legacy and real canonical-id
   namespaces (M2's design decision), and Neo4j is shared, persistent
   infrastructure across every run this benchmark has ever executed --
   so `get_entity_relationships("urn:icab:equipment:reactor")` returns
   *all 15* relationships ever written for that entity (confirmed via a
   direct query), including the real `MONITORS -> reactor_pressure` edge
   from unrelated prior scenario runs. The ground truth's required
   canonical id string is present in the stringified findings blob purely
   because of that unrelated side effect -- not because the agent
   retrieved or grounded on that measurement's value. This is a real false
   positive, not a hypothetical one.

Both are pre-existing conditions (the legacy baselines; the shared,
persistent Neo4j instance) that M9 surfaced by actually exercising them
end-to-end, not something M9 introduced. Per "keep the deterministic
baseline agents unchanged," neither was patched. Flagging this explicitly
rather than presenting the deterministic-agent experiment path as fully
validated: **the LLM-agent experiment path is fully validated (see the
real runs below); the deterministic-baseline path is schema/runner-complete
but currently produces misleading results against M5 scenarios**, and
needs a decision on one or more of:

- Update the legacy baselines to use real canonical ids/paths (a real
  change to agents previously asked to stay unchanged).
- Tighten `required_evidence` scoring to require the match come from a
  tool call that specifically targeted that identifier (e.g. the
  `get_current_value`/`get_historical_values` request's own
  `measurement_id` argument), not just presence anywhere in the run's
  full findings text -- closing the false-positive path independent of
  the baseline-agent issue.
- Scope "deterministic baseline" experiments, for now, to the original
  static prototype scenario rather than M5 `BenchmarkScenario`s, until one
  of the above is addressed.

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
