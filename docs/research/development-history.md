# Development History (M1-M13-D)

> **Historical development record**, preserved from the repository
> README (moved here during the production-readiness hardening pass so
> the README itself could focus on being a user guide -- see the repo
> root [`README.md`](../../README.md)). This is a milestone-by-milestone
> account of what was built and why; it is not re-derived automatically,
> so it can drift from the exact current state of the code in minor
> ways as work continues -- treat the code, tests, and the
> `docs/benchmark/`/`docs/architecture/` reference docs as authoritative
> for current behavior, and this file as the narrative of how it got
> there.

## Implemented and under test

- CIM entities/observations/relationships and JSON Schemas
- Historian (TimescaleDB), knowledge graph (Neo4j), UNS, i3X, OPC UA, and MQTT
  (Mosquitto) context sources, unified behind the Agent Gateway
- A real, closed-loop Tennessee Eastman Process simulator
  (`icab.tep.simulator.TEPSimulator`, wrapping the `tep-studio` Downs & Vogel
  kernel) alongside the original static prototype scenario path — see
  [`docs/architecture/tep-simulator.md`](../architecture/tep-simulator.md)
- MQTT as a first-class context/data source (`icab.context.mqtt`), including
  a `TEPMeasurementPublisher` bridge from the simulator onto an ICAB MQTT
  topic namespace and gateway `browse_mqtt`/`read_mqtt` tools — see
  [`docs/architecture/mqtt.md`](../architecture/mqtt.md)
- The real simulator wired into Historian + Knowledge Graph
  (`icab.tep.context_sync.TEPContextSync`), UNS
  (`icab.context.uns.tep_builder`), a real, self-hosted OPC UA server
  mirroring the full measurement set (`icab.context.opcua.TEPOPCUAServer`),
  and a **private, TEP-backed i3X instance** (CESMII's `i3xua` wrapper in
  front of that same OPC UA server) — each architecture deliberately keeps
  its own access pattern rather than exposing an identical view; see
  [`docs/architecture/context-architecture.md`](../architecture/context-architecture.md)
  and [`docs/architecture/i3x-private-server.md`](../architecture/i3x-private-server.md)
  (the public `api.i3x.dev` conformance server stays read-only/unused, by design)
- `StructuredRetrievalAgent`, `ContextAwareAgent`, `ArchitectureAwareAgent`
  (deterministic baselines) and `LLMInvestigationAgent` (real tool-calling
  LLM agent, provider-configurable, NIST RChat by default) — see
  [`docs/architecture/llm-agent.md`](../architecture/llm-agent.md)
- Trace collection/storage, the original keyword-matching investigation
  evaluator (`icab.evaluation.investigation.InvestigationEvaluator`,
  unchanged), and a stronger, fully deterministic, structured evaluator
  (`icab.evaluation.grounded.GroundedInvestigationEvaluator`) scoring
  required evidence, evidence provenance, canonical-id validity, temporal
  and relationship evidence, causal-reasoning/conclusion-correctness
  heuristics, unsupported numeric claims, acquired-vs-consumed context, and
  investigation completeness against a `BenchmarkScenario`'s ground truth —
  deliberately not an LLM-as-judge; see
  [`docs/benchmark/evaluation.md`](../benchmark/evaluation.md)
- `ArchitectureComparisonRunner` for running one case across architectures
  (unchanged since before M9 — see `icab.experiments.ExperimentRunner`
  below for the newer, scenario-based path)
- A D1-D4 investigation scenario framework (`icab.scenarios`) driving the
  real simulator over time with deterministic seeds, scheduled faults, and
  structured ground truth, plus one real, empirically-verified scenario per
  difficulty level under `configs/benchmark/scenarios/` — connected
  end-to-end to `LLMInvestigationAgent` and the real gateway/LLM provider;
  see [`docs/benchmark/tasks.md`](../benchmark/tasks.md)
- A locally reproducible experiment runner (`icab.experiments.
  ExperimentRunner`, `scripts/run_experiment.py`) that runs any agent
  (deterministic or LLM) against a `BenchmarkScenario`, holding the
  process/seed/objective/model fixed while varying only which
  architectures' tools are exposed — persisted as raw/trace/evaluation/
  aggregate JSON+CSV under `results/`. Every run is tagged `RunValidity`
  (the three pre-M5 deterministic baselines are `legacy_control_only` —
  regression/control use only, excluded from the main benchmark
  comparison by default — since they don't see real scenario data; a new,
  separate `ScenarioAwareBaselineAgent` deterministic baseline does, and is
  benchmark-eligible); a `generation_id` provenance tag on every
  observation/relationship a scenario preparation writes lets the
  evaluator scope relationship evidence to the current run rather than a
  shared historian/knowledge graph's accumulated history. See
  [`docs/research/experiment-plan.md`](experiment-plan.md)
