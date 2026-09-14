# Benchmark question/answer report: benchmark-tep-v1-9c04f063

Researcher-only artifact -- the ground truth shown below was NEVER visible to the agent during its run; see `tests/unit/reporting/test_qa_report.py` for the isolation check.

---

## d1-qa-current-pressure -- `benchmark-tep-v1-9c04f063-d1-qa-current-pressure-historian-seed1-rep1`

| Field | Value |
|---|---|
| Task ID | d1-qa-current-pressure |
| Scenario ID | d1_reactor_pressure_reading |
| Difficulty | D1 |
| Task type | qa |
| Architecture | historian |
| Seed | 1 |
| Fault ID | (none) |
| Status | completed |

**Question presented to the agent:**

> What is the current reactor pressure, and is it within the normal safe operating range (below the 3000 kPa high-pressure trip threshold)?


**Agent's answer (verbatim):**

> The current reactor pressure is 2712.39 kPa gauge, which is below the 3000 kPa high-pressure trip threshold and therefore within the normal safe operating range.

**Correct answer (ground truth):**

- **Reference conclusion:** Reactor pressure is near its nominal closed-loop steady-state value of approximately 2705 kPa gauge, well below the 3000 kPa high-pressure trip threshold -- the plant is operating normally.

- **Affected equipment:** `urn:icab:equipment:reactor`
- **Expected evidence:** `urn:icab:measurement:reactor_pressure`

**Required evidence:** `urn:icab:measurement:reactor_pressure`

**Evidence provided by the agent:** get_current_value: urn:icab:measurement:reactor_pressure

**Metrics:**

| Metric | Value |
|---|---|
| required_evidence_score | 1.000 |
| canonical_id_score | 1.000 |
| relationship_score | 1.000 |
| conclusion_correctness_score | 1.000 |
| grounding_score | 1.000 |
| completeness_score | 1.000 |
| tool_call_count | 1 |
| context_acquired | 1 |
| context_consumed | 0 |
| latency_ms | 371.231 |
| total_tokens | 1142 |

---

## Overall summary

- **Total runs:** 1
- **Successful:** 1
- **Failed:** 0
- **Skipped:** 0

### By architecture

- **architecture=historian**: n=1 (completed=1, failed=0)
  - conclusion_correctness_score: mean=1.000 (n=1)
  - required_evidence_score: mean=1.000 (n=1)
  - grounding_score: mean=1.000 (n=1)
  - completeness_score: mean=1.000 (n=1)
  - relationship_score: mean=1.000 (n=1)
  - unsupported_numeric_claims_count: mean=0.000 (n=1)
  - tool_call_count: mean=1.000 (n=1)
  - context_acquired_count: mean=1.000 (n=1)
  - context_consumed_count: mean=0.000 (n=1)
  - information_flow.redundant_acquisition_count: mean=0.000 (n=1)
  - information_flow.tool_error_count: mean=0.000 (n=1)
  - total_latency_ms: mean=371.231 (n=1)
  - total_tokens: mean=1142.000 (n=1)

### By difficulty

- **difficulty=D1**: n=1 (completed=1, failed=0)
  - conclusion_correctness_score: mean=1.000 (n=1)
  - required_evidence_score: mean=1.000 (n=1)
  - grounding_score: mean=1.000 (n=1)
  - completeness_score: mean=1.000 (n=1)
  - relationship_score: mean=1.000 (n=1)
  - unsupported_numeric_claims_count: mean=0.000 (n=1)
  - tool_call_count: mean=1.000 (n=1)
  - context_acquired_count: mean=1.000 (n=1)
  - context_consumed_count: mean=0.000 (n=1)
  - information_flow.redundant_acquisition_count: mean=0.000 (n=1)
  - information_flow.tool_error_count: mean=0.000 (n=1)
  - total_latency_ms: mean=371.231 (n=1)
  - total_tokens: mean=1142.000 (n=1)

### By task type

- **task_type=qa**: n=1 (completed=1, failed=0)
  - conclusion_correctness_score: mean=1.000 (n=1)
  - required_evidence_score: mean=1.000 (n=1)
  - grounding_score: mean=1.000 (n=1)
  - completeness_score: mean=1.000 (n=1)
  - relationship_score: mean=1.000 (n=1)
  - unsupported_numeric_claims_count: mean=0.000 (n=1)
  - tool_call_count: mean=1.000 (n=1)
  - context_acquired_count: mean=1.000 (n=1)
  - context_consumed_count: mean=0.000 (n=1)
  - information_flow.redundant_acquisition_count: mean=0.000 (n=1)
  - information_flow.tool_error_count: mean=0.000 (n=1)
  - total_latency_ms: mean=371.231 (n=1)
  - total_tokens: mean=1142.000 (n=1)
