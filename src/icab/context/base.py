from abc import ABC, abstractmethod
from datetime import datetime

from icab.cim import Entity, Observation, Relationship


class HistorianRepository(ABC):
    """Backend-independent interface for historical observations."""

    @abstractmethod
    def write_observations(
        self,
        observations: list[Observation],
    ) -> None:
        """Persist observations."""
        raise NotImplementedError

    @abstractmethod
    def get_current_value(
        self,
        measurement_id: str,
    ) -> Observation | None:
        """Return the latest observation for a measurement."""
        raise NotImplementedError

    @abstractmethod
    def get_historical_values(
        self,
        measurement_id: str,
        start_time: datetime,
        end_time: datetime,
    ) -> list[Observation]:
        """Return observations in the requested time range."""
        raise NotImplementedError


class KnowledgeGraphRepository(ABC):
    """Backend-independent interface for CIM entities and relationships."""

    @abstractmethod
    def write_entities(
        self,
        entities: list[Entity],
    ) -> None:
        """Persist CIM entities."""
        raise NotImplementedError

    @abstractmethod
    def write_relationships(
        self,
        relationships: list[Relationship],
    ) -> None:
        """Persist CIM relationships."""
        raise NotImplementedError

    @abstractmethod
    def get_entity(
        self,
        canonical_id: str,
    ) -> Entity | None:
        """Return an entity by canonical ID."""
        raise NotImplementedError

    @abstractmethod
    def get_entity_relationships(
        self,
        canonical_id: str,
    ) -> list[Relationship]:
        """Return relationships involving an entity."""
        raise NotImplementedError
