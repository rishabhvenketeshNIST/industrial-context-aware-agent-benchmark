from dataclasses import dataclass


@dataclass(frozen=True)
class TEPVariable:
    """A process variable exposed by the TEP prototype."""

    variable_id: str
    name: str
    unit: str
    equipment_id: str
    description: str = ""

    @property
    def canonical_id(self) -> str:
        """Return the ICAB canonical measurement identifier."""
        return f"urn:icab:measurement:{self.variable_id.lower()}"


TEP_VARIABLES = (
    TEPVariable(
        variable_id="TEP_PV_REACTOR_PRESSURE",
        name="Reactor Pressure",
        unit="kPa",
        equipment_id="urn:icab:equipment:reactor",
    ),
    TEPVariable(
        variable_id="TEP_PV_REACTOR_TEMPERATURE",
        name="Reactor Temperature",
        unit="degC",
        equipment_id="urn:icab:equipment:reactor",
    ),
    TEPVariable(
        variable_id="TEP_PV_REACTOR_LEVEL",
        name="Reactor Level",
        unit="percent",
        equipment_id="urn:icab:equipment:reactor",
    ),
    TEPVariable(
        variable_id="TEP_PV_CONDENSER_TEMPERATURE",
        name="Condenser Temperature",
        unit="degC",
        equipment_id="urn:icab:equipment:condenser",
    ),
)


# ---------------------------------------------------------------------------
# Real-simulator measurement registry
#
# ``TEP_VARIABLES`` above are four illustrative, ICAB-named prototype
# variables used by the static prototype scenario/adapter path. The registry
# below instead mirrors, one-to-one, the 41 published measurements of the
# real Downs & Vogel Tennessee Eastman Process kernel exposed through the
# `tep-studio` dependency (see icab.tep.simulator.TEPSimulator). Using the
# simulator's own names and units directly (rather than inventing new ones)
# avoids fabricating industrial semantics.
# ---------------------------------------------------------------------------

#: (equipment key, canonical equipment id, display name) for the equipment
#: introduced by the real measurement set. "reactor" and "condenser" reuse
#: the same canonical ids as the prototype TEPAdapter.EQUIPMENT so that a
#: combined environment refers to the same physical reactor/condenser.
REAL_TEP_EQUIPMENT: dict[str, tuple[str, str]] = {
    "reactor": ("urn:icab:equipment:reactor", "Reactor"),
    "condenser": ("urn:icab:equipment:condenser", "Condenser"),
    "separator": ("urn:icab:equipment:separator", "Separator"),
    "stripper": ("urn:icab:equipment:stripper", "Stripper"),
    "compressor": ("urn:icab:equipment:compressor", "Compressor"),
    "purge_system": ("urn:icab:equipment:purge-system", "Purge System"),
    "feed_system": ("urn:icab:equipment:feed-system", "Feed System"),
}

#: Ordered prefix -> equipment-key mapping used to assign each real
#: measurement to an ISA-95 Equipment entity. This is a simple, documented
#: heuristic based on the simulator's own measurement naming convention
#: (e.g. "reactor_pressure" -> reactor), not a precise P&ID-derived
#: assignment.
_EQUIPMENT_PREFIXES: tuple[tuple[str, str], ...] = (
    ("reactor_", "reactor"),
    ("condenser_", "condenser"),
    ("separator_", "separator"),
    ("stripper_", "stripper"),
    ("compressor_", "compressor"),
    ("purge_", "purge_system"),
    ("feed_", "feed_system"),
    ("recycle_", "feed_system"),
)


def derive_real_equipment_id(measurement_name: str) -> str:
    """Map a real TEP measurement name to an ICAB canonical equipment id."""

    for prefix, equipment_key in _EQUIPMENT_PREFIXES:
        if measurement_name.startswith(prefix):
            return REAL_TEP_EQUIPMENT[equipment_key][0]

    raise ValueError(
        f"Cannot derive an equipment assignment for measurement: {measurement_name!r}"
    )


def build_real_tep_variables() -> tuple[TEPVariable, ...]:
    """
    Build a ``TEPVariable`` for every measurement published by the real TEP
    kernel (via the optional ``tep-studio`` dependency).

    ``variable_id`` is the measurement name upper-cased (e.g.
    ``REACTOR_PRESSURE``), giving canonical ids such as
    ``urn:icab:measurement:reactor_pressure`` -- distinct from the
    ``tep_pv_*`` ids used by the static prototype variables above.
    """

    from tep_studio import list_measurements

    return tuple(
        TEPVariable(
            variable_id=name.upper(),
            name=description,
            unit=unit,
            equipment_id=derive_real_equipment_id(name),
            description=description,
        )
        for name, unit, description in list_measurements()
    )
