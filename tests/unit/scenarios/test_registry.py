from icab.scenarios import BenchmarkScenarioRegistry, ScenarioDifficulty, load_benchmark_scenario

SCENARIOS_DIR = "configs/benchmark/scenarios"


def test_load_each_committed_scenario_file():
    for filename in (
        "d1_reactor_pressure_reading.yaml",
        "d2_reactor_context_combination.yaml",
        "d3_reactor_pressure_deviation.yaml",
        "d4_plant_wide_investigation.yaml",
    ):
        scenario = load_benchmark_scenario(f"{SCENARIOS_DIR}/{filename}")
        assert scenario.scenario_id
        assert scenario.objective
        assert scenario.ground_truth.conclusion


def test_registry_discovers_at_least_one_scenario_per_difficulty():
    """
    M13-C added 5 more scenarios (9 total) built on additional
    empirically-verified M13-B faults -- this no longer asserts an exact
    count (that would need updating every time a scenario is added), just
    that every locked difficulty level still has real coverage.
    """

    registry = BenchmarkScenarioRegistry(SCENARIOS_DIR)

    assert len(registry) >= 4

    difficulties = {registry.get(scenario_id).difficulty for scenario_id in registry.list_ids()}

    assert difficulties == {
        ScenarioDifficulty.D1,
        ScenarioDifficulty.D2,
        ScenarioDifficulty.D3,
        ScenarioDifficulty.D4,
    }


def test_d1_is_the_simplest_single_architecture_scenario():
    registry = BenchmarkScenarioRegistry(SCENARIOS_DIR)
    scenario = registry.get("d1_reactor_pressure_reading")

    assert scenario.difficulty == ScenarioDifficulty.D1
    assert scenario.available_architectures == ["historian"]
    assert scenario.faults == []


def test_d3_and_d4_scenarios_schedule_a_real_fault():
    registry = BenchmarkScenarioRegistry(SCENARIOS_DIR)

    d3 = registry.get("d3_reactor_pressure_deviation")
    assert len(d3.faults) == 1
    assert d3.faults[0].disturbance == "idv_01"
    assert d3.ground_truth.root_cause_disturbance == "idv_01"

    d4 = registry.get("d4_plant_wide_investigation")
    assert len(d4.faults) == 1
    assert d4.faults[0].disturbance == "idv_06"
    assert len(d4.available_architectures) == 5


def test_registry_rejects_unknown_scenario_id():
    registry = BenchmarkScenarioRegistry(SCENARIOS_DIR)

    try:
        registry.get("not_a_real_scenario")
    except KeyError:
        pass
    else:
        raise AssertionError("Expected KeyError for an unknown scenario id")
