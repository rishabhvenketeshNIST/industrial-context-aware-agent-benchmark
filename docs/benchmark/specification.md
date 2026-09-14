# ICAB benchmark task specification (M13-C)

This is the formal reference for the ICAB benchmark **task** model --
what an agent is actually asked to do, evaluated against, and how that
is kept reproducible. For the current task inventory, architecture
coverage, and scenario/task pairing, see
[`docs/benchmark/tasks.md`](tasks.md). For the split strategy, see
[`docs/benchmark/splits.md`](splits.md).

## 1. Scenario/task separation (the core distinction)

Two concepts, not one, per the M13-C direction:

- **`icab.scenarios.models.BenchmarkScenario`** (M5) defines the PROCESS
  CONDITIONS: seed, warmup, fault schedule, duration, sync interval,
  which architectures are ever synced into. Running it via
  `icab.scenarios.runner.ScenarioRunner.prepare()` produces one concrete,
  reproducible simulated plant trajectory.
- **`icab.tasks.benchmark_task.BenchmarkTask`** (M13-C) defines WHAT THE
  AGENT IS ASKED: the objective/question, which architectures IT
  specifically permits (a subset of the scenario's), required evidence,
  required context dimensions, and its OWN evaluation criteria/ground
  truth.

```
BenchmarkScenario  (process state / fault / time-series conditions)
     |
     |  scenario_id (a task always resolves to exactly one scenario)
     v
BenchmarkTask      (the question, required evidence, evaluation criteria)
     |
     |  evaluated via
     v
GroundedInvestigationEvaluator.evaluate_task(...)
```

One scenario can carry SEVERAL tasks (a QA task asking for one value, a
diagnosis task asking for the root cause, etc., all against the exact
same underlying process trajectory) -- this is the intended way to get
task diversity without inflating the scenario count, and is how most of
the initial suite's 38 tasks are built from just 9 scenarios.

`icab.tasks.registry.BenchmarkTaskRegistry` discovers tasks (one YAML
file per scenario under `configs/benchmark/tasks/`, each holding a
`tasks:` list) and validates each against a
`BenchmarkScenarioRegistry`: the referenced scenario must exist, and the
task's `available_architectures` must be a SUBSET of the scenario's own
(never a superset -- a task cannot grant access to an architecture its
scenario never synced into).

## 2. Task types (locked)

Reused directly from `icab.scenarios.models.TaskMode` -- not a second
enum:

| Type | Meaning |
|---|---|
| `qa` | A focused question requiring retrieval/interpretation of industrial context. |
| `investigation` | Open-ended process investigation requiring discovery and combination of relevant context. |
| `diagnosis` | Fault/process diagnosis requiring evidence-based reasoning about abnormal behavior. |

## 3. Difficulty levels (locked)

Reused directly from `icab.scenarios.models.ScenarioDifficulty`:

| Level | Meaning |
|---|---|
| D1 | Simple/local -- answerable from one architecture, no fault. |
| D2 | Context combination -- requires combining at least two sources/dimensions. |
| D3 | Temporal/cross-unit reasoning -- requires a historical trend and/or evidence spanning more than one equipment item. |
| D4 | Non-obvious/context-intensive investigation -- the objective names no specific equipment; the real effect may not be where a naive guess would look. |

## 4. Context dimensions (locked, newly operationalized in M13-C)

`icab.tasks.context_dimensions.ContextDimension` -- C1-C7. Per the
direction not to assign a dimension merely because it sounds
appropriate, each is tied to concrete ICAB tools/relationship kinds, and
`BenchmarkTask` enforces (a NECESSARY, not sufficient, condition) that a
task cannot declare a dimension none of its own `available_architectures`
can supply:

| Dimension | Meaning | Supportable by |
|---|---|---|
| C1 Semantic | What a canonical id/name actually means | `uns`, `i3x` |
| C2 Asset/Hierarchy | Which equipment/area an item belongs to | `uns`, `opcua`, `i3x`, `knowledge_graph` |
| C3 Relational | Structural relationships (`PART_OF`/`MONITORS`/`ACTUATES`) | `knowledge_graph`, `i3x` |
| C4 Temporal | A value at/around a specific past time | `historian`, `i3x` |
| C5 Operational | A live, current value | `historian`, `mqtt`, `opcua`, `i3x` |
| C6 Procedural | How the process is controlled (`CONTROLS`/`HAS_LIMIT`/`ASSOCIATED_WITH`, M13-A) | `knowledge_graph`, `i3x` |
| C7 Historical | A gradual/delayed pattern across a WIDE window, not a single lookup | `historian`, `i3x` |

C4 and C7 use the same underlying tools (`get_historical_values`/
`i3x_get_history`); the distinction is the CLAIM a task's ground truth
makes -- C4 for "what was the value around time T," C7 for "does the
value develop/change across the whole window" (e.g. the stochastic
`idv_08` scenarios, where the effect is only visible by comparing an
early segment to a late one). This is a design choice about which
dimension label a task's ground truth earns, not a second enforcement
mechanism.

