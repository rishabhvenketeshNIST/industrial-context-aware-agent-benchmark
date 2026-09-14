"""
ICAB v2: discovers and validates `IndustrialUseCase`s, cross-checked
against a `BenchmarkScenarioRegistry` -- the same discipline
`icab.tasks.registry.BenchmarkTaskRegistry` already applies to
`BenchmarkTask.scenario_id`.

Layout: one YAML file per ISA-95 level under a use-case directory, each
holding a `use_cases:` list, e.g. `configs/usecases/equipment.yaml`.

## ISA-95 level coverage -- stated honestly, not filled to look complete

TEP is a single-site, single-process-cell, seven-equipment-item
simulation. It genuinely supports rich, varied REAL benchmark evidence
at the **Equipment** and **Process Cell** levels (the existing tep-v1
task suite, and the ICAB v3 50-question banks at these two levels, are
entirely real TEP data -- `data_provenance="real_tep"`, see
`icab.benchmark.levels`). It has exactly ONE real Site entity and ONE
real Area entity (`icab.tep.adapter.TEPAdapter`) -- real, but with no
variation to study on their own.

TEP has **zero** WorkCenter entities and **zero** multi-site/multi-
enterprise data at all. Rather than leave Enterprise/Site/Work Center
permanently unsupported, ICAB v3 added a CONTROLLED, deterministic,
versioned synthetic benchmark context layer
(`icab.benchmark_context`) -- clearly separate from real TEP data
(tagged `source="icab_benchmark_context"`, never presented as real
plant data), reached through the SAME architecture/context mechanisms
being evaluated. Area and Site are `data_provenance="mixed"` (their one
real TEP entity plus controlled synthetic siblings); Enterprise and
Work Center are `data_provenance="controlled_synthetic"` (no real TEP
analog exists at all). See `docs/benchmark/specification-v3.md` for the
full design and `icab.benchmark.levels.LEVEL_BENCHMARKS` for the
per-level provenance declaration every result can be traced back to.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from icab.scenarios import BenchmarkScenarioRegistry
from icab.tasks.isa95 import ISA95Level

from .models import IndustrialUseCase

#: Honest, current coverage-gap notes per level -- surfaced by
#: `scripts/icab_v2_cli.py list-isa95-levels` and the context design
#: profile generator, so a 0-use-case level reads as a stated limitation
#: rather than a silent absence.
ISA95_LEVEL_COVERAGE_NOTES: dict[ISA95Level, str] = {
    ISA95Level.ENTERPRISE: (
        "50 use-case-backed questions, entirely against the CONTROLLED "
        "benchmark context layer (icab.benchmark_context) -- TEP itself "
        "models a single site with no real multi-site/multi-enterprise "
        "data. See icab.benchmark.levels.LEVEL_BENCHMARKS "
        "(data_provenance='controlled_synthetic')."
    ),
    ISA95Level.SITE: (
        "50 use-case-backed questions across the one REAL Site entity "
        "plus 2 CONTROLLED synthetic sibling sites -- TEP itself has "
        "exactly one real Site entity, with no variation to study on its "
        "own. data_provenance='mixed'."
    ),
    ISA95Level.AREA: (
        "50 use-case-backed questions: real, verified hierarchy facts "
        "over the one real Area entity (Reaction Area) plus CONTROLLED "
        "synthetic sibling areas/KPI content. data_provenance='mixed'."
    ),
    ISA95Level.WORK_CENTER: (
        "50 use-case-backed questions, entirely against the CONTROLLED "
        "benchmark context layer -- TEP's real CIM data has no "
        "WorkCenter entities at all (icab.cim.EntityType.WORK_CENTER is "
        "modeled but never populated by icab.tep.adapter.TEPAdapter). "
        "data_provenance='controlled_synthetic'."
    ),
    ISA95Level.PROCESS_CELL: (
        "Well supported: 50 real questions over the one real Process "
        "Cell, all REAL TEP data. data_provenance='real_tep'."
    ),
    ISA95Level.EQUIPMENT: (
        "Best supported: 50 real questions across all seven real TEP "
        "equipment items and all 41 real measurements, all REAL TEP "
        "data. data_provenance='real_tep'."
    ),
}


def load_use_cases(path: str | Path) -> list[IndustrialUseCase]:
    """Load and validate every use case in one YAML file's `use_cases:` list."""

    path = Path(path)

    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}

    return [IndustrialUseCase.model_validate(entry) for entry in data.get("use_cases", [])]


class IndustrialUseCaseRegistry:
    """
    Discovers every use case under a directory, validating each against a
    `BenchmarkScenarioRegistry`: every `applicable_scenarios` entry must
    name a real, loadable scenario. Use-case ids must be unique across
    all files in the directory.
    """

    def __init__(self, directory: str | Path, *, scenario_registry: BenchmarkScenarioRegistry):
        self.directory = Path(directory)
        self.scenario_registry = scenario_registry

        if not self.directory.exists():
            raise FileNotFoundError(f"Use case directory does not exist: {self.directory}")
        if not self.directory.is_dir():
            raise NotADirectoryError(f"Use case path is not a directory: {self.directory}")

        self._use_cases = self._discover()

    def _discover(self) -> dict[str, IndustrialUseCase]:
        use_cases: dict[str, IndustrialUseCase] = {}

        for path in sorted(self.directory.glob("*.yaml")):
            for use_case in load_use_cases(path):
                if use_case.use_case_id in use_cases:
                    raise ValueError(f"Duplicate use_case_id: {use_case.use_case_id} (in {path})")

                self._validate_against_scenarios(use_case, source=path)
                use_cases[use_case.use_case_id] = use_case

        return use_cases

    def _validate_against_scenarios(self, use_case: IndustrialUseCase, *, source: Path) -> None:
        for scenario_id in use_case.applicable_scenarios:
            try:
                self.scenario_registry.get(scenario_id)
            except KeyError:
                raise ValueError(
                    f"Use case {use_case.use_case_id!r} (in {source}) references unknown "
                    f"scenario {scenario_id!r}."
                ) from None

    def get(self, use_case_id: str) -> IndustrialUseCase:
        try:
            return self._use_cases[use_case_id]
        except KeyError:
            raise KeyError(f"Unknown use_case_id: {use_case_id}") from None

    def list_ids(self) -> list[str]:
        return sorted(self._use_cases)

    def for_level(self, level: ISA95Level) -> list[IndustrialUseCase]:
        return [use_case for use_case in self._use_cases.values() if use_case.isa95_level == level]

    def __len__(self) -> int:
        return len(self._use_cases)

    def __iter__(self):
        return iter(self._use_cases.values())
