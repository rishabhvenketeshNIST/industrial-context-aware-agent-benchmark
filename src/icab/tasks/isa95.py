"""
ICAB v2: the ISA-95 equipment hierarchy as a first-class benchmark
classification concept -- distinct from, but consistent with,
`icab.cim.EntityType`'s existing `ENTERPRISE`/`SITE`/`AREA`/`WORK_CENTER`/
`PROCESS_CELL`/`EQUIPMENT` members (the CIM entity type is what an entity
IS; `ISA95Level` is what LEVEL a use case/task is ASKED ABOUT -- the same
six levels, reused rather than re-invented, but a task doesn't have an
`entity_type` of its own).

Lives under `icab.tasks` (not `icab.usecases`, which re-exports it) so
`icab.tasks.benchmark_task.BenchmarkTask` (which declares an
`isa95_level` field) and `icab.usecases.models.IndustrialUseCase` (which
also declares one) can both depend on it without a package import cycle
between `icab.tasks` and `icab.usecases`.
"""

from __future__ import annotations

from enum import StrEnum


class ISA95Level(StrEnum):
    """The six ISA-95 hierarchy levels ICAB's CIM already models (`icab.cim.EntityType`)."""

    ENTERPRISE = "enterprise"
    SITE = "site"
    AREA = "area"
    WORK_CENTER = "work_center"
    PROCESS_CELL = "process_cell"
    EQUIPMENT = "equipment"


#: Declaration order, top (broadest) to bottom (narrowest) -- used for
#: stable iteration/reporting (`list_isa95_levels`), not a claim that
#: every level has equal real-data support (see
#: `icab.usecases.registry.ISA95_LEVEL_COVERAGE_NOTES`).
ISA95_LEVEL_ORDER: tuple[ISA95Level, ...] = tuple(ISA95Level)