- Architecture combinations as a first-class experimental variable (M10):
  eight named, documented tool-availability presets
  (`icab.experiments.architecture_combinations`, `--combination` on
  `scripts/run_experiment.py`) an agent is never told about beyond its own
  tool list; a separate `InformationFlowAnalyzer`
  (`icab.evaluation.information_flow`) that distinguishes discoverability
  (learned a measurement exists) from acquisition (retrieved its value)
  from cross-architecture redundancy (the same value fetched through more
  than one architecture) per run; per-run latency/token-usage totals; and
  a `HeterogeneousControlsError` check in `ExperimentResultStore.
  write_aggregate` that refuses to treat a set of runs as a controlled
  architecture comparison unless their scenario/seed/model/budget actually
  match. See [`docs/research/experiment-plan.md`](experiment-plan.md)
- H1-H5 hypothesis-testing infrastructure (M11): `icab.experiments
  .hypotheses` maps each locked hypothesis
  ([`docs/research/hypotheses.md`](hypotheses.md)) to a
  specific treatment/control architecture-combination pair and an
  existing evaluator/information-flow metric, and produces a descriptive
  (never inferential -- no significance test, no "proven" claim)
  `HypothesisTestResult`; `scripts/run_hypothesis_experiment.py
  --scenario <id> --hypothesis H<n>` runs it end-to-end. Real validation
  against the live stack (one D4 run per arm) surfaced and fixed two
  evaluator measurement bugs (`tool_call_count` double-counting a new
  M10 trace-event kind; a cited timestamp's year misread as an
  unsupported numeric claim) -- see
  [`docs/research/experiment-plan.md`](experiment-plan.md)
- Result aggregation and reporting (M12): `icab.reporting` turns
  persisted `results/{raw,traces,evaluations}/` artifacts into grouped
  summaries (`aggregate_records` -- by scenario, difficulty, architecture
  (combination), agent type, LLM model, or seed/run, with
  mean/median/stdev/min/max/n and success/failure counts per group,
  reusing the same heterogeneous-controls safeguard as M9/M10's
  `write_aggregate`), richer hypothesis reports
  (`build_hypothesis_report` -- per-arm statistics plus data-derived
  `limitations`, never a "proven"/"significant" verdict), and
  reproducible plots (`icab.reporting.plotting`, matplotlib, headless).
  Effectiveness and efficiency metrics are kept in two explicit, separate
  groups rather than one collapsed score
  (`icab.reporting.metrics.EFFECTIVENESS_METRICS`/`EFFICIENCY_METRICS`).
  `scripts/generate_report.py`/`generate_hypothesis_report.py` operate
  entirely on already-persisted runs -- no simulator/gateway/LLM calls --
  and write `results/reports/*.{json,md}` + `results/figures/*.png`. See
  [`docs/research/experiment-plan.md`](experiment-plan.md)
- Complete TEP process-context model and knowledge graph (M13-A): all 53
  real TEP process variables (41 measurements + 12 manipulated
  variables/actuators, verified against `tep_studio` directly rather than
  assumed) now have a canonical identity, required metadata (unit,
  equipment location, a unit-derived physical-quantity `category`,
  source/provenance), and are synchronized into the knowledge graph.
  Beyond the pre-existing `PART_OF`/`MONITORS` hierarchy, the KG now
  represents `ACTUATES` (equipment -> actuator, structural),
  `CONTROLS` (actuator -> measurement, sourced from the real
  decentralized controller's own control-loop registry,
  `tep_studio.control.registry.RICKER_MODE1`), and `HAS_LIMIT`/
  `ASSOCIATED_WITH` (the two documented Mode-1 constraint overrides) --
  every nontrivial relationship traceable to a specific, citable source,
  no causal/diagnostic edges invented. See
  [`docs/architecture/tep-context-model.md`](../architecture/tep-context-model.md)
