# ICAB v2 specification

ICAB v2 answers a different, broader question than v1's fault-diagnosis
focus:

> What industrial context is required for AI-enabled industrial use
> cases at different levels of the ISA-95 hierarchy, how should that
> context be represented and exposed, how much context is sufficient,
> and which industrial information architectures can provide it
> reliably?

Fault detection/diagnosis (`tep-v1`, unchanged, still fully supported)
is ONE use-case family this now covers, concentrated at the Process Cell
and Equipment levels -- not the organizing principle of v2.

`tep-v1` is completely unmodified by v2 -- see
[`docs/benchmark/specification.md`](specification.md) for its own
(unchanged) spec. v2 reuses v1's scenarios, splits, fault catalog, and
evaluator as-is; it adds a parallel `tep-v2` task suite plus a new
`icab.usecases`/`icab.tasks.context_combinations`/`icab.analysis`/
`icab.architecture_health` layer on top.

## The experimental chain

```
ISA-95 LEVEL
      |
INDUSTRIAL USE CASE
      |
SCENARIO
      |
optional FAULT/DISTURBANCE
      |
CONTEXT REQUIREMENTS  (required_context -- what the use case NEEDS)
      |
CONTEXT REPRESENTATION (how each architecture exposes it)
      |
CONTEXT AVAILABILITY / SUFFICIENCY (provided vs. required vs. used)
      |
INFORMATION ARCHITECTURE (which architecture arm actually ran)
      |
AI AGENT (baseline or LLM -- unchanged from v1)
      |
EVIDENCE + OUTCOME (the existing deterministic evaluator, unchanged)
      |
CONTEXT DESIGN REQUIREMENT (icab.analysis's output)
```

Faults remain OPTIONAL scenario stimuli (M13-B, unchanged) -- most v2
use cases have no fault at all (equipment identification, current-value
retrieval, hierarchy facts); the diagnosis-typed use cases reuse the
same empirically-verified faults v1 already established
(`idv_01/02/06/08/17/20/24` -- see
[`docs/architecture/tep-fault-injection.md`](../architecture/tep-fault-injection.md)).
No new fault was added or invented for v2.

## ISA-95 levels (`icab.tasks.isa95.ISA95Level`)

Reuses the SAME six levels `icab.cim.EntityType` already models
(`Enterprise`/`Site`/`Area`/`WorkCenter`/`ProcessCell`/`Equipment`) as a
task/use-case classification concept. Coverage is reported honestly, not
filled to look complete -- TEP is a single-site, single-process-cell,
seven-equipment-item simulation:

| Level | Use cases | Why |
|---|---|---|
| `enterprise` | 0 | No multi-site/multi-enterprise data exists in TEP at all. |
| `site` | 0 | Exactly one real Site entity, with nothing to compare it against. |
| `area` | 2 | Exactly one real Area entity -- real, verified hierarchy facts (not scenario-varying). |
| `work_center` | 0 | `icab.tep.adapter.TEPAdapter` never populates a WorkCenter entity. |
| `process_cell` | 5 | Well supported -- the existing D4 "plant-wide"/"unknown" task suite. |
| `equipment` | 7 | Best supported -- most of the existing tep-v1 task suite. |

A 0-use-case level is a stated limitation (`icab.usecases.registry
.ISA95_LEVEL_COVERAGE_NOTES`), never silently absent -- `uv run python
scripts/icab_v2_cli.py list-isa95-levels` prints these notes directly.

## Industrial use cases (`icab.usecases.IndustrialUseCase`)

```python
class IndustrialUseCase(BaseModel):
    use_case_id: str
    name: str
    description: str
    isa95_level: ISA95Level
    task_type: TaskMode                          # reused from icab.scenarios
    required_context: list[ContextDimension]      # what the use case NEEDS
    candidate_context: list[ContextDimension]      # required_context plus what's worth testing
    success_criteria: EvaluationCriteria           # reused from icab.tasks.benchmark_task
    applicable_scenarios: list[str]                # real BenchmarkScenario ids
    difficulty: ScenarioDifficulty                 # reused from icab.scenarios
    provenance: str
    version: str
```

14 real use cases are registered under `configs/usecases/` (`area.yaml`,
`process_cell.yaml`, `equipment.yaml`), cross-validated against the real
`BenchmarkScenarioRegistry` (every `applicable_scenarios` entry must be a
real, loadable scenario) the same way `BenchmarkTaskRegistry` already
cross-validates `BenchmarkTask.scenario_id`.

`uv run python scripts/icab_v2_cli.py list-use-cases [--level <level>]`.

