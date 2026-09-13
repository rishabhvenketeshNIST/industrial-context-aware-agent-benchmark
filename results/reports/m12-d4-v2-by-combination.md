# m12 d4 v2 by combination

- **Grouped by**: architecture_combination_key
- **Held constant**: scenario_id, simulation_seed, llm_model, llm_temperature, max_steps
- **Controls consistent**: True
- **Invalid runs included**: False (0 excluded from metrics)
- **Source runs considered**: 3

Computed entirely from persisted `results/{raw,traces,evaluations}/` artifacts -- no simulator, gateway, or LLM calls were made to produce this report. This is a benchmark-measurement summary (mean/median/stdev/min/max over recorded metrics), not a statistical inference about any hypothesis.

## architecture_combination_key=full

- runs: 1 (completed=1, failed=0, valid=1, legacy_control_only=0)
- run_ids: m10-d4-combo-validation-v2-full

**Effectiveness**

| Metric | n | Mean | Median | Stdev | Min | Max |
|---|---|---|---|---|---|---|
| Investigation correctness | 1 | 0.222 | 0.222 | n/a | 0.222 | 0.222 |
| Evidence score | 1 | 1 | 1 | n/a | 1 | 1 |
| Grounded evidence | 1 | 1 | 1 | n/a | 1 | 1 |
| Context completeness | 1 | 0.667 | 0.667 | n/a | 0.667 | 0.667 |
| Relationship/causal reasoning | 1 | 0 | 0 | n/a | 0 | 0 |
| Temporal reasoning | 1 | 1 | 1 | n/a | 1 | 1 |
| Unsupported claims (lower is better) | 1 | 0 | 0 | n/a | 0 | 0 |

**Efficiency**

| Metric | n | Mean | Median | Stdev | Min | Max |
|---|---|---|---|---|---|---|
| Tool calls | 1 | 24 | 24 | n/a | 24 | 24 |
| Context acquired | 1 | 19 | 19 | n/a | 19 | 19 |
| Context consumed | 1 | 0 | 0 | n/a | 0 | 0 |
| Redundant acquisition | 1 | 5 | 5 | n/a | 5 | 5 |
| Tool errors | 1 | 0 | 0 | n/a | 0 | 0 |
| Latency (ms) | 1 | 9,918 | 9,918 | n/a | 9,918 | 9,918 |
| Token usage | 1 | 84,128 | 84,128 | n/a | 84,128 | 84,128 |

## architecture_combination_key=historian_only

- runs: 1 (completed=1, failed=0, valid=1, legacy_control_only=0)
- run_ids: m10-d4-combo-validation-v2-historian_only

**Effectiveness**

| Metric | n | Mean | Median | Stdev | Min | Max |
|---|---|---|---|---|---|---|
| Investigation correctness | 1 | 0 | 0 | n/a | 0 | 0 |
| Evidence score | 1 | 0 | 0 | n/a | 0 | 0 |
| Grounded evidence | 1 | 1 | 1 | n/a | 1 | 1 |
| Context completeness | 1 | 0 | 0 | n/a | 0 | 0 |
| Relationship/causal reasoning | 1 | 0 | 0 | n/a | 0 | 0 |
| Temporal reasoning | 1 | 0 | 0 | n/a | 0 | 0 |
| Unsupported claims (lower is better) | 1 | 0 | 0 | n/a | 0 | 0 |

**Efficiency**

| Metric | n | Mean | Median | Stdev | Min | Max |
|---|---|---|---|---|---|---|
| Tool calls | 1 | 81 | 81 | n/a | 81 | 81 |
| Context acquired | 1 | 81 | 81 | n/a | 81 | 81 |
| Context consumed | 1 | 0 | 0 | n/a | 0 | 0 |
| Redundant acquisition | 1 | 0 | 0 | n/a | 0 | 0 |
| Tool errors | 1 | 0 | 0 | n/a | 0 | 0 |
| Latency (ms) | 1 | 36,028 | 36,028 | n/a | 36,028 | 36,028 |
| Token usage | 1 | 64,655 | 64,655 | n/a | 64,655 | 64,655 |

## architecture_combination_key=kg_historian

- runs: 1 (completed=1, failed=0, valid=1, legacy_control_only=0)
- run_ids: m10-d4-combo-validation-v2-kg_historian

**Effectiveness**

| Metric | n | Mean | Median | Stdev | Min | Max |
|---|---|---|---|---|---|---|
| Investigation correctness | 1 | 0.167 | 0.167 | n/a | 0.167 | 0.167 |
| Evidence score | 1 | 0.5 | 0.5 | n/a | 0.5 | 0.5 |
| Grounded evidence | 1 | 1 | 1 | n/a | 1 | 1 |
| Context completeness | 1 | 0.667 | 0.667 | n/a | 0.667 | 0.667 |
| Relationship/causal reasoning | 1 | 0.5 | 0.5 | n/a | 0.5 | 0.5 |
| Temporal reasoning | 1 | 1 | 1 | n/a | 1 | 1 |
| Unsupported claims (lower is better) | 1 | 0 | 0 | n/a | 0 | 0 |

**Efficiency**

| Metric | n | Mean | Median | Stdev | Min | Max |
|---|---|---|---|---|---|---|
| Tool calls | 1 | 18 | 18 | n/a | 18 | 18 |
| Context acquired | 1 | 16 | 16 | n/a | 16 | 16 |
| Context consumed | 1 | 0 | 0 | n/a | 0 | 0 |
| Redundant acquisition | 1 | 2 | 2 | n/a | 2 | 2 |
| Tool errors | 1 | 0 | 0 | n/a | 0 | 0 |
| Latency (ms) | 1 | 7,562 | 7,562 | n/a | 7,562 | 7,562 |
| Token usage | 1 | 95,049 | 95,049 | n/a | 95,049 | 95,049 |
