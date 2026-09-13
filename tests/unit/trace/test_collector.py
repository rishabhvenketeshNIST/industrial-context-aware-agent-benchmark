from datetime import UTC, datetime

from icab.trace.collector import TraceCollector


def test_trace_collector_records_events():
    collector = TraceCollector()

    timestamp = datetime(
        2026,
        9,
        9,
        12,
        0,
        tzinfo=UTC,
    )

    event = collector.record(
        step=1,
        action="get_current_value",
        tool="get_current_value",
        arguments={"measurement_id": "urn:icab:measurement:tep_pv_reactor_pressure"},
        result={"value": 2834.0},
        latency_ms=10.5,
        timestamp=timestamp,
    )

    assert event.step == 1
    assert len(collector.events()) == 1
    assert collector.events()[0].result["value"] == 2834.0
    assert collector.events()[0].timestamp == timestamp


def test_trace_collector_preserves_event_order():
    collector = TraceCollector()

    collector.record(step=1, action="first")
    collector.record(step=2, action="second")

    events = collector.events()

    assert [event.step for event in events] == [1, 2]


def test_trace_collector_clear():
    collector = TraceCollector()

    collector.record(step=1, action="test")
    collector.clear()

    assert collector.events() == []
