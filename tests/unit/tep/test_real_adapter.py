from icab.cim import CIMEnvironment, Equipment, Measurement
from icab.tep import TEPAdapter, TEPSimulator
from icab.tep.measurements import build_real_tep_variables, derive_real_equipment_id


def test_build_real_tep_variables_covers_all_published_measurements():
    variables = build_real_tep_variables()

    assert len(variables) == 41

    ids = {variable.canonical_id for variable in variables}
    assert "urn:icab:measurement:reactor_pressure" in ids
    assert "urn:icab:measurement:separator_level" in ids
    assert "urn:icab:measurement:stripper_temperature" in ids

    # Distinct from the legacy prototype canonical ids (no collisions).
    assert "urn:icab:measurement:tep_pv_reactor_pressure" not in ids


def test_derive_real_equipment_id_covers_every_measurement():
    for variable in build_real_tep_variables():
        # Should not raise -- every published measurement name resolves to
        # exactly one of the equipment prefixes.
        equipment_id = derive_real_equipment_id(
            variable.variable_id.lower(),
        )
        assert equipment_id == variable.equipment_id


def test_get_real_equipment():
    adapter = TEPAdapter()

    equipment = adapter.get_real_equipment()

    assert all(isinstance(item, Equipment) for item in equipment)

    ids = {item.canonical_id for item in equipment}
    assert "urn:icab:equipment:reactor" in ids
    assert "urn:icab:equipment:separator" in ids
    assert "urn:icab:equipment:stripper" in ids
    assert "urn:icab:equipment:compressor" in ids


def test_get_real_measurements():
    adapter = TEPAdapter()

    measurements = adapter.get_real_measurements()

    assert len(measurements) == 41
    assert all(isinstance(item, Measurement) for item in measurements)


def test_build_real_environment_without_state():
    adapter = TEPAdapter()

    environment = adapter.build_real_environment()

    assert isinstance(environment, CIMEnvironment)
    assert len(environment.observations) == 0

    entity_ids = {entity.canonical_id for entity in environment.entities}
    assert "urn:icab:measurement:reactor_pressure" in entity_ids


def test_build_real_environment_from_simulator_state():
    adapter = TEPAdapter()
    simulator = TEPSimulator()

    state = simulator.reset(seed=1)

    environment = adapter.build_real_environment(state)

    assert len(environment.observations) == 41

    pressure_observation = next(
        observation
        for observation in environment.observations
        if observation.measurement_id == "urn:icab:measurement:reactor_pressure"
    )

    assert pressure_observation.value == state.values["REACTOR_PRESSURE"]
    assert pressure_observation.unit == "kPa gauge"
    assert pressure_observation.source == "tep"
