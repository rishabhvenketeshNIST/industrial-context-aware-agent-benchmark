from dataclasses import dataclass


@dataclass(frozen=True)
class TEPVariable:
    """A process variable exposed by the TEP prototype."""

    variable_id: str
    name: str
    unit: str
    equipment_id: str
    description: str = ""
    #: Physical-quantity category (e.g. "flow", "pressure", "temperature",
    #: "level", "composition", "work") -- see `_category_for_unit` for how
    #: this is derived for the real measurement set. "" for the static
    #: prototype variables predating this field is never produced; they
    #: are assigned directly in `TEP_VARIABLES` below.
    category: str = ""

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
        category="pressure",
    ),
    TEPVariable(
        variable_id="TEP_PV_REACTOR_TEMPERATURE",
        name="Reactor Temperature",
        unit="degC",
        equipment_id="urn:icab:equipment:reactor",
        category="temperature",
    ),
    TEPVariable(
        variable_id="TEP_PV_REACTOR_LEVEL",
        name="Reactor Level",
        unit="percent",
        equipment_id="urn:icab:equipment:reactor",
        category="level",
    ),
    TEPVariable(
        variable_id="TEP_PV_CONDENSER_TEMPERATURE",
        name="Condenser Temperature",
        unit="degC",
        equipment_id="urn:icab:equipment:condenser",
        category="temperature",
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
#
# M13-A additionally derives, from the SAME `tep-studio` dependency (never
# a second, hand-maintained list):
#   * a physical-quantity `category` for every measurement, from its own
#     published unit (`_category_for_unit`) -- not from a per-variable
#     hand-authored table, so it can't silently drift from the real unit.
#   * the 12 published manipulated variables (`build_real_tep_manipulated_variables`),
#     as first-class ``ManipulatedVariable`` entries with their own
#     canonical ids (`urn:icab:actuator:...`) and equipment assignment.
#   * which (measurement, manipulated variable) pairs are DIRECTLY linked
#     by the real decentralized controller the simulator runs closed-loop
#     (`real_control_loop_pairs`), and the two documented constraint
#     overrides (`real_control_overrides`) -- both read from
#     `tep_studio.control.registry.RICKER_MODE1`, the same control-loop
#     definition `TEPSimulator`'s `RickerMultiLoopController` executes,
#     not asserted independently of it.
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

#: Keyword -> equipment-key mapping used to assign each real manipulated
#: variable to an ISA-95 Equipment entity. A keyword-containment heuristic
#: (rather than the prefix one measurements use) because MV names put the
#: identifying word in the middle (e.g. "d_feed_valve",
#: "separator_cooling_water_valve") -- checked in this order so the more
#: specific equipment keywords never lose to a coincidental "feed"/"purge"
#: substring (none currently collide; order is defensive).
_ACTUATOR_EQUIPMENT_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("reactor", "reactor"),
    ("separator", "separator"),
    ("stripper", "stripper"),
    ("compressor", "compressor"),
    ("condenser", "condenser"),
    ("purge", "purge_system"),
    ("feed", "feed_system"),
)

#: Real measurement unit string -> physical-quantity category. Derived
#: from (and must be kept in sync with) the exact unit strings
#: `tep_studio.list_measurements()` publishes -- not a judgment call per
#: variable, a lookup on the simulator's own unit. A unit not in this
#: table raises rather than silently guessing (see `_category_for_unit`).
_CATEGORY_BY_UNIT: dict[str, str] = {
    "kscmh": "flow",
    "kg/h": "flow",
    "m3/h": "flow",
    "kPa gauge": "pressure",
    "%": "level",
    "degC": "temperature",
    "kW": "work",
    "mol %": "composition",
}


def _category_for_unit(unit: str) -> str:
    try:
        return _CATEGORY_BY_UNIT[unit]
    except KeyError:
        raise ValueError(
            f"No known category for TEP measurement unit: {unit!r}. "
            f"Known units: {sorted(_CATEGORY_BY_UNIT)}"
        ) from None


def derive_real_equipment_id(measurement_name: str) -> str:
    """Map a real TEP measurement name to an ICAB canonical equipment id."""

    for prefix, equipment_key in _EQUIPMENT_PREFIXES:
        if measurement_name.startswith(prefix):
            return REAL_TEP_EQUIPMENT[equipment_key][0]

    raise ValueError(
        f"Cannot derive an equipment assignment for measurement: {measurement_name!r}"
    )


