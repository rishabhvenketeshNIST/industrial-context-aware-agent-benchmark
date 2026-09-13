# H4: Selective retrieval beats undifferentiated context.

- **Metric**: information_flow.redundant_acquisition_count (higher supports H: False)
- **Treatment**: kg_historian
- **Control**: full
- **Controls consistent across arm records**: True

| Metric | n | Mean | Median | Stdev | Min | Max |
|---|---|---|---|---|---|---|
| Treatment | 1 | 2 | 2 | n/a | 2 | 2 |
| Control | 1 | 5 | 5 | n/a | 5 | 5 |

- **Observed difference (treatment - control)**: -3
- **Direction supports hypothesis**: True
- **Runs**: treatment n=1 (m10-d4-combo-validation-v2-kg_historian), control n=1 (m10-d4-combo-validation-v2-full)

## Limitations

- Descriptive comparison only -- not a significance test, and not proof or disproof of the hypothesis.
- Sample size is small (treatment n=1, control n=1) -- far too small for statistical inference. Treat this as a single (or a handful of) real observation(s), not a validated effect.

> Descriptive comparison of a small number of real runs -- not a significance test, and not proof or disproof of the hypothesis. See docs/research/experiment-plan.md.