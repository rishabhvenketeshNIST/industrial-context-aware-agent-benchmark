"""
ICAB v2 Phase 14: cross-use-case analysis outputs --

  1. context requirement matrix   (use case x C1-C7 -> required/
                                    sufficient/beneficial/not_demonstrated/
                                    not_applicable)
  2. architecture x context matrix (which architectures actually exposed
                                     which context dimensions, empirically)
  3. failure-mode matrix           (icab.analysis.failure_taxonomy, tallied)
  4. ISA-95 coverage matrix        (framework support vs. actual data/use-
                                     case/experiment coverage per level)
  5. candidate MSC table           (icab.analysis.sufficiency, one row per
                                     use case with evidence)

Every function here is, like the rest of `icab.analysis`, a thin,
deterministic aggregation over ALREADY-PERSISTED records plus the
already-registered use-case/ISA-95 metadata -- no new score, and always
conservative: a cell with no evidence is reported as such, never guessed.
"""

from __future__ import annotations

from typing import Iterable

from pydantic import BaseModel, ConfigDict

from icab.experiments.models import ExperimentRecord
from icab.tasks.context_dimensions import CONTEXT_DIMENSION_ARCHITECTURES, ContextDimension
from icab.usecases import ISA95_LEVEL_COVERAGE_NOTES, ISA95Level, IndustrialUseCase, IndustrialUseCaseRegistry

from ._shared import records_for_use_case, sample_size_label
from .failure_taxonomy import classify_failures
from .necessity import analyze_context_necessity
from .sufficiency import find_minimum_sufficient_context

__all__ = [
    "ArchitectureContextMatrix",
    "ArchitectureContextRow",
    "ContextRequirementMatrix",
    "ContextRequirementRow",
    "ISA95CoverageMatrix",
    "ISA95CoverageRow",
    "architecture_context_matrix",
    "candidate_msc_table",
    "context_requirement_matrix",
    "failure_mode_matrix",
    "isa95_coverage_matrix",
]

CellLabel = str  # "required" | "sufficient" | "beneficial" | "not_demonstrated" | "not_applicable"


class ContextRequirementRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    use_case_id: str
    isa95_level: str
    #: dimension value ("C1".."C7") -> CellLabel
    cells: dict[str, CellLabel]


