"""
M13-A: the real TEP measurement/manipulated-variable registry itself --
identity, required metadata, and the control-loop/override derivation
that (measurement, manipulated-variable, generation_id-agnostic
relationship) pairs are built from. See tests/unit/tep/test_real_adapter.py
for the CIM-entity/relationship layer built on top of this registry, and
tests/integration/test_tep_context_model_completeness.py for the real
simulator + real Neo4j validation.
"""

from tep_studio import list_manipulated_variables, list_measurements

from icab.tep.measurements import (
    build_real_tep_manipulated_variables,
    build_real_tep_variables,
    real_control_loop_pairs,
    real_control_overrides,
)


def test_every_published_measurement_has_a_canonical_identity_and_required_metadata():
    """Requirement 1/2: canonical id, stable variable id, name, unit,
    equipment location, category, and source are all present for every
    measurement the simulator actually publishes -- not a hand-picked
    subset."""

    published = list_measurements()
    variables = build_real_tep_variables()

    assert len(variables) == len(published) == 41

    published_names = {name.lower() for name, _, _ in published}
    variable_names = {variable.variable_id.lower() for variable in variables}
    assert variable_names == published_names

    for variable in variables:
        assert variable.canonical_id.startswith("urn:icab:measurement:")
        assert variable.variable_id
        assert variable.name
        assert variable.unit
        assert variable.equipment_id.startswith("urn:icab:equipment:")
        assert variable.category  # non-empty -- see _category_for_unit


def test_measurement_categories_are_derived_from_the_simulators_own_units():
    variables = build_real_tep_variables()

    by_id = {variable.variable_id: variable for variable in variables}

    assert by_id["REACTOR_PRESSURE"].category == "pressure"
    assert by_id["REACTOR_LEVEL"].category == "level"
    assert by_id["REACTOR_TEMPERATURE"].category == "temperature"
    assert by_id["FEED_A_FLOW"].category == "flow"
    assert by_id["COMPRESSOR_WORK"].category == "work"
    assert by_id["REACTOR_FEED_A_CONCENTRATION"].category == "composition"

    # every category actually used is one of the six physical-quantity
    # kinds the 41 measurements' units resolve to -- not a 42nd guess.
    assert {variable.category for variable in variables} == {
        "flow",
        "pressure",
        "level",
        "temperature",
        "work",
        "composition",
    }


def test_every_published_manipulated_variable_has_a_canonical_identity_and_metadata():
    """Requirement 1/2, for the 12 real manipulated variables (actuators)."""

    published = list_manipulated_variables()
    mvs = build_real_tep_manipulated_variables()

    assert len(mvs) == len(published) == 12

    published_names = {name.lower() for name, _, _ in published}
    mv_names = {mv.variable_id.lower() for mv in mvs}
    assert mv_names == published_names

    for mv in mvs:
        assert mv.canonical_id.startswith("urn:icab:actuator:")
        assert mv.variable_id
        assert mv.name
        assert mv.unit == "%"
        assert mv.equipment_id.startswith("urn:icab:equipment:")
        assert mv.category in ("valve", "speed")

    # exactly one speed actuator (the reactor agitator); the rest are valves.
    speeds = [mv for mv in mvs if mv.category == "speed"]
    assert [mv.variable_id for mv in speeds] == ["REACTOR_AGITATOR_SPEED"]


def test_measurement_and_actuator_canonical_ids_never_collide():
    measurement_ids = {variable.canonical_id for variable in build_real_tep_variables()}
    actuator_ids = {mv.canonical_id for mv in build_real_tep_manipulated_variables()}

    assert measurement_ids.isdisjoint(actuator_ids)


def test_control_loop_pairs_only_include_direct_measurement_to_actuator_pairings():
    """
    Every pair's measurement and actuator id must resolve to a real
    entry in the respective registries -- this is the guard against
    accidentally asserting a CONTROLS edge to an internal signal (a
    ratio/setpoint/trim) that isn't a first-class ICAB entity.
    """

    measurement_ids = {variable.variable_id for variable in build_real_tep_variables()}
    actuator_ids = {mv.variable_id for mv in build_real_tep_manipulated_variables()}

    pairs = real_control_loop_pairs()

    assert len(pairs) == 9  # 7 feed/flow loops + reactor/separator temperature

    for pv_id, mv_id, source in pairs:
        assert pv_id in measurement_ids
        assert mv_id in actuator_ids
        assert source  # every pair has a citation into the reference model

    # spot-check a couple of the actually-expected pairings
    by_mv = {mv_id: pv_id for pv_id, mv_id, _ in pairs}
    assert by_mv["REACTOR_COOLING_WATER_VALVE"] == "REACTOR_TEMPERATURE"
    assert by_mv["SEPARATOR_COOLING_WATER_VALVE"] == "SEPARATOR_TEMPERATURE"
    assert by_mv["A_FEED_VALVE"] == "FEED_A_FLOW"


def test_control_loop_pairs_exclude_loops_that_drive_an_internal_signal():
    """
    e.g. reactor_level's loop output becomes separator_temperature's
    SETPOINT (an internal signal), not a manipulated variable directly --
    must not appear as a (reactor_level, <something>) pair.
    """

    pairs = real_control_loop_pairs()
    pvs_with_a_direct_mv = {pv_id for pv_id, _, _ in pairs}

    assert "REACTOR_LEVEL" not in pvs_with_a_direct_mv
    assert "REACTOR_PRESSURE" not in pvs_with_a_direct_mv
    assert "STRIPPER_LEVEL" not in pvs_with_a_direct_mv


def test_control_overrides_are_the_two_documented_mode1_overrides():
    overrides = real_control_overrides()

    assert len(overrides) == 2

    by_name = {override.name: override for override in overrides}
    assert by_name["high_pressure_to_production"].trigger_pv == "reactor_pressure"
    assert by_name["high_level_to_recycle"].trigger_pv == "reactor_level"
    assert by_name["high_level_to_recycle"].target == "compressor_recycle_valve"

    # every override carries its own citation, distinct from a gain-table one.
    for override in overrides:
        assert override.confirmed_source
