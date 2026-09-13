"""
M13-B integration test: inject a REAL, empirically-verified disturbance
into the REAL TEP simulator, advance it, and confirm:

  1. actual process-variable behavior changed (direct measurement
     comparison against a same-seed no-fault baseline -- NOT merely that
     the fault specification says it was injected);
  2. the fault event is recorded separately, as ICAB/benchmark-internal
     bookkeeping (`simulator.get_events()`), not commingled with
     agent-visible data;
  3. the agent-visible context this run produces (real Historian +
     real Neo4j KG + real MQTT, via the actual TEPContextSync/
     ScenarioRunner path) does not expose the fault identifier anywhere,
     even though the fault genuinely happened.

Does not rely on an in-memory KG alone (see
tests/unit/scenarios/test_hidden_ground_truth.py for the fast,
in-memory-agent-messages regression covering the LLM-prompt side of the
same guarantee).
"""

import json

from icab.context.environment_loader import EnvironmentLoader
from icab.context.historian.repository import PostgresHistorianRepository
from icab.context.historian.service import HistorianService
from icab.context.knowledge_graph.repository import Neo4jKnowledgeGraphRepository
from icab.context.knowledge_graph.service import KnowledgeGraphService
from icab.context.mqtt import MQTTClient, TEPMeasurementPublisher
from icab.scenarios import BenchmarkScenario, FaultSchedule, GroundTruth, ScenarioDifficulty
from icab.scenarios.runner import ScenarioRunner
from icab.tep import TEPContextSync, TEPSimulator

DATABASE_URL = "postgresql://icab:icab@localhost:5432/icab"
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USERNAME = "neo4j"
NEO4J_PASSWORD = "icabpassword"
MQTT_HOST = "localhost"
MQTT_PORT = 1883

FAULT_ID = "idv_06"  # empirically verified -- see configs/benchmark/fault_catalog.json


def test_injecting_a_real_disturbance_actually_changes_process_behavior():
    """Requirement: verify the actual process response directly against
    a same-seed baseline, not merely that inject_fault() was called."""

    seed = 909

    baseline = TEPSimulator()
    baseline.reset(seed=seed)
    baseline.step(duration=1.0)  # warmup
    baseline.step(duration=3.0)  # no fault
    baseline_measurements = baseline.get_measurements()

    faulted = TEPSimulator()
    faulted.reset(seed=seed)
    faulted.step(duration=1.0)  # warmup
    faulted.inject_fault(FAULT_ID)
    faulted.step(duration=3.0)
    faulted_measurements = faulted.get_measurements()

    # feed_A_flow is idv_06's most direct, largest-magnitude effect (see
    # the fault catalog) -- should differ substantially from baseline.
    assert faulted_measurements["FEED_A_FLOW"] != baseline_measurements["FEED_A_FLOW"]
    relative_change = abs(
        faulted_measurements["FEED_A_FLOW"] - baseline_measurements["FEED_A_FLOW"]
    ) / max(abs(baseline_measurements["FEED_A_FLOW"]), 1e-9)
    assert relative_change > 0.5  # A feed loss -- a large, unmistakable drop

    # -- fault metadata recorded separately from the measurements
    # themselves (ICAB/benchmark-internal bookkeeping) --
    events = faulted.get_events()
    fault_events = [event for event in events if event["type"] == "fault_injected"]
    assert len(fault_events) == 1
    assert fault_events[0]["disturbance"] == FAULT_ID
    assert fault_events[0]["source"] == "icab"


def test_fault_injection_through_a_scenario_does_not_leak_into_agent_visible_context():
    """The full ScenarioRunner path (real simulator -> real Historian +
    real Neo4j + real MQTT), with a real fault active, produces
    agent-visible data that never mentions the fault id -- even though
    the fault genuinely ran and genuinely changed the plant."""

    historian = HistorianService(PostgresHistorianRepository(DATABASE_URL))
    kg_repository = Neo4jKnowledgeGraphRepository(
        uri=NEO4J_URI, username=NEO4J_USERNAME, password=NEO4J_PASSWORD
    )
    knowledge_graph = KnowledgeGraphService(kg_repository)
    mqtt_client = MQTTClient(MQTT_HOST, MQTT_PORT)
    publisher = TEPMeasurementPublisher(mqtt_client, source="m13b-fault-injection-test")

    scenario = BenchmarkScenario(
        scenario_id="m13b-fault-injection-test",
        name="M13-B fault injection integration test",
        difficulty=ScenarioDifficulty.D4,
        objective="Investigate whether the plant is behaving abnormally.",
        seed=910,
        warmup_hours=0.5,
        duration_hours=1.0,
        sync_interval_hours=0.25,
        faults=[FaultSchedule(disturbance=FAULT_ID, activate_at_hours=0.5)],
        ground_truth=GroundTruth(
            conclusion=f"{FAULT_ID} caused the deviation.",
            root_cause_disturbance=FAULT_ID,
            affected_measurements=["urn:icab:measurement:feed_a_flow"],
            affected_equipment=["urn:icab:equipment:feed-system"],
        ),
    )

    sync = TEPContextSync(
        environment_loader=EnvironmentLoader(historian=historian, knowledge_graph=knowledge_graph),
        mqtt_publisher=publisher,
    )
    runner = ScenarioRunner(context_sync=sync)

    try:
        with mqtt_client:
            result = runner.prepare(scenario)

        # -- the fault genuinely happened (checked via the SAME
        # ICAB-internal event log the previous test uses -- never
        # something an agent could call) --
        fault_events = [e for e in result.events if e["type"] == "fault_injected"]
        assert len(fault_events) == 1
        assert fault_events[0]["disturbance"] == FAULT_ID

        # -- and it genuinely changed the synced measurement value --
        feed_a_observation = next(
            observation
            for observation in result.environment.observations
            if observation.measurement_id == "urn:icab:measurement:feed_a_flow"
        )
        assert feed_a_observation.value < 0.1  # A feed loss -- flow collapses to ~0

        # -- but NONE of the agent-visible surfaces this run touched
        # mention the fault id anywhere --
        forbidden = FAULT_ID.lower()

        for entity in result.environment.entities:
            entity_text = entity.model_dump_json().lower()
            assert forbidden not in entity_text

        for relationship in result.environment.relationships:
            assert forbidden not in relationship.model_dump_json().lower()

        for observation in result.environment.observations:
            assert forbidden not in observation.model_dump_json().lower()

        # -- and the real Neo4j KG entities/relationships this actually
        # wrote don't either (not just the in-memory environment object)
        reactor_relationships = knowledge_graph.get_entity_relationships(
            "urn:icab:equipment:feed-system"
        )
        for relationship in reactor_relationships:
            assert forbidden not in relationship.model_dump_json().lower()

        # -- nor the real historian row for the affected measurement --
        current = historian.get_current_value("urn:icab:measurement:feed_a_flow")
        assert current is not None
        assert forbidden not in json.dumps(current.model_dump(), default=str).lower()

        # -- nor the real MQTT message --
        mqtt_message = mqtt_client.read("icab/tep/feed-system/feed_a_flow", timeout=2.0)
        assert mqtt_message is not None
        assert forbidden not in mqtt_message.model_dump_json().lower()

        # -- generation_id still correctly propagated for every
        # observation this run produced (M9 mechanism, unaffected by
        # M13-B) --
        assert all(
            observation.generation_id == result.generation_id
            for observation in result.environment.observations
        )

    finally:
        kg_repository.close()
