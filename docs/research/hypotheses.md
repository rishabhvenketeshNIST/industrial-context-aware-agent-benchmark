# Hypotheses

Locked (see `docs/research/research-questions.md` and the M1-M12
build-out spec) -- not to be changed without an explicit reason and clear
documentation. Verbatim:

- **H1**: Structured context improves investigation accuracy.
- **H2**: Structured semantics reduce context/tool usage.
- **H3**: Knowledge graph relationships improve causal reasoning.
- **H4**: Selective retrieval beats undifferentiated context.
- **H5**: Grounded data and relationships reduce unsupported claims.

None of these is claimed to be proven by ICAB itself. Per the M11 build
direction: "build the infrastructure needed to test H1-H5 ... do not
claim that these hypotheses are proven. The implementation should enable
controlled experiments that can test them." `icab.experiments.hypotheses`
is that infrastructure -- a documented mapping from each hypothesis to a
specific treatment/control architecture-combination pair and an existing,
deterministic metric, plus a descriptive (not inferential) comparison
function. See `docs/research/experiment-plan.md` for how each has
actually been run against the live stack, including its real (non-zero)
sample-size limitations.

## H1 -- Structured context improves investigation accuracy

- **Arms**: treatment = `kg_historian`, control = `historian_only`
  (`icab.experiments.architecture_combinations`).
- **Metric**: `EvaluationReport.conclusion_correctness_score` (higher
  supports H1).
- **Isolates**: relational/semantic structure (the knowledge graph) added
  on top of the same historian access -- nothing else differs between the
  arms.

## H2 -- Structured semantics reduce context/tool usage

- **Arms**: treatment = `uns_historian_kg`, control = `kg_historian`.
- **Metric**: `EvaluationReport.tool_call_count` (lower supports H2).
- **Isolates**: UNS semantic discovery (browsing a named namespace) added
  on top of the SAME knowledge_graph+historian access.

## H3 -- Knowledge graph relationships improve causal reasoning

- **Arms**: treatment = `kg_historian`, control = `historian_only` (same
  arms as H1, different metric).
- **Metric**: `EvaluationReport.relationship_score` (higher supports H3)
  -- specifically whether the scenario's `expected_relationships` were
  confirmed, as distinct from H1's overall-correctness metric.

## H4 -- Selective retrieval beats undifferentiated context

- **Arms**: treatment = `kg_historian` (a small, curated set -- selective),
  control = `full` (every architecture at once -- undifferentiated).
- **Metric**: `InformationFlowReport.redundant_acquisition_count` (lower
  supports H4) -- checked alongside `conclusion_correctness_score`/
  `required_evidence_score` so a lower redundancy count is only read as
  supporting H4 if it didn't come at the cost of a worse outcome.

## H5 -- Grounded data and relationships reduce unsupported claims

- **Arms**: treatment = `kg_historian`, control = `historian_only` (same
  arms as H1/H3, different metric).
- **Metric**: the count of `EvaluationReport.unsupported_numeric_claims`
  (lower supports H5) -- numeric values in the conclusion the agent never
  actually retrieved through a tool. `grounding_score` (the complementary
  0-1 summary of the same check) is reported alongside it.

## Why `kg_historian`/`historian_only` recur across H1/H3/H5

They are literally the "structured vs. unstructured" baseline pair --
adding exactly one thing (the knowledge graph) to the same historian
access. Reusing one clean, controlled comparison to speak to three
different hypotheses via three different metrics on the SAME runs is
realistic hypothesis testing, not a shortcut: it means a single real
experiment (one scenario preparation, two architecture configurations)
produces three independent pieces of evidence rather than one.

## Running these

    uv run python scripts/run_hypothesis_experiment.py \
        --scenario d4_plant_wide_investigation --hypothesis H3

resolves the hypothesis's treatment/control combinations, runs them
against one shared scenario preparation via
`ExperimentRunner.compare_combinations`, computes a
`HypothesisTestResult` via `icab.experiments.hypotheses.evaluate_hypothesis`,
and persists it to `results/hypotheses/<experiment_id>-<H?>.json`
alongside the usual `results/{raw,traces,evaluations,aggregate}/` files
for the underlying runs.

`evaluate_hypothesis`/`evaluate_all_hypotheses` can also be called
directly against any set of already-persisted `ExperimentRecord`s (they
need not share an `experiment_id` -- only the controls that make them a
valid comparison, which `ExperimentResultStore.write_aggregate`'s
`HeterogeneousControlsError` check enforces separately), so a hypothesis
comparison can be recomputed from prior runs (e.g. an existing M10
architecture-combination comparison) without spending more LLM calls.
