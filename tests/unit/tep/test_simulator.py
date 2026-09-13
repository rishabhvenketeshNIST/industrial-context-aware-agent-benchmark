from datetime import UTC, datetime

from icab.tep.simulator import DEFAULT_CHECKPOINT_INTERVAL, TEPSimulator


def test_reset_returns_mode1_steady_state():
    simulator = TEPSimulator()

    state = simulator.reset(seed=42)

    # Published Mode-1 base-case values (Downs & Vogel 1993).
    assert state.operating_state == "NORMAL"
    assert 2700.0 < state.values["REACTOR_PRESSURE"] < 2710.0
    assert 70.0 < state.values["REACTOR_LEVEL"] < 80.0
    assert 115.0 < state.values["REACTOR_TEMPERATURE"] < 125.0


def test_reset_is_deterministic_for_a_given_seed():
    first = TEPSimulator().reset(seed=42)
    second = TEPSimulator().reset(seed=42)

    assert first.values == second.values


def test_step_advances_simulation_time():
    simulator = TEPSimulator()
    simulator.reset(seed=1)

    assert simulator.time == 0.0

    simulator.step()

    assert simulator.time > 0.0
    assert abs(simulator.time - DEFAULT_CHECKPOINT_INTERVAL) < 1e-6


def test_step_accepts_explicit_duration():
    simulator = TEPSimulator()
    simulator.reset(seed=1)

    simulator.step(duration=0.2)

    assert abs(simulator.time - 0.2) < 1e-6


def test_closed_loop_plant_remains_stable_without_faults():
    simulator = TEPSimulator()
    simulator.reset(seed=3)

    for _ in range(20):  # 1 simulated hour
        simulator.step()

    assert not simulator.terminated

    pressure = simulator.get_measurements()["REACTOR_PRESSURE"]
    assert 2600.0 < pressure < 2800.0


def test_inject_fault_rejects_unknown_disturbance():
    simulator = TEPSimulator()
    simulator.reset(seed=1)

    try:
        simulator.inject_fault("not_a_real_disturbance")
    except ValueError as error:
        assert "Unknown TEP disturbance" in str(error)
    else:
        raise AssertionError("Expected ValueError for an unknown disturbance")


def test_inject_fault_is_recorded_as_icab_metadata():
    simulator = TEPSimulator()
    simulator.reset(seed=1)

    simulator.inject_fault("idv_01")

    events = simulator.get_events()

    assert len(events) == 1
    assert events[0]["type"] == "fault_injected"
    assert events[0]["source"] == "icab"
    assert events[0]["disturbance"] == "idv_01"


def test_fault_perturbs_the_plant_within_a_few_hours():
    simulator = TEPSimulator()
    simulator.reset(seed=5)

    for _ in range(20):
        simulator.step()

    baseline_pressure = simulator.get_measurements()["REACTOR_PRESSURE"]

    simulator.inject_fault("idv_01")

    for _ in range(60):  # 3 more simulated hours
        simulator.step()

    perturbed_pressure = simulator.get_measurements()["REACTOR_PRESSURE"]

    assert perturbed_pressure != baseline_pressure


def test_get_state_without_advancing_matches_last_step():
    simulator = TEPSimulator()
    simulator.reset(seed=1)
    simulator.step()

    state = simulator.get_state()
    state_again = simulator.get_state()

    assert state == state_again


def test_get_state_before_reset_raises():
    simulator = TEPSimulator()

    try:
        simulator.get_state()
    except RuntimeError:
        pass
    else:
        raise AssertionError("Expected RuntimeError before reset()")


def test_available_variable_names():
    simulator = TEPSimulator()

    assert len(simulator.available_measurements()) == 41
    assert len(simulator.available_manipulated_variables()) == 12
    assert len(simulator.available_disturbances()) == 28
    assert "idv_01" in simulator.available_disturbances()
    assert "reactor_pressure" in simulator.available_measurements()


def test_epoch_defaults_and_is_overridable():
    default_simulator = TEPSimulator()
    assert default_simulator.epoch == datetime(2026, 1, 1, tzinfo=UTC)

    custom_epoch = datetime(2030, 6, 15, tzinfo=UTC)
    custom_simulator = TEPSimulator(epoch=custom_epoch)
    assert custom_simulator.epoch == custom_epoch

    state = custom_simulator.reset(seed=1)
    assert state.timestamp == custom_epoch


def test_open_loop_mode_does_not_use_controller():
    simulator = TEPSimulator(closed_loop=False)

    state = simulator.reset(seed=1)
    next_state = simulator.step()

    # Open-loop with no disturbance should barely move from steady state
    # over a single short checkpoint.
    assert abs(
        next_state.values["REACTOR_PRESSURE"] - state.values["REACTOR_PRESSURE"]
    ) < 50.0
