"""
ICAB v2: discovers and validates `IndustrialUseCase`s, cross-checked
against a `BenchmarkScenarioRegistry` -- the same discipline
`icab.tasks.registry.BenchmarkTaskRegistry` already applies to
`BenchmarkTask.scenario_id`.

Layout: one YAML file per ISA-95 level under a use-case directory, each
holding a `use_cases:` list, e.g. `configs/usecases/equipment.yaml`.

## ISA-95 level coverage -- stated honestly, not filled to look complete

TEP is a single-site, single-process-cell, seven-equipment-item
simulation. It genuinely supports rich, varied benchmark evidence at the
**Equipment** and **Process Cell** levels (the existing 38-task tep-v1
suite is entirely at these two levels). It has exactly ONE real Site
entity and ONE real Area entity (`icab.tep.adapter.TEPAdapter`) -- real,
but with no variation to study (nothing to compare against), so **Area**
use cases here are deliberately few and thin (real hierarchy facts, not
scenario-varying investigations). TEP has **zero** WorkCenter entities
and **zero** multi-site/multi-enterprise data at all -- so, per the ICAB
v2 direction's explicit "do not fabricate context merely to fill the
matrix" rule, **Enterprise** and **Work Center** currently have ZERO
registered use cases. This is a real, reported coverage gap, not an
oversight: the framework (`ISA95Level` includes both) is ready for a
future scenario domain that actually has that data.
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
        "No use cases: TEP models a single site with no multi-site/"
        "multi-enterprise data. Framework-ready; requires a future "
        "scenario domain with real multi-site data."
    ),
    ISA95Level.SITE: (
        "No use cases: TEP has exactly one real Site entity, with no "
        "variation to study (nothing to compare it against)."
    ),
    ISA95Level.AREA: (
        "Minimal: TEP has exactly one real Area entity (Reaction Area). "
        "Use cases here are real, verified hierarchy facts (the Area's "
        "own Site/ProcessCell relationships), not scenario-varying "
        "investigations."
    ),
    ISA95Level.WORK_CENTER: (
        "No use cases: TEP's real CIM data has no WorkCenter entities at "
        "all (icab.cim.EntityType.WORK_CENTER is modeled but never "
        "populated by icab.tep.adapter.TEPAdapter)."
    ),
    ISA95Level.PROCESS_CELL: (
        "Well supported: the existing tep-v1 investigation/diagnosis "
        "task suite operates at this level."
    ),
    ISA95Level.EQUIPMENT: (
        "Best supported: most of the existing tep-v1 task suite operates "
        "at this level, across all seven real TEP equipment items."
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
