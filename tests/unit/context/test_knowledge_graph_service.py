from icab.cim import (
    Equipment,
    Relationship,
    RelationshipType,
    Site,
)
from icab.context.knowledge_graph.repository import (
    InMemoryKnowledgeGraphRepository,
)
from icab.context.knowledge_graph.service import KnowledgeGraphService


def test_knowledge_graph_service_reads_and_writes():
    repository = InMemoryKnowledgeGraphRepository()
    service = KnowledgeGraphService(repository)

    site = Site(
        canonical_id="urn:icab:test:service-site",
        name="Service Test Site",
    )

    reactor = Equipment(
        canonical_id="urn:icab:test:service-reactor",
        name="Service Test Reactor",
    )

    relationship = Relationship(
        subject=reactor.canonical_id,
        predicate=RelationshipType.PART_OF,
        object=site.canonical_id,
        source="service-test",
    )

    service.write_entities([site, reactor])
    service.write_relationships([relationship])

    result = service.get_entity(reactor.canonical_id)

    assert result is not None
    assert result.name == "Service Test Reactor"

    relationships = service.get_entity_relationships(reactor.canonical_id)

    assert len(relationships) == 1
    assert relationships[0].predicate == RelationshipType.PART_OF
