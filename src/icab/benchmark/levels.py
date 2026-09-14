"""
Six separate, ISA-95-level-specific benchmark definitions -- each with
its own benchmark id, question-bank directory, and results root, sharing
everything else (evaluator, agents, gateway, architecture adapters).

    ICAB Benchmark Suite
    |
    +-- Enterprise Benchmark   (framework-ready, not yet data-supported)
    +-- Site Benchmark         (framework-ready, not yet data-supported)
    +-- Area Benchmark         (real, thin)
    +-- Work Center Benchmark  (framework-ready, not yet data-supported)
    +-- Process Cell Benchmark (real)
    +-- Equipment Benchmark    (real, best-supported)

`data_supported`/`executable` are stated explicitly and honestly per
level (mirrors `icab.usecases.registry.ISA95_LEVEL_COVERAGE_NOTES`,
extended here with a hard `executable` flag a runner can check before
even attempting to load a question bank) -- TEP genuinely has no
Enterprise/Site/Work-Center data, and this framework does not fabricate
any to make those three benchmarks runnable.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from icab.tasks.isa95 import ISA95Level

#: This layer's own version -- bump only if the LEVEL-BENCHMARK
#: structure itself changes (e.g. a new required manifest field), not
#: for ordinary question-bank content changes (those bump
#: ISA95BenchmarkDefinition.question_bank_version instead).
BENCHMARK_LEVELS_VERSION = "1.0.0"


@dataclass(frozen=True)
class ISA95BenchmarkDefinition:
    """One ISA-95 level's own, independent benchmark."""

    benchmark_id: str
    isa95_level: ISA95Level
    name: str

    #: ISA95Level is modeled by the framework for every level -- always True.
    framework_supported: bool
    #: Whether ICAB's current data source (TEP) genuinely provides real
    #: information at this level.
    data_supported: bool
    #: Whether this benchmark can actually be run right now -- False
    #: whenever data_supported is False (a runner must refuse, not
    #: attempt a run against an empty/fabricated question bank).
    executable: bool
    #: Stated honestly either way -- surfaced by
    #: scripts/icab_v2_cli.py list-benchmarks.
    coverage_note: str

    question_bank_dir: Path
    question_bank_version: str

    #: Root under which this benchmark's OWN results live -- see
    #: icab.benchmark.question_runner / docs/benchmark/specification-v3.md
    #: for the full results/<level>/ layout this enforces.
    results_root: Path


LEVEL_BENCHMARKS: dict[ISA95Level, ISA95BenchmarkDefinition] = {
    ISA95Level.ENTERPRISE: ISA95BenchmarkDefinition(
        benchmark_id="icab-enterprise-v1",
        isa95_level=ISA95Level.ENTERPRISE,
        name="ICAB Enterprise Benchmark",
        framework_supported=True,
        data_supported=False,
        executable=False,
        coverage_note=(
            "No question bank: TEP models a single site with no multi-site/"
            "multi-enterprise data. Framework-ready; requires a future "
            "scenario domain with real multi-site/multi-enterprise data."
        ),
        question_bank_dir=Path("configs/questions/enterprise"),
        question_bank_version="0.0.0",
        results_root=Path("results/enterprise"),
    ),
    ISA95Level.SITE: ISA95BenchmarkDefinition(
        benchmark_id="icab-site-v1",
        isa95_level=ISA95Level.SITE,
        name="ICAB Site Benchmark",
        framework_supported=True,
        data_supported=False,
        executable=False,
        coverage_note=(
            "No question bank: TEP has exactly one real Site entity, with "
            "no variation to study (nothing to compare it against)."
        ),
        question_bank_dir=Path("configs/questions/site"),
        question_bank_version="0.0.0",
        results_root=Path("results/site"),
    ),
    ISA95Level.AREA: ISA95BenchmarkDefinition(
        benchmark_id="icab-area-v1",
        isa95_level=ISA95Level.AREA,
        name="ICAB Area Benchmark",
        framework_supported=True,
        data_supported=True,
        executable=True,
        coverage_note=(
            "Minimal but real: TEP has exactly one real Area entity "
            "(Reaction Area). Questions here are real, verified hierarchy "
            "facts, not scenario-varying investigations -- includes the "
            "known knowledge_graph-only discoverability challenge "
            "(docs/research/context-requirement-campaign-1.md)."
        ),
        question_bank_dir=Path("configs/questions/area"),
        question_bank_version="1.0.0",
        results_root=Path("results/area"),
    ),
    ISA95Level.WORK_CENTER: ISA95BenchmarkDefinition(
        benchmark_id="icab-work-center-v1",
        isa95_level=ISA95Level.WORK_CENTER,
        name="ICAB Work Center Benchmark",
        framework_supported=True,
        data_supported=False,
        executable=False,
        coverage_note=(
            "No question bank: TEP's real CIM data has no WorkCenter "
            "entities at all (icab.cim.EntityType.WORK_CENTER is modeled "
            "but never populated by icab.tep.adapter.TEPAdapter)."
        ),
        question_bank_dir=Path("configs/questions/work_center"),
        question_bank_version="0.0.0",
        results_root=Path("results/work_center"),
    ),
    ISA95Level.PROCESS_CELL: ISA95BenchmarkDefinition(
        benchmark_id="icab-process-cell-v1",
        isa95_level=ISA95Level.PROCESS_CELL,
        name="ICAB Process Cell Benchmark",
        framework_supported=True,
        data_supported=True,
        executable=True,
        coverage_note="Well supported: real, plant-wide TEP investigation/diagnosis questions over the one real Process Cell.",
        question_bank_dir=Path("configs/questions/process_cell"),
        question_bank_version="1.0.0",
        results_root=Path("results/process_cell"),
    ),
    ISA95Level.EQUIPMENT: ISA95BenchmarkDefinition(
        benchmark_id="icab-equipment-v1",
        isa95_level=ISA95Level.EQUIPMENT,
        name="ICAB Equipment Benchmark",
        framework_supported=True,
        data_supported=True,
        executable=True,
        coverage_note="Best supported: real TEP questions across all seven real equipment items.",
        question_bank_dir=Path("configs/questions/equipment"),
        question_bank_version="1.0.0",
        results_root=Path("results/equipment"),
    ),
}


def get_level_benchmark(level: ISA95Level) -> ISA95BenchmarkDefinition:
    try:
        return LEVEL_BENCHMARKS[level]
    except KeyError:
        raise KeyError(f"Unknown ISA-95 level: {level!r}") from None


def executable_levels() -> list[ISA95Level]:
    return [level for level, definition in LEVEL_BENCHMARKS.items() if definition.executable]
