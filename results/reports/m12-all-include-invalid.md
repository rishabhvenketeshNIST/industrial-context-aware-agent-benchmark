# m12 all include invalid

- **Grouped by**: scenario_id, architecture_combination_key
- **Held constant**: llm_model, llm_temperature, max_steps
- **Controls consistent**: False -- varies: {'llm_model': [None, 'gemma-4-31B-it'], 'llm_temperature': [0.0, None], 'max_steps': [10, 20, None]}
- **Invalid runs included**: True (0 excluded from metrics)
- **Source runs considered**: 19

Computed entirely from persisted `results/{raw,traces,evaluations}/` artifacts -- no simulator, gateway, or LLM calls were made to produce this report. This is a benchmark-measurement summary (mean/median/stdev/min/max over recorded metrics), not a statistical inference about any hypothesis.

## scenario_id=d1_reactor_pressure_reading, architecture_combination_key=None

- runs: 6 (completed=6, failed=0, valid=4, legacy_control_only=2)
- run_ids: d1_reactor_pressure_reading-historian+knowledge_graph+uns-4c5da10e, d1_reactor_pressure_reading-historian+knowledge_graph+uns-64db605a, d1_reactor_pressure_reading-historian+knowledge_graph-53fab193, d1_reactor_pressure_reading-historian+knowledge_graph-d6722bdb, d1_reactor_pressure_reading-historian-b3117556, d1_reactor_pressure_reading-historian-dc2c0989

**Effectiveness**

| Metric | n | Mean | Median | Stdev | Min | Max |
|---|---|---|---|---|---|---|
| Investigation correctness | 4 | 1 | 1 | 0 | 1 | 1 |
| Evidence score | 4 | 1 | 1 | 0 | 1 | 1 |
| Grounded evidence | 4 | 0.875 | 1 | 0.25 | 0.5 | 1 |
| Context completeness | 4 | 1 | 1 | 0 | 1 | 1 |
| Relationship/causal reasoning | 4 | 1 | 1 | 0 | 1 | 1 |
| Temporal reasoning | 0 | n/a | n/a | n/a | n/a | n/a |
| Unsupported claims (lower is better) | 4 | 0.25 | 0 | 0.5 | 0 | 1 |

**Efficiency**

| Metric | n | Mean | Median | Stdev | Min | Max |
|---|---|---|---|---|---|---|
| Tool calls | 4 | 7.25 | 7.5 | 6.65 | 1 | 13 |
| Context acquired | 4 | 6.75 | 7 | 7.23 | 0 | 13 |
| Context consumed | 4 | 0.5 | 0.5 | 0.577 | 0 | 1 |
| Redundant acquisition | 0 | n/a | n/a | n/a | n/a | n/a |
| Tool errors | 0 | n/a | n/a | n/a | n/a | n/a |
| Latency (ms) | 0 | n/a | n/a | n/a | n/a | n/a |
| Token usage | 0 | n/a | n/a | n/a | n/a | n/a |

## scenario_id=d2_reactor_context_combination, architecture_combination_key=None

- runs: 6 (completed=6, failed=0, valid=6, legacy_control_only=0)
- run_ids: compare-d2_reactor_context_combination-161b5d1e-historian, compare-d2_reactor_context_combination-161b5d1e-historian+knowledge_graph, validation-llm-comparison-3-historian, validation-llm-comparison-3-historian+knowledge_graph, validation-llm-comparison-historian, validation-llm-comparison-historian+knowledge_graph

**Effectiveness**

| Metric | n | Mean | Median | Stdev | Min | Max |
|---|---|---|---|---|---|---|
| Investigation correctness | 6 | 1 | 1 | 0 | 1 | 1 |
| Evidence score | 6 | 0.833 | 1 | 0.408 | 0 | 1 |
| Grounded evidence | 6 | 1 | 1 | 0 | 1 | 1 |
| Context completeness | 6 | 0.556 | 0.5 | 0.404 | 0 | 1 |
| Relationship/causal reasoning | 6 | 0.333 | 0 | 0.516 | 0 | 1 |
| Temporal reasoning | 0 | n/a | n/a | n/a | n/a | n/a |
| Unsupported claims (lower is better) | 6 | 0 | 0 | 0 | 0 | 0 |

