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
