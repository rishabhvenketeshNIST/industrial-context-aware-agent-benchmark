from icab.cim import (
    EntityType,
    Equipment,
    Relationship,
    RelationshipType,
    Site,
)
from icab.context.knowledge_graph.repository import (
    InMemoryKnowledgeGraphRepository,
)


def test_knowledge_graph_stores_and_retrieves_entities():
    repository = InMemoryKnowledgeGraphRepository()

    site = Site(
        canonical_id="urn:icab:site:tep",
        name="Tennessee Eastman Process",
    )

    repository.write_entities([site])

    result = repository.get_entity("urn:icab:site:tep")

    assert result is not None
    assert result.canonical_id == "urn:icab:site:tep"
    assert result.entity_type == EntityType.SITE


def test_knowledge_graph_returns_relationships_for_entity():
    repository = InMemoryKnowledgeGraphRepository()

    site = Site(
        canonical_id="urn:icab:site:tep",
        name="Tennessee Eastman Process",
    )

    reactor = Equipment(
        canonical_id="urn:icab:equipment:reactor",
        name="Reactor",
    )

    relationship = Relationship(
        subject=reactor.canonical_id,
        predicate=RelationshipType.PART_OF,
        object=site.canonical_id,
        source="CIM",
    )

    repository.write_entities([site, reactor])
    repository.write_relationships([relationship])

    result = repository.get_entity_relationships(reactor.canonical_id)

    assert len(result) == 1
    assert result[0].predicate == RelationshipType.PART_OF
    assert result[0].object == site.canonical_id
