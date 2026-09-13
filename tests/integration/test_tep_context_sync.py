"""
Integration test for the full M4 data flow:

    TEP simulator -> TEPContextSync -> Historian (TimescaleDB)
                                     -> Knowledge Graph (Neo4j)
                                     -> MQTT (Mosquitto)

Confirms canonical IDs, units, timestamps, and provenance ("source") agree
across all three architectures for the same underlying observation.
"""

from datetime import timedelta

from icab.cim import RelationshipType
from icab.context.historian.repository import PostgresHistorianRepository
from icab.context.historian.service import HistorianService
from icab.context.knowledge_graph.repository import Neo4jKnowledgeGraphRepository
from icab.context.knowledge_graph.service import KnowledgeGraphService
from icab.context.mqtt import MQTTClient, TEPMeasurementPublisher
from icab.context.environment_loader import EnvironmentLoader
from icab.tep import TEPContextSync, TEPSimulator

DATABASE_URL = "postgresql://icab:icab@localhost:5432/icab"
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USERNAME = "neo4j"
NEO4J_PASSWORD = "icabpassword"
MQTT_HOST = "localhost"
MQTT_PORT = 1883

REACTOR_PRESSURE_ID = "urn:icab:measurement:reactor_pressure"
REACTOR_EQUIPMENT_ID = "urn:icab:equipment:reactor"


def test_tep_context_sync_reaches_historian_kg_and_mqtt():
    historian = HistorianService(PostgresHistorianRepository(DATABASE_URL))

    kg_repository = Neo4jKnowledgeGraphRepository(
        uri=NEO4J_URI,
        username=NEO4J_USERNAME,
        password=NEO4J_PASSWORD,
    )
    knowledge_graph = KnowledgeGraphService(kg_repository)

    mqtt_client = MQTTClient(MQTT_HOST, MQTT_PORT)
    publisher = TEPMeasurementPublisher(mqtt_client, source="tep-context-sync-test")

    simulator = TEPSimulator()
    simulator.reset(seed=21)
    simulator.step()  # advance past the exact reset instant

    sync = TEPContextSync(
        environment_loader=EnvironmentLoader(
            historian=historian,
            knowledge_graph=knowledge_graph,
        ),
        mqtt_publisher=publisher,
    )

    try:
        with mqtt_client:
            environment = sync.sync(simulator)

        expected_pressure = simulator.get_measurements()["REACTOR_PRESSURE"]
        expected_timestamp = simulator.get_state().timestamp

        # -- Historian --------------------------------------------------
        # A bounded query, not get_current_value's global "latest timestamp
        # across everything" semantics: the historian is shared, persistent
        # infrastructure, and other scenarios' data can legitimately carry
        # a later simulated timestamp than this test's own (default-epoch)
        # simulator -- this test only needs to confirm *its own* write
        # landed correctly, not that it is globally the most recent row.
        matches = historian.get_historical_values(
            REACTOR_PRESSURE_ID,
            expected_timestamp - timedelta(seconds=1),
            expected_timestamp + timedelta(seconds=1),
        )
        assert len(matches) == 1
        observation = matches[0]

        assert observation is not None
        assert observation.value == expected_pressure
        assert observation.unit == "kPa gauge"
        assert observation.timestamp == expected_timestamp
        assert observation.source == "tep"

        # -- Knowledge graph ----------------------------------------------
        reactor = knowledge_graph.get_entity(REACTOR_EQUIPMENT_ID)
        assert reactor is not None
        assert reactor.name == "Reactor"

        relationships = knowledge_graph.get_entity_relationships(REACTOR_EQUIPMENT_ID)
        monitors_pressure = [
            relationship
            for relationship in relationships
            if relationship.predicate == RelationshipType.MONITORS
            and relationship.object == REACTOR_PRESSURE_ID
        ]
        assert len(monitors_pressure) == 1

        # -- MQTT -----------------------------------------------------------
        mqtt_message = mqtt_client.read(
            "icab/tep/reactor/reactor_pressure",
            timeout=1.0,
        )

        assert mqtt_message is not None
        assert mqtt_message.value == expected_pressure
        assert mqtt_message.unit == "kPa gauge"
        assert mqtt_message.canonical_id == REACTOR_PRESSURE_ID
        assert mqtt_message.timestamp == expected_timestamp

        # -- Cross-architecture consistency ------------------------------
        assert observation.value == mqtt_message.value
        assert observation.unit == mqtt_message.unit
        assert observation.timestamp == mqtt_message.timestamp
        assert len(environment.observations) == 41

    finally:
        kg_repository.close()
