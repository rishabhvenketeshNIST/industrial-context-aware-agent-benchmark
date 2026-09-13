from datetime import datetime

from icab.cim import (
    Area,
    CIMEnvironment,
    Equipment,
    Measurement,
    Observation,
    ProcessCell,
    Relationship,
    RelationshipType,
    Site,
)

from .measurements import TEP_VARIABLES
from .state import TEPProcessState


class TEPAdapter:
    """Translate the prototype TEP representation into ICAB CIM objects."""

    SITE_ID = "urn:icab:site:tep"
    AREA_ID = "urn:icab:area:reaction"
    PROCESS_CELL_ID = "urn:icab:processcell:reaction"

    EQUIPMENT = {
        "reactor": (
            "urn:icab:equipment:reactor",
            "Reactor",
        ),
        "condenser": (
            "urn:icab:equipment:condenser",
            "Condenser",
        ),
    }

    def get_site(self) -> Site:
        return Site(
            canonical_id=self.SITE_ID,
            name="Tennessee Eastman Process",
            description="Prototype TEP simulation site.",
            source="tep",
            source_id="TEP",
        )

    def get_area(self) -> Area:
        return Area(
            canonical_id=self.AREA_ID,
            name="Reaction Area",
            source="tep",
            source_id="REACTION_AREA",
        )

    def get_process_cell(self) -> ProcessCell:
        return ProcessCell(
            canonical_id=self.PROCESS_CELL_ID,
            name="Reaction Process Cell",
            source="tep",
            source_id="REACTION_CELL",
        )

    def get_equipment(self) -> list[Equipment]:
        return [
            Equipment(
                canonical_id=canonical_id,
                name=name,
                source="tep",
                source_id=key,
            )
            for key, (canonical_id, name) in self.EQUIPMENT.items()
        ]

    def get_hierarchy_relationships(self) -> list[Relationship]:
        return [
            Relationship(
                subject=self.AREA_ID,
                predicate=RelationshipType.PART_OF,
                object=self.SITE_ID,
                source="tep",
            ),
            Relationship(
                subject=self.PROCESS_CELL_ID,
                predicate=RelationshipType.PART_OF,
                object=self.AREA_ID,
                source="tep",
            ),
            *[
                Relationship(
                    subject=equipment_id,
                    predicate=RelationshipType.PART_OF,
                    object=self.PROCESS_CELL_ID,
                    source="tep",
                )
                for equipment_id, _ in self.EQUIPMENT.values()
            ],
        ]

    def get_measurements(self) -> list[Measurement]:
        return [
            Measurement(
                canonical_id=variable.canonical_id,
                name=variable.name,
                source="tep",
                source_id=variable.variable_id,
            )
            for variable in TEP_VARIABLES
        ]

    def get_measurement_relationships(self) -> list[Relationship]:
        relationships = []

        for variable in TEP_VARIABLES:
            measurement_id = variable.canonical_id

            relationships.append(
                Relationship(
                    subject=variable.equipment_id,
                    predicate=RelationshipType.MONITORS,
                    object=measurement_id,
                    source="tep",
                    source_id=variable.variable_id,
                )
            )

        return relationships

    def create_observation(
        self,
        variable_id: str,
        value: float,
        timestamp: datetime,
        observation_id: str,
    ) -> Observation:
        variable = next(
            variable
            for variable in TEP_VARIABLES
            if variable.variable_id == variable_id
        )

        measurement_id = variable.canonical_id

        return Observation(
            observation_id=observation_id,
            measurement_id=measurement_id,
            timestamp=timestamp,
            value=value,
            unit=variable.unit,
            quality="GOOD",
            source="tep",
            source_id=variable.variable_id,
        )

    def build_environment(
        self,
        state: TEPProcessState | None = None,
    ) -> CIMEnvironment:
        """Build a complete prototype TEP CIM environment."""

        entities = [
            self.get_site(),
            self.get_area(),
            self.get_process_cell(),
            *self.get_equipment(),
            *self.get_measurements(),
        ]

        relationships = [
            *self.get_hierarchy_relationships(),
            *self.get_measurement_relationships(),
        ]

        observations = []

        if state is not None:
            observations = self.create_observations(state)

        return CIMEnvironment(
            entities=entities,
            relationships=relationships,
            observations=observations,
        )

    def create_observations(
        self,
        state: TEPProcessState,
    ) -> list[Observation]:
        """Convert a process-state snapshot into CIM observations."""

        observations = []

        for variable_id, value in state.values.items():
            observations.append(
                self.create_observation(
                    variable_id=variable_id,
                    value=value,
                    timestamp=state.timestamp,
                    observation_id=(f"{state.timestamp.isoformat()}:{variable_id}"),
                )
            )

        return observations
