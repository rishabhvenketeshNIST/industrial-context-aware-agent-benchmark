"""
M11: infrastructure to test the locked H1-H5 hypotheses via controlled
architecture-combination comparisons.

This is a comparison LAYER over already-persisted `ExperimentRecord`s (M9)
and the M10 architecture-combination registry/`InformationFlowAnalyzer` --
it introduces no new experiment mechanics, benchmark metric, or ground
truth. What it adds is: (1) a documented mapping from each locked
hypothesis to a specific treatment/control combination pair and metric
already computed by `GroundedInvestigationEvaluator`/
`InformationFlowAnalyzer`, and (2) a descriptive (not inferential)
comparison of that metric across the two arms.

Locked hypotheses (verbatim, not to be changed here):

    H1: Structured context improves investigation accuracy.
    H2: Structured semantics reduce context/tool usage.
    H3: Knowledge graph relationships improve causal reasoning.
    H4: Selective retrieval beats undifferentiated context.
    H5: Grounded data and relationships reduce unsupported claims.

Per the research direction this module implements ("build the
infrastructure needed to test H1-H5... do not claim that these
hypotheses are proven"): `HypothesisTestResult` reports sample sizes and
a plain-language `caveat` alongside every comparison, and nothing here
computes a significance test -- with typically one real scenario per
difficulty and a handful of real-LLM runs, a p-value would be
manufactured precision, not evidence. `direction_supports_hypothesis` is
a strict, descriptive statement about which way the observed means point
given this data, not a claim that the hypothesis is confirmed.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from statistics import mean

from pydantic import BaseModel, ConfigDict, Field

from icab.evaluation.grounded import EvaluationReport

from .models import ExperimentRecord, ExperimentRunStatus, RunValidity


class HypothesisID(StrEnum):
    H1 = "H1"
    H2 = "H2"
    H3 = "H3"
    H4 = "H4"
    H5 = "H5"


@dataclass(frozen=True)
class HypothesisSpec:
    """
    One hypothesis's controlled-comparison design: which metric, and which
    two architecture-combination arms (`icab.experiments
    .architecture_combinations`) isolate the factor the hypothesis is
    about, holding everything else (scenario/seed/model/budget) fixed --
    that fixing is the caller's job (see `combinations_for_hypothesis` and
    `ExperimentRunner.compare_combinations`), this spec only names which
    combination keys go in which arm.
    """

    id: HypothesisID
    statement: str
    metric: str
    #: Whether a HIGHER metric value in the treatment arm is what the
    #: hypothesis predicts (True for H1/H3; False for H2/H4/H5, where the
    #: hypothesis predicts a LOWER value -- fewer tool calls, less
    #: redundancy, fewer unsupported claims).
    higher_is_better: bool
    treatment_combinations: tuple[str, ...]
    control_combinations: tuple[str, ...]
    rationale: str


HYPOTHESIS_SPECS: tuple[HypothesisSpec, ...] = (
    HypothesisSpec(
        id=HypothesisID.H1,
        statement="Structured context improves investigation accuracy.",
        metric="conclusion_correctness_score",
        higher_is_better=True,
        treatment_combinations=("kg_historian",),
        control_combinations=("historian_only",),
        rationale=(
            "Isolates one factor: relational/semantic structure "
            "(knowledge_graph) added on top of the same historian access. "
            "'Accuracy' is GroundedInvestigationEvaluator."
            "conclusion_correctness_score (structured root-cause/affected-"
            "asset match against ground truth) -- not an LLM judge."
        ),
    ),
    HypothesisSpec(
        id=HypothesisID.H2,
        statement="Structured semantics reduce context/tool usage.",
        metric="tool_call_count",
        higher_is_better=False,
        treatment_combinations=("uns_historian_kg",),
        control_combinations=("kg_historian",),
        rationale=(
            "Isolates one factor: UNS semantic discovery (browsing a named "
            "namespace) added on top of the SAME knowledge_graph+historian "
            "access. If structured naming lets the agent find what it "
            "needs directly instead of relying on relationship dumps or "
            "guessing ids, tool_call_count should fall."
        ),
    ),
    HypothesisSpec(
        id=HypothesisID.H3,
        statement="Knowledge graph relationships improve causal reasoning.",
        metric="relationship_score",
        higher_is_better=True,
        treatment_combinations=("kg_historian",),
        control_combinations=("historian_only",),
        rationale=(
            "Same arms as H1 (only the knowledge_graph tool differs), "
            "scored on a different metric: GroundedInvestigationEvaluator."
            "relationship_score checks the scenario's own "
            "expected_relationships -- the causal/structural claims a KG "
            "is meant to support, distinct from H1's overall-correctness "
            "metric."
        ),
    ),
    HypothesisSpec(
        id=HypothesisID.H4,
        statement="Selective retrieval beats undifferentiated context.",
        metric="information_flow.redundant_acquisition_count",
        higher_is_better=False,
        treatment_combinations=("kg_historian",),
        control_combinations=("full",),
        rationale=(
            "'kg_historian' is a small, curated architecture set "
            "(selective); 'full' exposes every architecture at once "
            "(undifferentiated). Primary metric is InformationFlowAnalyzer"
            ".redundant_acquisition_count (lower supports H4 -- the "
            "selective arm should not re-fetch the same measurement "
            "through multiple channels). Check conclusion_correctness_score/"
            "required_evidence_score alongside this: a lower redundant-"
            "acquisition count is only evidence FOR H4 if it did not come "
            "at the cost of a worse investigation outcome."
        ),
    ),
    HypothesisSpec(
        id=HypothesisID.H5,
        statement="Grounded data and relationships reduce unsupported claims.",
        metric="unsupported_numeric_claims_count",
        higher_is_better=False,
        treatment_combinations=("kg_historian",),
        control_combinations=("historian_only",),
        rationale=(
            "Same arms as H1/H3; metric is the COUNT of "
            "GroundedInvestigationEvaluator.unsupported_numeric_claims "
            "(numeric values in the conclusion the agent never actually "
            "retrieved through a tool) -- lower supports H5. grounding_score "
            "(the complementary 0-1 summary of the same check) is reported "
            "alongside it for context."
        ),
    ),
)

_BY_ID: dict[HypothesisID, HypothesisSpec] = {spec.id: spec for spec in HYPOTHESIS_SPECS}


def get_spec(hypothesis: HypothesisID | str) -> HypothesisSpec:
    """Return a hypothesis's spec by id, or raise KeyError with valid ids listed."""

    key = HypothesisID(hypothesis)
    try:
        return _BY_ID[key]
    except KeyError:
        raise KeyError(
            f"Unknown hypothesis: {hypothesis!r}. Valid ids: {sorted(_BY_ID)}"
        ) from None


