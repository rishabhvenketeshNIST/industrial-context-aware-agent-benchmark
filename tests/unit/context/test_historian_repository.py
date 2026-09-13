from datetime import UTC, datetime, timedelta

import pytest

from icab.cim import Observation
from icab.context.historian import InMemoryHistorianRepository

MEASUREMENT_ID = "urn:icab:measurement:reactor-pressure"

T0 = datetime(
    2026,
    9,
    9,
    12,
    0,
    tzinfo=UTC,
)

T1 = T0 + timedelta(minutes=1)
T2 = T0 + timedelta(minutes=2)


def make_observation(
    observation_id: str,
    timestamp: datetime,
    value: float,
) -> Observation:
    return Observation(
        observation_id=observation_id,
        measurement_id=MEASUREMENT_ID,
        timestamp=timestamp,
        value=value,
        unit="kPa",
        quality="GOOD",
        source="tep",
    )


def test_write_and_get_current_value():
    repository = InMemoryHistorianRepository()

    repository.write_observations(
        [
            make_observation("obs-1", T0, 2800.0),
            make_observation("obs-2", T1, 2810.0),
            make_observation("obs-3", T2, 2834.0),
        ]
    )

    current = repository.get_current_value(MEASUREMENT_ID)

    assert current is not None
    assert current.observation_id == "obs-3"
    assert current.value == 2834.0


def test_get_current_value_returns_none_for_unknown_measurement():
    repository = InMemoryHistorianRepository()

    assert repository.get_current_value("urn:icab:measurement:does-not-exist") is None


def test_get_historical_values():
    repository = InMemoryHistorianRepository()

    repository.write_observations(
        [
            make_observation("obs-1", T0, 2800.0),
            make_observation("obs-2", T1, 2810.0),
            make_observation("obs-3", T2, 2834.0),
        ]
    )

    results = repository.get_historical_values(
        measurement_id=MEASUREMENT_ID,
        start_time=T0,
        end_time=T1,
    )

    assert [item.observation_id for item in results] == [
        "obs-1",
        "obs-2",
    ]


def test_historical_results_are_chronological():
    repository = InMemoryHistorianRepository()

    repository.write_observations(
        [
            make_observation("obs-3", T2, 2834.0),
            make_observation("obs-1", T0, 2800.0),
            make_observation("obs-2", T1, 2810.0),
        ]
    )

    results = repository.get_historical_values(
        MEASUREMENT_ID,
        T0,
        T2,
    )

    assert [item.observation_id for item in results] == [
        "obs-1",
        "obs-2",
        "obs-3",
    ]


def test_historical_query_requires_timezone():
    repository = InMemoryHistorianRepository()

    with pytest.raises(ValueError):
        repository.get_historical_values(
            MEASUREMENT_ID,
            datetime(2026, 9, 9, 12, 0),
            T1,
        )


def test_measurements_are_isolated():
    repository = InMemoryHistorianRepository()

    repository.write_observations(
        [
            make_observation("pressure-1", T0, 2800.0),
            Observation(
                observation_id="temperature-1",
                measurement_id=("urn:icab:measurement:reactor-temperature"),
                timestamp=T0,
                value=120.0,
                unit="degC",
                quality="GOOD",
                source="tep",
            ),
        ]
    )

    results = repository.get_historical_values(
        MEASUREMENT_ID,
        T0,
        T2,
    )

    assert len(results) == 1
    assert results[0].observation_id == "pressure-1"
