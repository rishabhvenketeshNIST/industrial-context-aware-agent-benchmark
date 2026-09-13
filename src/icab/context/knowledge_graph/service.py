from icab.cim import Entity, Relationship
from icab.context.base import KnowledgeGraphRepository


class KnowledgeGraphService:
    """
    Application-level service for knowledge graph operations.
    """

    def __init__(
        self,
        repository: KnowledgeGraphRepository,
    ) -> None:
        self.repository = repository

    def write_entities(
        self,
        entities: list[Entity],
    ) -> None:
        self.repository.write_entities(entities)

    def write_relationships(
        self,
        relationships: list[Relationship],
    ) -> None:
        self.repository.write_relationships(relationships)

    def get_entity(
        self,
        canonical_id: str,
    ) -> Entity | None:
        return self.repository.get_entity(canonical_id)

    def get_entity_relationships(
        self,
        canonical_id: str,
    ) -> list[Relationship]:
        return self.repository.get_entity_relationships(canonical_id)