## The seven context dimensions

Unchanged from M13-C -- `icab.tasks.context_dimensions.ContextDimension`
(C1 Semantic, C2 Asset/Hierarchy, C3 Relational, C4 Temporal, C5
Operational, C6 Procedural, C7 Historical). Not renamed, not
re-implemented.

## Context combinations (`icab.tasks.context_combinations`)

The deterministic, complete, GENERATED (never hard-coded) space of every
non-empty subset of the seven dimensions -- exactly `2**7 - 1 = 127`,
each with a stable id (`"C2+C3"`), cardinality, canonical ordering, and
human-readable name.

```
uv run python scripts/icab_v2_cli.py list-context-combinations [--cardinality N]
```

Not every combination is meaningful at every ISA-95 level or use case --
`icab.analysis` only ever reports on combinations ACTUALLY TESTED (see
below), never fabricating a result for one that wasn't.

## required / available / provided / acquired / used context

Five distinct concepts, tracked separately, never conflated:

| Concept | Where it lives |
|---|---|
| **required** | `BenchmarkTask.required_context_dimensions` (unchanged, M13-C) -- what the task's ground truth NEEDS |
| **available** | `icab.tasks.context_dimensions.CONTEXT_DIMENSION_ARCHITECTURES` -- which architectures COULD supply a dimension, in principle |
| **provided** | `ExperimentConfig.context_combination_id` -- what the ACTUAL architecture arm given to the agent this run supplies (`icab.tasks.context_dimensions.provided_dimensions(architectures)`) -- this is what VARIES as `--architectures` varies, and is the grouping key `icab.analysis` uses |
| **acquired** | `EvaluationReport.context_acquired` (unchanged, M8/M13-D) -- what the trace shows the agent actually learned about |
| **used** | `EvaluationReport.grounding_score`/`required_evidence_score`/`InvestigationResult.evidence` (unchanged) -- what the agent's own conclusion actually cites |

`context_combination_id` is deliberately the PROVIDED combination, not
the task's fixed required combination: running the exact same task with
progressively fewer architectures changes what was provided, which is
the variable a necessity/sufficiency experiment needs to hold as its
independent condition.

## The `tep-v2` suite

Registered in `icab.benchmark.config.SUITES["tep-v2"]`, reusing tep-v1's
own `configs/benchmark/scenarios/` and `configs/benchmark/splits.yaml`
UNCHANGED -- only `tasks_dir` differs, pointing at
`configs/benchmark/tasks_v2/`.

