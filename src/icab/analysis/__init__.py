"""
ICAB v2: the context necessity/sufficiency/composition/representation/
efficiency analysis suites (see docs/benchmark/specification-v2.md) --
ICAB-CN/CS/CC/CR/CE, plus a deterministic failure taxonomy and a
Context Design Profile generator (ICAB-CA is the architecture health
check, `icab.architecture_health`; ICAB-IR is the existing grounded
evaluator/task suite itself, unchanged).

Every function here is a THIN, deterministic analysis layer over
ALREADY-PERSISTED `ExperimentRecord`s -- it computes no new score, makes
no simulator/gateway/LLM call, and (like `icab.reporting`) reuses
`icab.reporting.aggregation.aggregate_records` for the actual grouping/
statistics rather than re-implementing them. Every report is built ONLY
from context combinations/architectures/use cases actually present in
the given records -- never from the full 127-combination space, and
never by inventing an untested condition's result (see each module's
own docstring for the exact "among tested conditions" framing this
implies).
"""

from .composition import CompositionFinding, CompositionReport, analyze_context_composition
from .discoverability import (
    DiscoverabilityClassification,
    DiscoverabilityStage,
    classify_discoverability,
    discoverability_breakdown,
)
from .efficiency import EfficiencyReport, analyze_context_efficiency
from .failure_taxonomy import FailureCategory, FailureClassification, classify_failures
from .matrix import UseCaseExperimentMatrix, build_use_case_experiment_matrix
from .necessity import DimensionNecessityFinding, NecessityReport, analyze_context_necessity
from .profile import ContextDesignProfile, build_context_design_profile
from .question_stats import (
    BenchmarkLevelStats,
    QuestionStats,
    UseCaseQuestionStats,
    benchmark_level_stats,
    question_stats,
    use_case_question_stats,
)
from .representation import RepresentationFinding, RepresentationReport, analyze_representation
from .reports import (
    ArchitectureContextMatrix,
    ArchitectureContextRow,
    ContextRequirementMatrix,
    ContextRequirementRow,
    ISA95CoverageMatrix,
    ISA95CoverageRow,
    architecture_context_matrix,
    candidate_msc_table,
    context_requirement_matrix,
    failure_mode_matrix,
    isa95_coverage_matrix,
)
from .sufficiency import SufficiencyReport, find_minimum_sufficient_context

__all__ = [
    "ArchitectureContextMatrix",
    "ArchitectureContextRow",
    "BenchmarkLevelStats",
    "CompositionFinding",
    "CompositionReport",
    "ContextDesignProfile",
    "ContextRequirementMatrix",
    "ContextRequirementRow",
    "DimensionNecessityFinding",
    "DiscoverabilityClassification",
    "DiscoverabilityStage",
    "EfficiencyReport",
    "FailureCategory",
    "FailureClassification",
    "ISA95CoverageMatrix",
    "ISA95CoverageRow",
    "NecessityReport",
    "QuestionStats",
    "RepresentationFinding",
    "RepresentationReport",
    "SufficiencyReport",
    "UseCaseExperimentMatrix",
    "UseCaseQuestionStats",
    "analyze_context_composition",
    "analyze_context_efficiency",
    "analyze_context_necessity",
    "analyze_representation",
    "architecture_context_matrix",
    "benchmark_level_stats",
    "build_context_design_profile",
    "build_use_case_experiment_matrix",
    "candidate_msc_table",
    "classify_discoverability",
    "classify_failures",
    "context_requirement_matrix",
    "discoverability_breakdown",
    "failure_mode_matrix",
    "find_minimum_sufficient_context",
    "isa95_coverage_matrix",
    "question_stats",
    "use_case_question_stats",
]
