# ICAB context-requirement experimental protocol

This document defines HOW an ICAB v2 context-requirement campaign is
designed and run, independent of any one campaign's results (see
[`context-requirement-campaign-1.md`](context-requirement-campaign-1.md)
for the first campaign's actual observations). It governs every campaign
run via `scripts/run_context_experiment.py` from this point forward.

## The scientific unit

Every observation in a campaign is one point in:

```
USE CASE  x  CONTEXT CONDITION  x  ARCHITECTURE  x  SCENARIO  x  SEED
```

held together by a fixed **task** (the concrete question asked) and a
fixed **agent configuration** (agent type, model, temperature, step
budget) — see "What is held constant" below. A "context condition" is a
`icab.tasks.context_combinations.ContextCombination` id, resolved to a
real **architecture arm** by `icab.tasks.context_conditions
.resolve_condition_architectures` (never assumed realizable — see below).

## What varies, what is held constant

To isolate the effect of context, a single campaign batch varies **only
the context condition** (and, for repetition, the seed) while holding
everything else fixed:

| Factor | Held constant within a batch | Varies across batches/campaigns |
|---|---|---|
| Task (question asked) | Yes | Chosen once per use case, reused across all its batches |
| Scenario (process/fault conditions) | Yes (the task's own `scenario_id`) | Only if the task itself changes |
| Agent type | Yes (`llm` for this protocol's real-evidence campaigns) | `baseline` reserved for deterministic control runs, never mixed into the same necessity/sufficiency comparison without noting it |
| Model / temperature | Yes (provider default, temperature 0.0) | — |
| Step budget (`max_steps`) | Yes (12, this protocol's default) | Noted explicitly if changed — a tighter budget can turn a discovery success into an `efficiency_failure`, so budget is a confound if varied silently |
| Context condition | **No — this is the independent variable** | — |
| Seed | Repeated (>=2 distinct seeds per condition where the campaign budget allows) | — |

Mixing `llm` and `baseline`-agent records in the SAME necessity/
sufficiency comparison is possible (both are `RunValidity.VALID`) but is
a genuine confound — a campaign report must call this out explicitly
wherever it happens rather than silently pooling them (see Campaign 1's
`pc-equipment-composition-discovery` finding for a worked example).

## Step 1 — Establish the reference/full-context condition

Before designing ablations, compute, per task, the RICHEST combination
that task's own `available_architectures` can realize AT ALL (not
assumed to be `C1+C2+C3+C4+C5+C6+C7` — see `docs/benchmark
/specification-v2.md`'s "only 13 of 127 combinations are realizable"
finding):

```python
from icab.tasks.context_dimensions import provided_dimensions
from icab.tasks.context_combinations import combination_for_dimensions

realizable_maximum = combination_for_dimensions(provided_dimensions(task.available_architectures))
```

This combination is always EXACTLY realizable using every one of the
task's architectures together (by construction). It is the campaign's
**reference condition**. Separately record whether it lies WITHIN the
use case's own `candidate_context` or exceeds it — architectures
routinely overshoot a use case's declared scope (see Campaign 1: every
selected use case's task-realizable maximum exceeded its own
`candidate_context`). Run the reference condition with use-case scoping
disabled (`--usecases-dir ''`) specifically because it is expected to
exceed scope; every other batch keeps scoping on.

## Step 2 — Single-dimension sweep

Attempt `icab.tasks.experiment_design.single_dimension_conditions()`
(C1..C7) via `resolve-conditions` first (a dry run, no infrastructure)
to see the real classification before spending a single LLM call.
Execute only what the resolver marks `exact` or (explicitly,
`--allow-overshoot`) `overshoot`; never execute or fabricate a result
for `unrealizable`/`not_applicable`. Record every condition's outcome
regardless — "not executed" is data, not a gap.

## Step 3 — Pairwise / ablation, scoped to `candidate_context`

Do not run all 21 pairs blindly. Prioritize:

1. The use case's own `required_context` pair (if cardinality 2), or the
   most informative pair within `candidate_context`.
2. Pairs that isolate a specific complementarity question (e.g. does
   adding C3 to C5 change anything a C5-only run couldn't already show).

Ablation baselines default to the reference condition (Step 1) unless a
narrower, use-case-scoped baseline is scientifically more interesting
(e.g. the use case's own `required_context` combination) — always state
which baseline was used.

## Step 4 — Repetition

Where budget allows, repeat the reference condition and at least one
other high-value condition at a second, distinct seed. Two seeds is
`tentative_small_n` under `icab.analysis._shared.sample_size_label`;
five or more is `repeated_empirical_result`. Never report a mean from
`n=1` as if it were stable.

## Success predicate

Reuses the EXISTING, unchanged `GroundedInvestigationEvaluator` and each
use case's own `EvaluationCriteria` — this protocol does not introduce a
second scoring mechanism. A condition counts as **empirically
successful** for a use case if and only if the MEAN of every one of that
use case's `binding_scores` (declared in `configs/usecases/*.yaml`, e.g.
`required_evidence_score`, `relationship_score`, `conclusion_correctness_score`,
`grounding_score`, `canonical_id_score`, `completeness_score`) across
its usable runs is `>= pass_threshold`. The default `pass_threshold` is
explicitly `1.0` (`EvaluationCriteria.pass_threshold`'s own default) —
this protocol does not lower it. A campaign MAY additionally report a
condition's performance under a lower, explicitly-labeled threshold
(e.g. "how many binding scores does this condition satisfy, and by how
much") as a SEPARATE, clearly-marked exploratory statistic — never as a
silent redefinition of "successful."

## Candidate MSC — partial order, not a total order

`icab.analysis.sufficiency.find_minimum_sufficient_context` reports
EVERY tested sufficient condition that is not a proper superset of
another tested sufficient condition (`candidate_minimum_sufficient_contexts`)
— not merely the single smallest-cardinality one. Two conditions of
equal cardinality, or of different cardinality where neither's
dimensions are a subset of the other's, are genuinely incomparable and
are BOTH reported. `minimum_sufficient_context_among_tested` (singular)
remains for backward compatibility but is only a deterministic tie-break
over that same candidate set — always prefer the plural field when more
than one candidate exists.

## Failure classification discipline

Every run is classified by TWO independent, existing mechanisms, read
from the SAME already-computed `EvaluationReport` fields:

- `icab.analysis.failure_taxonomy.classify_failures` — WHAT kind of
  failure (architecture connectivity / context not discoverable /
  context not retrieved / representation / reasoning / grounding /
  context not integrated / efficiency / none).
- `icab.analysis.discoverability.classify_discoverability` — HOW FAR the
  evidence pipeline got (exists in architecture -> discovered identifier
  -> retrieved value -> used as evidence -> grounded in conclusion).

A run's classification is never overridden by hand to fit an
expectation. If neither mechanism's existing signals can distinguish
(e.g. a run failed for a reason genuinely outside both taxonomies),
report it as `unresolved` rather than forcing a category — this
protocol does not add a catch-all bucket to the taxonomy itself (that
would be new infrastructure beyond what a single campaign's findings
justify); "unresolved" is a REPORTING label a campaign author applies
when write-up, not a code-level category.

## Traceability

Every quantitative claim in a campaign report must be traceable to one
or more `run_id`s. `SufficiencyReport.tested_conditions[i].run_ids` and
`icab.analysis.reports.candidate_msc_table(...)`'s
`supporting_experiment_ids` provide this directly for sufficiency/MSC
claims; `FailureClassification.run_id`/`DiscoverabilityClassification
.run_id` provide it for every individual failure/discoverability
observation. A campaign report must never state a finding without
citing the `run_id`(s) it rests on.

## What this protocol does not claim

- Running every batch this protocol describes does not test all 127
  combinations — only a deliberately selected subset per use case (see
  Phase 4-8 rationale in each campaign report).
- A `pass_threshold=1.0` failure does not, by itself, mean the context
  dimension(s) tested were insufficient — see the failure/discoverability
  classification for WHERE in the pipeline it actually failed before
  drawing that conclusion.
- Repetition at 2 seeds supports "observed twice, consistently" language,
  not a statistical significance claim.
