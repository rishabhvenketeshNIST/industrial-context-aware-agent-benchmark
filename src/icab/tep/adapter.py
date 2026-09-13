from datetime import datetime

from icab.cim import (
    Actuator,
    Alarm,
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

from .measurements import (
    REAL_TEP_EQUIPMENT,
    TEP_VARIABLES,
    build_real_tep_manipulated_variables,
    build_real_tep_variables,
    real_control_loop_pairs,
    real_control_overrides,
)
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

    # -----------------------------------------------------------------
    # Real-simulator path.
    #
    # The methods above build a small, hand-picked CIM environment from
    # the four static ``TEP_VARIABLES`` used by the prototype scenario
    # system. The methods below are an additive, parallel path that
    # builds a CIM environment from the full 41-measurement real TEP
    # kernel (see icab.tep.simulator.TEPSimulator). They reuse the same
    # site/area/process-cell hierarchy but introduce additional
    # equipment (separator, stripper, compressor, feed/purge systems)
    # that the real measurement set actually covers.
    # -----------------------------------------------------------------

    def get_real_equipment(self) -> list[Equipment]:
        """Return the ISA-95 equipment entities covered by real measurements."""

        return [
            Equipment(
                canonical_id=canonical_id,
                name=name,
                source="tep",
                source_id=key,
            )
            for key, (canonical_id, name) in REAL_TEP_EQUIPMENT.items()
        ]

    def get_real_hierarchy_relationships(
        self,
        *,
        generation_id: str | None = None,
    ) -> list[Relationship]:
        return [
            Relationship(
                subject=self.AREA_ID,
                predicate=RelationshipType.PART_OF,
                object=self.SITE_ID,
                source="tep",
                generation_id=generation_id,
            ),
            Relationship(
                subject=self.PROCESS_CELL_ID,
                predicate=RelationshipType.PART_OF,
                object=self.AREA_ID,
                source="tep",
                generation_id=generation_id,
            ),
            *[
                Relationship(
                    subject=canonical_id,
                    predicate=RelationshipType.PART_OF,
                    object=self.PROCESS_CELL_ID,
                    source="tep",
                    generation_id=generation_id,
                )
                for canonical_id, _ in REAL_TEP_EQUIPMENT.values()
            ],
        ]

    def get_real_measurements(self) -> list[Measurement]:
        """Return a Measurement entity for each of the 41 real TEP measurements."""

        return [
            Measurement(
                canonical_id=variable.canonical_id,
                name=variable.name,
                description=variable.description or None,
                source="tep",
                source_id=variable.variable_id,
            )
            for variable in build_real_tep_variables()
        ]

    def get_real_measurement_relationships(
        self,
        *,
        generation_id: str | None = None,
    ) -> list[Relationship]:
        relationships = []

        for variable in build_real_tep_variables():
            relationships.append(
                Relationship(
                    subject=variable.equipment_id,
                    predicate=RelationshipType.MONITORS,
                    object=variable.canonical_id,
                    source="tep",
                    source_id=variable.variable_id,
                    generation_id=generation_id,
                )
            )

        return relationships

    # -----------------------------------------------------------------
    # M13-A: manipulated variables (actuators) and control/limit
    # relationships -- additive to the measurement-only KG projection
    # above. See icab.tep.measurements module docstring for the
    # structural/process-control/causal source distinction this follows.
    # -----------------------------------------------------------------

    def get_real_actuators(self) -> list[Actuator]:
        """Return an Actuator entity for each of the 12 real TEP manipulated variables."""

        return [
            Actuator(
                canonical_id=mv.canonical_id,
                name=mv.name,
                description=mv.description or None,
                source="tep",
                source_id=mv.variable_id,
            )
            for mv in build_real_tep_manipulated_variables()
        ]

    def get_real_actuator_relationships(
        self,
        *,
        generation_id: str | None = None,
    ) -> list[Relationship]:
        """
        Equipment ACTUATES actuator, one per manipulated variable --
        structural (the simulator's own MV-naming convention, same
        equipment-assignment heuristic as measurements' MONITORS edges),
        not a control-loop claim.
        """

        return [
            Relationship(
                subject=mv.equipment_id,
                predicate=RelationshipType.ACTUATES,
                object=mv.canonical_id,
                source="tep",
                source_id=mv.variable_id,
                generation_id=generation_id,
            )
            for mv in build_real_tep_manipulated_variables()
        ]

    def get_real_control_relationships(
        self,
        *,
        generation_id: str | None = None,
    ) -> list[Relationship]:
        """
        Actuator CONTROLS measurement, for every DIRECT process-variable
        <- manipulated-variable pairing in the real decentralized control
        strategy the simulator runs closed-loop (see
        icab.tep.measurements.real_control_loop_pairs -- a
        process/control relationship, sourced from the control-loop
        definition itself, not inferred from simulated behavior).
        """

        measurement_ids = {
            variable.variable_id: variable.canonical_id
            for variable in build_real_tep_variables()
        }
        actuator_ids = {
            mv.variable_id: mv.canonical_id for mv in build_real_tep_manipulated_variables()
        }

        return [
            Relationship(
                subject=actuator_ids[mv_id],
                predicate=RelationshipType.CONTROLS,
                object=measurement_ids[pv_id],
                source="tep_studio.control.registry.RICKER_MODE1",
                source_id=citation,
                generation_id=generation_id,
            )
            for pv_id, mv_id, citation in real_control_loop_pairs()
        ]

    def get_real_alarms(self) -> list[Alarm]:
        """
        One Alarm entity per documented Mode-1 constraint override (see
        icab.tep.measurements.real_control_overrides) -- e.g. the
        high-reactor-pressure override that cuts production. Not a FAULT:
        these are protective control actions the plant takes on its own
        measurements, not a diagnosed process fault.
        """

        alarms = []

        for override in real_control_overrides():
            alarms.append(
                Alarm(
                    canonical_id=f"urn:icab:alarm:{override.name.replace('_', '-')}",
                    name=override.name.replace("_", " "),
                    description=(
                        f"Overrides {override.target} when {override.trigger_pv} "
                        f"crosses {override.threshold} (gain {override.gain})."
                    ),
                    source="tep_studio.control.registry.RICKER_MODE1",
                    source_id=override.confirmed_source,
                )
            )

        return alarms

    def get_real_limit_relationships(
        self,
        *,
        generation_id: str | None = None,
    ) -> list[Relationship]:
        """
        measurement HAS_LIMIT alarm, for each documented override's
        trigger measurement; alarm ASSOCIATED_WITH actuator when the
        override's target is itself a real manipulated variable (one
        override's target, "production_index", is an internal signal
        with no ICAB entity, so it gets a HAS_LIMIT edge but no second
        ASSOCIATED_WITH edge -- left absent rather than invented).
        """

        measurement_ids = {
            variable.variable_id.lower(): variable.canonical_id
            for variable in build_real_tep_variables()
        }
        actuator_ids = {
            mv.variable_id.lower(): mv.canonical_id
            for mv in build_real_tep_manipulated_variables()
        }

        relationships = []

        for override in real_control_overrides():
            alarm_id = f"urn:icab:alarm:{override.name.replace('_', '-')}"

            relationships.append(
                Relationship(
                    subject=measurement_ids[override.trigger_pv],
                    predicate=RelationshipType.HAS_LIMIT,
                    object=alarm_id,
                    source="tep_studio.control.registry.RICKER_MODE1",
                    source_id=override.confirmed_source,
                    generation_id=generation_id,
                )
            )

            if override.target in actuator_ids:
                relationships.append(
                    Relationship(
                        subject=alarm_id,
                        predicate=RelationshipType.ASSOCIATED_WITH,
                        object=actuator_ids[override.target],
                        source="tep_studio.control.registry.RICKER_MODE1",
                        source_id=override.confirmed_source,
                        generation_id=generation_id,
                    )
                )

        return relationships

    def create_real_observation(
        self,
        variable_id: str,
        value: float,
        timestamp: datetime,
        observation_id: str,
        *,
        generation_id: str | None = None,
    ) -> Observation:
        variable = next(
            variable
            for variable in build_real_tep_variables()
            if variable.variable_id == variable_id
        )

        return Observation(
            observation_id=observation_id,
            measurement_id=variable.canonical_id,
            timestamp=timestamp,
            value=value,
            unit=variable.unit,
            quality="GOOD",
            source="tep",
            source_id=variable.variable_id,
            generation_id=generation_id,
        )

    def create_real_observations(
        self,
        state: TEPProcessState,
        *,
        generation_id: str | None = None,
    ) -> list[Observation]:
        """Convert a real-simulator process-state snapshot into CIM observations."""

        return [
            self.create_real_observation(
                variable_id=variable_id,
                value=value,
                timestamp=state.timestamp,
                observation_id=f"{state.timestamp.isoformat()}:{variable_id}",
                generation_id=generation_id,
            )
            for variable_id, value in state.values.items()
        ]

    def build_real_environment(
        self,
        state: TEPProcessState | None = None,
        *,
        generation_id: str | None = None,
    ) -> CIMEnvironment:
        """
        Build a CIM environment from the real (41-measurement) TEP kernel.

        ``generation_id``, when given, tags every relationship and
        observation this call produces (see
        icab.scenarios.runner.ScenarioRunner, which mints one per scenario
        preparation) -- the provenance mechanism that lets a benchmark run
        tell its own generation's data apart from an unrelated earlier
        run's leftovers in the same shared, persistent historian/knowledge
        graph. None (the default) preserves prior behavior: untagged data,
        as written before this mechanism existed.
        """

        entities = [
            self.get_site(),
            self.get_area(),
            self.get_process_cell(),
            *self.get_real_equipment(),
            *self.get_real_measurements(),
            *self.get_real_actuators(),
            *self.get_real_alarms(),
        ]

        relationships = [
            *self.get_real_hierarchy_relationships(generation_id=generation_id),
            *self.get_real_measurement_relationships(generation_id=generation_id),
            *self.get_real_actuator_relationships(generation_id=generation_id),
            *self.get_real_control_relationships(generation_id=generation_id),
            *self.get_real_limit_relationships(generation_id=generation_id),
        ]

        observations = []

        if state is not None:
            observations = self.create_real_observations(state, generation_id=generation_id)

        return CIMEnvironment(
            entities=entities,
            relationships=relationships,
            observations=observations,
        )
