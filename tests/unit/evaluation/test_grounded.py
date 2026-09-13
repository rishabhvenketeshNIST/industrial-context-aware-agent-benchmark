from datetime import UTC, datetime

from icab.agent.interface import EvidenceReference, InvestigationResult, TerminationReason
from icab.evaluation.grounded import GroundedInvestigationEvaluator
from icab.scenarios import BenchmarkScenarioRegistry
from icab.trace.models import TraceEvent

SCENARIOS_DIR = "configs/benchmark/scenarios"


def _event(
    tool: str,
    result: dict | None = None,
    *,
    context_acquired: list[str] | None = None,
    context_consumed: list[str] | None = None,
) -> TraceEvent:
    return TraceEvent(
        timestamp=datetime(2026, 9, 13, tzinfo=UTC),
        step=1,
        action="tool_call",
        tool=tool,
        result=result,
        context_acquired=context_acquired or [],
        context_consumed=context_consumed or [],
    )


def _d1_scenario():
    return BenchmarkScenarioRegistry(SCENARIOS_DIR).get("d1_reactor_pressure_reading")


def _d3_scenario():
    return BenchmarkScenarioRegistry(SCENARIOS_DIR).get("d3_reactor_pressure_deviation")


def test_required_evidence_hit_and_miss():
    scenario = _d1_scenario()
    evaluator = GroundedInvestigationEvaluator()

    hit_result = InvestigationResult(
        objective=scenario.objective,
        conclusion="Reactor pressure (urn:icab:measurement:reactor_pressure) is normal.",
    )
    report = evaluator.evaluate(scenario, hit_result, trace=[])
    assert report.required_evidence_score == 1.0

    miss_result = InvestigationResult(objective=scenario.objective, conclusion="Everything is fine.")
    report = evaluator.evaluate(scenario, miss_result, trace=[])
    assert report.required_evidence_score == 0.0


def test_canonical_id_validity_only_checked_for_cim_sourced_evidence():
    scenario = _d1_scenario()
    evaluator = GroundedInvestigationEvaluator()

    result = InvestigationResult(
        objective=scenario.objective,
        conclusion="ok",
        evidence=[
            EvidenceReference(source="get_current_value", identifier="urn:icab:measurement:reactor_pressure"),
            EvidenceReference(source="get_current_value", identifier="not-a-canonical-id"),
            EvidenceReference(source="opcua_read", identifier="ns=2;i=1"),
        ],
    )

    report = evaluator.evaluate(scenario, result, trace=[])

    assert report.canonical_id_validity == {
        "urn:icab:measurement:reactor_pressure": True,
        "not-a-canonical-id": False,
    }
    assert report.canonical_id_score == 0.5
    # The OPC UA node id is a different, valid identifier format -- not
    # scored against the canonical-id pattern at all.
    assert "ns=2;i=1" not in report.canonical_id_validity


def test_evidence_missing_source_or_identifier_fails_provenance():
    scenario = _d1_scenario()
    evaluator = GroundedInvestigationEvaluator()

    result = InvestigationResult(
        objective=scenario.objective,
        conclusion="ok",
        evidence=[EvidenceReference(source="", identifier="")],
    )

    report = evaluator.evaluate(scenario, result, trace=[])
    assert report.evidence_has_valid_provenance is False


def test_temporal_evidence_required_for_d3_not_d1():
    evaluator = GroundedInvestigationEvaluator()

    d1_result = InvestigationResult(objective="obj", conclusion="ok")
    d1_report = evaluator.evaluate(_d1_scenario(), d1_result, trace=[])
    assert d1_report.temporal_evidence_required is False

    d3_report = evaluator.evaluate(_d3_scenario(), d1_result, trace=[])
    assert d3_report.temporal_evidence_required is True
    assert d3_report.temporal_evidence_acquired is False

    trace_with_history = [_event("get_historical_values", {"observations": []})]
    d3_report_with_history = evaluator.evaluate(_d3_scenario(), d1_result, trace=trace_with_history)
    assert d3_report_with_history.temporal_evidence_acquired is True