Two additional model-level validators keep declared evidence and
declared dimensions from drifting apart:

- `expected_relationships` non-empty implies C3 or C6 must be declared.
- `expected_temporal_evidence=True` implies C4 or C7 must be declared.

## 5. The `BenchmarkTask` schema

```python
class BenchmarkTask(BaseModel):
    task_id: str
    scenario_id: str                                    # FK into BenchmarkScenarioRegistry

    task_type: TaskMode                                  # reused from icab.scenarios
    difficulty: ScenarioDifficulty                        # reused from icab.scenarios

    objective: str                                        # the agent-visible question

    available_architectures: list[str]                    # must subset the scenario's own
    required_context_dimensions: list[ContextDimension]    # must be architecturally supportable

    required_evidence: list[str]                           # canonical ids a grounded answer should cite
    expected_entities: list[str]                           # canonical ids the investigation should touch
    expected_relationships: list[tuple[str, str, str]]      # (subject, predicate, object) triples
    expected_temporal_evidence: bool

    ground_truth: GroundTruth                               # reused from icab.scenarios -- HIDDEN from the agent
    evaluation_criteria: EvaluationCriteria

    provenance: str                                         # where this task's design came from
    version: str
```

`ground_truth` reuses `icab.scenarios.models.GroundTruth` (conclusion,
`root_cause_disturbance`, `affected_measurements`, `affected_equipment`,
`expected_relationships`, `expected_evidence`) exactly -- not a second,
task-specific ground-truth model -- but each task's copy is authored to
match ITS OWN narrower or broader question, not blindly copied from the
underlying scenario's own ground truth (see `docs/benchmark/tasks.md`'s
"current task inventory" for concrete examples of both).

## 6. `EvaluationCriteria`

```python
class EvaluationCriteria(BaseModel):
    binding_scores: list[str]     # which EvaluationReport scores are THIS task's binding pass criteria
    pass_threshold: float = 1.0   # a single shared threshold across all binding_scores
    known_limitations: list[str]  # explicit, per-task acknowledgment of what can't be verified deterministically
```

`binding_scores` selects among `icab.tasks.benchmark_task.KNOWN_SCORE_FIELDS`
-- the six float-valued `EvaluationReport` scores
(`required_evidence_score`, `canonical_id_score`, `relationship_score`,
`conclusion_correctness_score`, `grounding_score`, `completeness_score`):
a small, explicit whitelist (not "any field"), cross-checked directly
against the real `EvaluationReport.model_fields` by
`tests/unit/tasks/test_benchmark_task.py::test_known_score_fields_are_all_real_evaluation_report_fields`
so an evaluator rename is caught by that test, not silently ignored by a
stale task file. This does not introduce a new evaluation mechanism --
it selects which of `GroundedInvestigationEvaluator`'s already-computed,
deterministic scores matter for a GIVEN task (a D1 QA task has no
relationships to confirm; a D4 diagnosis task's
`conclusion_correctness_score` is central).

## 7. Ground-truth separation

`ground_truth` is never read by anything agent-visible:

- `icab.agent.llm.agent.LLMInvestigationAgent` and
  `icab.experiments.ExperimentRunner` never read `ground_truth`/`faults`
  at all (verified structurally: `grep -rl ground_truth src/` finds only
  `icab.scenarios.models` and `icab.evaluation.grounded`, the latter only
  reading it AFTER an agent has already submitted its conclusion).
- `BenchmarkScenario` has an ENFORCED validator (M13-B) rejecting a
  scenario whose `objective` mentions its own fault's disturbance id.
