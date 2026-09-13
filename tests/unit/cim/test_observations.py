from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from icab.cim import Measurement, Observation


def test_measurement_and_observation_are_distinct():
    measurement = Measurement(
        canonical_id="urn:icab:measurement:reactor-pressure",
        name="Reactor Pressure",
    )

    observation = Observation(
        observation_id="obs-000001",
        measurement_id=measurement.canonical_id,
        timestamp=datetime(
            2026,
            9,
            9,
            12,
            0,
            tzinfo=UTC,
        ),
        value=2834.0,
        unit="kPa",
        quality="GOOD",
    )

    assert measurement.canonical_id == observation.measurement_id
    assert observation.value == 2834.0


def test_observation_requires_timezone():
    with pytest.raises(ValidationError):
        Observation(
            observation_id="obs-000001",
            measurement_id="urn:icab:measurement:reactor-pressure",
            timestamp=datetime(2026, 9, 9, 12, 0),
            value=2834.0,
        )


@pytest.mark.parametrize(
    "value",
    [
        2834.0,
        42,
        "RUNNING",
        True,
        None,
    ],
)
def test_observation_supports_value_types(value):
    observation = Observation(
        observation_id="obs-test",
        measurement_id="urn:icab:measurement:test",
        timestamp=datetime(
            2026,
            9,
            9,
            12,
            0,
            tzinfo=UTC,
        ),
        value=value,
    )

    assert observation.value == value


def test_observation_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        Observation(
            observation_id="obs-000001",
            measurement_id="urn:icab:measurement:test",
            timestamp=datetime(
                2026,
                9,
                9,
                12,
                0,
                tzinfo=UTC,
            ),
            value=42,
            unexpected_field="should_fail",
        )
