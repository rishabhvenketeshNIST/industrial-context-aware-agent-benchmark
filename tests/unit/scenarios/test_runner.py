from unittest.mock import Mock

import pytest

from icab.cim import CIMEnvironment
from icab.scenarios import BenchmarkScenario, FaultSchedule, GroundTruth, ScenarioDifficulty
from icab.scenarios.runner import ScenarioRunner
from icab.tep.context_sync import TEPContextSync


def _mock_sync():
    sync = Mock(spec=TEPContextSync)
    sync.sync.return_value = CIMEnvironment()
    return sync


def test_runner_syncs_at_least_once_with_no_warmup_or_faults():
    scenario = BenchmarkScenario(
        scenario_id="s1",
        name="s1",
        difficulty=ScenarioDifficulty.D1,
        objective="obj",
        seed=1,
        duration_hours=0.5,
        sync_interval_hours=0.25,
        ground_truth=GroundTruth(conclusion="ok"),
    )

    context_sync = _mock_sync()
    result = ScenarioRunner(context_sync=context_sync).prepare(scenario)

    assert result.scenario is scenario
    assert result.sync_count == context_sync.sync.call_count
    # initial sync + 2 duration steps (0.5h / 0.25h)
    assert context_sync.sync.call_count == 3
    assert result.simulator.time == pytest.approx(0.5)


def test_runner_activates_fault_at_the_scheduled_time():
    scenario = BenchmarkScenario(
        scenario_id="s2",
        name="s2",
        difficulty=ScenarioDifficulty.D3,
        objective="obj",
        seed=1,
        warmup_hours=0.5,
        duration_hours=1.0,
        sync_interval_hours=0.25,
        faults=[FaultSchedule(disturbance="idv_04", activate_at_hours=0.5)],
        ground_truth=GroundTruth(conclusion="ok", root_cause_disturbance="idv_04"),
    )

    context_sync = _mock_sync()
    result = ScenarioRunner(context_sync=context_sync).prepare(scenario)

    assert result.simulator.time == pytest.approx(1.5)
    assert "idv_04" in result.simulator.available_disturbances()

    fault_events = [
        event for event in result.events if event["type"] == "fault_injected"
    ]
    assert len(fault_events) == 1
    assert fault_events[0]["disturbance"] == "idv_04"
    assert fault_events[0]["time"] == pytest.approx(0.5)


def test_runner_deactivates_a_fault_after_its_duration_elapses():
    """M13-B: duration_hours clears the fault at activate_at_hours +
    duration_hours (a second fault_injected event with active=False),
    rather than leaving it active for the rest of the scenario."""

    scenario = BenchmarkScenario(
        scenario_id="s2b",
        name="s2b",
        difficulty=ScenarioDifficulty.D3,
        objective="obj",
        seed=1,
        warmup_hours=0.5,
        duration_hours=1.0,
        sync_interval_hours=0.25,
        faults=[
            FaultSchedule(disturbance="idv_04", activate_at_hours=0.5, duration_hours=0.5)
        ],
        ground_truth=GroundTruth(conclusion="ok", root_cause_disturbance="idv_04"),
    )

    context_sync = _mock_sync()
    result = ScenarioRunner(context_sync=context_sync).prepare(scenario)

    fault_events = [event for event in result.events if event["type"] == "fault_injected"]
    assert len(fault_events) == 2
    assert fault_events[0]["active"] is True
    assert fault_events[0]["time"] == pytest.approx(0.5)
    assert fault_events[1]["active"] is False
    assert fault_events[1]["time"] == pytest.approx(1.0)


def test_runner_leaves_a_fault_active_when_no_duration_is_given():
    """Pre-M13-B behavior preserved: duration_hours=None (default) never clears the fault."""

    scenario = BenchmarkScenario(
        scenario_id="s2c",
        name="s2c",
        difficulty=ScenarioDifficulty.D3,
        objective="obj",
        seed=1,
        warmup_hours=0.5,
        duration_hours=1.0,
        sync_interval_hours=0.25,
        faults=[FaultSchedule(disturbance="idv_04", activate_at_hours=0.5)],
        ground_truth=GroundTruth(conclusion="ok", root_cause_disturbance="idv_04"),
    )

    context_sync = _mock_sync()
    result = ScenarioRunner(context_sync=context_sync).prepare(scenario)

    fault_events = [event for event in result.events if event["type"] == "fault_injected"]
    assert len(fault_events) == 1
    assert fault_events[0]["active"] is True


def test_runner_does_not_sync_during_warmup():
    scenario = BenchmarkScenario(
        scenario_id="s3",
        name="s3",
        difficulty=ScenarioDifficulty.D1,
        objective="obj",
        seed=1,
        warmup_hours=1.0,
        duration_hours=0.25,
        sync_interval_hours=0.25,
        ground_truth=GroundTruth(conclusion="ok"),
    )

    context_sync = _mock_sync()
    ScenarioRunner(context_sync=context_sync).prepare(scenario)

    # 4 warmup steps produce no sync calls; only the initial sync plus one
    # duration-phase sync should have happened.
    assert context_sync.sync.call_count == 2
