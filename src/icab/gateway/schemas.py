from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from icab.cim import Observation, Relationship
from icab.context.mqtt.models import MQTTMessage
from icab.context.uns.models import UNSNode


class GetCurrentValueRequest(BaseModel):
    """Request for the latest observation of a measurement."""

    model_config = ConfigDict(extra="forbid")

    measurement_id: str = Field(min_length=1)


class GetCurrentValueResponse(BaseModel):
    """Response containing the latest observation."""

    model_config = ConfigDict(extra="forbid")

    observation: Observation | None


class GetHistoricalValuesRequest(BaseModel):
    """Request for observations in a time range."""

    model_config = ConfigDict(extra="forbid")

    measurement_id: str = Field(min_length=1)
    start_time: datetime
    end_time: datetime


class GetHistoricalValuesResponse(BaseModel):
    """Response containing historical observations."""

    model_config = ConfigDict(extra="forbid")

    observations: list[Observation]


class GetEntityRelationshipsRequest(BaseModel):
    """Request for relationships involving a CIM entity."""

    model_config = ConfigDict(extra="forbid")

    canonical_id: str = Field(min_length=1)


class GetEntityRelationshipsResponse(BaseModel):
    """Response containing CIM relationships."""

    model_config = ConfigDict(extra="forbid")

    relationships: list[Relationship]


class BrowseUNSRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1)


class BrowseUNSResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nodes: list[UNSNode]


class I3XGetInfoResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    spec_version: str
    server_version: str | None = None
    server_name: str | None = None
    capabilities: dict[str, Any] = Field(default_factory=dict)


class I3XGetNamespacesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    namespaces: list[dict[str, Any]]


class I3XGetObjectTypesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    object_types: list[dict[str, Any]]


class I3XGetObjectsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    objects: list[dict[str, Any]]


class I3XGetObjectResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    object: dict[str, Any]


class I3XGetRelatedObjectsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    related_objects: list[dict[str, Any]]


class I3XGetValueResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    element_id: str
    is_composition: bool
    value: Any
    quality: Any
    timestamp: Any
    components: Any


class I3XGetHistoryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    element_id: str
    is_composition: bool
    values: Any


class OPCUABrowseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str = "i=85"


class OPCUAReadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str


class BrowseMQTTRequest(BaseModel):
    """Discover ICAB MQTT topics (and their retained values) under a filter."""

    model_config = ConfigDict(extra="forbid")

    topic_filter: str = Field(default="icab/#", min_length=1)
    timeout: float = Field(default=1.0, gt=0.0, le=10.0)


class BrowseMQTTResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    messages: list[MQTTMessage]


class ReadMQTTRequest(BaseModel):
    """Read the (retained) value on a single, fully-qualified MQTT topic."""

    model_config = ConfigDict(extra="forbid")

    topic: str = Field(min_length=1)
    timeout: float = Field(default=1.0, gt=0.0, le=10.0)


class ReadMQTTResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: MQTTMessage | None
