from fastapi.testclient import TestClient

from icab.gateway.app import app, trace_collector

client = TestClient(app)


def test_health():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_get_current_value_for_unknown_measurement():
    response = client.post(
        "/tools/get_current_value",
        json={
            "measurement_id": "urn:icab:measurement:unknown",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"observation": None}


def test_get_current_value_records_http_trace():
    trace_collector.clear()

    response = client.post(
        "/tools/get_current_value",
        json={
            "measurement_id": "urn:icab:measurement:unknown",
        },
    )

    assert response.status_code == 200

    events = trace_collector.events()

    assert len(events) == 1
    assert events[0].tool == "get_current_value"
    assert events[0].arguments["measurement_id"] == "urn:icab:measurement:unknown"
    assert events[0].result["observation"] is None


def test_opcua_browse_endpoint():
    response = client.post(
        "/tools/opcua_browse",
        json={"node_id": "i=85"},
    )

    assert response.status_code == 200


def test_opcua_read_endpoint():
    response = client.post(
        "/tools/opcua_read",
        json={"node_id": "ns=2;i=2"},
    )

    assert response.status_code == 200
