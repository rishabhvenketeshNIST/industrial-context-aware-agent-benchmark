# ICAB v3 specification: ISA-95-level benchmarks and question banks

ICAB v3 answers the SAME research question ICAB v2 introduced, restated
with the machinery this milestone adds:

> At each ISA-95 level, across a broad and repeatable set of industrial
> questions, what context does an AI agent need, how reliably can it use
> that context, and how do those requirements change across
> architectures, scenarios, and repeated executions?

`tep-v1` and the ICAB v2 `tep-v2` suite are completely unmodified by
this milestone. v3 does not replace either -- it adds a THIRD, parallel
way to organize and run ICAB content: six independent, ISA-95-level
benchmarks, each with its own id, question bank, results tree, and
reports, sharing every piece of underlying infrastructure (evaluator,
agents, gateway, architecture adapters, context-condition resolver,
design strategies) unchanged.

## The central model

```
ISA-95 LEVEL
      |
LEVEL-SPECIFIC BENCHMARK        (icab.benchmark.levels.ISA95BenchmarkDefinition)
      |
INDUSTRIAL USE CASE              (icab.usecases.IndustrialUseCase, unchanged)
      |
QUESTION BANK                    (icab.questions.Question -- NEW)
      |
QUESTION INSTANCE                (icab.questions.QuestionInstance -- NEW)
      |
REPETITION                       (ExperimentConfig.repetition, reused)
      |
CONTEXT / REPRESENTATION / ARCHITECTURE   (icab.tasks.context_conditions, unchanged)
      |
AGENT                            (baseline or LLM, unchanged)
      |
EVIDENCE + OUTCOME                (GroundedInvestigationEvaluator, unchanged)
```

## Six separate benchmarks (`icab.benchmark.levels`)

```
ICAB Benchmark Suite  (all six now executable -- 50 validated questions each, see below)
|
+-- Enterprise Benchmark    icab-enterprise-v1     data_provenance=controlled_synthetic
+-- Site Benchmark          icab-site-v1           data_provenance=mixed
+-- Area Benchmark          icab-area-v1           data_provenance=mixed
+-- Work Center Benchmark   icab-work-center-v1    data_provenance=controlled_synthetic
+-- Process Cell Benchmark  icab-process-cell-v1   data_provenance=real_tep
+-- Equipment Benchmark     icab-equipment-v1      data_provenance=real_tep
```