- Automated TEP fault injection (M13-B): all 28 real TEP disturbances are
  injectable through ICAB without error; an empirical, paired
  same-seed-baseline characterization
  (`icab.tep.fault_characterization`, `scripts/characterize_tep_disturbances.py`,
  persisted at `configs/benchmark/fault_catalog.json`) establishes that
  **7 of 28** repeatably (across every tested seed) produce a real,
  above-noise-floor measurement effect -- distinct, explicit tiers
  (`simulator_supported`/`icab_injectable`/`empirically_verified`, never
  conflated). `FaultSchedule` gained scheduled deactivation
  (`duration_hours`); `BenchmarkScenario` gained an enforced technical
  safeguard rejecting a scenario whose objective leaks its own fault id.
  Hidden ground-truth separation (agent never sees the fault identifier
  or `GroundTruth`) is verified end to end against the real simulator +
  real Neo4j + real Historian + real MQTT, not merely asserted. See
  [`docs/architecture/tep-fault-injection.md`](../architecture/tep-fault-injection.md)
- Automated TEP benchmark task/question suite (M13-C): a first-class
  `BenchmarkTask` model (`icab.tasks`), explicitly separate from
  `BenchmarkScenario` — a scenario defines the process/fault conditions,
  a task defines the question/required evidence/evaluation criteria
  asked against it, and one scenario carries several tasks. 38 tasks
  across 9 scenarios (4 original + 5 new, built on M13-B's remaining
  verified faults), spanning all three locked task types
  (QA/investigation/diagnosis), all four difficulty levels (D1-D4, not
  D1-dominated), and all seven locked context dimensions (C1-C7, newly
  operationalized and architecturally enforced — a task cannot declare
  a dimension none of its own architectures can supply). Evaluated via
  `GroundedInvestigationEvaluator.evaluate_task` — the same
  deterministic, non-LLM-judge scoring `evaluate` already used, keyed on
  a task's own ground truth/difficulty. Development/validation/test
  splits are assigned per-SCENARIO specifically to prevent leakage (two
  tasks sharing a scenario always land in the same split). See
  [`docs/benchmark/specification.md`](../benchmark/specification.md),
  [`docs/benchmark/tasks.md`](../benchmark/tasks.md), and
  [`docs/benchmark/splits.md`](../benchmark/splits.md)
