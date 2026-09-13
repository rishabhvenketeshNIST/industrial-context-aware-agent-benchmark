from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from icab.context.mqtt.models import MQTTMessage


def test_mqtt_message_round_trip():
    message = MQTTMessage(
        topic="icab/tep/reactor/reactor_pressure",
        timestamp=datetime(2026, 9, 9, 12, 0, tzinfo=UTC),
        source="tep-simulator",
        value=2705.0,
        unit="kPa gauge",
        quality="GOOD",
        canonical_id="urn:icab:measurement:reactor_pressure",
    )

    assert message.topic == "icab/tep/reactor/reactor_pressure"
    assert message.value == 2705.0


def test_mqtt_message_rejects_naive_timestamp():
    with pytest.raises(ValidationError):
        MQTTMessage(
            topic="icab/tep/reactor/reactor_pressure",
            timestamp=datetime(2026, 9, 9, 12, 0),
            source="tep-simulator",
            value=2705.0,
        )


def test_mqtt_message_allows_missing_unit_and_quality():
    message = MQTTMessage(
        topic="icab/tep/reactor/reactor_pressure",
        timestamp=datetime(2026, 9, 9, 12, 0, tzinfo=UTC),
        source="tep-simulator",
        value=None,
    )

    assert message.unit is None
    assert message.quality is None
    assert message.canonical_id is None
