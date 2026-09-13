# H2: Structured semantics reduce context/tool usage.

- **Metric**: tool_call_count (higher supports H: False)
- **Treatment**: uns_historian_kg
- **Control**: kg_historian
- **Controls consistent across arm records**: True

| Metric | n | Mean | Median | Stdev | Min | Max |
|---|---|---|---|---|---|---|
| Treatment | 1 | 14 | 14 | n/a | 14 | 14 |
| Control | 1 | 18 | 18 | n/a | 18 | 18 |

- **Observed difference (treatment - control)**: -4
- **Direction supports hypothesis**: True
- **Runs**: treatment n=1 (m11-h2-uns_historian_kg-uns_historian_kg), control n=1 (m10-d4-combo-validation-v2-kg_historian)

## Limitations

- Descriptive comparison only -- not a significance test, and not proof or disproof of the hypothesis.
- Sample size is small (treatment n=1, control n=1) -- far too small for statistical inference. Treat this as a single (or a handful of) real observation(s), not a validated effect.

> Descriptive comparison of a small number of real runs -- not a significance test, and not proof or disproof of the hypothesis. See docs/research/experiment-plan.md.