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

- First real empirical context-requirement CAMPAIGN (a follow-up on the
  prior two ICAB v2 milestones, same broad direction): those milestones
  built the machinery; this one used it to actually produce, analyze,
  and write up a controlled empirical study. New
  `docs/research/context-requirement-protocol.md` (the fixed protocol:
  what varies/is held constant, the explicit `pass_threshold=1.0`
  success predicate, the partial-order MSC rule, the traceability
  requirement) and `docs/research/context-requirement-campaign-1.md`
  (the first campaign's full write-up: cohort selection rationale, Phase
  4 realizable-maximum-vs-candidate_context comparison for all 5 use
  cases, Tables A-E, and an explicit observed/tentative/unsupported
  claim audit). Ran 18 new real LLM runs (NIST RChat) across a 5-use-case
  cohort (`eq-abnormal-behavior-diagnosis`, `eq-value-and-relationship-combination`,
  `pc-equipment-composition-discovery`, `pc-cross-unit-diagnosis` --
  brand new, zero prior data -- and `area-process-cell-composition`),
  bringing the cohort to 33 real runs total (18 new + 15 carried over).
  **Fixed a real, load-bearing gap in `icab.analysis.sufficiency`**
  found while trying to report Table B honestly: the existing MSC
  determination used `min()` to pick ONE smallest-cardinality sufficient
  condition, silently discarding genuinely incomparable ties (context
  combinations form a partial order by dimension subset, not a total
  order) -- fixed by adding `SufficiencyReport
  .candidate_minimum_sufficient_contexts` (every minimal, non-dominated
  sufficient condition) computed via a proper subset-domination check,
  keeping the old singular field only as a backward-compatible
  tie-break; also added `run_ids` traceability to every tested condition
  so a matrix cell or candidate-MSC row can always be traced back to its
  exact `results/raw/<run_id>.json`. Propagated through
  `icab.analysis.matrix`/`.reports`. 8 new tests
  (`TestPartialOrderMultipleCandidates`,
  `TestTraceabilityFromConditionToExperimentId`, plus matrix/report
  field-propagation checks).
  **Real findings** (not merely designed, cited by `run_id` in the
  campaign report): only ONE (use case, condition) pair across the whole
  33-run cohort met its `pass_threshold=1.0` --
  `eq-value-and-relationship-combination` at the full realizable
  `C2+C3+C4+C5+C6+C7` (n=2, both seeds); every cohort task's
  architecture-realizable maximum context exceeded its own use case's
  declared `candidate_context` (5/5 use cases, extending the prior
  milestone's 13/127-realizable finding); combining `uns`+`opcua` for
  `pc-equipment-composition-discovery` produced a WORSE
  `canonical_id_score` (0.0, both seeds) than either architecture alone
  (0.31/0.96 pooled) -- a concrete "more context is not automatically
  better" case; the Area `knowledge_graph`-only discoverability failure
  reproduced a THIRD time (now across 3 runs, 2 distinct seeds), always
  stalling at the identical `discovered_identifier` stage; both
  diagnosis-type use cases reached `required_evidence_score`/
  `relationship_score`/`grounding_score`=1.0 at full context while
  `conclusion_correctness_score` stayed at 0.25 in every case -- traced
  to a genuine, pre-existing evaluator heuristic limitation
  (`root_cause_identified` requires exact-form matching), not
  necessarily poor agent reasoning, and reported with that caveat rather
  than overclaimed; full-context conditions were also frequently MORE
  efficient (fewer tool calls, lower latency) than the narrower
  conditions that failed to retrieve evidence at all, directly
  contradicting a naive "more context costs more" assumption.
  740 passed + 3 skipped (up from 732/3).

- ICAB v3: six ISA-95-level benchmarks, question banks, Question ->
  Instance -> Repetition (a major methodological restructuring, on top
  of the unchanged ICAB v2/campaign-1 machinery -- see
  `docs/benchmark/specification-v3.md`). New `icab.benchmark.levels`:
  `ISA95BenchmarkDefinition` x6 (`icab-{enterprise,site,area,work-center,
  process-cell,equipment}-v1`), each with its own `benchmark_id`,
  `question_bank_dir`, `results_root`, and an honest
  `data_supported`/`executable` flag -- Enterprise/Site/Work Center are
  `executable=False` (framework-ready, genuinely no TEP data), Area/
  Process Cell/Equipment are `executable=True`.
  New `icab.questions` package: `Question` (the semantic task, kept
  explicitly separate from the concrete, scenario-specific
  `BenchmarkTask` that realizes it -- `Question.realizations:
  dict[scenario_id, task_id]`, never a second evaluation path),
  `QuestionCategory` (12-value reusable cross-level taxonomy),
  `QuestionDifficulty` (basic/intermediate/advanced, ORTHOGONAL to
  `ScenarioDifficulty` D1-D4), `DifficultyFactors` (n_sources/
  relationship_depth/temporal/cross_source/evidence_count -- WHY a
  difficulty was assigned, not a hidden formula), `QuestionInstance`
  (question + scenario + canonical sorted architecture arm + agent
  config, with a deterministic `instance_id`), `RepetitionMode`
  (`exact` vs `controlled_variation`), `QuestionBankRegistry`
  (cross-validates against both `IndustrialUseCaseRegistry` and
  `BenchmarkTaskRegistry`, mirroring the existing registry discipline).
  `hypothesized_required_context` (design-time) is explicitly never
  conflated with empirically-demonstrated necessity (a derived
  `icab.analysis.necessity` output, not a model field).
  Question banks generated (`scripts/generate_question_banks.py`) FROM
  the real, already-validated tep-v2 task inventory (a small,
  documented, deterministic heuristic assigns difficulty/answer-type/
  tags over each task's own real fields) plus 2 new, hand-authored
  tasks (`configs/benchmark/tasks_v2/process_cell_new.yaml`, one new
  task appended to `area.yaml`) using real, independently-verified
  `TEPAdapter.get_real_hierarchy_relationships()` PART_OF data (caught,
  mid-authoring, that the LEGACY `get_hierarchy_relationships()` only
  covers 2/7 equipment items -- the REAL method covers all 7; used the
  real one). Final counts, reported honestly rather than padded to the
  requested ~30/~30/~15 targets: Equipment 31 (target met via reuse),
  Process Cell 8, Area 3 (targets NOT met -- TEP's real scenario/entity
  diversity at these levels genuinely limits how many distinct real
  questions can be authored without duplicating content).
  `ExperimentConfig` gained `question_id`/`question_instance_id`/
  `repetition_mode` (additive; `repetition` itself, from M13-D, IS the
  repetition id -- no new field needed). New
  `icab.benchmark.question_runner.QuestionBenchmarkRunner` +
  `scripts/run_question_benchmark.py`: selects/resolves/executes a
  filtered slice of one level's question bank (question ids/use cases/
  tags/context combinations/scenarios), reusing the SAME
  `icab.benchmark._execution` path every other ICAB v2 runner uses.
  **A hard isolation guard** (`IsaLevelMismatchError`, checked twice --
  right after building the config, and again on the record execution
  actually returns) refuses to persist a result whose own
  `config.isa95_level` disagrees with the benchmark it's about to be
  saved under. New `icab.benchmark.manifest.BenchmarkManifest` (one
  `manifest.json` per level, every field computed FROM already-
  persisted records, never hand-maintained).
  New `scripts/reset_active_results.py`: archives (never deletes) the
  old flat `results/{raw,traces,...}/` content to
  `results/_archive/<timestamp>/`, then creates the new
  `results/{enterprise,site,area,work_center,process_cell,equipment}/`
  skeleton; defaults to a dry run, requires `--force` to execute, and
  hard-refuses (`SystemExit`) to ever touch `src/`/`tests/`/`docs/`/
  `configs/`/`results/architecture_health.json`.
  New `icab.analysis.question_stats`: Question -> Use Case -> ISA-95
  Benchmark aggregation with BOTH macro-average (mean of each
  question's own mean -- a hard question can't be drowned out by an
  easy, heavily-repeated one) and micro-average (pooled,
  repetition-weighted) reported side by side; every question's own
  stats preserved even after rolling up. `icab.analysis.necessity`/
  `.sufficiency` gained an optional `question_id` parameter (question-
  level MSC/necessity, same unchanged logic, same conservative "among
  tested conditions" framing at every scope).
  **Two real bugs found and fixed via this milestone's OWN tests, before
  ever touching the real `results/` tree for real work:** (1)
  `QuestionBenchmarkRunner` called `write_manifest(definition, records)`
  without an explicit `root=`, so it silently defaulted to
  `definition.results_root` (the REAL production path) regardless of
  which `ExperimentResultStore` a runner was actually constructed
  against -- caught when a UNIT TEST using `tmp_path` left a real
  `manifest.json` in the actual `results/equipment/` directory; fixed by
  always passing `root=self.experiment_store.root` explicitly, with a
  regression test. (2) `scripts/reset_active_results.py`'s `execute()`
  built its new level skeleton from each `ISA95BenchmarkDefinition`'s
  own (hard-coded, production-default) `results_root` field instead of
  the `results_root` argument actually passed in -- meaning a
  parameterized call (e.g. from a test, or a future alternate location)
  would silently still write to the real `results/` tree; caught by the
  script's OWN test suite (`tests/unit/test_reset_active_results.py`)
  failing against a `tmp_path`; fixed to build every skeleton path from
  the passed-in root. A microsecond-resolution archive-timestamp bug
  (second-resolution collided across rapid successive calls) was also
  found and fixed via the same test file.
  **Real validation campaign** (38 new real LLM runs via NIST RChat,
  after archiving all prior mixed results via `--force`): Equipment (10
  questions + 1 extra context-condition comparison, 22 runs), Process
  Cell (5 questions, 10 runs), Area (all 3 available questions, 6 runs)
  -- every run at 2 EXACT repetitions (same instance, same seed, only
  LLM stochasticity varying). Zero orchestration-level failures (38/38
  completed); zero level-contamination (verified programmatically: 0/38
  records mismatched their own `results/<level>/` root). Real,
  cross-level finding: `pc-equipment-composition-discovery`'s two
  realizations -- the SAME semantic question -- succeed 2/2 via `uns`
  browsing but fail 0/2 via `knowledge_graph` (both at the
  `discovered_identifier` discoverability stage), the SAME pattern as
  the Area level's now-6/6-reproduced `knowledge_graph`-only
  discoverability failure -- suggesting this is a `knowledge_graph`-
  specific discovery weakness, not an Area-specific one. One Equipment
  diagnosis question showed genuine exact-repetition stochasticity (2/4
  successful across pooled conditions, stdev=0.58) -- real evidence
  repetition is doing its intended job, not a design assumption.
  792 passed + 3 skipped (up from 740/3) before the campaign; `tep-v1`
  verified untouched throughout (checked via `git diff` against its own
  directories before every commit in this milestone).

- ICAB v3 50-question milestone: `6 levels x 50 unique questions x 10
  repetitions = 3,000 executions` (see docs/benchmark/specification-v3.md).
  The core, hardest part of this milestone: TEP genuinely has no
  Enterprise/Site/Work-Center data and only one real Site/Area entity
  each -- reaching 50 REAL, grounded questions per level required
  building an entirely new CONTROLLED (never fabricated-and-hidden)
  benchmark context layer. New `icab.benchmark_context` package: a
  deterministic, versioned (`BENCHMARK_CONTEXT_VERSION`), clearly
  source-tagged (`source="icab_benchmark_context"`, sharply distinct
  from real TEP's `source="tep"`) synthetic Enterprise (1) -> Site (the
  real `urn:icab:site:tep` + 2 synthetic) -> Area (the real
  `urn:icab:area:reaction` + 2 synthetic) -> Work Center (3 synthetic,
  ADDITIVE siblings of the real Process Cell, deliberately never
  re-parenting it) hierarchy, plus 88 deterministic KPI measurements
  (`random.Random` seeded per entity/kpi/version -- same inputs always
  produce the same value). Seeded into the REAL historian/knowledge_graph
  via the SAME `EnvironmentLoader` real TEP data already uses
  (`scripts/seed_benchmark_context.py`) -- verified directly against the
  live databases that the real Site/Area's own existing relationships
  were untouched (only additive new edges appeared).
  300 questions generated across three scripts, all cross-validated
  (`BenchmarkTaskRegistry`/`IndustrialUseCaseRegistry`/
  `QuestionBankRegistry`, zero duplicates, zero level mismatches):
  `scripts/generate_synthetic_level_tasks.py` (Enterprise/Site/
  Work-Center + Area top-up, KPI-value/membership/comparison questions
  against the new controlled layer), `scripts/generate_extra_real_tasks.py`
  (19 new real Equipment questions over previously-unused real TEP
  measurements + 42 new real Process-Cell MONITORS/PART_OF relationship
  questions -- zero new facts, only more questions about already-real
  data), `scripts/generate_synthetic_level_usecases.py` (11 new
  `IndustrialUseCase`s derived directly from the generated tasks, so
  required_context always agrees with what the tasks actually declare).
  New `icab.questions.validation` (Section 25's formal per-question
  checklist -- grounded evidence, correct level, deterministically
  evaluable, real compatible scenario, documented context hypothesis, no
  duplicates) and `icab.benchmark.completeness` (the 3,000-execution
  invariant checker -- flags fewer than 50 questions, duplicate ids,
  isa95_level contamination, missing trace/experiment id, duplicate
  repetitions, and any question short of 10 completed repetitions; NEVER
  reports complete unless every check on every one of the six levels
  genuinely passes). New `scripts/run_level_benchmark.py` (`--level`/
  `--all`/`--repetitions`/`--check-only`, refuses to start a level's
  standard campaign unless its bank has exactly 50 questions).
  Extended `icab.benchmark.levels.ISA95BenchmarkDefinition` with a new
  `data_provenance` field (`real_tep`/`controlled_synthetic`/`mixed`,
  explicit per level) and flipped Enterprise/Site/Work-Center to
  `executable=True` -- updated `icab.usecases.registry
  .ISA95_LEVEL_COVERAGE_NOTES` and 4 pre-existing tests that had
  asserted "0 use cases forever" at those levels (now genuinely false
  and correctly updated, not weakened).
  **Two real bugs found while extending `scripts/reset_active_results.py`
  to be reusable across MULTIPLE campaign milestones (not just the
  original flat-to-level migration), caught by ITS OWN test suite before
  ever touching real data**: (1) it only detected the OLD flat
  `results/{raw,...}` layout, never the CURRENT level-scoped
  `results/<level>/{raw,...}` content -- so re-running it before this
  milestone's campaign would have left the PRIOR milestone's 38 real
  records sitting in the "clean" tree, contaminating the new one; fixed
  by also scanning each level's own subdirectories/manifest.json for
  non-`.gitkeep` content. (2) the archive destination used only each
  archived path's bare name (`archive_dir / source.name`) -- since
  multiple levels all have a `raw/`/`traces/`/etc. subdirectory with the
  IDENTICAL name, archiving more than one level in the same run would
  have silently overwritten one level's archived data with another's;
  fixed by preserving the full path relative to `results_root`.
  **Real validation, following the mandatory Step A/B/C/D sequence**:
  Step A -- `validate_question_bank` ran against all 300 questions,
  300/300 passed. Step B -- a real, live sample (NIST RChat, live
  Docker infra) of 2 questions x 2 repetitions was run against EVERY ONE
  of the six levels (24 executions total, `--name v3-stepb`): 24/24
  completed, 0 orchestration failures -- the controlled benchmark
  context layer works end to end, not merely "loads." Step C -- verified
  programmatically: 0/24 records mismatched their own `results/<level>/`
  root. Step D (the full 3,000-execution campaign) was explicitly NOT
  attempted this milestone (infeasible within one session's real-LLM
  wall-clock budget) -- `scripts/run_level_benchmark.py --all
  --repetitions 10` is fully built and tested, and running it to
  completion is named as remaining work, never claimed done.
  **A genuine, honestly-reported Step-B finding**: 0 of the 20 real runs
  against controlled-context or extra-real-relationship questions
  (Enterprise/Site/Area/Work-Center/Process-Cell) reached
  `required_evidence_score=1.0` -- the agent could not resolve a
  plain-language entity reference (e.g. "Port Arthur Site") to its real
  canonical id via `knowledge_graph`/`historian` alone, extending the
  SAME discoverability weakness already documented for the real
  Area+`knowledge_graph` case in the prior context-requirement-campaign
  milestone -- while Equipment's historian-only real measurement
  questions succeeded 4/4 in the same Step-B sample. Left as an open,
  documented lead (not root-caused this milestone) rather than adjusted
  or hidden.
  Before beginning the new campaign, `scripts/reset_active_results.py
  --force` archived the prior milestone's 38 real records
  (results/_archive/20260914T193527.124570Z/) -- verified intact,
  nothing lost -- and the new campaign started from a genuinely clean,
  contamination-free `results/<level>/` tree (verified: 0/3000
  executions before Step B, 24/3000 after).
  823 passed + 3 skipped (up from 793/3, full suite including real
  integration tests against live infrastructure); `tep-v1` verified
  untouched via `git diff` before committing.

## Not yet filled in

Present as empty placeholders/known gaps, not yet addressed:

- `configs/experiments/`, `configs/prototype/budget.yaml`,
  `configs/prototype/environment.yaml` — versioned experiment definitions
- A benchmark task suite broader than the current 38 tasks/9 scenarios
  (e.g. an i3X-specific task, more seeds per scenario) — see
  `docs/benchmark/tasks.md`'s known limitations
- `LICENSE`, `Makefile`
