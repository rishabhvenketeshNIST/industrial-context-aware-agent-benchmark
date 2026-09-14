# Investigation Scenarios and Benchmark Tasks (M5 + M13-C)

ICAB's flagship task is open-ended industrial investigation, not TEP
fault classification. This documents the scenario model (M5, driving the
real simulator over time) AND, as of M13-C, the TASK layer built on top
of it (what an agent is actually asked, evaluated against, and how) --
see [`docs/benchmark/specification.md`](specification.md) for the full
formal schema and [`docs/benchmark/splits.md`](splits.md) for the
development/validation/test split strategy.

## Scenario model (unchanged since M5)

`icab.scenarios.models.BenchmarkScenario` (distinct from
`icab.tep.scenarios.TEPScenario`, the static measurement snapshot the
original prototype path uses) describes an investigation over the *real*
TEP simulator:

- `seed` -- deterministic measurement-noise seed.
- `warmup_hours` -- time the closed-loop plant runs, unrecorded, before
  anything is pushed to a context architecture (so historian/KG data
  reflects only the scenario's own timeline).
- `duration_hours` / `sync_interval_hours` -- how long the scenario runs
  and how often (`icab.tep.context_sync.TEPContextSync`) pushes a snapshot
  into the historian/knowledge graph/MQTT during that time. This is what
  gives a D3/D4 scenario a real, retrievable historical trend rather than
  one final value.
- `faults` -- a list of `FaultSchedule` entries (`disturbance`,
  `activate_at_hours`, `magnitude`, and, since M13-B, an optional
  `duration_hours` for scheduled deactivation) -- real Downs & Vogel/
  Bathelt-Ricker-Jelali IDVs, activated partway through the run.
- `available_architectures` -- which context architectures' tools an
  agent is given (`icab.agent.llm.tools.tools_for_architectures`). This is
  what makes an architecture comparison meaningful: a scenario restricted
  to `["historian"]` genuinely cannot be solved with a knowledge-graph
  call, because the agent is never given that tool.
- `ground_truth` -- structured (`root_cause_disturbance`,
  `affected_measurements`, `affected_equipment`,
  `expected_relationships` as canonical-id triples, `expected_evidence`)
  plus a reference `conclusion` string. Structured fields are canonical
  ids/disturbance names, not free text, so they can be checked, not just
  keyword-matched.

`icab.scenarios.runner.ScenarioRunner.prepare(scenario)` resets a fresh
`TEPSimulator`, runs the warmup, activates (and, if scheduled,
deactivates) faults at their scheduled time, and syncs the running plant
into the historian/knowledge graph/MQTT at `sync_interval_hours` --
returning a `ScenarioRunResult` with the final simulator, the last
synced `CIMEnvironment`, the simulator's event log, and a
`generation_id` (M9) shared by every observation/relationship that
preparation wrote.

Each scenario gets a **distinct epoch** (`_EPOCH_BASE + timedelta(days=seed)`),
not simulated time relative to a single shared "now" -- see the M5 commit
history for the collision this prevents.

## Scenario/task separation (M13-C)

```
BenchmarkScenario  (process state / fault / time-series conditions)
     |  scenario_id
     v
BenchmarkTask      (the question, required evidence, evaluation criteria)
     |  evaluated via
     v
GroundedInvestigationEvaluator.evaluate_task(...)
```

A `BenchmarkTask` (`icab.tasks.benchmark_task`) is NOT a scenario, and
several tasks legitimately share one scenario -- e.g. all 4 tasks
against `d4_feed_pressure_reactor_effect` investigate the exact same
process trajectory, but ask different questions (a diagnosis, a negative
check on the feed system, a positive-identification investigation, and
an explanatory diagnosis) with different required evidence and
architecture restrictions. See
[`docs/benchmark/specification.md`](specification.md) for the full
schema.

## The 9 committed scenarios

The original 4 (M5) plus 5 new ones (M13-C) built on M13-B's empirically
verified faults not yet used by any scenario. All 9 are checked against
the actual simulator, not hand-typed/assumed numbers -- see
`tests/integration/test_scenario_runner.py` (all 9... well, 6 of the 9
have a dedicated empirical-verification test; see "Validation coverage"
below for exactly which).

| Scenario | Difficulty | Fault | Architectures | Why it isn't keyword-matching |
|---|---|---|---|---|
| `d1_reactor_pressure_reading` | D1 | none | `historian` | One current-value read; the trivial baseline case. |
| `d2_reactor_context_combination` | D2 | none | `historian`, `knowledge_graph` | Needs a value (historian) AND a relationship (KG) -- neither source alone answers it. |
| `d2_reactor_cooling_deviation` | D2 | `idv_17` | `historian`, `knowledge_graph` | M13-B's cleanest "obvious single-variable response" case -- one measurement, one equipment. |
| `d3_reactor_pressure_deviation` | D3 | `idv_01` | `historian`, `knowledge_graph` | Requires a historical range query (a decline, not a point) plus a KG lookup. |
| `d3_stream4_composition_shift` | D3 | `idv_02` | `historian`, `knowledge_graph` | Moderate multi-variable, 3-equipment cross-unit pattern. |
| `d3_stochastic_composition_drift` | D3 | `idv_08` | `historian`, `knowledge_graph` | Stochastic (not step) disturbance -- effect only clearly visible in the LATE part of the window, testing historical reasoning specifically, not just "was a historical call made." |
| `d4_plant_wide_investigation` | D4 | `idv_06` | all five | The objective names no equipment. Reactor's own readings stay near-normal while Stripper/Compressor/Separator/Condenser show large, real deviations. |
| `d4_unknown_plant_disturbance` | D4 | `idv_20` | all five | The disturbance itself has NO documented physical description in `tep_studio` ("Unknown random disturbance") -- yet its cross-unit effect (Separator/Stripper/Purge System/Reactor) is empirically characterized anyway. |
| `d4_feed_pressure_reactor_effect` | D4 | `idv_24` | all five | Named after the feed system; its real, repeatable effect is entirely on reactor/separator/stripper pressure -- the feed system itself shows nothing. The sharpest available "fault name predicts nothing about affected equipment" case. |

## Current task inventory (M13-C)

**38 tasks** across the 9 scenarios above (`configs/benchmark/tasks/`,
one YAML file per scenario, loaded/validated by
`icab.tasks.BenchmarkTaskRegistry`).

### By difficulty

| D1 | D2 | D3 | D4 |
|---|---|---|---|
| 6 | 9 | 11 | 12 |

Deliberately not D1-dominated: D3+D4 (23) outnumber D1+D2 (15), and D1's
own share is well under a third of the suite.

### By task type

| QA | Investigation | Diagnosis |
|---|---|---|
| 14 | 14 | 10 |

Every diagnosis-typed task binds on `conclusion_correctness_score`
(checked directly: `tests/unit/tasks/test_real_task_inventory.py
::test_diagnosis_tasks_bind_on_conclusion_correctness`) -- a diagnosis
task that never checked it would not really be testing diagnosis.

### By context dimension

All seven are required by at least one real task -- checked directly,
not merely definable in principle
(`test_every_context_dimension_is_required_by_at_least_one_task`):

| Dimension | Example task |
|---|---|
| C1 Semantic | `d4plant-qa-discover-equipment` (UNS/OPC UA discovery, deliberately isolated from C2-C7) |
| C2 Asset/Hierarchy | `d4plant-qa-discover-equipment` (equipment discovery) |
| C3 Relational | `d2ctx-qa-monitors-relationship-confirmed` (KG-only, MONITORS) |
| C4 Temporal | `d3pressure-qa-trend-direction` (bounded historical range) |
| C5 Operational | `d1-qa-current-pressure` (current value) |
| C6 Procedural | `d2ctx-qa-cooling-valve-controls-temperature` (KG CONTROLS relationship, sourced from M13-A's real control-loop registry) |
| C7 Historical | `d3stochastic-qa-gradual-or-instantaneous` (a gradual, developing pattern across the whole window) |

### By architecture

Every one of `historian`, `knowledge_graph`, `uns`, `opcua`, `mqtt` is
required by at least one real task. **`i3x` is not required by any task
in this initial suite** -- a deliberate, documented absence (see
Limitations), confirmed as deliberate (not an oversight) by
`test_every_available_architecture_is_used_by_at_least_one_task`, which
asserts `i3x` IS a legitimate, resolvable architecture name
(`icab.agent.llm.tools.ARCHITECTURE_TOOL_NAMES`) that simply isn't used
yet.

Task-level architecture restriction is used deliberately, not just
inherited from the scenario:

- `d2ctx-qa-monitors-relationship-confirmed` and
  `d2ctx-qa-cooling-valve-controls-temperature` grant ONLY
  `knowledge_graph`, even though their scenario also has `historian` --
  because the question is answerable from the KG alone (per the M13-C
  direction: "do not make an architecture required unless the task
  genuinely cannot be completed from another available source").
- `d4plant-qa-discover-equipment` grants ONLY `uns`/`opcua` (no
  historian/KG at all) -- isolating discoverability (C1/C2) from value
  retrieval/relational reasoning.
- Several D4 tasks narrow the scenario's full 5-architecture set down to
  just `historian`/`knowledge_graph` when the specific question doesn't
  need discovery tools.

### By fault/scenario

All 7 of M13-B's empirically verified faults underlie at least one
scenario a real task is built on (`idv_01`, `idv_02`, `idv_06`,
`idv_08`, `idv_17`, `idv_20`, `idv_24`) -- checked directly against the
real registries, not merely claimed
(`test_at_least_one_task_per_verified_fault_is_used_somewhere`).

## Ground-truth separation

Structural, not merely disciplined -- see
[`docs/benchmark/specification.md`](specification.md)'s section 7 for
the full mechanism (the M13-B objective-leak validator, the
`grep -rl ground_truth` structural argument, and what's tested where).

## Evaluation

Every task is scored via
`GroundedInvestigationEvaluator.evaluate_task` -- see
[`docs/benchmark/evaluation.md`](evaluation.md), which documents the
deterministic (non-LLM-judge) scoring mechanism, what `evaluate_task`
changes vs. the original `evaluate`, and a real, minor limitation
(`_slug`'s hyphen-vs-underscore handling) caught while validating M13-C
tasks against the real stack.

## Validation coverage

- Every one of the 38 real tasks validates against its schema (subset
  architecture check, dimension-architecture consistency, etc.) at
  `BenchmarkTaskRegistry` load time -- `tests/unit/tasks/test_real_task_inventory.py`.
- 6 of the 9 scenarios have a dedicated real-simulator empirical-verification
  test (`tests/integration/test_scenario_runner.py`): the 4 original M5
  scenarios, plus `d3_stochastic_composition_drift` and
  `d4_feed_pressure_reactor_effect` (one representative new D3 and one
  representative new D4 scenario). `d2_reactor_cooling_deviation`,
  `d3_stream4_composition_shift`, and `d4_unknown_plant_disturbance`'s
  ground truth was derived from direct
  `icab.tep.fault_characterization.characterize_disturbance()` runs at
  their own specific seeds (still real simulator runs, just not wrapped
  in a dedicated pytest assertion) -- see M13-B's characterization
  methodology.
- 3 representative tasks (one per D1/D3/D4) are checked end-to-end
  against the REAL historian/knowledge graph AND the real
  `GroundedInvestigationEvaluator.evaluate_task` path in
  `tests/integration/test_benchmark_tasks_against_real_stack.py` --
  confirming required evidence genuinely exists and a realistic,
  tool-grounded answer scores as expected, not merely that the YAML
  parses.

## Connecting a scenario/task to the LLM agent

`icab.agent.llm.tools.tools_for_architectures(task.available_architectures)`
gives the exact tool subset a TASK permits (narrower than or equal to
its scenario's own); pass it as
`LLMInvestigationAgent(..., tools=tools_for_architectures(task.available_architectures))`.
`tests/integration/test_scenario_llm_end_to_end.py` (gated behind
`ICAB_RUN_LLM_INTEGRATION_TESTS=1`) still runs the D1 SCENARIO (not yet
migrated to run a specific TASK's objective) through the complete real
path -- TEP simulator, `ScenarioRunner`, the real FastAPI gateway, the
real NIST RChat LLM, and the original (unmodified) `InvestigationEvaluator`.

## Known limitations

- **`i3x` is not exercised by any task in this initial suite.** All 5
  new scenarios that DO grant `i3x`-capable architecture sets grant
  `opcua`/`uns`/`mqtt` instead of `i3x` specifically for their discovery/
  hierarchy tasks -- not because i3X is broken (M13-A's private i3X
  instance works), just because this milestone's task authoring didn't
  reach it. A natural, bounded follow-up: add an i3x-specific discovery
  task against one of the full-architecture D4 scenarios.
- **No new BenchmarkScenario was built specifically to isolate C1
  (Semantic) alone** -- `d4plant-qa-discover-equipment` combines C1+C2
  (UNS/OPC UA both provide naming AND hierarchy together in this
  implementation); a task isolating "what does this id semantically
  mean" from "what equipment is it under" would need a source that
  provides one without the other, which none of ICAB's current
  architectures cleanly do.
- **Diagnosis tasks' `conclusion_correctness_score`** checks that the
  right concepts (disturbance id, affected assets) are MENTIONED, not
  that the causal argument connecting them is sound -- the same
  limitation `GroundedInvestigationEvaluator` has carried since M8, now
  inherited by every diagnosis-typed task; each affected task's own
  `evaluation_criteria.known_limitations` restates this where relevant
  rather than leaving it implicit.
- **`d3_stochastic_composition_drift`'s C7 tasks** cannot have their
  "gradual vs. instantaneous" CLAIM independently verified by the
  evaluator (only that a historical query was made and the right ids
  are mentioned) -- stated explicitly in each such task's
  `known_limitations`, not silently assumed solved.
- **`d2ctx-qa-cooling-valve-controls-temperature`'s CONTROLS fact is
  static** (holds regardless of which fault, if any, is active) -- it
  exists specifically to give C6 real coverage, not because a scenario
  requires it as evidence of an active fault.
- **Only 3 of 38 tasks have a dedicated real-stack integration test**
  (one per D1/D3/D4) -- the rest are validated at the schema level
  (`BenchmarkTaskRegistry`) and via their underlying scenario's own
  empirical verification, but not individually re-run end-to-end through
  the evaluator against live infrastructure.

## Running these tasks (M13-D)

This entire task inventory is executed end to end -- task selection,
scenario preparation, fault injection, agent execution, evaluation,
persistence, aggregation, and reporting -- by the one-command benchmark
orchestrator:

```
uv run python scripts/run_benchmark.py --suite tep-v1 --agent llm --architectures all --seeds 1,2,3,4,5
```

`--suite tep-v1` loads this exact, actually-registered task inventory
(via `icab.tasks.registry.BenchmarkTaskRegistry` against
`configs/benchmark/tasks/`) -- nothing about the task list above is
hard-coded into the runner. See
[`docs/benchmark/specification.md#10-one-command-orchestration-m13-d`](specification.md#10-one-command-orchestration-m13-d)
for the full CLI reference, architecture-arm resolution rules, and
persistence/aggregation/reporting details.
