from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

MQTTValue = str | int | float | bool | None


class MQTTMessage(BaseModel):
    """
    A single ICAB MQTT message.

    Preserves the fields an agent needs to trust a value acquired through
    the MQTT channel rather than a preassembled context dictionary:
    timestamp, source, topic, value, unit (where available), quality
    (where available), and canonical ID (where available).
    """

    model_config = ConfigDict(extra="forbid")

    topic: str = Field(min_length=1)
    timestamp: datetime
    source: str = Field(min_length=1)
    value: MQTTValue

    unit: str | None = None
    quality: str | None = None
    canonical_id: str | None = None

    @field_validator("timestamp")
    @classmethod
    def timestamp_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("MQTT message timestamp must be timezone-aware.")

        return value