- Real tasks are checked directly, not just trusted:
  `tests/unit/tasks/test_task_ground_truth_isolation.py` parametrizes
  over every real, checked-in task file and asserts no task's `objective`
  mentions its own `ground_truth.root_cause_disturbance`, and separately
  runs a real `LLMInvestigationAgent` and inspects the actual messages
  sent to the (mocked, no-network) LLM.
- MQTT/UNS/OPC UA/i3X/KG never carry fault information at all -- the M13-A
  KG projection and every other architecture's projection are built
  entirely from the STATIC process-context registry
  (`icab.tep.measurements`), with zero dependency on which fault (if any)
  is currently active; there is no code path for a fault id to reach any
  of them.

## 8. Architecture requirements

A task's `available_architectures` is the actual enforcement mechanism
(via `icab.agent.llm.tools.tools_for_architectures`, unchanged from
M6/M10) -- never a superset of what its scenario ever synced into
(enforced at registry load time, not just documented). Per the M13-C
direction ("do not make an architecture required unless the task
genuinely cannot be completed from another available source"), several
tasks are deliberately narrower than their scenario's own full
architecture set -- e.g. `d2ctx-qa-monitors-relationship-confirmed`
grants ONLY `knowledge_graph` (not `historian`, which the scenario also
has) because the question is answerable from the KG alone; see
`docs/benchmark/tasks.md` for the full per-task table.

## 9. Reproducibility and versioning

Every task is reproducible from: `scenario_id` (-> the scenario's own
`seed`/`warmup_hours`/`faults`/`duration_hours`, all fixed in YAML),
`task_id`, and the task's own `version` string. `generation_id`
(M9/M13-B, unchanged) still scopes relationship confirmation to the
specific scenario preparation that produced it --
`GroundedInvestigationEvaluator.evaluate_task(task, result, trace,
generation_id=...)` threads it through identically to `evaluate`.
`EvaluationReport` gained an additive `task_id` field so a persisted
evaluation is traceable back to exactly which task (not just which
scenario) produced it.

No task content is generated by uncontrolled randomness -- every
task's objective/ground truth is hand-authored against a specific,
already-empirically-characterized scenario (see M13-B's fault catalog),
not sampled or templated.

## 10. One-command orchestration (M13-D)

`scripts/run_benchmark.py` / `icab.benchmark` is the ONE-COMMAND
execution layer over everything above -- it introduces no new scientific
methodology, evaluation logic, or persistence format. It orchestrates,
in order: benchmark configuration -> task selection (this suite's real
registered task inventory, never hard-coded) -> scenario selection ->
deterministic TEP initialization -> fault injection -> context
synchronization -> agent execution -> trace collection -> grounded
evaluation -> persistence -> aggregation -> reporting.

```
uv run python scripts/run_benchmark.py \
    --suite tep-v1 \
    --agent llm \
    --architectures all \
    --seeds 1,2,3,4,5
```

### 10.1 CLI flags

| Flag | Meaning | Default |
|---|---|---|
| `--suite` | Registered suite name (`icab.benchmark.config.SUITES`) | required |
| `--split` | `development`/`validation`/`test` -- restricts to that split's scenarios | unset = every split |
| `--task` | One explicit `task_id` (overrides `--split`/`--scenario`) | unset |
| `--scenario` | Restrict to tasks against one `scenario_id` | unset |
| `--agent` | `baseline` (`ScenarioAwareBaselineAgent`) or `llm` (`LLMInvestigationAgent`); a legacy `DeterministicAgentKind` value is an explicit, separate opt-in | `llm` |
| `--architectures` | `all`, a named `icab.experiments.architecture_combinations` key, or a raw comma-separated list -- see 10.2 | `all` |
| `--seeds` | Comma-separated seed overrides, e.g. `1,2,3,4,5` | unset = each scenario's own built-in seed, once |
| `--repetitions` | Repeat each (task, arm, seed) this many times | `1` |
| `--llm-model`, `--temperature` | LLM generation config | provider default / `0.0` |
| `--max-steps`, `--max-tool-calls`, `--max-context-tokens`, `--max-wall-time` | Agent budgets (all optional; unset = unbounded, matching pre-M13-D behavior) | unset |
| `--name` | Benchmark/experiment id | auto-generated |
| `--gateway-url` | Agent Gateway base URL (a separate `uv run uvicorn icab.gateway.app:app` process) | `http://localhost:8000` |
| `--results-root` | Where `results/` lives | `results` |

### 10.2 Architecture-arm resolution (`--architectures`)

Resolved per TASK (never against the full universe of architectures
ICAB happens to know how to talk to -- a task must actually declare/
support an architecture, e.g. i3X is not "available" merely because the
private i3X service exists):

- `all` expands to one single-architecture arm per architecture the task
  itself declares in its own `available_architectures` -- the standard
  architecture-as-independent-treatment sweep this benchmark compares.
- a named `icab.experiments.architecture_combinations` key expands to one
  arm using that combination's architectures, ONLY if every one of them
  is in the task's own `available_architectures`.
- anything else is a raw comma-separated architecture list -- one arm
  using exactly those architectures together, again only if it's a
  subset of the task's own `available_architectures`.

Any `(task, architecture spec)` pair that isn't a subset is SKIPPED (not
silently narrowed, not failed) -- counted in the final `skipped_runs`
tally and named in the printed `skipped_reasons`.

### 10.3 Execution model

Strictly sequential -- no Kubernetes, distributed workers, Kafka, or
Celery. Task selection expands to (task x architecture arm x seed x
repetition) runs; `icab.benchmark.runner.BenchmarkRunner._run_one`
executes exactly one such run via
`ExperimentRunner.run_task(task, config, scenario=..., ...)`, which:

1. prepares the task's own scenario fresh (`ScenarioRunner.prepare` --
   real simulator reset/warmup/fault-schedule activation/context sync,
   producing a fresh `generation_id` for this run),
