"""
ICAB v2: the standards-oriented "Context Design Profile" -- one per use
case, generated FROM experimental results (never hard-coded), combining
the necessity/sufficiency/representation analyses into the structure the
ICAB v2 direction specifies (its "Standards-oriented output" section).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from icab.experiments.models import ExperimentRecord
from icab.usecases import IndustrialUseCase

from .necessity import analyze_context_necessity
from .representation import ARCHITECTURE_REPRESENTATION_LABELS, analyze_representation
from .sufficiency import find_minimum_sufficient_context


class ContextDesignProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    use_case: str
    isa95_level: str

    required_context: list[str]
    minimum_sufficient_context_among_tested: list[str] | None
    sufficiency_caveat: str

    #: dimension -> best-tested representing architecture's own label
    #: (icab.analysis.representation.ARCHITECTURE_REPRESENTATION_LABELS),
    #: only for dimensions this use case's candidate_context declares.
    representations: dict[str, str]

    #: Architectures that were actually run, single-architecture, for
    #: this use case -- i.e. genuinely evidenced options, not every
    #: architecture that could theoretically supply the dimension
    #: (see icab.tasks.context_dimensions.CONTEXT_DIMENSION_ARCHITECTURES
    #: for the theoretical/necessary-condition mapping; this field is
    #: the narrower, EVIDENCED subset).
    architecture_options: list[str]

    evidence: dict[str, int]  # {"scenarios": n, "seeds": n, "runs": n}

    #: "high" (>= 5 usable runs across >= 2 tested combinations),
    #: "medium" (>= 2 usable runs), "low" (< 2) -- a simple, documented,
    #: deterministic rule, not a statistical confidence interval.
    confidence: str


def _confidence_for(n_runs: int, n_combinations: int) -> str:
    if n_runs >= 5 and n_combinations >= 2:
        return "high"
    if n_runs >= 2:
        return "medium"
    return "low"


def build_context_design_profile(
    records: list[ExperimentRecord],
    use_case: IndustrialUseCase,
) -> ContextDesignProfile:
    from ._shared import records_for_use_case, tested_combination_ids

    scoped = records_for_use_case(records, use_case.use_case_id)
    tested = tested_combination_ids(scoped)

    sufficiency = find_minimum_sufficient_context(records, use_case)
    representation = analyze_representation(records, use_case)

    minimum_dims: list[str] | None = None
    if sufficiency.minimum_sufficient_context_among_tested is not None:
        from icab.tasks.context_combinations import combination_for_id

        combo = combination_for_id(sufficiency.minimum_sufficient_context_among_tested)
        minimum_dims = [dimension.value for dimension in combo.dimensions]

    # Build a PER-DIMENSION representation recommendation from whichever
    # tested single-architecture arm ACTUALLY SUPPLIES that dimension
    # (icab.tasks.context_dimensions.CONTEXT_DIMENSION_ARCHITECTURES)
    # and scored highest on effectiveness for THIS use case -- real
    # evidence restricted to architectures capable of the dimension in
    # question, never a single "best overall" architecture applied
    # blanket to every dimension regardless of whether it can supply it.
    from icab.tasks.context_dimensions import CONTEXT_DIMENSION_ARCHITECTURES

    representations: dict[str, str] = {}
    for dimension in use_case.required_context:
        capable = CONTEXT_DIMENSION_ARCHITECTURES[dimension]
        candidates = [
            finding
            for finding in representation.findings
            if finding.architecture in capable and finding.effectiveness.get("conclusion_correctness_score") is not None
        ]
        if candidates:
            best = max(candidates, key=lambda finding: finding.effectiveness["conclusion_correctness_score"])
            representations[dimension.value] = f"{best.representation} (via {best.architecture})"
        else:
            representations[dimension.value] = "(no single-architecture evidence yet)"

    architecture_options = sorted({finding.architecture for finding in representation.findings})

    seeds = {record.simulation_seed for record in scoped}
    scenarios = {record.config.scenario_id for record in scoped}

    return ContextDesignProfile(
        use_case=use_case.use_case_id,
        isa95_level=use_case.isa95_level.value,
        required_context=[dimension.value for dimension in use_case.required_context],
        minimum_sufficient_context_among_tested=minimum_dims,
        sufficiency_caveat=sufficiency.caveat,
        representations=representations,
        architecture_options=architecture_options,
        evidence={"scenarios": len(scenarios), "seeds": len(seeds), "runs": len(scoped)},
        confidence=_confidence_for(len(scoped), len(tested)),
    )
