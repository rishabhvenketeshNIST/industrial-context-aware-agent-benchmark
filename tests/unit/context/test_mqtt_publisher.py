from unittest.mock import Mock

from icab.context.mqtt import MQTTClient, MQTTMessage, TEPMeasurementPublisher
from icab.tep.simulator import TEPSimulator


def test_topic_for_known_real_measurement():
    publisher = TEPMeasurementPublisher(Mock(spec=MQTTClient))

    assert publisher.topic_for("REACTOR_PRESSURE") == "icab/tep/reactor/reactor_pressure"
    assert publisher.topic_for("SEPARATOR_LEVEL") == "icab/tep/separator/separator_level"


def test_publish_state_publishes_every_real_measurement():
    client = Mock(spec=MQTTClient)
    publisher = TEPMeasurementPublisher(client, source="test-sim")

    simulator = TEPSimulator()
    simulator.reset(seed=1)

    published_topics = publisher.publish_state(simulator)

    assert len(published_topics) == 41
    assert client.publish.call_count == 41
    assert "icab/tep/reactor/reactor_pressure" in published_topics


def test_publish_state_messages_carry_provenance():
    client = Mock(spec=MQTTClient)
    publisher = TEPMeasurementPublisher(client, source="test-sim")

    simulator = TEPSimulator()
    simulator.reset(seed=1)

    publisher.publish_state(simulator)

    published_messages = [call.args[0] for call in client.publish.call_args_list]
    pressure_message = next(
        message
        for message in published_messages
        if message.topic == "icab/tep/reactor/reactor_pressure"
    )

    assert isinstance(pressure_message, MQTTMessage)
    assert pressure_message.source == "test-sim"
    assert pressure_message.canonical_id == "urn:icab:measurement:reactor_pressure"
    assert pressure_message.unit == "kPa gauge"
    assert pressure_message.quality == "GOOD"
