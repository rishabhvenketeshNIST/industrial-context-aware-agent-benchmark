from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TEPProcessState(BaseModel):
    """
    Immutable snapshot of the TEP process at a specific point in time.

    A new process state should be created for each simulation timestep
    rather than mutating an existing state.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    timestamp: datetime

    operating_state: str = Field(min_length=1)

    values: dict[str, float]

    @field_validator("timestamp")
    @classmethod
    def timestamp_must_be_timezone_aware(
        cls,
        value: datetime,
    ) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Process state timestamp must be timezone-aware.")

        return value
