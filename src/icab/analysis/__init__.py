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
from .efficiency import EfficiencyReport, analyze_context_efficiency
from .failure_taxonomy import FailureCategory, FailureClassification, classify_failures
from .necessity import DimensionNecessityFinding, NecessityReport, analyze_context_necessity
from .profile import ContextDesignProfile, build_context_design_profile
from .representation import RepresentationFinding, RepresentationReport, analyze_representation
from .sufficiency import SufficiencyReport, find_minimum_sufficient_context

__all__ = [
    "CompositionFinding",
    "CompositionReport",
    "ContextDesignProfile",
    "DimensionNecessityFinding",
    "EfficiencyReport",
    "FailureCategory",
    "FailureClassification",
    "NecessityReport",
    "RepresentationFinding",
    "RepresentationReport",
    "SufficiencyReport",
    "analyze_context_composition",
    "analyze_context_efficiency",
    "analyze_context_necessity",
    "analyze_representation",
    "build_context_design_profile",
    "classify_failures",
    "find_minimum_sufficient_context",
]