- One-command automated benchmark orchestration (M13-D): `icab.benchmark`/
  `scripts/run_benchmark.py` execute the FULL pipeline -- task selection
  (the suite's real registered inventory, never hard-coded) → scenario
  selection → deterministic TEP initialization/fault injection → context
  synchronization → agent execution (`ScenarioAwareBaselineAgent` or
  `LLMInvestigationAgent`; legacy deterministic agents remain available
  only as an explicit, separate, non-default opt-in) → trace collection →
  `GroundedInvestigationEvaluator.evaluate_task` → persistence → automatic
  aggregation → an M12-style report, from one command, reusing every
  M5/M9/M12/M13-A/B/C component as-is. `--architectures all` expands to
  exactly the architectures the SELECTED TASK declares available (an
  unsupported combination is skipped, never silently narrowed or run);
  `--seeds`/`--repetitions` expand a controlled sweep holding task,
  objective, model, and budgets fixed across architecture arms (the sole
  independent treatment). Every run -- including a failed one -- persists
  a `configuration_hash`, `generation_id`, `git_commit`, and
  `benchmark_version` for audit; execution is strictly sequential (no
  Kubernetes/Kafka/Celery). A CLI-level preflight check
  (`GET /health` against `--gateway-url`) fails fast with an actionable
  message if the Agent Gateway isn't running, rather than letting every
  run independently waste a full scenario preparation on the same
  connection error. Also produces a researcher-facing question/answer
  report (`results/reports/<benchmark_id>-qa.{json,md}`) -- see
  [`docs/benchmark/specification.md §10`](../benchmark/specification.md#10-one-command-orchestration-m13-d)
- Production-readiness/release-hardening pass (post-M13-D): a
  `BenchmarkIdCollisionError` guard so rerunning an explicit `--name`
  never silently overwrites a prior benchmark's artifacts (`--force` to
  override deliberately); `ExperimentRecord.fault_version` (looked up
  from `configs/benchmark/fault_catalog.json`); CLI-level preflight
  checks for PostgreSQL/Neo4j/MQTT reachability and clear, actionable
  errors (not raw tracebacks) for unknown suites/tasks/scenarios/
  architectures, malformed seeds, and non-positive repetitions/budgets;
  `results/` cleared of accumulated development-era artifacts and
  gitignored going forward (directory skeleton kept via `.gitkeep`); a
  dedicated credential-leakage test suite
  (`tests/unit/security/test_no_credential_leakage.py`); and this README
  rewritten as a user guide, with this file split out to keep the
  detailed development narrative without it dominating the README.

- ICAB v2 (post-hardening): a broader organizing principle than fault
  diagnosis -- ISA-95 level -> industrial use case -> scenario ->
  optional fault -> context requirement -> representation ->
  sufficiency -> architecture -> agent -> outcome. See
  [`docs/benchmark/specification-v2.md`](../benchmark/specification-v2.md)
  for the full spec; `tep-v1` is completely unmodified. New
  `icab.usecases.IndustrialUseCase` (14 real, honestly-scoped use cases
  under `configs/usecases/` -- 7 Equipment, 5 Process Cell, 2 Area, and
  explicitly ZERO at Enterprise/Site/Work Center, since TEP genuinely
  has no data there); `icab.tasks.context_combinations` (a deterministic,
  generated 127-combination space over the seven locked dimensions);
  `icab.tasks.context_dimensions.provided_dimensions` (what an
  architecture ARM actually makes available, distinct from a task's
  fixed `required_context_dimensions` -- the variable
  necessity/sufficiency experiments actually need to vary); a new
  `tep-v2` suite (`configs/benchmark/tasks_v2/`, generated by
  `scripts/generate_tep_v2_tasks.py` from tep-v1's own, byte-for-byte
  unmodified task content plus `isa95_level`/`use_case_id`, via an
  explicit, reviewable mapping table cross-checked against the real
  inventory at generation time -- plus 2 new, hand-authored Area-level
  tasks verifying the real Site/Area/ProcessCell hierarchy). The
  MANDATORY architecture connectivity suite
  (`icab.architecture_health`, `tests/integration
  /test_architecture_connectivity.py`,
  `scripts/check_architecture_health.py`): a REAL functional round trip
  through every component (Historian/KG/UNS/MQTT/OPC UA/i3X/Gateway),
  asserting on actual returned data, never just a status code -- found
  and fixed two real bugs during development (a `psycopg.connect()`
  against an unresponsive port hanging 20+ seconds on Windows with no
  bounded timeout; a pydantic-settings `validation_alias` gotcha where
  constructing `ICABSettings(field_name=...)` directly is silently
  ignored in favor of the real `.env` value unless the ALIAS name is
  used, fixed by using `model_copy(update=...)` for test overrides
  instead). `icab.analysis` (ICAB-CN/CS/CC/CE/CR): necessity/
  sufficiency/composition/efficiency/representation analysis, all
  reusing `icab.reporting.aggregate_records` and scoped ONLY to context
  combinations actually tested -- sufficiency is explicitly labeled
  "Minimum Sufficient Context Among Tested Conditions," never a global
  minimality claim; representation recommendations are per-dimension,
  restricted to architectures actually capable of that dimension (a
  real bug -- an initial version recommended `historian` for a
  Relational dimension it cannot supply -- was found and fixed before
  committing). A deterministic failure taxonomy
  (`icab.analysis.failure_taxonomy`) so a broken architecture is never
  scored as poor agent reasoning. `scripts/icab_v2_cli.py`: list-isa95-
  levels/list-use-cases/list-context-dimensions/list-context-
  combinations/validate-architectures/validate-faults/analyze-*/
  generate-profiles. Real experiments were run (not merely designed) to
  validate the whole pipeline, including one genuine, honestly-reported
  finding: an Area-level task restricted to `knowledge_graph` alone
  failed because the agent could not discover the Area's own canonical
  id from a plain-language reference -- a real representation-gap
  finding, not a bug masked or hidden.

- ICAB v2 context-requirement EXPERIMENTATION layer (a follow-up
  milestone on top of the above, same session boundary): the prior
  milestone built the framework and its analysis suites; this one built
  the missing EXPERIMENTAL-DESIGN machinery to actually choose and run
  context conditions systematically, rather than only analyzing whatever
  happened to already be persisted. New
  `icab.tasks.context_conditions.resolve_condition_architectures` --
  the direction `provided_dimensions()` didn't cover: given a TARGET
  context combination, which real architecture arm realizes it, exactly
  or only as an overshoot, or not at all (`unrealizable`). This
  surfaced a genuine, load-bearing finding purely from the existing
  `CONTEXT_DIMENSION_ARCHITECTURES` mapping: only 13 of the 127 possible
  combinations are exactly realizable by ICAB's six architectures in
  isolation (each architecture supplies more than one dimension; `i3x`
  alone supplies all seven), so most single- and low-cardinality
  combinations can only ever be tested as a real, larger, honestly-
  labeled overshoot arm -- documented in
  `docs/benchmark/specification-v2.md`, not hidden or worked around.
  New `icab.tasks.experiment_design`: five design strategies (single-
  dimension, pairwise, progressive, targeted, ablation) as deterministic
  generators over the existing 127-combination space, plus a sixth
  (replay) resolved from already-persisted records. New
  `icab.benchmark.context_experiment.ContextExperimentRunner` +
  `scripts/run_context_experiment.py`: runs a chosen design strategy
  against one task, resolving and classifying every selected condition
  (`not_applicable`/`unrealizable`/`overshoot`/`exact`) and executing
  only the realizable ones -- "not executed" is never counted as a
  failure. Reuses the EXACT SAME execution path `BenchmarkRunner` uses
  (extracted into `icab.benchmark._execution` as a pure, behavior-
  preserving refactor, verified by the pre-existing `BenchmarkRunner`
  test suite passing unchanged) so every run lands in the same
  `results/` layout the existing `icab.analysis` suites already read.
  New `icab.analysis.discoverability`: a 5-stage pipeline
  (`exists_in_architecture` -> `discovered_identifier` ->
  `retrieved_value` -> `used_as_evidence` -> `grounded_in_conclusion`)
  classifying how far a run's evidence pipeline got, from existing
  `EvaluationReport` fields only -- complementary to (not a replacement
  for) the existing failure taxonomy. New `icab.analysis.matrix`
  (a per-use-case experiment matrix combining necessity/sufficiency/
  failure/discoverability with the actual factor inventory tested) and
  `icab.analysis.reports` (context requirement matrix, architecture x
  context matrix, failure-mode matrix, ISA-95 coverage matrix, candidate
  MSC table) -- five cross-use-case outputs, all thin facades over
  already-existing analyses, reusing a new shared
  `icab.analysis._shared.sample_size_label` (a fixed, documented,
  descriptive n-size label -- `single_observation`/`tentative_small_n`/
  `repeated_empirical_result` -- never a statistical significance
  claim). `scripts/icab_v2_cli.py` gained `resolve-conditions` (a
  dry-run preview needing no infrastructure) and five `matrix-*`
  commands. 62 new unit tests (context-condition resolution, all five
  design strategies, the orchestrator's classification logic via a
  mocked `ExperimentRunner`, discoverability staging, the new matrices)
  + 3 new integration tests against the real stack
  (`tests/integration/test_context_experiment_against_real_stack.py`).
  Validated with REAL LLM runs (NIST RChat) covering one Equipment, one
  Process Cell, and one Area use case, each exercising a baseline/full
  condition, at least one ablation, and (where the task's own
  architectures allowed it) at least two distinct single-architecture
  conditions: `eq-abnormal-behavior-diagnosis` (historian+
  knowledge_graph, 3 runs), `pc-equipment-composition-discovery` (uns+
  opcua, 3 runs, baseline EXACT via `uns` alone), and
  `area-process-cell-composition` (knowledge_graph only -- the SAME
  discoverability failure as the prior milestone's `v2-area-smoke`
  reproduced a second time, both runs landing at the identical
  `discovered_identifier` stage, strengthening rather than merely
  repeating the earlier finding). Across all tep-v2 evidence gathered so
  far (8 prior + 7 new = 15 real records), NO tested context combination
  for either `eq-abnormal-behavior-diagnosis` or
  `pc-equipment-composition-discovery` yet meets its use case's own
  `pass_threshold=1.0` -- reported plainly as an open sufficiency gap in
  `docs/benchmark/specification-v2.md`, not rounded up.

## Not yet filled in

Present as empty placeholders/known gaps, not yet addressed:

- `configs/experiments/`, `configs/prototype/budget.yaml`,
  `configs/prototype/environment.yaml` — versioned experiment definitions
- A benchmark task suite broader than the current 38 tasks/9 scenarios
  (e.g. an i3X-specific task, more seeds per scenario) — see
  `docs/benchmark/tasks.md`'s known limitations
- `LICENSE`, `Makefile`
