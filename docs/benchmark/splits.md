# Benchmark task splits (M13-C)

## Why grouped by scenario, not by task

Two tasks against the SAME scenario share the exact same underlying
process trajectory -- same seed, same fault schedule, same synced
historian/knowledge-graph/MQTT state. If one such task were used during
agent/evaluator development and a near-duplicate sibling task from the
SAME scenario ended up in the held-out test split, "unseen" test
performance would partly reflect memorized/tuned familiarity with that
one specific process trajectory, not genuine generalization to new
process conditions.

`icab.tasks.splits.SplitAssignment` therefore assigns SCENARIOS to
splits, not individual tasks -- `split_for_scenario(scenario_id)`
resolves every task built on that scenario to the same split by
construction. There is no per-task override; this is the leakage
prevention mechanism, not merely a convention tasks are expected to
follow.

## The three splits

| Split | Scenarios | Tasks | Purpose |
|---|---|---|---|
| `development` | `d1_reactor_pressure_reading`, `d2_reactor_context_combination`, `d3_reactor_pressure_deviation` | 15 | The three original, longest-standing scenarios -- for iterating on baseline agent/tool behavior and initial evaluator tuning. |
| `validation` | `d2_reactor_cooling_deviation`, `d3_stream4_composition_shift` | 7 | Two new (M13-C), moderate-difficulty scenarios -- for comparing configurations before committing to a final test-split run. |
| `test` | `d3_stochastic_composition_drift`, `d4_plant_wide_investigation`, `d4_unknown_plant_disturbance`, `d4_feed_pressure_reactor_effect` | 16 | Held out. Deliberately weighted toward D3/D4 and toward the hardest/most novel scenarios (the stochastic/gradual case, and all three "non-obvious equipment" D4 scenarios) -- a benchmark's test split should emphasize genuinely difficult cases, not dilute them with easy repeats. |

Defined at `configs/benchmark/splits.yaml`, loaded via
`icab.tasks.splits.load_split_assignment`.

## How leakage is prevented, concretely

1. **Assignment granularity is the scenario, not the task** (see above).
2. **`icab.tasks.splits.validate_split_coverage`** confirms every
   scenario a real task actually references has SOME split assignment
   (an unassigned scenario would mean that scenario's tasks are silently
   excluded from every split-scoped experiment, not a leakage risk
   itself, but a real gap this catches).
3. **`tests/unit/tasks/test_splits.py::test_two_tasks_sharing_a_scenario_always_land_in_the_same_split`**
   checks this DIRECTLY against the real, checked-in task suite and
   `splits.yaml` -- not just against the mechanism's design -- iterating
   every scenario with more than one task and confirming all of that
   scenario's tasks resolve to one split.
4. **`test_real_splits_file_assigns_every_scenario_to_at_most_one_split`**
   checks the real `splits.yaml` itself has no scenario appearing in two
   lists (a scenario in two lists would resolve to whichever list
   `split_for_scenario` checks first -- `development`, then
   `validation`, then `test` -- silently hiding the duplication rather
   than raising; this test exists specifically so that silent behavior
   is at least caught by CI, not just possible).
5. **`tasks_in_split` partitions the whole registry** --
   `test_tasks_in_split_partitions_the_whole_registry_with_no_overlap`
   confirms development/validation/test are pairwise disjoint and their
   union is every real task, so no task is silently dropped or
   double-counted across splits.

## What is NOT (yet) split

- **No task-level held-out subset within a scenario.** Since assignment
  is per-scenario, every task built on a `test`-split scenario is
  entirely in the test split -- there is no notion of "some tasks from
  this scenario are dev, some are test," which would reintroduce the
  leakage risk this design avoids.
- **No cross-validation folds.** With only 9 scenarios, a k-fold split
  would produce folds too small to be meaningful; a single
  development/validation/test partition is the appropriate scale for the
  current suite size.
- **Split sizes are not equal, on purpose.** `test` (16 tasks) is the
  largest split -- deliberately, since it concentrates the hardest
  scenarios (see the table above), not because of an arbitrary
  70/15/15-style ratio.

## Reproducibility

`configs/benchmark/splits.yaml` is checked-in, versioned configuration,
not generated at runtime -- the same file always produces the same
`SplitAssignment`, and adding a new scenario requires an explicit edit
to this file (caught, if forgotten, by
`validate_split_coverage`/`test_real_splits_file_covers_every_scenario_a_real_task_references`
rather than silently defaulting a new scenario into any particular
split).
