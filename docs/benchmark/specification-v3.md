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
ICAB Benchmark Suite
|
+-- Enterprise Benchmark    icab-enterprise-v1     framework-ready, data_supported=False, executable=False
+-- Site Benchmark          icab-site-v1           framework-ready, data_supported=False, executable=False
+-- Area Benchmark          icab-area-v1           data_supported=True,  executable=True
+-- Work Center Benchmark   icab-work-center-v1    framework-ready, data_supported=False, executable=False
+-- Process Cell Benchmark  icab-process-cell-v1   data_supported=True,  executable=True
+-- Equipment Benchmark     icab-equipment-v1      data_supported=True,  executable=True
```

Each is a `dataclass` in `LEVEL_BENCHMARKS`, carrying its own
`benchmark_id`, `question_bank_dir` (`configs/questions/<level>/`),
`results_root` (`results/<level>/`), and an honest `coverage_note`.
`QuestionBenchmarkRunner` REFUSES TO EVEN CONSTRUCT against a
non-`executable` definition (`ValueError`, not a run that silently
produces zero/fabricated results):

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

## Question bank counts (actual, as of this milestone -- never inflated)

| Level | Questions | Target | Note |
|---|---|---|---|
| Equipment | 31 | ~30 | Met via real reuse of the existing, already-validated tep-v2 Equipment task inventory -- zero fabrication needed |
| Process Cell | 8 | ~30 | NOT met -- TEP's single real Process Cell and 9 real scenarios genuinely limit how many DISTINCT real questions can be authored without duplicating content; reported honestly rather than padded |
| Area | 3 | ~15 | NOT met, for the same reason, more acutely (TEP has exactly one real Area entity) |
| Enterprise / Site / Work Center | 0 | n/a | Genuinely unsupported -- see `icab.benchmark.levels`' own `coverage_note` per level |

Every question is generated (`scripts/generate_question_banks.py`) FROM
the real, already-validated tep-v2 `BenchmarkTask` inventory, plus a
small number of genuinely new, hand-authored questions
(`configs/benchmark/tasks_v2/process_cell_new.yaml`, and one new task
appended to `configs/benchmark/tasks_v2/area.yaml`) using REAL,
independently-verified CIM relationships
(`icab.tep.adapter.TEPAdapter.get_real_hierarchy_relationships()`) --
never invented entities, relationships, or ground truth.

`difficulty`/`difficulty_factors`/`expected_answer_type`/`tags` for the
GENERATED (tep-v2-derived) questions are assigned by a small,
deterministic, DOCUMENTED heuristic over each task's own real fields
(`scripts/generate_question_banks.py`) -- not independently hand-verified
per question given the volume (40 source tasks). Stated here explicitly
rather than presented as individual expert judgment.

## What this milestone does not do (over-engineering guardrails honored)

- Did not rewrite the CIM, the evaluator, the Gateway, or any
  architecture adapter.
- Did not introduce MCP.
- Did not modify `tep-v1` (verified via `git diff` against its own
  directories before every commit).
- Did not fabricate Enterprise/Site/Work-Center scenarios, entities,
  relationships, or results.
- Did not force Process Cell/Area question counts to their target
  numbers by inventing content.
- Did not make all 127 (or even all 13 realizable) context combinations
  mandatory for any campaign.
- Did not lower any evaluator threshold to raise pass rates.
- Did not delete any historical result -- the reset mechanism archives.
