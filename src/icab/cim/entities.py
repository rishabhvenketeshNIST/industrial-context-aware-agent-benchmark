from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from .identifiers import CanonicalId


class EntityType(StrEnum):
    # ISA-95-aligned hierarchy
    ENTERPRISE = "Enterprise"
    SITE = "Site"
    AREA = "Area"
    WORK_CENTER = "WorkCenter"
    PROCESS_CELL = "ProcessCell"
    EQUIPMENT = "Equipment"

    # ICAB process/context extensions
    PROCESS = "Process"
    PROCESS_UNIT = "ProcessUnit"
    DEVICE = "Device"
    SENSOR = "Sensor"
    ACTUATOR = "Actuator"
    MEASUREMENT = "Measurement"
    PROCESS_VARIABLE = "ProcessVariable"
    CONTROL_LOOP = "ControlLoop"
    ALARM = "Alarm"
    OPERATING_STATE = "OperatingState"
    FAULT = "Fault"
    EVENT = "Event"
    PROCEDURE = "Procedure"
    DOCUMENT = "Document"


class Entity(BaseModel):
    """
    Base entity in the ICAB Canonical Information Model.

    The CIM is ISA-95-aligned for industrial hierarchy concepts,
    while adding ICAB-specific entities needed for contextual
    investigation and diagnosis.
    """

    model_config = ConfigDict(extra="forbid")

    canonical_id: CanonicalId
    entity_type: EntityType
    name: str = Field(min_length=1)
    description: str | None = None

    # Mapping back to external information systems.
    source: str | None = None
    source_id: str | None = None


# ---------------------------------------------------------------------------
# ISA-95-aligned hierarchy
# ---------------------------------------------------------------------------


class Enterprise(Entity):
    entity_type: EntityType = EntityType.ENTERPRISE


class Site(Entity):
    entity_type: EntityType = EntityType.SITE


class Area(Entity):
    entity_type: EntityType = EntityType.AREA


class WorkCenter(Entity):
    entity_type: EntityType = EntityType.WORK_CENTER


class ProcessCell(Entity):
    entity_type: EntityType = EntityType.PROCESS_CELL


class Equipment(Entity):
    entity_type: EntityType = EntityType.EQUIPMENT


# ---------------------------------------------------------------------------
# ICAB process/context extensions
# ---------------------------------------------------------------------------


class Process(Entity):
    entity_type: EntityType = EntityType.PROCESS


class ProcessUnit(Entity):
    entity_type: EntityType = EntityType.PROCESS_UNIT


class Device(Entity):
    entity_type: EntityType = EntityType.DEVICE


class Sensor(Entity):
    entity_type: EntityType = EntityType.SENSOR


class Actuator(Entity):
    entity_type: EntityType = EntityType.ACTUATOR


class Measurement(Entity):
    entity_type: EntityType = EntityType.MEASUREMENT


class ProcessVariable(Entity):
    entity_type: EntityType = EntityType.PROCESS_VARIABLE


class ControlLoop(Entity):
    entity_type: EntityType = EntityType.CONTROL_LOOP


class Alarm(Entity):
    entity_type: EntityType = EntityType.ALARM


class OperatingState(Entity):
    entity_type: EntityType = EntityType.OPERATING_STATE


class Fault(Entity):
    entity_type: EntityType = EntityType.FAULT


class Event(Entity):
    entity_type: EntityType = EntityType.EVENT


class Procedure(Entity):
    entity_type: EntityType = EntityType.PROCEDURE


class Document(Entity):
    entity_type: EntityType = EntityType.DOCUMENT