Each is a `dataclass` in `LEVEL_BENCHMARKS`, carrying its own
`benchmark_id`, `question_bank_dir` (`configs/questions/<level>/`),
`results_root` (`results/<level>/`), `data_provenance` (see "The
controlled benchmark context layer" below), and an honest
`coverage_note`. `QuestionBenchmarkRunner` REFUSES TO EVEN CONSTRUCT
against a non-`executable` definition (`ValueError`, not a run that
silently produces zero/fabricated results) -- the guard itself is
unchanged even though all six levels are executable as of this
milestone.

```
uv run python scripts/icab_v2_cli.py list-benchmarks
```

## The `Question` model (`icab.questions.Question`)

Deliberately NOT a second execution/evaluation path -- a `Question` is
the SEMANTIC task; it is realized, per compatible scenario, by an
EXISTING, unmodified `icab.tasks.benchmark_task.BenchmarkTask`
(`Question.realizations: dict[scenario_id, task_id]`). When a
`QuestionInstance` actually runs, it resolves that real `BenchmarkTask`
and goes through the EXACT SAME `ExperimentRunner.run_task` /
`GroundedInvestigationEvaluator.evaluate_task` path every other ICAB v2
run already uses.

```python
class Question(BaseModel):
    question_id: str
    benchmark_id: str
    use_case_id: str
    isa95_level: ISA95Level
    question_text: str
    task_type: TaskMode
    objective: str
    hypothesized_required_context: list[ContextDimension]   # design-time HYPOTHESIS
    expected_evidence_description: str
    expected_answer_type: ExpectedAnswerType
    compatible_scenarios: list[str]        # superset of realizations' keys
    realizations: dict[str, str]           # scenario_id -> real BenchmarkTask.task_id
    difficulty: QuestionDifficulty          # basic | intermediate | advanced
    difficulty_factors: DifficultyFactors   # WHY -- n_sources, relationship_depth, ...
    tags: list[QuestionCategory]            # the reusable taxonomy, below
    version: str
    validation_status: ValidationStatus     # draft | validated | deprecated
```

**`hypothesized_required_context` is never conflated with empirically
demonstrated necessity.** The latter is NOT a field on this model at
all -- it is a DERIVED analysis output, computed only from already-
persisted records, via `icab.analysis.necessity.analyze_context_necessity(...,
question_id=...)`. Conflating a design-time guess with an experimental
conclusion is exactly the mistake this separation exists to prevent.

## The reusable question taxonomy (`icab.questions.QuestionCategory`)

`identification`, `state_interpretation`, `measurement_interpretation`,
`relationship_reasoning`, `temporal_reasoning`, `historical_reasoning`,
`operational_reasoning`, `procedural_reasoning`, `diagnosis`,
`contextualized_qa`, `evidence_verification`, `cross_source_reasoning`.
No level is required to use every category; no category is required at
every level -- a shared vocabulary for CROSS-level comparison, not a
per-level checklist.

## Question -> Question Instance -> Repetition -> Experiment Run -> Trace

```
ISA-95 Benchmark
    |
Use Case
    |
Question              <- the semantic task
    |
Question Instance     <- that question fixed to ONE scenario + architecture arm + agent config
    |
Repetition             <- one actual execution (ExperimentConfig.repetition)
    |
Experiment Run          <- ExperimentRecord (unchanged M9/M13-D schema, + question_id/question_instance_id/repetition_mode)
    |
Trace                   <- unchanged TraceEvent list
```

A **Question Instance** (`icab.questions.QuestionInstance`) is a
question fixed to a scenario, a canonical (sorted) architecture arm, and
an agent configuration (agent/model/temperature) -- everything that must
be held constant for repeated executions to be comparable at all. Its
`instance_id` is a stable, deterministic, human-legible-prefixed string
(`instance_id_for`), so the SAME instance always gets the SAME id
regardless of call order.

**Why repeated questions matter** (the direction's explicit rationale,
implemented, not just asserted):

- **Reproducibility** -- can the same instance be run again and produce
  a comparable result?
- **Stochasticity measurement** -- an LLM agent is not deterministic;
  `EXACT` repetition (below) is what lets `icab.analysis.question_stats`
  report a real `mean`/`median`/`stdev`/`success_rate` instead of a
  single, possibly-lucky (or unlucky) sample.
- **Statistical reliability** -- `icab.analysis._shared.sample_size_label`
  attaches an honest, fixed label (`single_observation`/
  `tentative_small_n`/`repeated_empirical_result`) to every reported
  mean, never a false confidence-interval claim from n=1 or n=2.
- **Robustness/generalization** -- `CONTROLLED_VARIATION` repetition
  (below) separates "does this agent handle THIS exact scenario
  reliably" from "does this agent handle the semantic question across
  DIFFERENT real process conditions."
- **Separating question effects from agent randomness** -- a
  `QuestionInstance`'s own `mean`/`stdev` (over its repetitions) is what
  makes it possible to ask "was this a hard question, or an unlucky
  run?" instead of conflating the two.

### Distinguishing the four counts

A researcher must be able to tell these apart at a glance -- they are
NEVER the same number:

| Count | What it counts | Where |
|---|---|---|
| Unique questions | Distinct `Question.question_id`s | `len(QuestionBankRegistry)` |
| Question instances | Distinct `(question, scenario, architecture arm, agent config)` tuples actually selected | Distinct `QuestionInstance.instance_id`s across a campaign |
| Executions | Every real `ExperimentRunner.run_task` call actually made | `QuestionBenchmarkResult.total_runs` |
| Repetitions | Executions PER instance (a subset of "executions," grouped) | `ExperimentConfig.repetition` (1..N) within one instance |

## Two repetition modes (`icab.questions.RepetitionMode`)

- **`exact`** -- same question, scenario, context condition,
  architecture, AND agent configuration, executed repeatedly. Measures
  LLM stochasticity/reproducibility/answer variance/tool-use variance.
- **`controlled_variation`** -- same SEMANTIC question, deliberately run
  against a DIFFERENT scenario (a different `QuestionInstance`, same
  `Question`). Measures robustness/generalization/scenario sensitivity,
  NOT agent stochasticity.

Recorded on every run (`ExperimentConfig.repetition_mode`) so a reader
never has to guess which kind of variation produced a given comparison.
Repetition count is a configurable `--repetitions` flag
(`scripts/run_question_benchmark.py`), never hard-coded.

## Results, organized by ISA-95 level

```
results/
├── enterprise/    (skeleton only -- not executable, never populated)
├── site/          (skeleton only -- not executable, never populated)
├── area/
│   ├── raw/            ExperimentRecord JSON (icab.experiments.storage's existing name for "the experiment record")
│   ├── traces/          TraceEvent JSONL
│   ├── evaluations/     EvaluationReport JSON
│   ├── aggregate/        cross-run comparison tables (M9/M12, unchanged)
│   ├── hypotheses/       (M11, unchanged, rarely used here)
│   ├── reports/          aggregation/QA reports (M12, unchanged)
│   ├── matrices/         NEW -- Tables A-E JSON (icab.analysis.reports)
│   ├── summaries/        NEW -- question/use-case/benchmark stats JSON (icab.analysis.question_stats)
│   └── manifest.json     NEW -- icab.benchmark.manifest.BenchmarkManifest
├── process_cell/   (same layout)
├── equipment/      (same layout)
└── _archive/<timestamp>/   old, pre-v3 flat results, ARCHIVED not deleted -- see reset below
```

The internal per-level layout deliberately REUSES
`icab.experiments.storage.ExperimentResultStore`'s own existing
subdirectory names (`raw`/`traces`/`evaluations`/`aggregate`/
`hypotheses`) rather than inventing new ones -- only `matrices/` and
`summaries/` (plus the level separation itself) are genuinely new,
via `icab.reporting.store.ReportStore.matrices_dir`/`.summaries_dir`.

**Every persisted `ExperimentRecord`'s own `config.isa95_level` is
checked against the benchmark it is about to be saved under.**
`QuestionBenchmarkRunner` raises `IsaLevelMismatchError` (never silently
writes to the wrong level's tree) if they disagree -- checked twice: once
right after building the config (before any real work happens) and once
more on the record actually returned by execution.

## The reset mechanism (`scripts/reset_active_results.py`)

Archives (moves, NEVER deletes) the OLD flat
`results/{raw,traces,evaluations,aggregate,reports,figures,hypotheses,
prototype}/` content into `results/_archive/<timestamp>/`, then creates
the new level-scoped skeleton. Defaults to a DRY RUN (prints the exact
plan, changes nothing) -- pass `--force` to actually execute it. Refuses
outright (hard-coded `PROTECTED_PATHS` check, `SystemExit`) to ever
touch `src/`, `tests/`, `docs/`, `configs/`, or
`results/architecture_health.json`.

```
uv run python scripts/reset_active_results.py             # dry run
uv run python scripts/reset_active_results.py --force      # actually archive + create the new skeleton
```

## Running a question-bank campaign (`scripts/run_question_benchmark.py`)

```
uv run python scripts/run_question_benchmark.py \
    --level equipment --question-ids Q-d1-qa-current-pressure \
    --context-combinations C5 --agent llm --repetitions 5

uv run python scripts/run_question_benchmark.py \
    --level process_cell --tags diagnosis --context-combinations C3+C4 \
    --allow-overshoot --agent llm --repetitions 3 --seeds 1,2
```

Filtering supports `--question-ids`/`--use-case-ids`/`--tags` (question
selection), `--context-combinations`/`--allow-overshoot` (which
conditions, resolved via the EXISTING, unchanged
`icab.tasks.context_conditions.resolve_condition_architectures`), and
`--scenario-ids` (which of a question's real realizations to run). The
full combinatorial space is NEVER executed automatically -- a filtered
slice is the norm, matching the ICAB v2 direction's own "do not require
all 127 combinations" rule, now applied one level up to "do not require
every question x every combination x every scenario."

## Aggregation: Question -> Use Case -> ISA-95 Benchmark (`icab.analysis.question_stats`)

Every level supports BOTH:

- **macro-average** -- the mean of each QUESTION's own mean. An easy
  question run 20 times cannot outweigh a hard question run twice.
- **micro-average** -- the mean pooled over every individual run,
  traditional repetition-weighted average.

Both are always reported side by side, and every question's own
`QuestionStats` (success rate, mean, median, stdev, failure breakdown,
discoverability breakdown, efficiency) is PRESERVED in the output even
after rolling up to the use-case or benchmark level -- an aggregate
number never replaces the ability to see which specific question drove
it.

```
uv run python scripts/icab_v2_cli.py analyze-question-stats --level equipment --question Q-d1-qa-current-pressure
uv run python scripts/icab_v2_cli.py analyze-use-case-question-stats --level equipment --use-case eq-current-value-interpretation
uv run python scripts/icab_v2_cli.py analyze-benchmark-level-stats --level equipment
```

## Context-requirement analysis at three levels

The EXISTING `icab.analysis.necessity`/`.sufficiency` machinery
(unchanged logic) gained an optional `question_id` parameter:

- `question_id=<id>` -- necessity/candidate-MSC for ONE question.
- `question_id=None` (default, unchanged) -- for the whole use case.
- Benchmark-level: call the SAME functions once per use case whose
  `isa95_level` matches, or use `icab.analysis.reports.candidate_msc_table`
  with a level-filtered use-case list -- no new function needed, this
  was already possible by filtering the existing `use_cases` argument.

`SufficiencyReport.candidate_minimum_sufficient_contexts` (the
partial-order-correct plural field added in the prior context-
requirement-campaign milestone) is unchanged and applies identically at
all three scopes -- the conservative "Minimum Sufficient Context Among
Tested Conditions" framing, never global minimality, is never relaxed
regardless of which level the analysis is run at.

## Traceability

```
Benchmark -> Use Case -> Question -> Question Instance -> Repetition -> Experiment ID -> Trace
```

`BenchmarkManifest.run_ids` lists every run behind a level's counts;
`SufficiencyReport.tested_conditions[i].run_ids` and
`icab.analysis.reports.candidate_msc_table(...)`'s
`supporting_experiment_ids` trace a specific MSC claim; `QuestionStats
.run_ids` traces a specific question's own statistics. Every one of
these is computed FROM already-persisted `results/<level>/raw/*.json`
files, never hand-maintained.

## Question bank counts (actual, as of the 50-question milestone -- never inflated)

Every ISA-95 level now has EXACTLY 50 validated questions (300 total):

| Level | Questions | Data provenance | Note |
|---|---|---|---|
| Enterprise | 50 | `controlled_synthetic` | Entirely against `icab.benchmark_context` -- TEP has no real multi-enterprise data at all |
| Site | 50 | `mixed` | The one REAL `urn:icab:site:tep` + 2 controlled synthetic sibling sites |
| Area | 50 | `mixed` | 3 REAL hand-authored hierarchy-fact questions over the real Reaction Area + 47 controlled-synthetic |
| Work Center | 50 | `controlled_synthetic` | Entirely against `icab.benchmark_context` -- TEP has zero WorkCenter entities |
| Process Cell | 50 | `real_tep` | 8 original (7 tep-v1-derived + 1 new) + 42 new real MONITORS/PART_OF relationship questions over all 41 real measurements |
| Equipment | 50 | `real_tep` | 31 original (tep-v1-derived) + 19 new real current-value QA questions over previously-unused real measurements |

`data_provenance` is declared per level (`icab.benchmark.levels
.ISA95BenchmarkDefinition.data_provenance`, one of `real_tep`/
`controlled_synthetic`/`mixed`) and every generated question's own
`provenance` field states exactly which mechanism produced it --
`scripts/generate_question_banks.py` (real tep-v2-derived),
`scripts/generate_synthetic_level_tasks.py` (controlled benchmark
context), or `scripts/generate_extra_real_tasks.py` (additional real
TEP measurements/relationships never previously used by any task).

## The controlled benchmark context layer (`icab.benchmark_context`)

TEP genuinely has no Enterprise/Site/Work-Center data, and only ONE real
Site/Area entity each. Rather than leave three levels permanently
unsupported or fabricate untraceable facts, this milestone added a
DETERMINISTIC, VERSIONED, clearly-labeled synthetic hierarchy and KPI
catalog (`src/icab/benchmark_context/data.py`):

```
urn:icab:enterprise:northwind-chemical                    (1, synthetic)
  +-- urn:icab:site:tep                                    (REAL, reused as-is)
  |     +-- urn:icab:area:reaction                          (REAL, reused as-is)
  |           +-- urn:icab:workcenter:reaction-utilities     (1, synthetic, ADDITIVE sibling of the real Process Cell)
  +-- urn:icab:site:riverside                               (1, synthetic)
  |     +-- urn:icab:area:riverside-utilities                (1, synthetic)
  |           +-- urn:icab:workcenter:riverside-packaging     (1, synthetic)
  +-- urn:icab:site:port-arthur                             (1, synthetic)
        +-- urn:icab:area:port-arthur-processing              (1, synthetic)
              +-- urn:icab:workcenter:port-arthur-distillation (1, synthetic)
```

Plus 88 synthetic KPI measurements (10 enterprise + 30 site + 24 area +
24 work-center), each a deterministic value seeded from
`random.Random(f"{entity_id}:{kpi_key}:{BENCHMARK_CONTEXT_VERSION}")` --
same inputs always produce the same value; changing
`BENCHMARK_CONTEXT_VERSION` is how this layer would ever be
deliberately revised.

**Real vs. controlled, explicit and structural, never just a claim:**

- Every synthetic entity/relationship/observation is tagged
  `source="icab_benchmark_context"` (`BENCHMARK_CONTEXT_SOURCE`), sharply
  distinct from `source="tep"` (real TEP data) -- verifiable directly in
  the historian/knowledge_graph.
- The real `urn:icab:site:tep`/`urn:icab:area:reaction` entities and
  their OWN existing relationships are NEVER redefined or altered --
  `icab.benchmark_context.builder` only ADDS new relationships (e.g.
  `site:tep PART_OF enterprise`), verified directly against the live
  knowledge graph before this milestone's first real campaign ran.
- Reached through the SAME `icab.context.environment_loader
  .EnvironmentLoader`/historian/knowledge_graph real TEP data already
  uses (`scripts/seed_benchmark_context.py`) -- no hidden database only
  the evaluator can see. The agent discovers/retrieves this data through
  the exact same `get_current_value`/`get_entity_relationships` gateway
  tools it already uses for real TEP data.
- Ground truth conclusions never leak the synthetic numeric value itself
  for value-lookup questions (the same generic-template convention every
  other ICAB measurement-QA task already uses) -- only comparison
  questions state a computed winner, and only in the researcher-only
  ground truth, never the agent-visible objective.

```
uv run python scripts/seed_benchmark_context.py
```

## The 3,000-execution invariant (`icab.benchmark.completeness`)

```
6 levels x 50 unique questions x 10 repetitions = 3,000 executions
```

`check_level_completeness()` computes a `LevelCompletenessReport` PURELY
from already-persisted `results/<level>/raw/*.json` records and the
real question bank -- never a hand-maintained count -- and flags:
fewer than 50 questions in the bank, duplicate question ids, records
whose own `isa95_level` disagrees with the level being checked
(contamination), missing experiment id/trace reference, duplicate
(instance, repetition) executions, and any question with fewer than 10
completed repetitions. `LevelCompletenessReport.is_complete` is False if
ANY of these hold -- a partial campaign is NEVER reported as complete.
`SuiteCompletenessReport.is_complete` additionally requires all SIX
levels to be present and each individually complete.

```
uv run python scripts/run_level_benchmark.py --check-only
```

## Standard benchmark vs. research experiments

Two distinct entry points, deliberately kept separate so ad-hoc research
experiments never silently change the canonical benchmark score:

- **Standard benchmark** (`scripts/run_level_benchmark.py`) -- the
  canonical 50-question x 10-repetition baseline. Each question's own
  DESIGNATED architecture arm (resolved from its
  `hypothesized_required_context`, `icab.tasks.context_conditions
  .resolve_condition_architectures`) is held FIXED across all 10
  repetitions of that question (`RepetitionMode.EXACT`) -- refuses to
  even start unless the level's bank has exactly 50 questions.
- **Research experiments** (`icab.benchmark.context_experiment`,
  `scripts/run_context_experiment.py`) -- freely vary context
  combination/architecture/scenario for one question at a time
  (ablation, pairwise, single-dimension, ...), reusing the SAME 300
  questions rather than a separate question bank per experiment. Never
  mutates or is conflated with the standard benchmark's own results.

```
uv run python scripts/run_level_benchmark.py --level equipment --repetitions 10
uv run python scripts/run_level_benchmark.py --all --repetitions 10
```

## Validated (Step A) and real-executed (Step B) -- exact numbers

Following the mandatory Step-A/B/C/D sequence (never jumping straight to
a 3,000-run campaign):

- **Step A**: `icab.questions.validate_question_bank` ran against all
  six levels -- **300/300 questions validated**, 0 failures, every one
  of the 9 checks (grounded evidence, correct ISA-95 level, documented
  evidence/context-hypothesis, deterministically evaluable, real
  compatible scenario, real evaluator scoring, no duplicates) passing.
- **Step B**: a real, small sample was run against LIVE infrastructure
  and NIST RChat (`--name v3-stepb`) -- 2 questions x 2 repetitions
  EACH, across ALL SIX levels: **24/24 real executions completed**
  (0 orchestration failures), proving the controlled benchmark context
  layer works end to end (real gateway call, real historian/
  knowledge_graph round trip, real evaluator scoring) for the first
  time at Enterprise/Site/Work-Center, not merely that it loads.
- **Step C**: verified programmatically -- 0/24 records mismatched their
  own `results/<level>/` root; every manifest/completeness check ran
  cleanly against the real data.
- **Step D**: the FULL 3,000-execution campaign was **NOT** run this
  milestone (infeasible within one session's real-LLM wall-clock budget
  -- see "Known limitations" below). `scripts/run_level_benchmark.py
  --all --repetitions 10` is fully built, tested, and resumable
  level-by-level; running it to completion is explicitly named as
  remaining work, not silently treated as done.

**A genuine, honestly-reported finding from Step B**: at Enterprise/
Site/Area/Work-Center/Process-Cell, 0 of 20 controlled-context or extra
real-relationship questions reached `required_evidence_score=1.0`
(the agent could not resolve a plain-language reference, e.g. "Port
Arthur Site," to its real canonical id via `knowledge_graph`/`historian`
alone, without a semantic discovery tool) -- while Equipment's
historian-only measurement questions succeeded 4/4. This extends the
SAME `knowledge_graph`-only discoverability weakness first observed for
the real Area level (`docs/research/context-requirement-campaign-1.md`)
to the new controlled-context levels, and raises a genuinely open
question (why Equipment's historian-only value lookups succeed while
these do not) that this milestone deliberately leaves open rather than
speculating about -- see "Known limitations."

## Known limitations

- **The full 3,000-execution campaign has NOT been run.** Only 24 real
  executions (Step B, across all six levels) have been completed as of
  this milestone. `scripts/run_level_benchmark.py --all --repetitions 10`
  is the documented, tested, resumable path to complete it -- doing so
  is explicit remaining work, not claimed as done.
- **The Enterprise/Site/Work-Center/Area-extra/Process-Cell-extra
  discoverability finding above is OBSERVED, not yet explained.** Only
  20 real runs support it; no root-cause investigation (e.g. comparing
  exact tool-call sequences between a succeeding Equipment run and a
  failing Enterprise run) was performed this milestone. Treat it as a
  concrete lead for the next context-requirement campaign, not a
  settled conclusion.
- **Controlled benchmark context KPI values are synthetic**, generated
  by a deterministic formula (`random.Random` seeded per entity/KPI/
  version) within a plausible real-world range -- realistic in
  magnitude, never claimed to be empirically measured. Any conclusion
  drawn from Enterprise/Site/Work-Center/the-synthetic-half-of-Area
  results is a conclusion about THIS controlled layer, not about real
  industrial enterprises.
- **Work Center's synthetic entities are NOT parented to the real
  Process Cell.** To avoid altering the real, already-experimentally-
  used `processcell:reaction PART_OF area:reaction` relationship, the
  new work centers are additive SIBLINGS of the real Process Cell under
  their Area, each with their own KPI content, rather than a literal
  Area -> WorkCenter -> ProcessCell chain wrapping the real process
  cell. Documented here rather than silently assumed away.
- **Difficulty/tag/answer-type assignment for generated questions is
  heuristic**, not independently hand-verified per question given the
  volume (300 questions) -- see `scripts/generate_question_banks.py`'s
  own documented, deterministic rule.

## What this milestone does not do (over-engineering guardrails honored)

- Did not rewrite the CIM, the evaluator, the Gateway, or any
  architecture adapter.
- Did not introduce MCP.
- Did not modify `tep-v1` (verified via `git diff` against its own
  directories before every commit).
- Did not fabricate ENTITIES/relationships/ground truth for Enterprise/
  Site/Work-Center -- every fact there comes from the explicit,
  deterministic, versioned, clearly-labeled controlled benchmark context
  layer (`icab.benchmark_context`), reached through the same real
  architecture mechanisms being evaluated -- never a hidden database,
  never presented as real plant data.
- Did not disturb any of the real TEP entities' own existing
  relationships -- every controlled-layer hierarchy edge is ADDITIVE.
- Did not run all 127 (or even all 13 realizable) context combinations
  for the standard campaign -- each question uses its own single
  designated architecture arm, exactly as Section 14 specifies.
- Did not lower any evaluator threshold to raise pass rates -- the real,
  honestly-reported 0/20 controlled-context success rate from Step B was
  left as-is, not adjusted.
- Did not delete any historical result -- `scripts/reset_active_results.py`
  archives (verified: the prior milestone's 38 real records are intact
  under `results/_archive/`).
- Did not claim the 3,000-execution benchmark is complete -- it is not.

## Standalone benchmark execution and export layer (`icab.export`)

A separate, later milestone from the 50-question suite above: a
user-facing execution/export layer sitting ABOVE
`icab.benchmark.question_runner.QuestionBenchmarkRunner` (no new
execution mechanism -- every execution still goes through
`icab.benchmark._execution.run_one`, the same path
`BenchmarkRunner`/`QuestionBenchmarkRunner` already use). Its purpose:
let a user inspect, dry-run, execute, resume, and export a fully
self-contained Q&A/results dataset for ONE ISA-95 level's campaign,
without needing to import or understand ICAB's own Python internals.

### CLI (`scripts/run_level_benchmark.py`)

```
# Inspect the question bank
uv run python scripts/run_level_benchmark.py --level equipment --list-questions
uv run python scripts/run_level_benchmark.py --level equipment --show-question Q-d1-qa-current-pressure

# See the exact plan -- no LLM call
uv run python scripts/run_level_benchmark.py --level equipment --dry-run --repetitions 10

# Execute (also writes the standalone export, unless --no-export)
uv run python scripts/run_level_benchmark.py --level equipment --repetitions 10 --name my-campaign

# Resume an interrupted campaign -- never duplicates a completed execution
uv run python scripts/run_level_benchmark.py --level equipment --repetitions 10 --name my-campaign --resume
```

`scripts/run_benchmark.py` already existed (the pre-existing tep-v1/
tep-v2 suite runner, M13-D) -- rather than introduce a THIRD,
confusingly named script, this functionality was added to the existing
`scripts/run_level_benchmark.py` (the ICAB v3 50-question-per-level
runner), which already had the `--level`/`--repetitions` shape the
export milestone asked for.

### Resume semantics (`QuestionBenchmarkConfig.resume`)

Every execution's `run_id` is fully deterministic
(`{campaign_id}-{instance_id}-seed{seed}-rep{repetition}`). `resume=True`
checks, per planned execution, whether that exact `run_id` already has a
persisted record; if so it is loaded and counted, never re-executed. A
`--resume` on a campaign that added MORE repetitions since its last
invocation only executes the new ones.

### Standalone export (`benchmark_exports/<level>/<campaign_id>/`)

A NEW root, entirely separate from `results/` (never read from or
written into by the exporter):

```
benchmark_exports/<level>/<campaign_id>/
  README.md                  written for a researcher who has never opened the ICAB repo
  benchmark_manifest.json    what exactly was run (config, question ids, git commit, environment)
  questions.json              the question bank slice this campaign covers
  ground_truth.json           one entry per question, kept separate from any LLM answer
  executions.jsonl            one canonical execution record per line (primary dataset)
  results.json                the same executions, with campaign-level metadata
  results.csv                 a flattened, analysis-friendly table
  metrics.json                completion/correctness rates, breakdowns, repetition consistency
  q_and_a/<execution_id>.json / .md
  traces/<execution_id>.json
```

Every file is plain JSON/JSONL/CSV -- `icab.export.validation
.validate_export` (and its own tests) confirm a written export parses
with nothing but `json`/`csv` from the standard library. A field with no
ICAB analog (e.g. `ground_truth.unit`/`acceptable_range`,
`llm.raw_response`) is always `null`, never guessed.

### Canonical execution record (`icab.export.schema.CanonicalExecutionRecord`)

`benchmark` / `isa95` / `question` / `ground_truth` / `llm` / `execution`
/ `context` / `evidence` / `trace` / `evaluation` -- built by
`icab.export.build.build_canonical_record`, which computes no new score
itself: ground truth/per-run metrics are read via the existing
`icab.reporting.qa_report.build_qa_report_entry`, and `failure_mode` via
the existing `icab.analysis.failure_taxonomy.classify_failures`.
`evaluation.correct` is the one genuinely new (but not fabricated)
computation: the run's own task `EvaluationCriteria.binding_scores`/
`pass_threshold` applied to that ONE run -- the same binding criteria
`icab.analysis.sufficiency` already applies at the aggregate level.

### What the export layer deliberately does NOT do

Per its own milestone's explicit instruction, `icab.export` makes no
scientific claim -- no "context X is necessary," no "architecture Y is
the minimum sufficient context." It executes, observes, evaluates, and
exports; independent analysis (aggregation, comparison, statistical
inference, necessity/sufficiency conclusions) stays entirely in
`icab.analysis`, applied AFTER export, never inside it. Launching the
full 3,000-execution campaign was explicitly out of scope for this
milestone -- see `docs/research/development-history.md` for what was
actually run.