**Efficiency**

| Metric | n | Mean | Median | Stdev | Min | Max |
|---|---|---|---|---|---|---|
| Tool calls | 6 | 7.5 | 7.5 | 4.93 | 3 | 12 |
| Context acquired | 6 | 7.5 | 7.5 | 4.93 | 3 | 12 |
| Context consumed | 6 | 0 | 0 | 0 | 0 | 0 |
| Redundant acquisition | 0 | n/a | n/a | n/a | n/a | n/a |
| Tool errors | 0 | n/a | n/a | n/a | n/a | n/a |
| Latency (ms) | 0 | n/a | n/a | n/a | n/a | n/a |
| Token usage | 0 | n/a | n/a | n/a | n/a | n/a |

## scenario_id=d4_plant_wide_investigation, architecture_combination_key=full

- runs: 2 (completed=2, failed=0, valid=2, legacy_control_only=0)
- run_ids: m10-d4-combo-validation-full, m10-d4-combo-validation-v2-full

**Effectiveness**

| Metric | n | Mean | Median | Stdev | Min | Max |
|---|---|---|---|---|---|---|
| Investigation correctness | 2 | 0.111 | 0.111 | 0.157 | 0 | 0.222 |
| Evidence score | 2 | 0.75 | 0.75 | 0.354 | 0.5 | 1 |
| Grounded evidence | 2 | 1 | 1 | 0 | 1 | 1 |
| Context completeness | 2 | 0.417 | 0.417 | 0.354 | 0.167 | 0.667 |
| Relationship/causal reasoning | 2 | 0 | 0 | 0 | 0 | 0 |
| Temporal reasoning | 2 | 0.5 | 0.5 | 0.707 | 0 | 1 |
| Unsupported claims (lower is better) | 2 | 0 | 0 | 0 | 0 | 0 |

**Efficiency**

| Metric | n | Mean | Median | Stdev | Min | Max |
|---|---|---|---|---|---|---|
| Tool calls | 2 | 19 | 19 | 7.07 | 14 | 24 |
| Context acquired | 2 | 16.5 | 16.5 | 3.54 | 14 | 19 |
| Context consumed | 2 | 0 | 0 | 0 | 0 | 0 |
| Redundant acquisition | 2 | 2.5 | 2.5 | 3.54 | 0 | 5 |
| Tool errors | 2 | 0 | 0 | 0 | 0 | 0 |
| Latency (ms) | 2 | 8,122 | 8,122 | 2,540 | 6,326 | 9,918 |
| Token usage | 2 | 58,134 | 58,134 | 36,761 | 32,140 | 84,128 |

## scenario_id=d4_plant_wide_investigation, architecture_combination_key=historian_only

- runs: 2 (completed=2, failed=0, valid=2, legacy_control_only=0)
- run_ids: m10-d4-combo-validation-historian_only, m10-d4-combo-validation-v2-historian_only

**Effectiveness**

| Metric | n | Mean | Median | Stdev | Min | Max |
|---|---|---|---|---|---|---|
| Investigation correctness | 2 | 0 | 0 | 0 | 0 | 0 |
| Evidence score | 2 | 0 | 0 | 0 | 0 | 0 |
| Grounded evidence | 2 | 1 | 1 | 0 | 1 | 1 |
| Context completeness | 2 | 0 | 0 | 0 | 0 | 0 |
| Relationship/causal reasoning | 2 | 0 | 0 | 0 | 0 | 0 |
| Temporal reasoning | 2 | 0 | 0 | 0 | 0 | 0 |
| Unsupported claims (lower is better) | 2 | 0 | 0 | 0 | 0 | 0 |

**Efficiency**

