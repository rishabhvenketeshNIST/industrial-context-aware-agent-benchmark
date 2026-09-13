from icab.cim import Actuator, Alarm, CIMEnvironment, Equipment, Measurement, RelationshipType
from icab.tep import TEPAdapter, TEPSimulator
from icab.tep.measurements import (
    build_real_tep_manipulated_variables,
    build_real_tep_variables,
    derive_real_equipment_id,
)


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


# ---------------------------------------------------------------------------
# M13-A: manipulated variables (actuators), CONTROLS/ACTUATES/HAS_LIMIT
# relationships, and generation_id provenance on all of them.
# ---------------------------------------------------------------------------


def test_get_real_actuators():
    adapter = TEPAdapter()

    actuators = adapter.get_real_actuators()

    assert len(actuators) == 12
    assert all(isinstance(item, Actuator) for item in actuators)

    ids = {item.canonical_id for item in actuators}
    assert "urn:icab:actuator:reactor_cooling_water_valve" in ids
    assert "urn:icab:actuator:a_feed_valve" in ids


def test_get_real_actuator_relationships_are_equipment_actuates_actuator():
    adapter = TEPAdapter()

    relationships = adapter.get_real_actuator_relationships()

    assert len(relationships) == 12
    assert all(r.predicate == RelationshipType.ACTUATES for r in relationships)

    reactor_valve = next(
        r for r in relationships if r.object == "urn:icab:actuator:reactor_cooling_water_valve"
    )
    assert reactor_valve.subject == "urn:icab:equipment:reactor"
    assert reactor_valve.source == "tep"


def test_get_real_control_relationships_are_actuator_controls_measurement():
    adapter = TEPAdapter()

    relationships = adapter.get_real_control_relationships()

    assert len(relationships) == 9
    assert all(r.predicate == RelationshipType.CONTROLS for r in relationships)
    assert all(r.subject.startswith("urn:icab:actuator:") for r in relationships)
    assert all(r.object.startswith("urn:icab:measurement:") for r in relationships)
    assert all(r.source == "tep_studio.control.registry.RICKER_MODE1" for r in relationships)

    cooling_valve_controls = next(
        r for r in relationships if r.subject == "urn:icab:actuator:reactor_cooling_water_valve"
    )
    assert cooling_valve_controls.object == "urn:icab:measurement:reactor_temperature"


def test_get_real_alarms():
    adapter = TEPAdapter()

    alarms = adapter.get_real_alarms()

    assert len(alarms) == 2
    assert all(isinstance(item, Alarm) for item in alarms)

    ids = {item.canonical_id for item in alarms}
    assert "urn:icab:alarm:high-pressure-to-production" in ids
    assert "urn:icab:alarm:high-level-to-recycle" in ids


def test_get_real_limit_relationships():
    adapter = TEPAdapter()

    relationships = adapter.get_real_limit_relationships()

    has_limit = [r for r in relationships if r.predicate == RelationshipType.HAS_LIMIT]
    associated_with = [r for r in relationships if r.predicate == RelationshipType.ASSOCIATED_WITH]

    # one HAS_LIMIT per override (2); only one override's target is a real
    # actuator, so only one ASSOCIATED_WITH edge.
    assert len(has_limit) == 2
    assert len(associated_with) == 1

    pressure_limit = next(
        r for r in has_limit if r.subject == "urn:icab:measurement:reactor_pressure"
    )
    assert pressure_limit.object == "urn:icab:alarm:high-pressure-to-production"

    recycle_association = associated_with[0]
    assert recycle_association.subject == "urn:icab:alarm:high-level-to-recycle"
    assert recycle_association.object == "urn:icab:actuator:compressor_recycle_valve"


