from fastapi.testclient import TestClient

from icab.gateway.app import app

client = TestClient(app)


def test_gateway_reads_loaded_tep_observation():
    response = client.post(
        "/tools/get_current_value",
        json={"measurement_id": ("urn:icab:measurement:tep_pv_reactor_pressure")},
    )

    assert response.status_code == 200

    body = response.json()

    assert body["observation"] is not None
    assert body["observation"]["value"] == 2834.0
    assert body["observation"]["unit"] == "kPa"
    assert body["observation"]["source"] == "tep"


def test_gateway_reads_historical_tep_observations():
    response = client.post(
        "/tools/get_historical_values",
        json={
            "measurement_id": ("urn:icab:measurement:tep_pv_reactor_pressure"),
            "start_time": "2026-09-09T11:59:00Z",
            "end_time": "2026-09-09T12:01:00Z",
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert len(body["observations"]) == 1

    observation = body["observations"][0]

    assert observation["value"] == 2834.0
    assert observation["unit"] == "kPa"
    assert observation["source"] == "tep"


def test_gateway_reads_loaded_tep_relationships():
    response = client.post(
        "/tools/get_entity_relationships",
        json={"canonical_id": "urn:icab:equipment:reactor"},
    )

    assert response.status_code == 200

    body = response.json()

    relationships = body["relationships"]

    assert len(relationships) == 4

    predicates = {relationship["predicate"] for relationship in relationships}

    assert "PART_OF" in predicates
    assert "MONITORS" in predicates
