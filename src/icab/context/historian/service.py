from datetime import datetime

from icab.cim import Observation
from icab.context.base import HistorianRepository


class HistorianService:
    """
    Application-level service for historian operations.

    The service depends only on the backend-independent
    HistorianRepository contract.
    """

    def __init__(self, repository: HistorianRepository) -> None:
        self.repository = repository

    def write_observations(
        self,
        observations: list[Observation],
    ) -> None:
        self.repository.write_observations(observations)

    def get_current_value(
        self,
        measurement_id: str,
    ) -> Observation | None:
        return self.repository.get_current_value(measurement_id)

    def get_historical_values(
        self,
        measurement_id: str,
        start_time: datetime,
        end_time: datetime,
    ) -> list[Observation]:
        if start_time.tzinfo is None or end_time.tzinfo is None:
            raise ValueError("Historian query timestamps must be timezone-aware.")

        if start_time > end_time:
            raise ValueError("Historian start_time must not be after end_time.")

        return self.repository.get_historical_values(
            measurement_id,
            start_time,
            end_time,
        )
