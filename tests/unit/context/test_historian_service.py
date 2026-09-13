from datetime import UTC, datetime

import pytest

from icab.cim import Observation
from icab.context.historian.repository import InMemoryHistorianRepository
from icab.context.historian.service import HistorianService


def test_historian_service_reads_and_writes():
    repository = InMemoryHistorianRepository()
    service = HistorianService(repository)

    timestamp = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)

    observation = Observation(
        observation_id="service-test-001",
        measurement_id="urn:icab:measurement:reactor-pressure",
        timestamp=timestamp,
        value=2834.0,
        unit="kPa",
        source="TEP",
    )

    service.write_observations([observation])

    result = service.get_current_value("urn:icab:measurement:reactor-pressure")

    assert result is not None
    assert result.value == 2834.0


def test_historian_service_rejects_invalid_time_range():
    repository = InMemoryHistorianRepository()
    service = HistorianService(repository)

    start = datetime(2026, 9, 10, 13, 0, tzinfo=UTC)
    end = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)

    with pytest.raises(ValueError, match="start_time"):
        service.get_historical_values(
            "urn:icab:measurement:reactor-pressure",
            start,
            end,
        )
