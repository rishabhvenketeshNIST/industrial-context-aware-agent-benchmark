"""
M13-A integration test: the COMPLETE real TEP process-context
representation (41 measurements, 12 manipulated variables/actuators, and
their MONITORS/ACTUATES/CONTROLS/HAS_LIMIT/ASSOCIATED_WITH relationships)
synchronized from the real TEP simulator into the REAL Neo4j knowledge
graph (and, for one cross-architecture check, the real MQTT broker) --
not an in-memory KG. See tests/unit/context/test_environment_loader.py
and tests/unit/tep/test_real_adapter.py for the fast, in-memory-KG
regression coverage of the same model; this test is the "does it actually
work against the real stack" complement the M13-A validation requires.
"""

from datetime import timedelta

from icab.cim import RelationshipType
from icab.context.environment_loader import EnvironmentLoader
from icab.context.historian.repository import PostgresHistorianRepository
from icab.context.historian.service import HistorianService
from icab.context.knowledge_graph.repository import Neo4jKnowledgeGraphRepository
from icab.context.knowledge_graph.service import KnowledgeGraphService
from icab.context.mqtt import MQTTClient, TEPMeasurementPublisher
from icab.tep import TEPContextSync, TEPSimulator
from icab.tep.measurements import (
    build_real_tep_manipulated_variables,
    build_real_tep_variables,
)

DATABASE_URL = "postgresql://icab:icab@localhost:5432/icab"
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USERNAME = "neo4j"
NEO4J_PASSWORD = "icabpassword"
MQTT_HOST = "localhost"
MQTT_PORT = 1883

REACTOR_TEMPERATURE_ID = "urn:icab:measurement:reactor_temperature"
REACTOR_PRESSURE_ID = "urn:icab:measurement:reactor_pressure"
COOLING_VALVE_ID = "urn:icab:actuator:reactor_cooling_water_valve"
RECYCLE_VALVE_ID = "urn:icab:actuator:compressor_recycle_valve"


def test_full_tep_context_model_syncs_into_the_real_knowledge_graph():
    historian = HistorianService(PostgresHistorianRepository(DATABASE_URL))

    kg_repository = Neo4jKnowledgeGraphRepository(
        uri=NEO4J_URI,
        username=NEO4J_USERNAME,
        password=NEO4J_PASSWORD,
    )
    knowledge_graph = KnowledgeGraphService(kg_repository)

    mqtt_client = MQTTClient(MQTT_HOST, MQTT_PORT)
    publisher = TEPMeasurementPublisher(mqtt_client, source="m13a-completeness-test")

    simulator = TEPSimulator()
    simulator.reset(seed=77)
    simulator.step()  # advance past the exact reset instant

    sync = TEPContextSync(
        environment_loader=EnvironmentLoader(historian=historian, knowledge_graph=knowledge_graph),
        mqtt_publisher=publisher,
    )

    generation_id = "m13a-integration-test-generation"

    try:
        with mqtt_client:
            environment = sync.sync(simulator, generation_id=generation_id)

        # -- requirement 1/3: every published measurement AND manipulated
        # variable actually landed as its own entity in the real KG -----
        for variable in build_real_tep_variables():
            entity = knowledge_graph.get_entity(variable.canonical_id)
            assert entity is not None, f"missing measurement entity: {variable.canonical_id}"
            assert entity.entity_type.value == "Measurement"

        for mv in build_real_tep_manipulated_variables():
            entity = knowledge_graph.get_entity(mv.canonical_id)
            assert entity is not None, f"missing actuator entity: {mv.canonical_id}"
            assert entity.entity_type.value == "Actuator"

        # -- requirement 4: equipment/process hierarchy -------------------
        reactor_relationships = knowledge_graph.get_entity_relationships(
            "urn:icab:equipment:reactor"
        )
        predicates_from_reactor = {r.predicate for r in reactor_relationships}
        assert RelationshipType.PART_OF in predicates_from_reactor
        assert RelationshipType.MONITORS in predicates_from_reactor
        assert RelationshipType.ACTUATES in predicates_from_reactor

        actuates_cooling_valve = [
            r
            for r in reactor_relationships
            if r.predicate == RelationshipType.ACTUATES and r.object == COOLING_VALVE_ID
        ]
        assert len(actuates_cooling_valve) == 1

        # -- requirement 5/6: process/control relationship, with its
        # control-loop-definition provenance, not a hierarchy/monitoring
        # edge -----------------------------------------------------------
        cooling_valve_relationships = knowledge_graph.get_entity_relationships(COOLING_VALVE_ID)
        controls = [
            r for r in cooling_valve_relationships if r.predicate == RelationshipType.CONTROLS
        ]
        assert len(controls) == 1
        assert controls[0].object == REACTOR_TEMPERATURE_ID
        assert controls[0].source == "tep_studio.control.registry.RICKER_MODE1"
        assert controls[0].source_id  # a citation into the reference model, e.g. "mode1.mdl:3058"

        # -- HAS_LIMIT / ASSOCIATED_WITH override chain, its own distinct
        # provenance -------------------------------------------------------
        pressure_relationships = knowledge_graph.get_entity_relationships(REACTOR_PRESSURE_ID)
        has_limit = [r for r in pressure_relationships if r.predicate == RelationshipType.HAS_LIMIT]
        assert len(has_limit) == 1
        alarm_id = has_limit[0].object
        assert alarm_id.startswith("urn:icab:alarm:")
        alarm_entity = knowledge_graph.get_entity(alarm_id)
        assert alarm_entity is not None
        assert alarm_entity.entity_type.value == "Alarm"

        recycle_valve_relationships = knowledge_graph.get_entity_relationships(RECYCLE_VALVE_ID)
        associated_with_alarm = [
            r
            for r in recycle_valve_relationships
            if r.predicate == RelationshipType.ASSOCIATED_WITH
        ]
        assert len(associated_with_alarm) == 1

        # -- requirement 7: generation_id preserved end-to-end through the
        # real read path for every new relationship kind, not just MONITORS
        # (which the M9 regression test already covers) --------------------
        assert controls[0].generation_id == generation_id
        assert actuates_cooling_valve[0].generation_id == generation_id
        assert has_limit[0].generation_id == generation_id

        # -- requirement 9: the same canonical measurement id is what the
        # real MQTT broker publishes under, too (already-verified for KG
        # above) -- cross-architecture identity, not merely asserted -----
        mqtt_message = mqtt_client.read("icab/tep/reactor/reactor_temperature", timeout=1.0)
        assert mqtt_message is not None
        assert mqtt_message.canonical_id == REACTOR_TEMPERATURE_ID == controls[0].object

        expected_temperature = simulator.get_measurements()["REACTOR_TEMPERATURE"]
        assert mqtt_message.value == expected_temperature

        assert len(environment.observations) == 41  # actuators produce none (see measurements.py)

    finally:
        kg_repository.close()