def test_real_relationships_thread_generation_id_through_every_new_relationship_kind():
    adapter = TEPAdapter()
    generation_id = "test-generation-42"

    actuator_relationships = adapter.get_real_actuator_relationships(generation_id=generation_id)
    control_relationships = adapter.get_real_control_relationships(generation_id=generation_id)
    limit_relationships = adapter.get_real_limit_relationships(generation_id=generation_id)

    assert all(r.generation_id == generation_id for r in actuator_relationships)
    assert all(r.generation_id == generation_id for r in control_relationships)
    assert all(r.generation_id == generation_id for r in limit_relationships)

    # None (the default) preserves untagged behavior.
    assert all(r.generation_id is None for r in adapter.get_real_actuator_relationships())


def test_build_real_environment_includes_actuators_alarms_and_their_relationships():
    adapter = TEPAdapter()

    environment = adapter.build_real_environment()

    entities_by_type: dict[str, int] = {}
    for entity in environment.entities:
        entities_by_type[entity.entity_type.value] = entities_by_type.get(entity.entity_type.value, 0) + 1

    assert entities_by_type["Measurement"] == 41
    assert entities_by_type["Actuator"] == 12
    assert entities_by_type["Alarm"] == 2
    assert entities_by_type["Equipment"] == 7

    relationships_by_predicate: dict[str, int] = {}
    for relationship in environment.relationships:
        key = relationship.predicate.value
        relationships_by_predicate[key] = relationships_by_predicate.get(key, 0) + 1

    assert relationships_by_predicate["MONITORS"] == 41
    assert relationships_by_predicate["ACTUATES"] == 12
    assert relationships_by_predicate["CONTROLS"] == 9
    assert relationships_by_predicate["HAS_LIMIT"] == 2
    assert relationships_by_predicate["ASSOCIATED_WITH"] == 1
    assert relationships_by_predicate["PART_OF"] == 9  # area+processcell+7 equipment


def test_actuator_canonical_ids_agree_between_kg_entities_and_uns_nodes():
    """Requirement 9: the same real manipulated-variable identity is
    recognizable in both the knowledge-graph entity set and the UNS node
    tree -- both derive from build_real_tep_manipulated_variables(), the
    single authoritative registry, not two independently maintained lists."""

    from icab.context.uns.tep_builder import build_real_uns_nodes

    adapter = TEPAdapter()
    kg_actuator_ids = {item.canonical_id for item in adapter.get_real_actuators()}
    uns_actuator_ids = {
        node.canonical_id for node in build_real_uns_nodes() if node.node_type == "actuator"
    }
    registry_ids = {mv.canonical_id for mv in build_real_tep_manipulated_variables()}

    assert kg_actuator_ids == uns_actuator_ids == registry_ids
    assert len(registry_ids) == 12


def test_measurement_canonical_ids_agree_across_kg_uns_and_mqtt():
    """
    Requirement 9, for measurements: the knowledge graph (via TEPAdapter),
    the UNS node tree, and the MQTT publisher's per-message canonical_id
    all resolve to the exact same 41 ids -- because all three read
    build_real_tep_variables() directly rather than each keeping their
    own copy (see icab.context.mqtt.publisher.TEPMeasurementPublisher and
    icab.context.uns.tep_builder.build_real_uns_nodes).
    """

    from unittest.mock import MagicMock

    from icab.context.mqtt import MQTTClient, TEPMeasurementPublisher
    from icab.context.uns.tep_builder import build_real_uns_nodes

    adapter = TEPAdapter()
    kg_measurement_ids = {item.canonical_id for item in adapter.get_real_measurements()}
    uns_measurement_ids = {
        node.canonical_id for node in build_real_uns_nodes() if node.node_type == "measurement"
    }
    registry_ids = {variable.canonical_id for variable in build_real_tep_variables()}

    assert kg_measurement_ids == uns_measurement_ids == registry_ids
    assert len(registry_ids) == 41

    # MQTTMessage.canonical_id, per variable -- no live broker needed,
    # topic_for()/the variable lookup are pure.
    publisher = TEPMeasurementPublisher(MagicMock(spec=MQTTClient), source="identity-test")
    for variable in build_real_tep_variables():
        topic = publisher.topic_for(variable.variable_id)
        assert variable.variable_id.lower() in topic
