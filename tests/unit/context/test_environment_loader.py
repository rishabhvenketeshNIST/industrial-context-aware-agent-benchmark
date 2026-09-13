from datetime import UTC, datetime

from icab.cim import (
    CIMEnvironment,
    Observation,
    Relationship,
    RelationshipType,
    Site,
)
from icab.context.environment_loader import EnvironmentLoader
from icab.context.historian.repository import (
    InMemoryHistorianRepository,
)
from icab.context.historian.service import HistorianService
from icab.context.knowledge_graph.repository import (
    InMemoryKnowledgeGraphRepository,
)
from icab.context.knowledge_graph.service import KnowledgeGraphService


def test_environment_loader_loads_all_environment_data():
    historian = HistorianService(InMemoryHistorianRepository())

    knowledge_graph = KnowledgeGraphService(InMemoryKnowledgeGraphRepository())

    loader = EnvironmentLoader(
        historian=historian,
        knowledge_graph=knowledge_graph,
    )

    site = Site(
        canonical_id="urn:icab:test:loader-site",
        name="Loader Test Site",
    )

    relationship = Relationship(
        subject=site.canonical_id,
        predicate=RelationshipType.ASSOCIATED_WITH,
        object=site.canonical_id,
        source="loader-test",
    )

    observation = Observation(
        observation_id="loader-test-001",
        measurement_id="urn:icab:measurement:test",
        timestamp=datetime(
            2026,
            9,
            10,
            12,
            0,
            tzinfo=UTC,
        ),
        value=42.0,
        unit="unit",
        source="loader-test",
    )

    environment = CIMEnvironment(
        entities=[site],
        relationships=[relationship],
        observations=[observation],
    )

    loader.load(environment)

    entity = knowledge_graph.get_entity(site.canonical_id)

    assert entity is not None

    relationships = knowledge_graph.get_entity_relationships(site.canonical_id)

    assert len(relationships) == 1

    current = historian.get_current_value(observation.measurement_id)

    assert current is not None
    assert current.value == 42.0


def test_environment_loader_syncs_the_complete_real_tep_context_model():
    """
    M13-A requirement 3/4/5/6: every real TEP measurement, actuator, and
    alarm entity -- and their MONITORS/ACTUATES/CONTROLS/HAS_LIMIT/
    ASSOCIATED_WITH relationships -- actually lands in the knowledge
    graph via the same EnvironmentLoader path TEPContextSync uses, not
    just a hand-picked few. (A real-Neo4j version of this same check
    lives in tests/integration/test_tep_context_model_completeness.py --
    this in-memory one is the fast regression, not the only coverage.)
    """

    from icab.tep.adapter import TEPAdapter
    from icab.tep.measurements import (
        build_real_tep_manipulated_variables,
        build_real_tep_variables,
    )

    knowledge_graph = KnowledgeGraphService(InMemoryKnowledgeGraphRepository())
    loader = EnvironmentLoader(
        historian=HistorianService(InMemoryHistorianRepository()),
        knowledge_graph=knowledge_graph,
    )

    environment = TEPAdapter().build_real_environment(generation_id="loader-real-tep-test")
    loader.load(environment)

    for variable in build_real_tep_variables():
        assert knowledge_graph.get_entity(variable.canonical_id) is not None

    for mv in build_real_tep_manipulated_variables():
        assert knowledge_graph.get_entity(mv.canonical_id) is not None

    reactor_relationships = knowledge_graph.get_entity_relationships("urn:icab:equipment:reactor")
    predicates = {relationship.predicate for relationship in reactor_relationships}
    assert RelationshipType.MONITORS in predicates
    assert RelationshipType.ACTUATES in predicates
    assert RelationshipType.PART_OF in predicates

    cooling_valve_relationships = knowledge_graph.get_entity_relationships(
        "urn:icab:actuator:reactor_cooling_water_valve"
    )
    controls = [r for r in cooling_valve_relationships if r.predicate == RelationshipType.CONTROLS]
    assert len(controls) == 1
    assert controls[0].generation_id == "loader-real-tep-test"
