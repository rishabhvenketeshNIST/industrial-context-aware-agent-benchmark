"""
ICAB v2 Phase 8: the use-case-centered experiment matrix -- USE CASE x
CONTEXT CONDITION x ARCHITECTURE x SCENARIO x AGENT x SEED, made
explicit, so a researcher can answer, for one use case: "what context
was necessary, what was sufficient, how was it represented, and which
architecture exposed it most effectively?"

A thin FACADE over the existing necessity/sufficiency/failure-taxonomy/
discoverability suites -- computes no new score, just assembles their
already-computed outputs (plus raw factor inventories: which scenarios/
architectures/agents/seeds were actually exercised) into one per-use-case
object. See `icab.analysis.reports.candidate_msc_table` for the same
sufficiency result condensed across every use case with evidence.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from icab.experiments.models import ExperimentRecord
from icab.usecases import IndustrialUseCase

from ._shared import records_for_use_case, sample_size_label, tested_combination_ids
from .discoverability import discoverability_breakdown
from .failure_taxonomy import classify_failures
from .necessity import NecessityReport, analyze_context_necessity
from .sufficiency import SufficiencyReport, find_minimum_sufficient_context


class UseCaseExperimentMatrix(BaseModel):
    model_config = ConfigDict(extra="forbid")

    use_case_id: str
    isa95_level: str
    task_type: str
    required_context: list[str]
    candidate_context: list[str]

    tested_context_combinations: list[str]
    architectures_tested: list[str]
    scenarios_tested: list[str]
    agents_tested: list[str]
    seeds_tested: list[int]

    total_runs: int
    successful_runs: int
    failed_runs: int
    sample_size_label: str

    necessity: NecessityReport
    sufficiency: SufficiencyReport
    #: Dimensions of ONE chosen candidate MSC (the same single value
    #: `sufficiency.minimum_sufficient_context_among_tested` resolves to)
    #: -- kept for backward compatibility. When several tested conditions
    #: are genuinely incomparable (see `candidate_msc_combinations`
    #: below), this reflects only the deterministic tie-break, not the
    #: full picture.
    candidate_msc: list[str] | None
    #: EVERY minimal candidate MSC's own combination id (see
    #: `SufficiencyReport.candidate_minimum_sufficient_contexts`) --
    #: prefer this field when reporting on Minimum Sufficient Context,
    #: since context combinations form a partial order and can have more
    #: than one incomparable minimal element.
    candidate_msc_combinations: list[str]

    failure_breakdown: dict[str, int]
    discoverability_breakdown: dict[str, int]


def build_use_case_experiment_matrix(
    records: list[ExperimentRecord],
    use_case: IndustrialUseCase,
    *,
    necessity_metric: str = "required_evidence_score",
) -> UseCaseExperimentMatrix:
    scoped = records_for_use_case(records, use_case.use_case_id)

    necessity = analyze_context_necessity(records, use_case, metric=necessity_metric)
    sufficiency = find_minimum_sufficient_context(records, use_case)

    candidate_msc: list[str] | None = None
    if sufficiency.minimum_sufficient_context_among_tested is not None:
        from icab.tasks.context_combinations import combination_for_id

        combo = combination_for_id(sufficiency.minimum_sufficient_context_among_tested)
        candidate_msc = [d.value for d in combo.dimensions]

    from icab.experiments.models import ExperimentRunStatus

    successful = sum(1 for r in scoped if r.status == ExperimentRunStatus.COMPLETED)
    failed = sum(1 for r in scoped if r.status == ExperimentRunStatus.FAILED)

    architectures = sorted({architecture for r in scoped for architecture in r.config.architectures})
    scenarios = sorted({r.config.scenario_id for r in scoped})
    agents = sorted(
        {
            (r.config.deterministic_agent.value if r.config.deterministic_agent else r.config.agent_type.value)
            for r in scoped
        }
    )
    seeds = sorted({r.simulation_seed for r in scoped})

    return UseCaseExperimentMatrix(
        use_case_id=use_case.use_case_id,
        isa95_level=use_case.isa95_level.value,
        task_type=use_case.task_type.value,
        required_context=[d.value for d in use_case.required_context],
        candidate_context=[d.value for d in use_case.candidate_context],
        tested_context_combinations=tested_combination_ids(scoped),
        architectures_tested=architectures,
        scenarios_tested=scenarios,
        agents_tested=agents,
        seeds_tested=seeds,
        total_runs=len(scoped),
        successful_runs=successful,
        failed_runs=failed,
        sample_size_label=sample_size_label(len(scoped)),
        necessity=necessity,
        sufficiency=sufficiency,
        candidate_msc=candidate_msc,
        candidate_msc_combinations=sufficiency.candidate_minimum_sufficient_contexts,
        failure_breakdown=_count_by(classify_failures(scoped), key="category"),
        discoverability_breakdown=discoverability_breakdown(scoped),
    )


def _count_by(classifications: list, *, key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in classifications:
        value = getattr(item, key)
        counts[value] = counts.get(value, 0) + 1
    return counts
