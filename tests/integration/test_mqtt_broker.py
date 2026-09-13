import uuid
from datetime import UTC, datetime

from icab.context.mqtt import MQTTClient, MQTTMessage, TEPMeasurementPublisher
from icab.tep.simulator import TEPSimulator

MQTT_HOST = "localhost"
MQTT_PORT = 1883


def _unique_topic(name: str) -> str:
    # Avoid collisions with retained messages from earlier test runs.
    return f"icab/test/{name}/{uuid.uuid4().hex}"


def test_publish_then_read_round_trip():
    topic = _unique_topic("round-trip")
    message = MQTTMessage(
        topic=topic,
        timestamp=datetime(2026, 9, 9, 12, 0, tzinfo=UTC),
        source="integration-test",
        value=42.0,
        unit="unit",
        quality="GOOD",
        canonical_id="urn:icab:measurement:integration-test",
    )

    client = MQTTClient(MQTT_HOST, MQTT_PORT)

    with client:
        client.publish(message, retain=True)

    read_back = client.read(topic, timeout=1.0)

    assert read_back is not None
    assert read_back.topic == topic
    assert read_back.value == 42.0
    assert read_back.source == "integration-test"
    assert read_back.canonical_id == "urn:icab:measurement:integration-test"


def test_discover_finds_multiple_topics_under_a_filter():
    prefix = uuid.uuid4().hex
    client = MQTTClient(MQTT_HOST, MQTT_PORT)

    with client:
        for name, value in (("a", 1.0), ("b", 2.0)):
            client.publish(
                MQTTMessage(
                    topic=f"icab/test/{prefix}/{name}",
                    timestamp=datetime(2026, 9, 9, 12, 0, tzinfo=UTC),
                    source="integration-test",
                    value=value,
                ),
                retain=True,
            )

    discovered = client.discover(f"icab/test/{prefix}/#", timeout=1.0)

    assert {message.topic for message in discovered} == {
        f"icab/test/{prefix}/a",
        f"icab/test/{prefix}/b",
    }


def test_read_missing_topic_returns_none():
    client = MQTTClient(MQTT_HOST, MQTT_PORT)

    result = client.read(_unique_topic("missing"), timeout=0.5)

    assert result is None


def test_tep_simulator_to_mqtt_pipeline():
    """TEP simulator -> MQTT broker -> ICAB MQTT client (end-to-end)."""

    simulator = TEPSimulator()
    simulator.reset(seed=11)

    client = MQTTClient(MQTT_HOST, MQTT_PORT)
    publisher = TEPMeasurementPublisher(client, source="pipeline-test")

    with client:
        published_topics = publisher.publish_state(simulator)

    assert "icab/tep/reactor/reactor_pressure" in published_topics

    read_back = client.read("icab/tep/reactor/reactor_pressure", timeout=1.0)

    assert read_back is not None
    assert read_back.source == "pipeline-test"
    assert read_back.canonical_id == "urn:icab:measurement:reactor_pressure"
    assert (
        read_back.value
        == simulator.get_measurements()["REACTOR_PRESSURE"]
    )
