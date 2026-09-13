from pydantic import BaseModel, ConfigDict, Field

from .entities import Entity
from .observations import Observation
from .relationships import Relationship


class CIMEnvironment(BaseModel):
    """
    A technology-neutral snapshot of the industrial information
    environment represented using the ICAB CIM.
    """

    model_config = ConfigDict(extra="forbid")

    entities: list[Entity] = Field(default_factory=list)
    relationships: list[Relationship] = Field(default_factory=list)
    observations: list[Observation] = Field(default_factory=list)
