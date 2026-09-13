from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .identifiers import CanonicalId

ObservationValue = str | int | float | bool | None


class Observation(BaseModel):
    """
    A timestamped observation associated with a persistent Measurement entity.
    """

    model_config = ConfigDict(extra="forbid")

    observation_id: str = Field(min_length=1)

    measurement_id: CanonicalId

    timestamp: datetime

    value: ObservationValue

    unit: str | None = None

    quality: str | None = None

    source: str | None = None

    source_id: str | None = None

    @field_validator("timestamp")
    @classmethod
    def timestamp_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Observation timestamp must be timezone-aware.")

        return value
