from datetime import UTC, datetime

from icab.trace.models import TraceEvent


def test_trace_event():
    event = TraceEvent(
        timestamp=datetime(2026, 9, 9, 12, 0, tzinfo=UTC),
        step=1,
        action="get_current_value",
        tool="get_current_value",
        arguments={"measurement_id": "urn:icab:measurement:tep_pv_reactor_pressure"},
        result={"value": 2834.0},
        latency_ms=12.5,
        token_usage={
            "input": 100,
            "output": 25,
        },
    )

    assert event.step == 1
    assert event.tool == "get_current_value"
    assert event.result["value"] == 2834.0
    assert event.latency_ms == 12.5


from icab.trace.models import InvestigationTrace


def test_investigation_trace():
    started_at = datetime.now(UTC)

    trace = InvestigationTrace(
        run_id="prototype-001",
        objective="Investigate reactor condition.",
        agent="structured_retrieval",
        started_at=started_at,
    )

    assert trace.run_id == "prototype-001"
    assert trace.objective == "Investigate reactor condition."
    assert trace.agent == "structured_retrieval"
    assert trace.status == "running"
    assert trace.events == []


def test_investigation_trace_can_complete():
    started_at = datetime.now(UTC)
    completed_at = datetime.now(UTC)

    trace = InvestigationTrace(
        run_id="prototype-001",
        objective="Investigate reactor condition.",
        agent="structured_retrieval",
        started_at=started_at,
        completed_at=completed_at,
        status="completed",
    )

    assert trace.completed_at == completed_at
    assert trace.status == "completed"
