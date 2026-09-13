import pytest
from pydantic import ValidationError

from icab.scenarios import (
    BenchmarkScenario,
    FaultSchedule,
    GroundTruth,
    ScenarioDifficulty,
    TaskMode,
)


def _scenario(**overrides):
    defaults = dict(
        scenario_id="test_scenario",
        name="Test Scenario",
        difficulty=ScenarioDifficulty.D1,
        objective="Investigate something.",
        seed=1,
        duration_hours=1.0,
        ground_truth=GroundTruth(conclusion="Nothing is wrong."),
    )
    defaults.update(overrides)
    return BenchmarkScenario(**defaults)


def test_minimal_scenario_has_sensible_defaults():
    scenario = _scenario()

    assert scenario.task_mode == TaskMode.INVESTIGATION
    assert scenario.warmup_hours == 0.0
    assert scenario.sync_interval_hours == 0.25
    assert scenario.faults == []
    assert "historian" in scenario.available_architectures
    assert "knowledge_graph" in scenario.available_architectures


def test_scenario_rejects_zero_duration():
    with pytest.raises(ValidationError):
        _scenario(duration_hours=0.0)


def test_scenario_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        BenchmarkScenario(
            scenario_id="x",
            name="x",
            difficulty=ScenarioDifficulty.D1,
            objective="x",
            seed=1,
            duration_hours=1.0,
            ground_truth=GroundTruth(conclusion="x"),
            not_a_real_field=True,
        )


def test_fault_schedule_and_ground_truth_round_trip():
    scenario = _scenario(
        difficulty=ScenarioDifficulty.D3,
        faults=[FaultSchedule(disturbance="idv_04", activate_at_hours=1.0)],
        ground_truth=GroundTruth(
            conclusion="Reactor cooling water inlet temperature disturbance.",
            root_cause_disturbance="idv_04",
            affected_measurements=["urn:icab:measurement:reactor_temperature"],
            affected_equipment=["urn:icab:equipment:reactor"],
            expected_relationships=[
                (
                    "urn:icab:equipment:reactor",
                    "MONITORS",
                    "urn:icab:measurement:reactor_temperature",
                )
            ],
            expected_evidence=["urn:icab:measurement:reactor_temperature"],
        ),
    )

    assert scenario.faults[0].disturbance == "idv_04"
    assert scenario.ground_truth.root_cause_disturbance == "idv_04"
    assert scenario.difficulty == ScenarioDifficulty.D3


def test_all_four_difficulty_levels_are_valid():
    for difficulty in (
        ScenarioDifficulty.D1,
        ScenarioDifficulty.D2,
        ScenarioDifficulty.D3,
        ScenarioDifficulty.D4,
    ):
        assert _scenario(difficulty=difficulty).difficulty == difficulty
