# Research questions

Locked (see `docs/research/experiment-plan.md` and the M1-M12 build-out
spec) -- not to be changed without an explicit reason and clear
documentation:

- **RQ1 -- context capability**: what industrial context can an agent
  actually discover and acquire through a given architecture (or
  combination), and how completely does that cover what a task needs?
- **RQ2 -- architecture**: how does which industrial information
  architecture(s) an agent has access to (MQTT, UNS, OPC UA, i3X,
  Historian, Knowledge Graph, or a combination -- see
  `icab.experiments.architecture_combinations`) affect its ability to
  investigate and diagnose a dynamic industrial process?
- **RQ3 -- efficiency**: how many tool calls, how much context
  acquisition, how much redundant retrieval (see
  `icab.evaluation.information_flow.InformationFlowAnalyzer`), how many
  tokens, and how much latency does an architecture (or combination)
  cost an agent to reach a conclusion?
- **RQ4 -- robustness**: how does agent performance hold up across
  difficulty levels (D1-D4), and does it degrade gracefully or fail
  outright when a needed architecture is unavailable (e.g.
  `historian_only` on a D4 scenario -- see the M10 validation runs in
  `docs/research/experiment-plan.md`)?
- **RQ5 -- grounding**: how well does an agent's conclusion stay
  supported by evidence it actually retrieved through a tool, as opposed
  to values or relationships it merely mentions
  (`icab.evaluation.grounded.GroundedInvestigationEvaluator`, deliberately
  not an LLM-as-judge)?

## Where each is operationalized

| RQ | Primary mechanism |
|---|---|
| RQ1 | `InformationFlowAnalyzer.discovered_canonical_ids`/`acquisitions`; `GroundedInvestigationEvaluator.completeness_score` |
| RQ2 | `icab.experiments.architecture_combinations`; `ExperimentRunner.compare_architectures`/`compare_combinations` |
| RQ3 | `ExperimentRecord.total_latency_ms`/`total_tokens`; `EvaluationReport.tool_call_count`; `InformationFlowReport.redundant_acquisition_count` |
| RQ4 | D1-D4 scenarios (`icab.scenarios`); cross-difficulty comparison of the above metrics |
| RQ5 | `EvaluationReport.grounding_score`/`unsupported_numeric_claims`/`evidence_has_valid_provenance` |

This file records the questions themselves; `hypotheses.md` records the
specific, falsifiable hypotheses (H1-H5) derived from them, and
`experiment-plan.md` records how each has actually been tested against
the live stack so far.
