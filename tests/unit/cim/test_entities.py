import pytest
from pydantic import ValidationError

from icab.cim import (
    Alarm,
    Area,
    Enterprise,
    EntityType,
    Equipment,
    Fault,
    Measurement,
    Process,
    ProcessCell,
    ProcessUnit,
    Sensor,
    Site,
    WorkCenter,
)


def test_isa95_hierarchy_entities():
    enterprise = Enterprise(
        canonical_id="urn:icab:enterprise:demo",
        name="Demo Enterprise",
    )

    site = Site(
        canonical_id="urn:icab:site:tep",
        name="TEP Site",
    )

    area = Area(
        canonical_id="urn:icab:area:reaction",
        name="Reaction Area",
    )

    work_center = WorkCenter(
        canonical_id="urn:icab:workcenter:reaction",
        name="Reaction Work Center",
    )

    process_cell = ProcessCell(
        canonical_id="urn:icab:processcell:reactor",
        name="Reactor Process Cell",
    )

    equipment = Equipment(
        canonical_id="urn:icab:equipment:reactor",
        name="Reactor",
    )

    assert enterprise.entity_type == EntityType.ENTERPRISE
    assert site.entity_type == EntityType.SITE
    assert area.entity_type == EntityType.AREA
    assert work_center.entity_type == EntityType.WORK_CENTER
    assert process_cell.entity_type == EntityType.PROCESS_CELL
    assert equipment.entity_type == EntityType.EQUIPMENT


def test_icab_context_entities():
    process = Process(
        canonical_id="urn:icab:process:reaction",
        name="Reaction Process",
    )

    process_unit = ProcessUnit(
        canonical_id="urn:icab:process-unit:reactor",
        name="Reactor Unit",
    )

    sensor = Sensor(
        canonical_id="urn:icab:sensor:reactor-pressure",
        name="Reactor Pressure Sensor",
    )

    measurement = Measurement(
        canonical_id="urn:icab:measurement:reactor-pressure",
        name="Reactor Pressure",
    )

    alarm = Alarm(
        canonical_id="urn:icab:alarm:reactor-pressure-high",
        name="Reactor Pressure High",
    )

    fault = Fault(
        canonical_id="urn:icab:fault:reactor-pressure",
        name="Reactor Pressure Fault",
    )

    assert process.entity_type == EntityType.PROCESS
    assert process_unit.entity_type == EntityType.PROCESS_UNIT
    assert sensor.entity_type == EntityType.SENSOR
    assert measurement.entity_type == EntityType.MEASUREMENT
    assert alarm.entity_type == EntityType.ALARM
    assert fault.entity_type == EntityType.FAULT


def test_entity_requires_name():
    with pytest.raises(ValidationError):
        Equipment(
            canonical_id="urn:icab:equipment:reactor",
            name="",
        )


def test_entity_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        Equipment(
            canonical_id="urn:icab:equipment:reactor",
            name="Reactor",
            unexpected_field="should_fail",
        )
