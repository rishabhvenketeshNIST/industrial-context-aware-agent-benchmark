from datetime import UTC, datetime, timedelta

from icab.cim import Observation
from icab.context.historian.repository import PostgresHistorianRepository

DATABASE_URL = "postgresql://icab:icab@localhost:5432/icab"


def test_postgres_historian_round_trip():
    repository = PostgresHistorianRepository(DATABASE_URL)

    measurement_id = "urn:icab:measurement:reactor-pressure"

    start = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)
    later = start + timedelta(minutes=1)

    observations = [
        Observation(
            observation_id="integration-test-001",
            measurement_id=measurement_id,
            timestamp=start,
            value=2834.0,
            unit="kPa",
            quality="GOOD",
            source="TEP",
            source_id="TEP_PV_REACTOR_PRESSURE",
        ),
        Observation(
            observation_id="integration-test-002",
            measurement_id=measurement_id,
            timestamp=later,
            value=2840.0,
            unit="kPa",
            quality="GOOD",
            source="TEP",
            source_id="TEP_PV_REACTOR_PRESSURE",
        ),
    ]

    repository.write_observations(observations)

    current = repository.get_current_value(measurement_id)

    assert current is not None
    assert current.observation_id == "integration-test-002"
    assert current.value == 2840.0

    historical = repository.get_historical_values(
        measurement_id,
        start,
        later,
    )

    assert len(historical) == 2
    assert historical[0].value == 2834.0
    assert historical[1].value == 2840.0

    # Writing the same observations again must not create duplicates.
    repository.write_observations(observations)

    historical_after_duplicate = repository.get_historical_values(
        measurement_id,
        start,
        later,
    )

    assert len(historical_after_duplicate) == 2
