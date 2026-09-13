import pytest
from pydantic import ValidationError

from icab.tep.scenarios import (
    ScenarioMeasurement,
    TEPScenario,
    load_scenario,
)


def test_load_normal_scenario():
    scenario = load_scenario("configs/prototype/scenarios/normal_001.yaml")

    assert scenario.scenario_id == "normal_001"
    assert scenario.operating_state == "NORMAL"
    assert scenario.timestamp.tzinfo is not None

    assert len(scenario.measurements) == 4

    assert scenario.measurements["TEP_PV_REACTOR_PRESSURE"].value == 2834.0


def test_scenario_timestamp_is_timezone_aware():
    scenario = TEPScenario(
        scenario_id="test",
        name="Test Scenario",
        operating_state="NORMAL",
        timestamp="2026-09-09T12:00:00Z",
        measurements={
            "TEST_VARIABLE": ScenarioMeasurement(
                value=10.0,
                unit="unit",
            )
        },
    )

    assert scenario.timestamp.tzinfo is not None
    assert scenario.timestamp.utcoffset() is not None


def test_scenario_rejects_naive_timestamp():
    with pytest.raises(ValidationError):
        TEPScenario(
            scenario_id="test",
            name="Test Scenario",
            operating_state="NORMAL",
            timestamp="2026-09-09T12:00:00",
            measurements={},
        )


def test_scenario_to_process_state():
    scenario = load_scenario("configs/prototype/scenarios/normal_001.yaml")

    state = scenario.to_process_state()

    assert state.timestamp == scenario.timestamp
    assert state.operating_state == "NORMAL"

    assert state.values["TEP_PV_REACTOR_PRESSURE"] == 2834.0

    assert len(state.values) == 4
