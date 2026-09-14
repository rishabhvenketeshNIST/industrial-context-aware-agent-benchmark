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
    #: Whether this level has ENOUGH grounded, real-or-controlled data to
    #: support a real question bank -- distinct from whether that data
    #: came from the real TEP simulator (see `data_provenance`).
    data_supported: bool
    #: Whether this benchmark can actually be run right now -- False
    #: whenever data_supported is False (a runner must refuse, not
    #: attempt a run against an empty/fabricated question bank).
    executable: bool
    #: "real_tep" -- every fact comes from the real TEP simulator/CIM
    #:   data (icab.tep.adapter), unchanged.
    #: "controlled_synthetic" -- every fact comes from the deterministic,
    #:   versioned, clearly-labeled synthetic benchmark context layer
    #:   (icab.benchmark_context) -- realistic in shape, NOT empirically
    #:   measured, NEVER presented as real plant data.
    #: "mixed" -- both: at least one real TEP-derived fact plus
    #:   controlled synthetic ones (e.g. Area's real Reaction Area
    #:   alongside 2 synthetic sibling areas).
    #: This is the "real TEP process data" vs. "controlled benchmark
    #: context data" distinction the ICAB v3 50-question milestone
    #: requires every result to be traceable to -- see
    #: docs/benchmark/specification-v3.md.
    data_provenance: str
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
        data_supported=True,
        executable=True,
        data_provenance="controlled_synthetic",
        coverage_note=(
            "50 questions, all against the CONTROLLED benchmark context layer "
            "(icab.benchmark_context) -- TEP itself models a single site with "
            "no real multi-site/multi-enterprise data. The synthetic "
            "'Northwind Chemical' enterprise (icab.benchmark_context.data) "
            "provides deterministic, versioned KPIs and a real, additive "
            "PART_OF link from the REAL TEP site (urn:icab:site:tep) up to "
            "it -- never presented as real plant data. See "
            "docs/benchmark/specification-v3.md."
        ),
        question_bank_dir=Path("configs/questions/enterprise"),
        question_bank_version="1.0.0",
        results_root=Path("results/enterprise"),
    ),
    ISA95Level.SITE: ISA95BenchmarkDefinition(
        benchmark_id="icab-site-v1",
        isa95_level=ISA95Level.SITE,
        name="ICAB Site Benchmark",
        framework_supported=True,
        data_supported=True,
        executable=True,
        data_provenance="mixed",
        coverage_note=(
            "50 questions across 3 sites: the REAL urn:icab:site:tep plus 2 "
            "CONTROLLED synthetic sites (Riverside, Port Arthur) from "
            "icab.benchmark_context -- deterministic, versioned KPIs, never "
            "presented as real plant data. TEP itself has exactly one real "
            "Site entity with no variation to study; the synthetic siblings "
            "exist to give this level genuine cross-site comparison content."
        ),
        question_bank_dir=Path("configs/questions/site"),
        question_bank_version="1.0.0",
        results_root=Path("results/site"),
    ),
    ISA95Level.AREA: ISA95BenchmarkDefinition(
        benchmark_id="icab-area-v1",
        isa95_level=ISA95Level.AREA,
        name="ICAB Area Benchmark",
        framework_supported=True,
        data_supported=True,
        executable=True,
        data_provenance="mixed",
        coverage_note=(
            "50 questions: 3 REAL, hand-authored hierarchy-fact questions "
            "over the real Reaction Area (including the known "
            "knowledge_graph-only discoverability challenge -- see "
            "docs/research/context-requirement-campaign-1.md), plus 47 "
            "CONTROLLED synthetic questions (2 additional synthetic sibling "
            "areas + KPI/hierarchy content, icab.benchmark_context)."
        ),
        question_bank_dir=Path("configs/questions/area"),
        question_bank_version="2.0.0",
        results_root=Path("results/area"),
    ),
    ISA95Level.WORK_CENTER: ISA95BenchmarkDefinition(
        benchmark_id="icab-work-center-v1",
        isa95_level=ISA95Level.WORK_CENTER,
        name="ICAB Work Center Benchmark",
        framework_supported=True,
        data_supported=True,
        executable=True,
        data_provenance="controlled_synthetic",
        coverage_note=(
            "50 questions, entirely against the CONTROLLED benchmark "
            "context layer (icab.benchmark_context) -- TEP's real CIM data "
            "has no WorkCenter entities at all "
            "(icab.cim.EntityType.WORK_CENTER is modeled but never "
            "populated by icab.tep.adapter.TEPAdapter). Three synthetic "
            "work centers, each a real, additive PART_OF child of a real or "
            "synthetic Area, with deterministic, versioned KPIs -- never "
            "presented as real plant data."
        ),
        question_bank_dir=Path("configs/questions/work_center"),
        question_bank_version="1.0.0",
        results_root=Path("results/work_center"),
    ),
    ISA95Level.PROCESS_CELL: ISA95BenchmarkDefinition(
        benchmark_id="icab-process-cell-v1",
        isa95_level=ISA95Level.PROCESS_CELL,
        name="ICAB Process Cell Benchmark",
        framework_supported=True,
        data_supported=True,
        executable=True,
        data_provenance="real_tep",
        coverage_note="50 questions, all against REAL TEP data (plant-wide investigation/diagnosis questions plus real MONITORS/PART_OF relationship-confirmation questions over all 41 real measurements) -- no controlled/synthetic content at this level.",
        question_bank_dir=Path("configs/questions/process_cell"),
        question_bank_version="2.0.0",
        results_root=Path("results/process_cell"),
    ),
    ISA95Level.EQUIPMENT: ISA95BenchmarkDefinition(
        benchmark_id="icab-equipment-v1",
        isa95_level=ISA95Level.EQUIPMENT,
        name="ICAB Equipment Benchmark",
        framework_supported=True,
        data_supported=True,
        executable=True,
        data_provenance="real_tep",
        coverage_note="50 questions, all against REAL TEP data, across all seven real equipment items and all 41 real measurements -- no controlled/synthetic content at this level.",
        question_bank_dir=Path("configs/questions/equipment"),
        question_bank_version="2.0.0",
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