def combinations_for_hypothesis(spec: HypothesisSpec) -> list[str]:
    """
    Unique architecture-combination keys (treatment + control, in order,
    de-duplicated) needed to run this hypothesis's comparison -- what to
    pass to `ExperimentRunner.compare_combinations`.
    """

    keys: list[str] = []
    for key in (*spec.treatment_combinations, *spec.control_combinations):
        if key not in keys:
            keys.append(key)
    return keys


class HypothesisTestResult(BaseModel):
    """
    A descriptive (NOT inferential) comparison of one metric between a
    hypothesis's treatment and control arms, over whatever real
    `ExperimentRecord`s were supplied. Never claims significance or proof
    -- see the module docstring and `caveat`.
    """

    model_config = ConfigDict(extra="forbid")

    hypothesis: HypothesisID
    statement: str
    metric: str
    higher_is_better: bool

    treatment_combinations: tuple[str, ...]
    control_combinations: tuple[str, ...]

    treatment_run_ids: list[str]
    control_run_ids: list[str]
    treatment_values: list[float]
    control_values: list[float]

    treatment_mean: float | None = None
    control_mean: float | None = None
    mean_difference: float | None = Field(
        default=None, description="treatment_mean - control_mean; None if either arm is empty."
    )
    #: Whether the observed mean difference's direction is consistent with
    #: what the hypothesis predicts -- None when either arm has no usable
    #: data. Strict (a tie counts as not-supporting): this is a
    #: description of this data, not a confirmation of the hypothesis.
    direction_supports_hypothesis: bool | None = None

    caveat: str = (
        "Descriptive comparison of a small number of real runs -- not a "
        "significance test, and not proof or disproof of the hypothesis. "
        "See docs/research/experiment-plan.md."
    )


#: Records must be VALID (not a legacy control-only baseline -- see
#: RunValidity) and COMPLETED (a FAILED run has no evaluation/
#: information_flow to score) to be usable as evidence for a hypothesis --
#: also used by icab.reporting.aggregation (M12) for the same reason.
def is_usable_record(record: ExperimentRecord) -> bool:
    return record.validity == RunValidity.VALID and record.status == ExperimentRunStatus.COMPLETED


#: Synthetic (not a direct EvaluationReport field) metrics derived from a
#: record's evaluation -- resolved by `metric_value` alongside real field
#: names. Kept alongside `metric_value` (not in icab.reporting) since it's
#: the single place both M11 hypotheses and M12 aggregation resolve a
#: metric name from an ExperimentRecord.
_SYNTHETIC_EVALUATION_METRICS = frozenset(
    {"unsupported_numeric_claims_count", "context_acquired_count", "context_consumed_count", "temporal_reasoning_score"}
)