def test_relationship_confirmed_from_trace_result():
    scenario = _d3_scenario()
    evaluator = GroundedInvestigationEvaluator()
    result = InvestigationResult(objective=scenario.objective, conclusion="ok")

    unconfirmed = evaluator.evaluate(scenario, result, trace=[])
    assert unconfirmed.relationship_score == 0.0
    assert unconfirmed.expected_relationships[0].confirmed is False

    trace = [
        _event(
            "get_entity_relationships",
            {
                "relationships": [
                    {
                        "subject": "urn:icab:equipment:reactor",
                        "predicate": "MONITORS",
                        "object": "urn:icab:measurement:reactor_pressure",
                    }
                ]
            },
        )
    ]
    confirmed = evaluator.evaluate(scenario, result, trace=trace)
    assert confirmed.relationship_score == 1.0
    assert confirmed.expected_relationships[0].confirmed is True


def test_relationship_score_is_vacuous_when_none_expected():
    scenario = _d1_scenario()  # no expected_relationships
    evaluator = GroundedInvestigationEvaluator()
    result = InvestigationResult(objective=scenario.objective, conclusion="ok")

    report = evaluator.evaluate(scenario, result, trace=[])
    assert report.relationship_score == 1.0
    assert report.expected_relationships == []


def test_root_cause_identified_accepts_idv_phrasing_variants():
    scenario = _d3_scenario()
    evaluator = GroundedInvestigationEvaluator()

    for phrasing in ("idv_01", "IDV 1", "idv(1)", "IDV(1) A/C ratio disturbance"):
        result = InvestigationResult(
            objective=scenario.objective,
            conclusion=f"Root cause is {phrasing}.",
        )
        report = evaluator.evaluate(scenario, result, trace=[])
        assert report.root_cause_identified is True, phrasing

    unrelated = InvestigationResult(objective=scenario.objective, conclusion="No obvious cause found.")
    report = evaluator.evaluate(scenario, unrelated, trace=[])
    assert report.root_cause_identified is False


def test_conclusion_correctness_score_combines_root_cause_and_assets():
    scenario = _d3_scenario()
    evaluator = GroundedInvestigationEvaluator()

    full = InvestigationResult(
        objective=scenario.objective,
        conclusion=(
            "idv_01 caused reactor pressure, separator pressure, stripper "
            "level, and compressor work to fall, affecting the reactor, "
            "separator, stripper, and compressor."
        ),
    )
    report = evaluator.evaluate(scenario, full, trace=[])
    assert report.conclusion_correctness_score == 1.0

    partial = InvestigationResult(objective=scenario.objective, conclusion="idv_01 is the cause.")
    report = evaluator.evaluate(scenario, partial, trace=[])
    assert 0.0 < report.conclusion_correctness_score < 1.0


def test_unsupported_numeric_claims_flags_fabricated_values():
    scenario = _d1_scenario()
    evaluator = GroundedInvestigationEvaluator()

    trace = [_event("get_current_value", {"observation": {"value": 2705.3}})]

    grounded_result = InvestigationResult(
        objective=scenario.objective,
        conclusion="Reactor pressure is 2705.3 kPa.",
    )
    report = evaluator.evaluate(scenario, grounded_result, trace=trace)
    assert report.unsupported_numeric_claims == []
    assert report.grounding_score == 1.0

    fabricated_result = InvestigationResult(
        objective=scenario.objective,
        conclusion="Reactor pressure is 9999.9 kPa.",
    )
    report = evaluator.evaluate(scenario, fabricated_result, trace=trace)
    assert 9999.9 in report.unsupported_numeric_claims
    assert report.grounding_score == 0.0


def test_numbers_given_in_the_objective_are_not_flagged_as_unsupported():
    """A number the agent was told (e.g. a stated trip threshold), not one it fabricated."""

    scenario = _d1_scenario()
    assert "3000" in scenario.objective  # the scenario's high-pressure trip threshold

    evaluator = GroundedInvestigationEvaluator()
    trace = [_event("get_current_value", {"observation": {"value": 2705.3}})]

    result = InvestigationResult(
        objective=scenario.objective,
        conclusion="Reactor pressure is 2705.3 kPa, below the 3000 kPa trip threshold.",
    )
    report = evaluator.evaluate(scenario, result, trace=trace)

    assert report.unsupported_numeric_claims == []
    assert report.grounding_score == 1.0


def test_context_acquired_and_consumed_come_from_trace():
    scenario = _d1_scenario()
    evaluator = GroundedInvestigationEvaluator()
    result = InvestigationResult(objective=scenario.objective, conclusion="ok")

    trace = [
        _event("browse_uns", {}, context_acquired=["site/tep/reactor"]),
        _event(
            "get_current_value",
            {},
            context_acquired=["urn:icab:measurement:reactor_pressure"],
            context_consumed=["site/tep/reactor"],
        ),
    ]

    report = evaluator.evaluate(scenario, result, trace=trace)

    assert report.context_acquired == [
        "site/tep/reactor",
        "urn:icab:measurement:reactor_pressure",
    ]
    assert report.context_consumed == ["site/tep/reactor"]
    assert report.tool_call_count == 2
    assert report.unique_tools_used == ["browse_uns", "get_current_value"]


