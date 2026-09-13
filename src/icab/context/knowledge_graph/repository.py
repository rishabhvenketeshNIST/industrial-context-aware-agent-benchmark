from icab.cim import Entity, Relationship
from icab.context.base import KnowledgeGraphRepository


class InMemoryKnowledgeGraphRepository(KnowledgeGraphRepository):
    """
    In-memory knowledge graph used for unit tests and lightweight prototypes.
    """

    def __init__(self) -> None:
        self._entities: dict[str, Entity] = {}
        self._relationships: list[Relationship] = []

    def write_entities(
        self,
        entities: list[Entity],
    ) -> None:
        for entity in entities:
            self._entities[entity.canonical_id] = entity

    def write_relationships(
        self,
        relationships: list[Relationship],
    ) -> None:
        self._relationships.extend(relationships)

    def get_entity(
        self,
        canonical_id: str,
    ) -> Entity | None:
        return self._entities.get(canonical_id)

    def get_entity_relationships(
        self,
        canonical_id: str,
    ) -> list[Relationship]:
        return [
            relationship
            for relationship in self._relationships
            if (
                relationship.subject == canonical_id
                or relationship.object == canonical_id
            )
        ]


from neo4j import GraphDatabase

from icab.cim import Entity, Relationship
from icab.context.base import KnowledgeGraphRepository


class Neo4jKnowledgeGraphRepository(KnowledgeGraphRepository):
    """
    Neo4j-backed implementation of the ICAB knowledge graph contract.
    """

    def __init__(
        self,
        uri: str,
        username: str,
        password: str,
    ) -> None:
        self._driver = GraphDatabase.driver(
            uri,
            auth=(username, password),
        )

    def close(self) -> None:
        """Close the Neo4j driver."""
        self._driver.close()

    def write_entities(
        self,
        entities: list[Entity],
    ) -> None:
        if not entities:
            return

        with self._driver.session() as session:
            session.execute_write(
                self._write_entities,
                entities,
            )

    @staticmethod
    def _write_entities(
        tx,
        entities: list[Entity],
    ) -> None:
        for entity in entities:
            tx.run(
                """
                MERGE (e:Entity {canonical_id: $canonical_id})
                SET
                    e.entity_type = $entity_type,
                    e.name = $name,
                    e.description = $description,
                    e.source = $source,
                    e.source_id = $source_id
                """,
                canonical_id=entity.canonical_id,
                entity_type=entity.entity_type.value,
                name=entity.name,
                description=entity.description,
                source=entity.source,
                source_id=entity.source_id,
            )

    def write_relationships(
        self,
        relationships: list[Relationship],
    ) -> None:
        if not relationships:
            return

        with self._driver.session() as session:
            session.execute_write(
                self._write_relationships,
                relationships,
            )

    @staticmethod
    def _write_relationships(
        tx,
        relationships: list[Relationship],
    ) -> None:
        for relationship in relationships:
            tx.run(
                """
                MATCH (subject:Entity {canonical_id: $subject})
                MATCH (object:Entity {canonical_id: $object})
                MERGE (
                    subject
                )-[r:RELATIONSHIP {
                    predicate: $predicate
                }]->(
                    object
                )
                SET
                    r.source = $source,
                    r.source_id = $source_id
                """,
                subject=relationship.subject,
                predicate=relationship.predicate.value,
                object=relationship.object,
                source=relationship.source,
                source_id=relationship.source_id,
            )

    def get_entity(
        self,
        canonical_id: str,
    ) -> Entity | None:
        with self._driver.session() as session:
            record = session.execute_read(
                self._get_entity,
                canonical_id,
            )

        if record is None:
            return None

        return Entity.model_validate(record)

    @staticmethod
    def _get_entity(
        tx,
        canonical_id: str,
    ) -> dict | None:
        result = tx.run(
            """
            MATCH (e:Entity {canonical_id: $canonical_id})
            RETURN e {
                .canonical_id,
                .entity_type,
                .name,
                .description,
                .source,
                .source_id
            } AS entity
            """,
            canonical_id=canonical_id,
        )

        record = result.single()

        if record is None:
            return None

        return record["entity"]

    def get_entity_relationships(
        self,
        canonical_id: str,
    ) -> list[Relationship]:
        with self._driver.session() as session:
            records = session.execute_read(
                self._get_entity_relationships,
                canonical_id,
            )

        return [Relationship.model_validate(record) for record in records]

    @staticmethod
    def _get_entity_relationships(
        tx,
        canonical_id: str,
    ) -> list[dict]:
        result = tx.run(
            """
            MATCH (subject:Entity)-[r:RELATIONSHIP]->(object:Entity)
            WHERE subject.canonical_id = $canonical_id
                OR object.canonical_id = $canonical_id
            RETURN {
                subject: subject.canonical_id,
                predicate: r.predicate,
                object: object.canonical_id,
                source: r.source,
                source_id: r.source_id
            } AS relationship
            ORDER BY relationship.subject,
                     relationship.predicate,
                     relationship.object
            """,
            canonical_id=canonical_id,
        )

        return [record["relationship"] for record in result]
