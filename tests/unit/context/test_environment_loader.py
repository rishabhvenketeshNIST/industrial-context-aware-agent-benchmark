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
