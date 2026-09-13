from pathlib import Path

import pytest

from icab.tep import ScenarioRegistry

SCENARIO_DIR = Path("configs/prototype/scenarios")


def test_registry_discovers_scenarios():
    registry = ScenarioRegistry(SCENARIO_DIR)

    assert len(registry) == 1
    assert registry.list_ids() == ["normal_001"]


def test_registry_get():
    registry = ScenarioRegistry(SCENARIO_DIR)

    scenario = registry.get("normal_001")

    assert scenario.scenario_id == "normal_001"
    assert scenario.name == "Normal TEP Operation"


def test_registry_missing_scenario():
    registry = ScenarioRegistry(SCENARIO_DIR)

    with pytest.raises(KeyError, match="Unknown scenario ID"):
        registry.get("does_not_exist")


def test_registry_missing_directory(tmp_path):
    missing_directory = tmp_path / "does-not-exist"

    with pytest.raises(FileNotFoundError):
        ScenarioRegistry(missing_directory)


def test_registry_rejects_file_as_directory(tmp_path):
    file_path = tmp_path / "scenario.yaml"
    file_path.write_text("test")

    with pytest.raises(NotADirectoryError):
        ScenarioRegistry(file_path)


def test_registry_rejects_duplicate_ids(tmp_path):
    scenario = """
scenario_id: duplicate
name: Duplicate Scenario
operating_state: NORMAL
timestamp: "2026-09-09T12:00:00Z"
measurements: {}
"""

    (tmp_path / "a.yaml").write_text(scenario)
    (tmp_path / "b.yaml").write_text(scenario)

    with pytest.raises(
        ValueError,
        match="Duplicate scenario ID: duplicate",
    ):
        ScenarioRegistry(tmp_path)
