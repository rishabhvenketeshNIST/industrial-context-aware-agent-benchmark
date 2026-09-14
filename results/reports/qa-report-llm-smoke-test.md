# ICAB benchmark: qa-report-llm-smoke-test

- **Grouped by**: task_type, difficulty, architecture
- **Held constant**: scenario_id, simulation_seed, llm_model, llm_temperature, max_steps
- **Controls consistent**: True
- **Invalid runs included**: False (0 excluded from metrics)
- **Source runs considered**: 1

Computed entirely from persisted `results/{raw,traces,evaluations}/` artifacts -- no simulator, gateway, or LLM calls were made to produce this report. This is a benchmark-measurement summary (mean/median/stdev/min/max over recorded metrics), not a statistical inference about any hypothesis.

## task_type=qa, difficulty=D1, architecture=historian

- runs: 1 (completed=1, failed=0, valid=1, legacy_control_only=0)
- run_ids: qa-report-llm-smoke-test-d1-qa-current-pressure-historian-seed1-rep1

**Effectiveness**

| Metric | n | Mean | Median | Stdev | Min | Max |
|---|---|---|---|---|---|---|
| Investigation correctness | 1 | 1 | 1 | n/a | 1 | 1 |
| Evidence score | 1 | 1 | 1 | n/a | 1 | 1 |
| Grounded evidence | 1 | 1 | 1 | n/a | 1 | 1 |
| Context completeness | 1 | 1 | 1 | n/a | 1 | 1 |
| Relationship/causal reasoning | 1 | 1 | 1 | n/a | 1 | 1 |
| Temporal reasoning | 0 | n/a | n/a | n/a | n/a | n/a |
| Unsupported claims (lower is better) | 1 | 0 | 0 | n/a | 0 | 0 |

**Efficiency**

| Metric | n | Mean | Median | Stdev | Min | Max |
|---|---|---|---|---|---|---|
| Tool calls | 1 | 1 | 1 | n/a | 1 | 1 |
| Context acquired | 1 | 1 | 1 | n/a | 1 | 1 |
| Context consumed | 1 | 0 | 0 | n/a | 0 | 0 |
| Redundant acquisition | 1 | 0 | 0 | n/a | 0 | 0 |
| Tool errors | 1 | 0 | 0 | n/a | 0 | 0 |
| Latency (ms) | 1 | 359 | 359 | n/a | 359 | 359 |
| Token usage | 1 | 1,142 | 1,142 | n/a | 1,142 | 1,142 |
