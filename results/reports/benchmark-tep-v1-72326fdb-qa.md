# Benchmark question/answer report: benchmark-tep-v1-72326fdb

Researcher-only artifact -- the ground truth shown below was NEVER visible to the agent during its run; see `tests/unit/reporting/test_qa_report.py` for the isolation check.

---

## d1-qa-current-pressure -- `benchmark-tep-v1-72326fdb-d1-qa-current-pressure-historian-seed1-rep1`

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

> Reactor: urn:icab:measurement:reactor_cooling_water_outlet_temperature_meas=95.10441830224873 degC; urn:icab:measurement:reactor_feed_a_concentration=30.534977351458473 mol %; urn:icab:measurement:reactor_feed_b_concentration=9.033231786513653 mol %; urn:icab:measurement:reactor_feed_c_concentration=27.721481604617953 mol %; urn:icab:measurement:reactor_feed_d_concentration=7.0818308469430775 mol %; urn:icab:measurement:reactor_feed_e_concentration=19.42126213757921 mol %; urn:icab:measurement:reactor_feed_f_concentration=1.6991780215870544 mol %; urn:icab:measurement:reactor_feed_flow=41.20724164140155 kscmh; urn:icab:measurement:reactor_level=75.99928204577297 %; urn:icab:measurement:reactor_pressure=2712.3935955989655 kPa gauge; urn:icab:measurement:reactor_temperature=120.38710275664974 degC

**Correct answer (ground truth):**

- **Reference conclusion:** Reactor pressure is near its nominal closed-loop steady-state value of approximately 2705 kPa gauge, well below the 3000 kPa high-pressure trip threshold -- the plant is operating normally.

- **Affected equipment:** `urn:icab:equipment:reactor`
- **Expected evidence:** `urn:icab:measurement:reactor_pressure`

**Required evidence:** `urn:icab:measurement:reactor_pressure`

**Evidence provided by the agent:** browse_uns: site/tep/reactor, get_entity_relationships: urn:icab:equipment:reactor, get_current_value: urn:icab:measurement:reactor_cooling_water_outlet_temperature_meas, get_current_value: urn:icab:measurement:reactor_feed_a_concentration, get_current_value: urn:icab:measurement:reactor_feed_b_concentration, get_current_value: urn:icab:measurement:reactor_feed_c_concentration, get_current_value: urn:icab:measurement:reactor_feed_d_concentration, get_current_value: urn:icab:measurement:reactor_feed_e_concentration, get_current_value: urn:icab:measurement:reactor_feed_f_concentration, get_current_value: urn:icab:measurement:reactor_feed_flow, get_current_value: urn:icab:measurement:reactor_level, get_current_value: urn:icab:measurement:reactor_pressure, get_current_value: urn:icab:measurement:reactor_temperature

**Metrics:**

| Metric | Value |
|---|---|
| required_evidence_score | 1.000 |
| canonical_id_score | 0.923 |
| relationship_score | 1.000 |
| conclusion_correctness_score | 1.000 |
| grounding_score | 1.000 |
| completeness_score | 1.000 |
| tool_call_count | 13 |
| context_acquired | 13 |
| context_consumed | 1 |
| latency_ms | 4819.809 |
| total_tokens | n/a |

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
  - tool_call_count: mean=13.000 (n=1)
  - context_acquired_count: mean=13.000 (n=1)
  - context_consumed_count: mean=1.000 (n=1)
  - information_flow.redundant_acquisition_count: mean=0.000 (n=1)
  - information_flow.tool_error_count: mean=0.000 (n=1)
  - total_latency_ms: mean=4819.809 (n=1)

### By difficulty

- **difficulty=D1**: n=1 (completed=1, failed=0)
  - conclusion_correctness_score: mean=1.000 (n=1)
  - required_evidence_score: mean=1.000 (n=1)
  - grounding_score: mean=1.000 (n=1)
  - completeness_score: mean=1.000 (n=1)
  - relationship_score: mean=1.000 (n=1)
  - unsupported_numeric_claims_count: mean=0.000 (n=1)
  - tool_call_count: mean=13.000 (n=1)
  - context_acquired_count: mean=13.000 (n=1)
  - context_consumed_count: mean=1.000 (n=1)
  - information_flow.redundant_acquisition_count: mean=0.000 (n=1)
  - information_flow.tool_error_count: mean=0.000 (n=1)
  - total_latency_ms: mean=4819.809 (n=1)

### By task type

- **task_type=qa**: n=1 (completed=1, failed=0)
  - conclusion_correctness_score: mean=1.000 (n=1)
  - required_evidence_score: mean=1.000 (n=1)
  - grounding_score: mean=1.000 (n=1)
  - completeness_score: mean=1.000 (n=1)
  - relationship_score: mean=1.000 (n=1)
  - unsupported_numeric_claims_count: mean=0.000 (n=1)
  - tool_call_count: mean=13.000 (n=1)
  - context_acquired_count: mean=13.000 (n=1)
  - context_consumed_count: mean=1.000 (n=1)
  - information_flow.redundant_acquisition_count: mean=0.000 (n=1)
  - information_flow.tool_error_count: mean=0.000 (n=1)
  - total_latency_ms: mean=4819.809 (n=1)
