"""
M13-B: cross-reference the existing D1-D4 scenarios' fault choices
against the new empirical fault catalog -- confirms D3/D4's own
disturbance selections (made during M5, before this catalog existed)
hold up empirically, and that the catalog/scenario-registry integration
actually works end to end. Loads the REAL, checked-in
configs/benchmark/fault_catalog.json (not a synthetic fixture).
"""

from icab.scenarios import BenchmarkScenarioRegistry
from icab.tep.faults import is_benchmark_ready, load_fault_catalog

SCENARIOS_DIR = "configs/benchmark/scenarios"


def test_d3_and_d4_fault_choices_are_empirically_verified():
    registry = BenchmarkScenarioRegistry(SCENARIOS_DIR)
    catalog = load_fault_catalog()

    d3 = registry.get("d3_reactor_pressure_deviation")
    d4 = registry.get("d4_plant_wide_investigation")

    assert d3.ground_truth.root_cause_disturbance == "idv_01"
    assert d4.ground_truth.root_cause_disturbance == "idv_06"

    assert is_benchmark_ready("idv_01", catalog=catalog) is True
    assert is_benchmark_ready("idv_06", catalog=catalog) is True

    d3_entry = catalog.get("idv_01")
    d4_entry = catalog.get("idv_06")

    # D4's own ground truth is that the REACTOR barely moves while
    # downstream equipment (stripper/compressor/condenser) shows the
    # real effect -- confirm the empirical catalog agrees rather than
    # merely trusting the scenario author's claim.
    assert "urn:icab:equipment:stripper" in d4_entry.affected_equipment
    assert "urn:icab:equipment:compressor" in d4_entry.affected_equipment

    # D3's own ground truth centers on the reactor pressure DECLINE --
    # a real effect (reactor_pressure clears the deviation threshold at
    # seed 101: see tests/unit/tep/test_fault_characterization.py-style
    # single-seed checks), but this characterization's tail-mean-vs-
    # baseline-stdev statistic is seed-sensitive for this specific,
    # gradually-declining (not step-shaped) measurement -- it does NOT
    # repeat at seed 202, so it is correctly excluded from the
    # cross-seed-repeatable `affected_measurements` here. Documented as
    # a real methodological limitation in
    # docs/architecture/tep-fault-injection.md, not papered over.
    # reactor_feed_flow and compressor_work DO repeat across both seeds
    # and are equally reactor/upstream-adjacent evidence for idv_01.
    assert "urn:icab:measurement:reactor_feed_flow" in d3_entry.affected_measurements
    assert "urn:icab:measurement:compressor_work" in d3_entry.affected_measurements


def test_every_scenario_fault_is_at_least_recorded_in_the_catalog():
    """Every disturbance any D1-D4 scenario actually schedules must have
    SOME catalog entry (even if hypothetically unverified) -- a scenario
    referencing a disturbance the characterization run never covered
    would be a real gap worth surfacing, not silently ignored."""

    registry = BenchmarkScenarioRegistry(SCENARIOS_DIR)
    catalog = load_fault_catalog()
    known_ids = {entry.disturbance for entry in catalog.entries}

    for scenario_id in registry.list_ids():
        scenario = registry.get(scenario_id)
        for fault in scenario.faults:
            assert fault.disturbance in known_ids, (
                f"{scenario_id} schedules {fault.disturbance!r}, which has no "
                "fault-catalog entry -- run scripts/characterize_tep_disturbances.py."
            )
