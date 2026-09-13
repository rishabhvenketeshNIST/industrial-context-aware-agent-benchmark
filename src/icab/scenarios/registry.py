from pathlib import Path

import yaml

from .models import BenchmarkScenario


def load_benchmark_scenario(path: str | Path) -> BenchmarkScenario:
    """Load and validate a benchmark investigation scenario from YAML."""

    path = Path(path)

    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file)

    return BenchmarkScenario.model_validate(data)


class BenchmarkScenarioRegistry:
    """
    Discover and provide deterministic access to benchmark investigation
    scenarios. Scenario IDs must be unique across all YAML files in the
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

    def _discover(self) -> dict[str, BenchmarkScenario]:
        scenarios: dict[str, BenchmarkScenario] = {}

        for path in sorted(self.directory.glob("*.yaml")):
            scenario = load_benchmark_scenario(path)

            if scenario.scenario_id in scenarios:
                raise ValueError(f"Duplicate scenario ID: {scenario.scenario_id}")

            scenarios[scenario.scenario_id] = scenario

        return scenarios

    def get(self, scenario_id: str) -> BenchmarkScenario:
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