def metric_value(record: ExperimentRecord, metric: str) -> float | None:
    """
    Resolve a metric name (a `HypothesisSpec.metric`, or any of
    `icab.reporting.metrics`' core-metric names) to a numeric value for
    one record. Supports: a handful of synthetic evaluation-derived
    metrics (below), a dotted `information_flow.<field>` path onto
    `ExperimentRecord.information_flow`, any `EvaluationReport` field name
    directly, or any `ExperimentRecord` field name directly. Returns None
    (never raises) when the record has no evaluation/information_flow to
    resolve the metric from -- callers drop those from the value list
    rather than treating a missing observation as a zero.
    """

    if metric in _SYNTHETIC_EVALUATION_METRICS:
        if record.evaluation is None:
            return None
        evaluation = record.evaluation
        if metric == "unsupported_numeric_claims_count":
            return float(len(evaluation.unsupported_numeric_claims))
        if metric == "context_acquired_count":
            return float(len(evaluation.context_acquired))
        if metric == "context_consumed_count":
            return float(len(evaluation.context_consumed))
        if metric == "temporal_reasoning_score":
            # Vacuous (None, not 0.0) when this scenario didn't require
            # temporal evidence at all -- mirrors relationship_score's
            # own vacuous-when-nothing-expected handling.
            if not evaluation.temporal_evidence_required:
                return None
            return 1.0 if evaluation.temporal_evidence_acquired else 0.0

    if metric.startswith("information_flow."):
        if record.information_flow is None:
            return None
        field_name = metric.split(".", 1)[1]
        return float(getattr(record.information_flow, field_name))

    if metric in EvaluationReport.model_fields:
        # A known EvaluationReport field -- if THIS record's evaluation is
        # missing (e.g. a FAILED run), that's a missing observation, not
        # an unknown metric: return None rather than falling through to
        # the "unknown metric" error below.
        if record.evaluation is None:
            return None
        return float(getattr(record.evaluation, metric))

    if hasattr(record, metric):
        value = getattr(record, metric)
        return None if value is None else float(value)

    raise ValueError(f"Unknown metric: {metric!r}")


def _arm_values(
    records: list[ExperimentRecord],
    combinations: tuple[str, ...],
    metric: str,
) -> tuple[list[str], list[float]]:
    run_ids: list[str] = []
    values: list[float] = []

    for record in records:
        if not is_usable_record(record):
            continue
        if record.config.architecture_combination_key not in combinations:
            continue

        value = metric_value(record, metric)
        if value is None:
            continue

        run_ids.append(record.run_id)
        values.append(value)

    return run_ids, values


def evaluate_hypothesis(
    spec: HypothesisSpec,
    records: list[ExperimentRecord],
) -> HypothesisTestResult:
    """
    Compare `spec.metric` between records whose
    `config.architecture_combination_key` falls in `spec.treatment_combinations`
    vs `spec.control_combinations`, from whatever real `ExperimentRecord`s
    are supplied (typically loaded via `ExperimentResultStore`, from one
    or several experiment ids -- they need not share an `experiment_id`,
    only the controls that matter for a valid comparison: see
    `ExperimentResultStore.write_aggregate`'s `_CONTROL_FIELDS` check,
    which callers should still run before treating these arms as a
    controlled comparison).

    Records that are not `RunValidity.VALID`, not `ExperimentRunStatus
    .COMPLETED`, or whose combination key isn't in either arm are silently
    excluded (not an error) -- an arm can legitimately end up empty if no
    matching records were supplied, in which case the corresponding
    mean/difference/direction are None rather than a crash or a fabricated
    zero.
    """

    treatment_run_ids, treatment_values = _arm_values(
        records, spec.treatment_combinations, spec.metric
    )
    control_run_ids, control_values = _arm_values(records, spec.control_combinations, spec.metric)

    treatment_mean = mean(treatment_values) if treatment_values else None
    control_mean = mean(control_values) if control_values else None

    mean_difference = None
    direction_supports_hypothesis = None
    if treatment_mean is not None and control_mean is not None:
        mean_difference = treatment_mean - control_mean
        direction_supports_hypothesis = (
            mean_difference > 0 if spec.higher_is_better else mean_difference < 0
        )

    return HypothesisTestResult(
        hypothesis=spec.id,
        statement=spec.statement,
        metric=spec.metric,
        higher_is_better=spec.higher_is_better,
        treatment_combinations=spec.treatment_combinations,
        control_combinations=spec.control_combinations,
        treatment_run_ids=treatment_run_ids,
        control_run_ids=control_run_ids,
        treatment_values=treatment_values,
        control_values=control_values,
        treatment_mean=treatment_mean,
        control_mean=control_mean,
        mean_difference=mean_difference,
        direction_supports_hypothesis=direction_supports_hypothesis,
    )


def evaluate_all_hypotheses(records: list[ExperimentRecord]) -> list[HypothesisTestResult]:
    """Run `evaluate_hypothesis` for every spec in `HYPOTHESIS_SPECS` against the same records."""

    return [evaluate_hypothesis(spec, records) for spec in HYPOTHESIS_SPECS]