`configs/benchmark/tasks_v2/*.yaml` is GENERATED by
`scripts/generate_tep_v2_tasks.py` from the real, unmodified tep-v1 task
YAMLs (objective/ground_truth/required_evidence/evaluation_criteria
copied byte-for-byte) plus two fields added: `isa95_level`/`use_case_id`
(looked up from an explicit, reviewable `TASK_TO_USE_CASE` table in that
script, cross-checked at generation time against the real registered
inventory -- the script refuses to run if they've drifted apart). 40
tasks total: the 38 real tep-v1 tasks, all classified, plus 2 genuinely
new, hand-authored Area-level tasks (`configs/benchmark/tasks_v2/area.yaml`)
verifying the real Site/Area/ProcessCell hierarchy facts.

Run it exactly like tep-v1, via the SAME `scripts/run_benchmark.py`:

```
uv run python scripts/run_benchmark.py --suite tep-v2 --agent llm --architectures all --seeds 1
```

## Architecture connectivity/health (mandatory)

Before trusting any benchmark result, every architecture component's
REAL, functional connectivity is verified -- not merely "the port is
open" or "HTTP 200" (`icab.architecture_health`, `tests/integration
/test_architecture_connectivity.py`, `scripts/check_architecture_health.py`,
`uv run python scripts/icab_v2_cli.py validate-architectures`). Each
check performs a real round trip and asserts on the actual data:
Historian (write/read a real observation), Knowledge Graph (a real
MONITORS relationship), UNS (the real, in-process TEP node tree), MQTT
(a real retained message), OPC UA (browse + read against the real,
already-running TEP-backed server), i3X (the same, against ICAB's real
PRIVATE instance -- never the public `api.i3x.dev`), Gateway (a real
HTTP round trip through the real FastAPI routes). `scripts/run_benchmark.py
--validate-architectures` runs this before a benchmark invocation and
refuses to proceed if any component fails.

A broken architecture is NEVER interpreted as a scoring result -- see
the failure taxonomy below.

## Failure taxonomy (`icab.analysis.failure_taxonomy`)

Every run is classified, deterministically, from EXISTING signals only
(`ExperimentRecord.status`/`.error`, `EvaluationReport`'s existing
fields) into: `architecture_connectivity_failure`,
`context_not_discoverable`, `context_not_retrieved`,
`context_not_integrated`, `representation_failure`, `reasoning_failure`,
`grounding_failure`, `efficiency_failure`, or `none` (succeeded). A
broken KG connection is never scored as a "KG reasoning failure"; a
missing context dimension is never scored as an agent failure.

## The analysis suites

All operate ONLY on already-persisted `ExperimentRecord`s (no new
simulator/gateway/LLM call), reusing `icab.reporting.aggregate_records`
for the actual grouping/statistics -- see `icab.analysis`'s own module
docstring. Every report is scoped to context combinations/architectures
ACTUALLY TESTED for a given use case; nothing is ever extrapolated to an
untested condition.

| Suite | Module | What it answers |
|---|---|---|
| ICAB-CN | `icab.analysis.necessity` | Which dimensions' presence/absence correlates with a metric difference, among tested conditions |
| ICAB-CS | `icab.analysis.sufficiency` | The smallest-cardinality TESTED combination meeting a use case's own success criteria -- explicitly labeled "Minimum Sufficient Context Among Tested Conditions," never a global minimality claim |
| ICAB-CC | `icab.analysis.composition` | Does a tested combination outperform its individual dimensions, among tested conditions |
| ICAB-CE | `icab.analysis.efficiency` | Tool-call/context-acquired/latency/token cost per tested combination/architecture -- the EXISTING efficiency metrics, regrouped |
| ICAB-CR | `icab.analysis.representation` | How single-architecture arms actually represented the required context, and the effectiveness/efficiency cost of each real representation |
| ICAB-CA | `icab.architecture_health` | Real connectivity -- see above |
| ICAB-IR | the existing task suite + `GroundedInvestigationEvaluator` | Realistic industrial investigation/diagnosis, unchanged |

```
uv run python scripts/icab_v2_cli.py analyze-necessity --use-case <id>
uv run python scripts/icab_v2_cli.py analyze-sufficiency --use-case <id>
uv run python scripts/icab_v2_cli.py analyze-composition --use-case <id>
uv run python scripts/icab_v2_cli.py analyze-representation --use-case <id>
uv run python scripts/icab_v2_cli.py analyze-architecture --use-case <id>
```

## Context Design Profiles (`icab.analysis.profile`)

The standards-oriented output, generated FROM experimental results
(never hard-coded): per use case, its required context, the minimum
sufficient context among tested conditions (with the same explicit
caveat), a PER-DIMENSION representation recommendation (restricted to
architectures actually capable of that dimension -- never a single
"best overall" architecture applied blanket to every dimension), the
architectures actually evidenced, and a `confidence` level
(`high`/`medium`/`low`) derived from how much evidence (`n` runs,
`n` tested combinations) actually exists -- not a statistical confidence
interval.

```
uv run python scripts/icab_v2_cli.py generate-profiles --out results/reports/context-design-profiles.json
```

## Reproducibility

Every run persists `isa95_level`, `use_case_id`, and
`context_combination_id` on its `ExperimentConfig` alongside every field
M13-D already persists (`benchmark_id`, `configuration_hash`,
`generation_id`, `git_commit`, seed, architecture, etc. -- unchanged).
No new randomness is introduced anywhere in v2.

## Known limitations

- Enterprise/Site/Work Center have zero use cases -- a real, stated data
  gap, not a bug (see the coverage table above).
- Necessity/sufficiency/composition results are only ever reported over
  combinations actually run in a given `results/` directory -- running
  the full 127-combination space is not attempted or claimed; a
  researcher choosing to run more conditions gets correspondingly richer
  (but still honestly-scoped) analysis output.
- `icab.analysis.representation`'s architecture-representation labels
  (`ARCHITECTURE_REPRESENTATION_LABELS`) are a fixed, documented mapping
  of each architecture's real mechanism -- not independently re-verified
  per run beyond what the architecture connectivity suite already
  confirms.
- The Area-level `area-qa-site-membership`/`area-investigation-process-cell-composition`
  tasks require `knowledge_graph` specifically; a knowledge-graph-only
  arm cannot discover the Area's own canonical id from a plain-language
  reference (no semantic/UNS discovery layer was included for Area
  entities) -- a REAL, observed finding from running the task (see
  `docs/research/development-history.md`'s ICAB v2 entry), not a
  hypothetical one, illustrating exactly the kind of representation gap
  this framework exists to surface.
