from datetime import datetime

import psycopg

from icab.cim import Observation
from icab.context.base import HistorianRepository


class PostgresHistorianRepository(HistorianRepository):
    """PostgreSQL/TimescaleDB implementation of the historian contract."""

    def __init__(self, connection_string: str):
        self.connection_string = connection_string

    def _connect(self):
        return psycopg.connect(self.connection_string)

    def write_observations(
        self,
        observations: list[Observation],
    ) -> None:
        if not observations:
            return

        rows = [
            (
                observation.observation_id,
                observation.measurement_id,
                observation.timestamp,
                observation.value,
                observation.unit,
                observation.quality,
                observation.source,
                observation.source_id,
            )
            for observation in observations
        ]

        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.executemany(
                    """
                    INSERT INTO observations (
                        observation_id,
                        measurement_id,
                        timestamp,
                        value,
                        unit,
                        quality,
                        source,
                        source_id
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (observation_id, timestamp)
                    DO NOTHING
                    """,
                    rows,
                )

            connection.commit()

    def get_current_value(
        self,
        measurement_id: str,
    ) -> Observation | None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                    SELECT
                        observation_id,
                        measurement_id,
                        timestamp,
                        value,
                        unit,
                        quality,
                        source,
                        source_id
                    FROM observations
                    WHERE measurement_id = %s
                    ORDER BY timestamp DESC, observation_id DESC
                    LIMIT 1
                    """,
                (measurement_id,),
            )

            row = cursor.fetchone()

        if row is None:
            return None

        return self._row_to_observation(row)

    def get_historical_values(
        self,
        measurement_id: str,
        start_time: datetime,
        end_time: datetime,
    ) -> list[Observation]:
        if start_time.tzinfo is None or end_time.tzinfo is None:
            raise ValueError("Historian query timestamps must be timezone-aware.")

        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                    SELECT
                        observation_id,
                        measurement_id,
                        timestamp,
                        value,
                        unit,
                        quality,
                        source,
                        source_id
                    FROM observations
                    WHERE measurement_id = %s
                      AND timestamp >= %s
                      AND timestamp <= %s
                    ORDER BY timestamp ASC, observation_id ASC
                    """,
                (
                    measurement_id,
                    start_time,
                    end_time,
                ),
            )

            rows = cursor.fetchall()

        return [self._row_to_observation(row) for row in rows]

    @staticmethod
    def _row_to_observation(row) -> Observation:
        return Observation(
            observation_id=row[0],
            measurement_id=row[1],
            timestamp=row[2],
            value=row[3],
            unit=row[4],
            quality=row[5],
            source=row[6],
            source_id=row[7],
        )


class InMemoryHistorianRepository(HistorianRepository):
    """
    In-memory historian used for unit tests and lightweight prototypes.

    This implementation intentionally mirrors the public historian
    contract without introducing database dependencies.
    """

    def __init__(self) -> None:
        self._observations: list[Observation] = []

    def write_observations(
        self,
        observations: list[Observation],
    ) -> None:
        self._observations.extend(observations)

        # Keep deterministic chronological ordering.
        self._observations.sort(
            key=lambda observation: (
                observation.measurement_id,
                observation.timestamp,
                observation.observation_id,
            )
        )

    def get_current_value(
        self,
        measurement_id: str,
    ) -> Observation | None:
        matching = [
            observation
            for observation in self._observations
            if observation.measurement_id == measurement_id
        ]

        if not matching:
            return None

        return max(
            matching,
            key=lambda observation: (
                observation.timestamp,
                observation.observation_id,
            ),
        )

    def get_historical_values(
        self,
        measurement_id: str,
        start_time: datetime,
        end_time: datetime,
    ) -> list[Observation]:
        if start_time.tzinfo is None or end_time.tzinfo is None:
            raise ValueError("Historian query timestamps must be timezone-aware.")

        return [
            observation
            for observation in self._observations
            if (
                observation.measurement_id == measurement_id
                and start_time <= observation.timestamp <= end_time
            )
        ]
