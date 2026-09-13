# Investigation Evaluation (M8)

## Two evaluators, on purpose

- `icab.evaluation.investigation.InvestigationEvaluator` -- the original,
  simple evaluator: keyword-substring matching of `InvestigationCase.
  required_evidence` against the stringified findings/evidence.
  **Unchanged.** Existing callers/tests keep working exactly as before.
- `icab.evaluation.grounded.GroundedInvestigationEvaluator` (this
  milestone) -- a stronger, structured evaluator that scores an
  `InvestigationResult` against a `BenchmarkScenario`'s ground truth
  (`icab.scenarios`, M5) and its recorded trace
  (`list[icab.trace.models.TraceEvent]`).

The new evaluator is additive specifically so nothing existing had to be
touched to add it -- `InvestigationCase`-based scoring and
`BenchmarkScenario`-based scoring are two different, both-supported paths.

## Deterministic by design -- no LLM-as-judge

Every dimension below is computed from structured data already present in
the `InvestigationResult`/trace/ground truth: string containment, exact
dict/tuple matching, numeric tolerance comparison. The same
`(scenario, result, trace)` triple always produces the same
`EvaluationReport` -- there is no second model call, no sampling, nothing
non-reproducible. This was a hard requirement for the milestone and is
verified structurally, not just claimed: `GroundedInvestigationEvaluator`
imports nothing LLM-related.

## What each field checks

| `EvaluationReport` field(s) | Checks | How |
|---|---|---|
| `required_evidence_hits`/`_score` | Required evidence | Ground truth's `expected_evidence` canonical ids found (substring) in the conclusion/findings text. |
| `evidence_has_valid_provenance` | Evidence provenance | Every `EvidenceReference` has a non-empty `source` and `identifier`. |
| `canonical_id_validity`/`_score` | Canonical IDs | For evidence sourced from CIM/canonical-id tools (`get_current_value`, `get_historical_values`, `get_entity_relationships`, `browse_uns`) only -- OPC UA node ids, MQTT topics, and i3X element ids are different, equally valid formats and are correctly excluded from this check. |
| `temporal_evidence_required`/`_acquired` | Temporal evidence | Required whenever the scenario is D3/D4 or has a `root_cause_disturbance`; acquired iff the trace contains a `get_historical_values` or `i3x_get_history` call. |
| `expected_relationships`/`relationship_score` | Relationship evidence | Each ground-truth `(subject, predicate, object)` triple checked against the *actual* relationships returned by a real `get_entity_relationships` call recorded in the trace -- not just that the tool was called. |
| `root_cause_identified`, `affected_assets_mentioned`, `conclusion_correctness_score` | Structured conclusion correctness / causal reasoning | Whether the ground truth's `root_cause_disturbance` (accepting `idv_01`/`IDV 1`/`idv(1)` phrasing variants) and `affected_measurements`/`affected_equipment` are mentioned in the conclusion. **Documented limitation:** this checks that the right concepts appear, not that the agent's causal argument is sound -- a correct-sounding guess scores identically to a properly reasoned one. Full causal verification is out of scope for a deterministic evaluator. |
| `unsupported_numeric_claims`, `grounding_score` | Unsupported claims | Every number appearing in the conclusion is checked against every number appearing anywhere in the trace's recorded tool results (recursively), within a 2%-or-1.0 tolerance; numbers that don't match anything actually observed are flagged as unsupported/fabricated. |
| `context_acquired`, `context_consumed` | Acquired vs. consumed context | Read directly from `TraceEvent.context_acquired`/`.context_consumed` -- the same fields `ArchitectureAwareAgent` and `LLMInvestigationAgent` already populate; not recomputed. |
| `tool_call_count`, `unique_tools_used`, `terminated_properly`, `completeness_score` | Investigation completeness | `terminated_properly` is `False` exactly when `InvestigationResult.termination == TerminationReason.STEP_BUDGET_EXCEEDED` (see below); `completeness_score` averages required-evidence, relationship, and termination scores. |

## `InvestigationResult.termination` (new, additive field)

Before this milestone, whether an LLM investigation actually concluded (vs.
running out of its step budget) was only recoverable by string-matching
`LLMInvestigationAgent`'s exact fallback conclusion text -- fragile, and not
something a deterministic baseline agent's result carried at all.
`InvestigationResult` gained `termination: TerminationReason = SUBMITTED`
(`SUBMITTED` / `NO_TOOL_CALL` / `STEP_BUDGET_EXCEEDED`), defaulting to
`SUBMITTED` so every existing caller -- including the three deterministic
baseline agents, none of which were touched -- keeps working unchanged.
`LLMInvestigationAgent.run()` now sets it explicitly at each of its three
return points.

## Verified against a real trace, not just hand-written dicts

`tests/integration/test_grounded_evaluator_real_trace.py` runs the D3
scenario against the real simulator/historian/knowledge graph, makes real
`get_historical_values`/`get_entity_relationships` calls through the real
FastAPI gateway, and evaluates the resulting real
`TraceCollector`/`InvestigationResult`. This exists specifically to catch
the case where a hand-typed unit-test fixture dict doesn't actually match
the real, serialized shape of a gateway tool response (e.g.
`GetEntityRelationshipsResponse.model_dump(mode="json")`'s exact
`relationships[i]["predicate"]`/`["object"]` keys) -- unit tests alone
would not have caught a schema-shape mismatch like that.
