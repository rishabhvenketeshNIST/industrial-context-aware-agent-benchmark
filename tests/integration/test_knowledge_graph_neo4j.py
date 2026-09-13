from icab.cim import (
    Equipment,
    Relationship,
    RelationshipType,
    Site,
)
from icab.context.knowledge_graph.repository import (
    Neo4jKnowledgeGraphRepository,
)

NEO4J_URI = "bolt://localhost:7687"
NEO4J_USERNAME = "neo4j"
NEO4J_PASSWORD = "icabpassword"


def test_neo4j_knowledge_graph_round_trip():
    repository = Neo4jKnowledgeGraphRepository(
        uri=NEO4J_URI,
        username=NEO4J_USERNAME,
        password=NEO4J_PASSWORD,
    )

    try:
        site = Site(
            canonical_id="urn:icab:test:site",
            name="Integration Test Site",
        )

        reactor = Equipment(
            canonical_id="urn:icab:test:reactor",
            name="Integration Test Reactor",
        )

        relationship = Relationship(
            subject=reactor.canonical_id,
            predicate=RelationshipType.PART_OF,
            object=site.canonical_id,
            source="integration-test",
        )

        repository.write_entities([site, reactor])
        repository.write_relationships([relationship])

        retrieved_site = repository.get_entity(site.canonical_id)

        assert retrieved_site is not None
        assert retrieved_site.name == "Integration Test Site"

        relationships = repository.get_entity_relationships(reactor.canonical_id)

        assert len(relationships) == 1
        assert relationships[0].predicate == RelationshipType.PART_OF
        assert relationships[0].object == site.canonical_id

    finally:
        repository.close()