2. builds the configured agent (`ScenarioAwareBaselineAgent` or
   `LLMInvestigationAgent`, restricted to the resolved architecture arm's
   tools),
3. runs it against the task's own `objective` (never the broader
   scenario objective) through the real Agent Gateway HTTP API,
4. evaluates via `GroundedInvestigationEvaluator.evaluate_task` (the
   task's own, possibly narrower, ground truth),
5. builds a full `ExperimentRecord` (see 10.4) and persists it.

A `--seeds` override is applied as
`scenario.model_copy(update={"seed": seed})` -- the ONE field varied,
never re-authoring the scenario. Everything else (task objective,
budgets, LLM model/temperature, fault schedule) is held constant across
architecture arms; architecture is the sole independent treatment.

Any exception anywhere in this sequence (scenario preparation, agent
execution, evaluation) is caught at the orchestration level, turned into
a persisted `status=FAILED` `ExperimentRecord` with the exception message
in `error`, and does NOT stop the remaining runs -- no evaluation is ever
fabricated for a failed run.

### 10.4 Persistence

Every run -- successful or failed -- is persisted via the existing
`ExperimentResultStore` (`results/{raw,traces,evaluations}/`, unchanged
M9 layout). `ExperimentConfig`/`ExperimentRecord` gained these additive
M13-D fields (all `None` for any pre-M13-D, scenario-only run):

- `ExperimentConfig`: `task_id`, `task_type`, `suite`, `split`,
  `repetition`, `max_tool_calls`, `max_context_tokens`,
  `max_wall_time_seconds`.
- `ExperimentRecord`: `benchmark_version` (`icab.benchmark.config
  .BENCHMARK_SUITE_VERSION`), `git_commit` (best-effort `git rev-parse
  HEAD`, `None` outside a git repo), `fault_id` (the run's scenario's
  own scheduled disturbance, if any), `scenario_version`, `task_version`,
  `configuration_hash` (sha256 of a canonical JSON serialization of the
  run's `ExperimentConfig` -- `icab.experiments.compute_configuration_hash`).

### 10.5 Aggregation and reporting

After every run in the invocation completes, `BenchmarkRunner.run()`
automatically calls the EXISTING M9/M12 infrastructure -- no new
aggregation or reporting mechanism:

- `ExperimentResultStore.write_aggregate(benchmark_id, records,
  allow_heterogeneous_controls=True)` -- heterogeneous controls are
  explicitly allowed here because a full benchmark invocation
  legitimately spans many different scenarios/tasks (that is the point
  of running a suite, not a single controlled A/B comparison); the
  written JSON's own `controls_consistent`/`control_variance` fields
  keep this fully auditable rather than silently hidden.
- `icab.reporting.aggregate_records(records, group_by=("task_type",
  "difficulty", "architecture"), allow_heterogeneous_controls=True)` +
  `render_aggregation_markdown` -- the same M12 report format.
- `icab.reporting.plotting.plot_metric_by_group` for
  `conclusion_correctness_score` and `tool_call_count`, when present.

`icab.reporting.aggregation.DIMENSION_RESOLVERS` gained `task_id`,
`task_type`, `suite`, `split`, `repetition` entries (read directly off
`ExperimentConfig`, no task-registry lookup at aggregation time).

### 10.6 Failure handling and the final summary

The CLI's final printed summary always reports: `benchmark_id`, `suite`,
`split`, task/scenario/architecture/agent/seed/repetition counts, and
`total_runs`/`successful_runs`/`failed_runs`/`skipped_runs`, plus the
aggregate/report output paths. A non-zero exit code is returned if any
run failed. See `docs/benchmark/tasks.md` for the current task inventory
and `docs/benchmark/splits.md` for split semantics, both unchanged by
M13-D.

Before any run starts, `scripts/run_benchmark.py` performs one cheap
`GET /health` preflight check against `--gateway-url`
(`_check_gateway_reachable`) and exits immediately with an actionable
message if it fails, rather than letting every expanded run
independently discover an unreachable gateway only AFTER a full,
potentially expensive scenario preparation. This is a CLI-level
fail-fast convenience only -- `BenchmarkRunner`/`ExperimentRunner`
themselves are unchanged, and a per-run gateway failure that happens
mid-invocation (e.g. the gateway crashes partway through a long run)
still produces its own persisted FAILED record exactly as before.

### 10.7 The researcher-facing question/answer report

In addition to the M12-style aggregate report (10.5),
`BenchmarkRunner.run()` also builds a per-run, researcher-only
"question/answer" report (`icab.reporting.qa_report`) -- one section per
persisted run showing exactly what happened on that benchmark question,
followed by an overall summary:

- Task ID, scenario ID, difficulty, task type, architecture, seed, fault
  ID (if any), status.
- The exact `objective` presented to the agent.
- The agent's final answer, **verbatim** -- never paraphrased,
  truncated, or re-summarized.
- The **correct answer**, rendered as readable prose from the task's (or,
  for a scenario-only run, the scenario's) own `GroundTruth` -- never a
  raw Pydantic/Python dump. Only fields the ground truth actually
  contains are shown (e.g. a relationship triple renders as `subject
  --[predicate]--> object`); if neither a task nor a scenario could be
  resolved for a run, the report says so explicitly
  (`CorrectAnswer.limitation`) rather than fabricating an answer.
- Required evidence (from the task/scenario) vs. evidence the agent
  actually provided (`InvestigationResult.evidence`).
- That run's own metrics, read directly off the existing
  `EvaluationReport`/`ExperimentRecord` -- `required_evidence_score`,
  `canonical_id_score`, `relationship_score`,
  `conclusion_correctness_score`, `grounding_score`,
  `completeness_score`, `tool_call_count`, `context_acquired`,
  `context_consumed`, `latency_ms`, `total_tokens` -- nothing
  recomputed.
- A FAILED run still gets its own section (status/error only -- no
  fabricated metrics or answer).

At the bottom: total/successful/failed/skipped counts, plus
architecture/difficulty/task-type breakdowns -- each one an
`icab.reporting.aggregate_records` call (the same M12 mechanism 10.5
uses), not a new statistics implementation.

Written to `results/reports/<benchmark_id>-qa.json` (machine-readable)
and `results/reports/<benchmark_id>-qa.md` (the rendered Markdown), via
the existing `ReportStore` (`write_qa_report`/`write_markdown`) -- no new
results directory.

**This is a researcher-only artifact.** Building it makes no
agent/gateway/LLM call -- it reads only already-persisted
`ExperimentRecord`s (whose `result`/`evidence`/trace were produced by an
agent that never had access to `ground_truth` in the first place; see
§10.3) -- so it cannot leak ground truth back to an agent. Verified
directly: `tests/unit/reporting/test_qa_report.py
::TestGroundTruthNeverReachesTheAgent` captures the actual messages sent
to a (mocked) LLM during a real `LLMInvestigationAgent.run()` call and
asserts the task's ground truth is absent from them, then builds this
same report from that run's own result and asserts the ground truth
IS present in the rendered report -- proving the report legitimately
knows more than the agent ever did, not merely that both happen to lack
it. `tests/integration/test_benchmark_runner_against_real_stack.py`
repeats the same check against a REAL run's REAL persisted trace.