class ContextRequirementMatrix(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dimensions: list[str]
    rows: list[ContextRequirementRow]


def context_requirement_matrix(
    use_cases: Iterable[IndustrialUseCase],
    records: list[ExperimentRecord],
) -> ContextRequirementMatrix:
    rows: list[ContextRequirementRow] = []

    for use_case in use_cases:
        scoped = records_for_use_case(records, use_case.use_case_id)
        sufficiency = find_minimum_sufficient_context(records, use_case)
        necessity = analyze_context_necessity(records, use_case)

        msc_dimensions: set[ContextDimension] = set()
        if sufficiency.minimum_sufficient_context_among_tested is not None:
            from icab.tasks.context_combinations import combination_for_id

            msc_dimensions = set(combination_for_id(sufficiency.minimum_sufficient_context_among_tested).dimensions)

        beneficial_dimensions = {
            finding.dimension
            for finding in necessity.findings
            if finding.evidence_status == "evidence" and finding.delta is not None and finding.delta > 0
        }

        cells: dict[str, CellLabel] = {}
        for dimension in ContextDimension:
            if dimension not in use_case.candidate_context:
                cells[dimension.value] = "not_applicable"
            elif dimension in msc_dimensions:
                cells[dimension.value] = "sufficient"
            elif dimension in use_case.required_context:
                cells[dimension.value] = "required"
            elif dimension in beneficial_dimensions:
                cells[dimension.value] = "beneficial"
            else:
                cells[dimension.value] = "not_demonstrated"

        rows.append(ContextRequirementRow(use_case_id=use_case.use_case_id, isa95_level=use_case.isa95_level.value, cells=cells))

    return ContextRequirementMatrix(dimensions=[d.value for d in ContextDimension], rows=rows)


class ArchitectureContextRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    architecture: str
    #: Dimensions this architecture is DECLARED capable of
    #: (icab.tasks.context_dimensions.CONTEXT_DIMENSION_ARCHITECTURES) --
    #: a necessary-condition claim, not empirical.
    claims_to_expose: list[str]
    #: Runs where this architecture was the ONLY one available (so any
    #: effectiveness observed is unambiguously attributable to it).
    n_single_architecture_runs: int
    mean_conclusion_correctness_score: float | None
    mean_grounding_score: float | None
    sample_size_label: str


class ArchitectureContextMatrix(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rows: list[ArchitectureContextRow]


def architecture_context_matrix(records: list[ExperimentRecord]) -> ArchitectureContextMatrix:
    """
    Across EVERY use case (not scoped to one) -- which architectures
    actually appeared as the sole architecture in a run, and how that run
    scored on the two metrics most directly tied to "did this
    architecture's representation of context actually work" (correctness,
    grounding). Distinct from mere connectivity (icab.architecture_health):
    this is about whether the EXPOSED context was effective, not whether
    the architecture merely responded.
    """

    from icab.experiments.hypotheses import is_usable_record

    architectures = sorted({architecture for record in records for architecture in record.config.architectures})

    rows: list[ArchitectureContextRow] = []
    for architecture in architectures:
        single = [
            record
            for record in records
            if record.config.architectures == [architecture] and is_usable_record(record)
        ]
        correctness = [
            record.evaluation.conclusion_correctness_score
            for record in single
            if record.evaluation is not None
        ]
        grounding = [record.evaluation.grounding_score for record in single if record.evaluation is not None]

        claims = sorted(
            dimension.value
            for dimension in ContextDimension
            if architecture in CONTEXT_DIMENSION_ARCHITECTURES[dimension]
        )

        rows.append(
            ArchitectureContextRow(
                architecture=architecture,
                claims_to_expose=claims,
                n_single_architecture_runs=len(single),
                mean_conclusion_correctness_score=(sum(correctness) / len(correctness)) if correctness else None,
                mean_grounding_score=(sum(grounding) / len(grounding)) if grounding else None,
                sample_size_label=sample_size_label(len(single)),
            )
        )

    return ArchitectureContextMatrix(rows=rows)


def failure_mode_matrix(records: list[ExperimentRecord]) -> dict[str, int]:
    """Tally of `icab.analysis.failure_taxonomy.FailureCategory` across `records` -- system-wide, not scoped to one use case."""

    counts: dict[str, int] = {}
    for classification in classify_failures(records):
        counts[classification.category] = counts.get(classification.category, 0) + 1
    return counts


class ISA95CoverageRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    level: str
    framework_support: bool  # always True -- ISA95Level models every level
    use_case_count: int
    experiment_coverage: int  # distinct runs recorded at this level
    coverage_note: str


class ISA95CoverageMatrix(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rows: list[ISA95CoverageRow]


def isa95_coverage_matrix(
    use_case_registry: IndustrialUseCaseRegistry,
    records: list[ExperimentRecord],
) -> ISA95CoverageMatrix:
    rows = []
    for level in ISA95Level:
        use_cases = use_case_registry.for_level(level)
        experiment_count = sum(1 for record in records if record.config.isa95_level == level.value)
        rows.append(
            ISA95CoverageRow(
                level=level.value,
                framework_support=True,
                use_case_count=len(use_cases),
                experiment_coverage=experiment_count,
                coverage_note=ISA95_LEVEL_COVERAGE_NOTES[level],
            )
        )
    return ISA95CoverageMatrix(rows=rows)


def candidate_msc_table(
    use_cases: Iterable[IndustrialUseCase],
    records: list[ExperimentRecord],
) -> list[dict]:
    """One row per use case that has ANY persisted evidence -- the sufficiency report condensed to a flat table."""

    rows = []
    for use_case in use_cases:
        scoped = records_for_use_case(records, use_case.use_case_id)
        if not scoped:
            continue
        report = find_minimum_sufficient_context(records, use_case)
        conditions_by_id = {c.context_combination_id: c for c in report.tested_conditions}
        rows.append(
            {
                "use_case_id": use_case.use_case_id,
                "isa95_level": use_case.isa95_level.value,
                "candidate_msc": report.minimum_sufficient_context_among_tested,
                #: Every minimal candidate, not just one arbitrarily
                #: chosen among incomparable ties -- see
                #: SufficiencyReport.candidate_minimum_sufficient_contexts.
                "candidate_msc_combinations": report.candidate_minimum_sufficient_contexts,
                #: run_id(s) backing each candidate MSC -- traceability
                #: from this table's claim back to the exact persisted
                #: ExperimentRecord(s) it rests on.
                "supporting_experiment_ids": {
                    combination_id: conditions_by_id[combination_id].run_ids
                    for combination_id in report.candidate_minimum_sufficient_contexts
                },
                "tested_conditions": [c.context_combination_id for c in report.tested_conditions],
                "n_runs": len(scoped),
                "sample_size_label": sample_size_label(len(scoped)),
                "caveat": report.caveat,
            }
        )
    return rows
