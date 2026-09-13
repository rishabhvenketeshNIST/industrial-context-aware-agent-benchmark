from datetime import UTC, datetime

from icab.evaluation.information_flow import InformationFlowAnalyzer
from icab.trace.models import TraceEvent

REACTOR_PRESSURE_ID = "urn:icab:measurement:reactor_pressure"


def _event(tool: str, result: dict, step: int = 1) -> TraceEvent:
    return TraceEvent(
        timestamp=datetime(2026, 9, 13, tzinfo=UTC),
        step=step,
        action="tool_call",
        tool=tool,
        result=result,
    )


def test_historian_acquisition_is_resolved_directly():
    trace = [
        _event(
            "get_current_value",
            {"observation": {"measurement_id": REACTOR_PRESSURE_ID, "value": 2705.0}},
        )
    ]

    report = InformationFlowAnalyzer().analyze(trace)

    assert len(report.acquisitions) == 1
    assert report.acquisitions[0].canonical_id == REACTOR_PRESSURE_ID
    assert report.acquisitions[0].architecture == "historian"
    assert report.unresolved_acquisition_count == 0


def test_mqtt_acquisition_resolved_via_canonical_id_field():
    trace = [
        _event(
            "read_mqtt",
            {"message": {"topic": "icab/tep/reactor/reactor_pressure", "canonical_id": REACTOR_PRESSURE_ID, "value": 2705.0}},
        )
    ]

    report = InformationFlowAnalyzer().analyze(trace)

    assert report.acquisitions[0].canonical_id == REACTOR_PRESSURE_ID
    assert report.acquisitions[0].architecture == "mqtt"


def test_opcua_read_resolved_via_prior_browse_in_the_same_trace():
    trace = [
        _event(
            "opcua_browse",
            {"nodes": [{"node_id": "ns=2;i=14", "display_name": "Reactor pressure", "node_class": "Variable"}]},
            step=1,
        ),
        _event("opcua_read", {"node_id": "ns=2;i=14", "value": 2705.0}, step=2),
    ]

    report = InformationFlowAnalyzer().analyze(trace)

    assert REACTOR_PRESSURE_ID in report.discovered_canonical_ids
    assert len(report.acquisitions) == 1
    assert report.acquisitions[0].canonical_id == REACTOR_PRESSURE_ID
    assert report.acquisitions[0].architecture == "opcua"
    assert report.unresolved_acquisition_count == 0


def test_opcua_read_without_a_prior_browse_is_unresolved_not_guessed():
    trace = [_event("opcua_read", {"node_id": "ns=2;i=14", "value": 2705.0})]

    report = InformationFlowAnalyzer().analyze(trace)

    assert report.acquisitions == []
    assert report.unresolved_acquisition_count == 1


def test_i3x_value_resolved_from_element_id_format():
    trace = [
        _event(
            "i3x_get_value",
            {"element_id": "icab_tep!Reactor.Reactor pressure", "value": 2705.0, "is_composition": False, "quality": "Good", "timestamp": "now", "components": None},
        )
    ]

    report = InformationFlowAnalyzer().analyze(trace)

    assert report.acquisitions[0].canonical_id == REACTOR_PRESSURE_ID
    assert report.acquisitions[0].architecture == "i3x"


def test_redundant_acquisition_across_two_architectures_is_detected():
    trace = [
        _event(
            "get_current_value",
            {"observation": {"measurement_id": REACTOR_PRESSURE_ID, "value": 2705.0}},
            step=1,
        ),
        _event(
            "read_mqtt",
            {"message": {"canonical_id": REACTOR_PRESSURE_ID, "value": 2705.0}},
            step=2,
        ),
    ]

    report = InformationFlowAnalyzer().analyze(trace)

    assert report.redundant_measurements == [REACTOR_PRESSURE_ID]
    assert report.redundant_acquisition_count == 1
    assert report.architectures_used_per_measurement[REACTOR_PRESSURE_ID] == [
        "historian",
        "mqtt",
    ]


def test_same_architecture_repeated_reads_are_not_cross_architecture_redundant_but_still_counted():
    trace = [
        _event(
            "get_current_value",
            {"observation": {"measurement_id": REACTOR_PRESSURE_ID, "value": 2705.0}},
            step=1,
        ),
        _event(
            "get_current_value",
            {"observation": {"measurement_id": REACTOR_PRESSURE_ID, "value": 2705.1}},
            step=2,
        ),
    ]

    report = InformationFlowAnalyzer().analyze(trace)

    # Only one architecture used -- not "redundant across architectures" --
    # but it's still two acquisitions of the same measurement.
    assert report.redundant_measurements == []
    assert report.redundant_acquisition_count == 1
    assert report.architectures_used_per_measurement[REACTOR_PRESSURE_ID] == ["historian"]


def test_no_redundancy_for_a_single_clean_acquisition():
    trace = [
        _event(
            "get_current_value",
            {"observation": {"measurement_id": REACTOR_PRESSURE_ID, "value": 2705.0}},
        )
    ]

    report = InformationFlowAnalyzer().analyze(trace)

    assert report.redundant_measurements == []
    assert report.redundant_acquisition_count == 0


def test_discovery_via_uns_and_knowledge_graph():
    trace = [
        _event(
            "browse_uns",
            {
                "nodes": [
                    {
                        "path": "site/tep/reactor/reactor_pressure",
                        "display_name": "Reactor pressure",
                        "node_type": "measurement",
                        "canonical_id": REACTOR_PRESSURE_ID,
                    }
                ]
            },
        ),
        _event(
            "get_entity_relationships",
            {
                "relationships": [
                    {
                        "subject": "urn:icab:equipment:reactor",
                        "predicate": "MONITORS",
                        "object": REACTOR_PRESSURE_ID,
                    }
                ]
            },
        ),
    ]

    report = InformationFlowAnalyzer().analyze(trace)

    assert report.discovered_canonical_ids == [REACTOR_PRESSURE_ID]
    assert report.acquisitions == []  # discovery only, no value retrieved


def test_tool_error_events_are_counted_and_excluded_from_acquisitions():
    trace = [
        _event("get_current_value", {"error": "measurement not found"}),
        _event(
            "get_current_value",
            {"observation": {"measurement_id": REACTOR_PRESSURE_ID, "value": 2705.0}},
            step=2,
        ),
    ]

    report = InformationFlowAnalyzer().analyze(trace)

    assert report.tool_error_count == 1
    assert len(report.acquisitions) == 1
