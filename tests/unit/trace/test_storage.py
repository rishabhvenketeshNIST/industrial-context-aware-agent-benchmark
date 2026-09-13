from datetime import UTC, datetime

from icab.trace.models import InvestigationTrace, TraceEvent
from icab.trace.storage import JsonlTraceStorage


def test_jsonl_trace_storage_round_trip(tmp_path):
    storage = JsonlTraceStorage()

    events = [
        TraceEvent(
            timestamp=datetime(
                2026,
                9,
                9,
                12,
                0,
                tzinfo=UTC,
            ),
            step=1,
            action="get_current_value",
            tool="get_current_value",
            arguments={"measurement_id": "test"},
            result={"value": 2834.0},
        ),
        TraceEvent(
            timestamp=datetime(
                2026,
                9,
                9,
                12,
                0,
                1,
                tzinfo=UTC,
            ),
            step=2,
            action="submit_investigation",
            result={"status": "submitted"},
        ),
    ]

    path = tmp_path / "trace.jsonl"

    storage.write(path, events)

    loaded = storage.read(path)

    assert loaded == events
    assert path.exists()


def test_investigation_trace_round_trip(tmp_path):
    trace = InvestigationTrace(
        run_id="prototype-001",
        objective="Investigate reactor condition.",
        agent="structured_retrieval",
        started_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
        status="completed",
    )

    path = tmp_path / "investigation.json"

    storage = JsonlTraceStorage()
    storage.write_investigation(path, trace)

    loaded = storage.read_investigation(path)

    assert loaded.run_id == "prototype-001"
    assert loaded.objective == "Investigate reactor condition."
    assert loaded.agent == "structured_retrieval"
    assert loaded.status == "completed"
    assert loaded.events == []
