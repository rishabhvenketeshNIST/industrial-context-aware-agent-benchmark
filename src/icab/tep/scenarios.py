from datetime import datetime
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .state import TEPProcessState


class ScenarioMeasurement(BaseModel):
    """A deterministic measurement value defined by a scenario."""

    model_config = ConfigDict(extra="forbid")

    value: float
    unit: str = Field(min_length=1)


class TEPScenario(BaseModel):
    """Definition of a deterministic TEP benchmark scenario."""

    model_config = ConfigDict(extra="forbid")

    scenario_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str | None = None

    operating_state: str = Field(min_length=1)

    timestamp: datetime

    measurements: dict[str, ScenarioMeasurement]

    @field_validator("timestamp")
    @classmethod
    def timestamp_must_be_timezone_aware(
        cls,
        value: datetime,
    ) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Scenario timestamp must be timezone-aware.")

        return value

    def to_process_state(self) -> TEPProcessState:
        """Convert the scenario definition into an immutable process state."""

        return TEPProcessState(
            timestamp=self.timestamp,
            operating_state=self.operating_state,
            values={
                variable_id: measurement.value
                for variable_id, measurement in self.measurements.items()
            },
        )


def load_scenario(path: str | Path) -> TEPScenario:
    """Load and validate a TEP scenario from YAML."""

    path = Path(path)

    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file)

    return TEPScenario.model_validate(data)


class ScenarioRegistry:
    """
    Discover and provide deterministic access to TEP scenarios.

    Scenario IDs must be unique across all YAML files in the
    configured directory.
    """

    def __init__(self, directory: str | Path):
        self.directory = Path(directory)

        if not self.directory.exists():
            raise FileNotFoundError(
                f"Scenario directory does not exist: {self.directory}"
            )

        if not self.directory.is_dir():
            raise NotADirectoryError(
                f"Scenario path is not a directory: {self.directory}"
            )

        self._scenarios = self._discover()

    def _discover(self) -> dict[str, TEPScenario]:
        scenarios: dict[str, TEPScenario] = {}

        for path in sorted(self.directory.glob("*.yaml")):
            scenario = load_scenario(path)

            if scenario.scenario_id in scenarios:
                raise ValueError(f"Duplicate scenario ID: {scenario.scenario_id}")

            scenarios[scenario.scenario_id] = scenario

        return scenarios

    def get(self, scenario_id: str) -> TEPScenario:
        """Return a scenario by ID."""

        try:
            return self._scenarios[scenario_id]
        except KeyError:
            raise KeyError(f"Unknown scenario ID: {scenario_id}") from None

    def list_ids(self) -> list[str]:
        """Return scenario IDs in deterministic order."""

        return sorted(self._scenarios)

    def __len__(self) -> int:
        return len(self._scenarios)