def derive_real_equipment_id_for_actuator(mv_name: str) -> str:
    """Map a real TEP manipulated-variable name to an ICAB canonical equipment id."""

    for keyword, equipment_key in _ACTUATOR_EQUIPMENT_KEYWORDS:
        if keyword in mv_name:
            return REAL_TEP_EQUIPMENT[equipment_key][0]

    raise ValueError(
        f"Cannot derive an equipment assignment for manipulated variable: {mv_name!r}"
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
            category=_category_for_unit(unit),
        )
        for name, unit, description in list_measurements()
    )


@dataclass(frozen=True)
class ManipulatedVariable:
    """
    A manipulated variable (actuator/valve/drive setpoint) exposed by the
    real TEP kernel -- distinct from ``TEPVariable`` (a measured process
    output): an MV is something the control system WRITES, not something
    that is observed. See `icab.cim.Actuator` for the CIM entity this maps
    to.
    """

    variable_id: str
    name: str
    unit: str
    equipment_id: str
    category: str  # "valve" | "speed"
    description: str = ""

    @property
    def canonical_id(self) -> str:
        """Return the ICAB canonical actuator identifier."""
        return f"urn:icab:actuator:{self.variable_id.lower()}"


def build_real_tep_manipulated_variables() -> tuple[ManipulatedVariable, ...]:
    """
    Build a ``ManipulatedVariable`` for every one of the 12 manipulated
    variables published by the real TEP kernel.

    Manipulated-variable CURRENT VALUES are not synchronized anywhere in
    ICAB yet (`TEPSimulator` does not expose a public getter for them --
    only `get_measurements()`, the 41 published measurement outputs) --
    these are structural/identity entities only (used for KG
    ACTUATES/CONTROLS relationships and UNS discovery), with no
    Observation/time-series counterpart yet. See
    docs/architecture/tep-simulator.md.
    """

    from tep_studio import list_manipulated_variables

    return tuple(
        ManipulatedVariable(
            variable_id=name.upper(),
            name=description,
            unit=unit,
            equipment_id=derive_real_equipment_id_for_actuator(name),
            category="speed" if name.endswith("_speed") else "valve",
            description=description,
        )
        for name, unit, description in list_manipulated_variables()
    )


def real_control_loop_pairs() -> tuple[tuple[str, str, str], ...]:
    """
    ``(measurement_variable_id, manipulated_variable_id, source_citation)``
    triples for every DIRECT process-variable -> manipulated-variable
    control pairing in the real TEP kernel's own decentralized control
    strategy (`tep_studio.control.registry.RICKER_MODE1` -- Ricker,
    "Decentralized control of the Tennessee Eastman Challenge Process",
    J. Proc. Cont. 6(4), 1996 -- the SAME controller
    `icab.tep.simulator.TEPSimulator` runs closed-loop by default).

    Not every control loop the registry defines drives a named
    manipulated variable directly -- several instead drive an internal
    setpoint/ratio/composition-trim signal (e.g. reactor_level's loop
    output becomes separator_temperature's setpoint, not a valve
    position). Those cascades are real per the registry, but their
    targets are not first-class ICAB entities in this milestone, so they
    are deliberately left unrepresented here rather than asserting a
    relationship to something that doesn't exist as an entity -- see
    docs/architecture/tep-simulator.md for the full list of excluded
    loops and why. Every triple returned here IS one whose target is a
    real manipulated variable, checked programmatically against
    ``list_manipulated_variables()`` rather than hand-picked.
    """

    from tep_studio import list_manipulated_variables
    from tep_studio.control.registry import RICKER_MODE1

    mv_names = {name for name, _, _ in list_manipulated_variables()}

    pairs: list[tuple[str, str, str]] = []

    for loop in RICKER_MODE1.feed_loops:
        pairs.append((loop.pv.upper(), loop.mv.upper(), loop.source))

    for loop in RICKER_MODE1.pi_loops():
        if loop.pv and loop.drives in mv_names:
            pairs.append((loop.pv.upper(), loop.drives.upper(), loop.source))

    return tuple(pairs)


def real_control_overrides():
    """
    The documented Mode-1 constraint overrides from the same
    `RICKER_MODE1` registry (`tep_studio.control.loops.OverrideSpec`) --
    e.g. "reactor pressure crossing 2900 kPa cuts the production index."
    Each carries its own `confirmed_source` citation (Ricker 1996 sec. 4,
    per the registry's own docstring) distinct from the gain-table
    citations `real_control_loop_pairs` uses.
    """

    from tep_studio.control.registry import RICKER_MODE1

    return RICKER_MODE1.overrides