def test_completeness_penalizes_step_budget_exceeded():
    scenario = _d1_scenario()
    evaluator = GroundedInvestigationEvaluator()

    submitted = InvestigationResult(
        objective=scenario.objective,
        conclusion="urn:icab:measurement:reactor_pressure is normal.",
        termination=TerminationReason.SUBMITTED,
    )
    exceeded = InvestigationResult(
        objective=scenario.objective,
        conclusion="urn:icab:measurement:reactor_pressure is normal.",
        termination=TerminationReason.STEP_BUDGET_EXCEEDED,
    )

    submitted_report = evaluator.evaluate(scenario, submitted, trace=[])
    exceeded_report = evaluator.evaluate(scenario, exceeded, trace=[])

    assert submitted_report.terminated_properly is True
    assert exceeded_report.terminated_properly is False
    assert exceeded_report.completeness_score < submitted_report.completeness_score


def test_relationship_mention_alone_does_not_count_as_required_evidence():
    """
    Regression test for a real, demonstrated false positive: an agent that
    reads the WRONG measurement (a legacy id) but also happens to call
    get_entity_relationships (which incidentally mentions the ground
    truth's required real canonical id, as a related object -- not a
    retrieved value) must NOT be credited with having found that evidence.
    """

    scenario = _d1_scenario()  # requires urn:icab:measurement:reactor_pressure
    evaluator = GroundedInvestigationEvaluator()

    result = InvestigationResult(
        objective=scenario.objective,
        conclusion="Current reactor pressure is 2834.0 kPa.",  # wrong data, wrong id
    )

    trace = [
        # The agent queried the WRONG (legacy) measurement -- not the
        # ground truth's required real id.
        _event(
            "get_current_value",
            {
                "observation": {
                    "measurement_id": "urn:icab:measurement:tep_pv_reactor_pressure",
                    "value": 2834.0,
                }
            },
        ),
        # An unrelated relationship listing that happens to mention the
        # REQUIRED real id as a related object -- this is real, legitimate
        # knowledge-graph content, not fabricated -- but the agent never
        # retrieved ITS value.
        _event(
            "get_entity_relationships",
            {
                "relationships": [
                    {
                        "subject": "urn:icab:equipment:reactor",
                        "predicate": "MONITORS",
                        "object": "urn:icab:measurement:reactor_pressure",
                    },
                    {
                        "subject": "urn:icab:equipment:reactor",
                        "predicate": "MONITORS",
                        "object": "urn:icab:measurement:tep_pv_reactor_pressure",
                    },
                ]
            },
        ),
    ]

    report = evaluator.evaluate(scenario, result, trace=trace)

    assert report.required_evidence_hits == {"urn:icab:measurement:reactor_pressure": False}
    assert report.required_evidence_score == 0.0


def test_relationship_confirmation_is_scoped_to_the_current_generation():
    scenario = _d3_scenario()
    evaluator = GroundedInvestigationEvaluator()
    result = InvestigationResult(objective=scenario.objective, conclusion="ok")

    trace = [
        _event(
            "get_entity_relationships",
            {
                "relationships": [
                    {
                        "subject": "urn:icab:equipment:reactor",
                        "predicate": "MONITORS",
                        "object": "urn:icab:measurement:reactor_pressure",
                        "generation_id": "some-other-run",
                    }
                ]
            },
        )
    ]

    # Ungated (no generation_id passed): matches, as before M9.
    ungated = evaluator.evaluate(scenario, result, trace=trace)
    assert ungated.relationship_score == 1.0

    # Scoped to a DIFFERENT generation than the one that wrote it: the
    # match is rejected, closing the cross-run false-positive path.
    scoped_to_other_run = evaluator.evaluate(
        scenario, result, trace=trace, generation_id="this-run"
    )
    assert scoped_to_other_run.relationship_score == 0.0

    # Scoped to the SAME generation that wrote it: confirmed.
    scoped_to_same_run = evaluator.evaluate(
        scenario, result, trace=trace, generation_id="some-other-run"
    )
    assert scoped_to_same_run.relationship_score == 1.0
