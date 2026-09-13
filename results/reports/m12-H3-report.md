# H3: Knowledge graph relationships improve causal reasoning.

- **Metric**: relationship_score (higher supports H: True)
- **Treatment**: kg_historian
- **Control**: historian_only
- **Controls consistent across arm records**: True

| Metric | n | Mean | Median | Stdev | Min | Max |
|---|---|---|---|---|---|---|
| Treatment | 1 | 0.5 | 0.5 | n/a | 0.5 | 0.5 |
| Control | 1 | 0 | 0 | n/a | 0 | 0 |

- **Observed difference (treatment - control)**: 0.5
- **Direction supports hypothesis**: True
- **Runs**: treatment n=1 (m10-d4-combo-validation-v2-kg_historian), control n=1 (m10-d4-combo-validation-v2-historian_only)

## Limitations

- Descriptive comparison only -- not a significance test, and not proof or disproof of the hypothesis.
- Sample size is small (treatment n=1, control n=1) -- far too small for statistical inference. Treat this as a single (or a handful of) real observation(s), not a validated effect.

> Descriptive comparison of a small number of real runs -- not a significance test, and not proof or disproof of the hypothesis. See docs/research/experiment-plan.md.