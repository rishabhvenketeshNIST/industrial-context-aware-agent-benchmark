from datetime import UTC, datetime

from icab.cim import (
    Area,
    CIMEnvironment,
    Equipment,
    Measurement,
    Observation,
    ProcessCell,
    RelationshipType,
    Site,
)
from icab.tep import TEPAdapter
from icab.tep.measurements import TEP_VARIABLES
from icab.tep.scenarios import load_scenario


def test_get_site():
    adapter = TEPAdapter()

    site = adapter.get_site()

    assert isinstance(site, Site)
    assert site.canonical_id == "urn:icab:site:tep"
    assert site.name == "Tennessee Eastman Process"


def test_get_area():
    adapter = TEPAdapter()

    area = adapter.get_area()

    assert isinstance(area, Area)
    assert area.canonical_id == "urn:icab:area:reaction"


def test_get_process_cell():
    adapter = TEPAdapter()

    process_cell = adapter.get_process_cell()

    assert isinstance(process_cell, ProcessCell)
    assert process_cell.canonical_id == "urn:icab:processcell:reaction"


def test_get_equipment():
    adapter = TEPAdapter()

    equipment = adapter.get_equipment()

    assert len(equipment) == 2
    assert all(isinstance(item, Equipment) for item in equipment)

    ids = {item.canonical_id for item in equipment}

    assert "urn:icab:equipment:reactor" in ids
    assert "urn:icab:equipment:condenser" in ids


def test_hierarchy_relationships():
    adapter = TEPAdapter()

    relationships = adapter.get_hierarchy_relationships()

    assert len(relationships) == 4
    assert all(
        relationship.predicate == RelationshipType.PART_OF
        for relationship in relationships
    )


def test_get_measurements():
    adapter = TEPAdapter()

    measurements = adapter.get_measurements()

    assert len(measurements) == 4
    assert all(isinstance(item, Measurement) for item in measurements)

    names = {item.name for item in measurements}

    assert "Reactor Pressure" in names
    assert "Reactor Temperature" in names


def test_tep_variable_canonical_ids():
    ids = {variable.canonical_id for variable in TEP_VARIABLES}

    assert ids == {
        "urn:icab:measurement:tep_pv_reactor_pressure",
        "urn:icab:measurement:tep_pv_reactor_temperature",
        "urn:icab:measurement:tep_pv_reactor_level",
        "urn:icab:measurement:tep_pv_condenser_temperature",
    }


def test_measurement_relationships():
    adapter = TEPAdapter()

    relationships = adapter.get_measurement_relationships()

    assert len(relationships) == 4
    assert all(
        relationship.predicate == RelationshipType.MONITORS
        for relationship in relationships
    )


def test_create_observation():
    adapter = TEPAdapter()

    timestamp = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)

    observation = adapter.create_observation(
        variable_id="TEP_PV_REACTOR_PRESSURE",
        value=2834.0,
        timestamp=timestamp,
        observation_id="obs-000001",
    )

    assert isinstance(observation, Observation)
    assert observation.measurement_id == "urn:icab:measurement:tep_pv_reactor_pressure"
    assert observation.value == 2834.0
    assert observation.unit == "kPa"
    assert observation.source == "tep"


def test_build_environment():
    adapter = TEPAdapter()

    environment = adapter.build_environment()

    assert isinstance(environment, CIMEnvironment)

    assert len(environment.entities) == 9
    assert len(environment.relationships) == 8
    assert len(environment.observations) == 0

    entity_ids = {entity.canonical_id for entity in environment.entities}

    assert "urn:icab:site:tep" in entity_ids
    assert "urn:icab:area:reaction" in entity_ids
    assert "urn:icab:processcell:reaction" in entity_ids
    assert "urn:icab:equipment:reactor" in entity_ids
    assert "urn:icab:measurement:tep_pv_reactor_pressure" in entity_ids


def test_build_environment_from_process_state():
    adapter = TEPAdapter()

    scenario = load_scenario("configs/prototype/scenarios/normal_001.yaml")

    state = scenario.to_process_state()

    environment = adapter.build_environment(state)

    assert isinstance(environment, CIMEnvironment)

    assert len(environment.entities) == 9
    assert len(environment.relationships) == 8
    assert len(environment.observations) == 4

    observation_ids = {
        observation.observation_id for observation in environment.observations
    }

    assert any(
        "TEP_PV_REACTOR_PRESSURE" in observation_id
        for observation_id in observation_ids
    )


def test_create_observations_from_process_state():
    adapter = TEPAdapter()

    scenario = load_scenario("configs/prototype/scenarios/normal_001.yaml")

    state = scenario.to_process_state()

    observations = adapter.create_observations(state)

    assert len(observations) == 4

    pressure = next(
        observation
        for observation in observations
        if observation.measurement_id == "urn:icab:measurement:tep_pv_reactor_pressure"
    )

    assert pressure.value == 2834.0
    assert pressure.unit == "kPa"
    assert pressure.timestamp == state.timestamp
