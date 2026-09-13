# Investigation Scenarios (M5)

ICAB's flagship task is open-ended industrial investigation, not TEP fault
classification. This documents the scenario model that drives it and the
four scenarios committed so far (one per locked difficulty level).

## Scenario model

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
- `faults` -- a list of `(disturbance, activate_at_hours, magnitude)`
  entries -- real Downs & Vogel IDVs (1-20 documented faults, 21-28
  documented random variations), activated partway through the run.
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
`TEPSimulator`, runs the warmup, activates faults at their scheduled time,
and syncs the running plant into the historian/knowledge graph/MQTT at
`sync_interval_hours` -- returning a `ScenarioRunResult` with the final
simulator, the last synced `CIMEnvironment`, and the simulator's event log.

Each scenario gets a **distinct epoch** (`_EPOCH_BASE + timedelta(days=seed)`),
not simulated time relative to a single shared "now": the historian/MQTT
are shared, persistent infrastructure across scenario runs, and observation
identity is timestamp + canonical id, so two scenarios reaching the same
*elapsed* hour with the same default epoch would silently collide (whichever
was written first wins under `ON CONFLICT ... DO NOTHING`). This was caught
by an actual test failure while building M5 -- see the M4/M5 commit history.

## The four committed scenarios

All four are real, checked against the actual simulator (not
hand-typed/assumed numbers) -- see
`tests/integration/test_scenario_runner.py`, which asserts the ground truth
is empirically true of the real run (a D3/D4 pressure/level trend actually
moves in the claimed direction by more than a threshold, not just "the YAML
says so").

| Scenario | Difficulty | Fault | Architectures | Why it isn't keyword-matching |
|---|---|---|---|---|
| `d1_reactor_pressure_reading` | D1 | none | `historian` | One current-value read; the trivial case, included as a baseline. |
| `d2_reactor_context_combination` | D2 | none | `historian`, `knowledge_graph` | The objective asks for a value (historian) AND a relationship (KG) -- neither source alone answers it. |
| `d3_reactor_pressure_deviation` | D3 | `idv_01` (A/C ratio, stream 4) at t=1h, 4h run | `historian`, `knowledge_graph` | Requires a historical range query to see the pressure *decline*, not a single point, plus a KG lookup to confirm the equipment. |
| `d4_plant_wide_investigation` | D4 | `idv_06` (A feed loss) at t=1h, 4h run | all five | The objective names no equipment or measurement. The reactor's own readings stay close to normal (`< 10` kPa/% drift) while the Stripper/Compressor/Separator/Condenser show large, real deviations (verified `> 15` unit drops) -- an agent that only ever checks "the reactor" (the obvious guess) finds nothing wrong. |

## Connecting a scenario to the LLM agent

`icab.agent.llm.tools.tools_for_architectures(scenario.available_architectures)`
gives the exact tool subset a scenario permits; pass it as
`LLMInvestigationAgent(..., tools=tools_for_architectures(scenario.available_architectures))`.
`tests/integration/test_scenario_llm_end_to_end.py` (gated behind
`ICAB_RUN_LLM_INTEGRATION_TESTS=1`, like `test_llm_rchat.py`) runs the D1
scenario through the complete path -- TEP simulator, `ScenarioRunner`,
the real FastAPI gateway (via `TestClient`, so real tool implementations
against the real docker-compose services, not a separate server process),
the real NIST RChat LLM, the resulting `InvestigationResult`, the
`TraceCollector` trace, and the existing (unmodified)
`InvestigationEvaluator` -- and passed on first run.

## What is intentionally not yet built (M11 territory)

- H1-H5 hypothesis-specific experimental support (statistical comparison
  across seeds/runs, effect sizes) -- M8's `GroundedInvestigationEvaluator`,
  M9's `ExperimentRunner`/`ExperimentResultStore`, and M10's named
  architecture combinations/`InformationFlowAnalyzer` are all in place;
  what M11 adds is hypothesis-level analysis on top of the
  already-persisted per-run records.
- Only one scenario per difficulty exists -- enough to prove the complete
  loop end-to-end, not a full scenario suite.