| Metric | n | Mean | Median | Stdev | Min | Max |
|---|---|---|---|---|---|---|
| Tool calls | 2 | 61 | 61 | 28.3 | 41 | 81 |
| Context acquired | 2 | 61 | 61 | 28.3 | 41 | 81 |
| Context consumed | 2 | 0 | 0 | 0 | 0 | 0 |
| Redundant acquisition | 2 | 0 | 0 | 0 | 0 | 0 |
| Tool errors | 2 | 0 | 0 | 0 | 0 | 0 |
| Latency (ms) | 2 | 27,156 | 27,156 | 12,547 | 18,284 | 36,028 |
| Token usage | 2 | 43,197 | 43,197 | 30,346 | 21,739 | 64,655 |

## scenario_id=d4_plant_wide_investigation, architecture_combination_key=kg_historian

- runs: 2 (completed=2, failed=0, valid=2, legacy_control_only=0)
- run_ids: m10-d4-combo-validation-kg_historian, m10-d4-combo-validation-v2-kg_historian

**Effectiveness**

| Metric | n | Mean | Median | Stdev | Min | Max |
|---|---|---|---|---|---|---|
| Investigation correctness | 2 | 0.0833 | 0.0833 | 0.118 | 0 | 0.167 |
| Evidence score | 2 | 0.25 | 0.25 | 0.354 | 0 | 0.5 |
| Grounded evidence | 2 | 1 | 1 | 0 | 1 | 1 |
| Context completeness | 2 | 0.417 | 0.417 | 0.354 | 0.167 | 0.667 |
| Relationship/causal reasoning | 2 | 0.5 | 0.5 | 0 | 0.5 | 0.5 |
| Temporal reasoning | 2 | 0.5 | 0.5 | 0.707 | 0 | 1 |
| Unsupported claims (lower is better) | 2 | 0 | 0 | 0 | 0 | 0 |

**Efficiency**

| Metric | n | Mean | Median | Stdev | Min | Max |
|---|---|---|---|---|---|---|
| Tool calls | 2 | 14 | 14 | 5.66 | 10 | 18 |
| Context acquired | 2 | 13 | 13 | 4.24 | 10 | 16 |
| Context consumed | 2 | 0 | 0 | 0 | 0 | 0 |
| Redundant acquisition | 2 | 1 | 1 | 1.41 | 0 | 2 |
| Tool errors | 2 | 0 | 0 | 0 | 0 | 0 |
| Latency (ms) | 2 | 5,927 | 5,927 | 2,312 | 4,292 | 7,562 |
| Token usage | 2 | 63,512 | 63,512 | 44,600 | 31,975 | 95,049 |

## scenario_id=d4_plant_wide_investigation, architecture_combination_key=uns_historian_kg

- runs: 1 (completed=1, failed=0, valid=1, legacy_control_only=0)
- run_ids: m11-h2-uns_historian_kg-uns_historian_kg

**Effectiveness**

| Metric | n | Mean | Median | Stdev | Min | Max |
|---|---|---|---|---|---|---|
| Investigation correctness | 1 | 0.222 | 0.222 | n/a | 0.222 | 0.222 |
| Evidence score | 1 | 0.5 | 0.5 | n/a | 0.5 | 0.5 |
| Grounded evidence | 1 | 1 | 1 | n/a | 1 | 1 |
| Context completeness | 1 | 0.5 | 0.5 | n/a | 0.5 | 0.5 |
| Relationship/causal reasoning | 1 | 0 | 0 | n/a | 0 | 0 |
| Temporal reasoning | 1 | 1 | 1 | n/a | 1 | 1 |
| Unsupported claims (lower is better) | 1 | 0 | 0 | n/a | 0 | 0 |

**Efficiency**

| Metric | n | Mean | Median | Stdev | Min | Max |
|---|---|---|---|---|---|---|
| Tool calls | 1 | 14 | 14 | n/a | 14 | 14 |
| Context acquired | 1 | 13 | 13 | n/a | 13 | 13 |
| Context consumed | 1 | 0 | 0 | n/a | 0 | 0 |
| Redundant acquisition | 1 | 1 | 1 | n/a | 1 | 1 |
| Tool errors | 1 | 0 | 0 | n/a | 0 | 0 |
| Latency (ms) | 1 | 5,847 | 5,847 | n/a | 5,847 | 5,847 |
| Token usage | 1 | 57,121 | 57,121 | n/a | 57,121 | 57,121 |
