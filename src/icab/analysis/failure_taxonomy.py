"""
ICAB v2 failure taxonomy: classify a run deterministically so a broken
architecture is never mistaken for poor agent reasoning, and a missing
context dimension is never mistaken for an agent failure (see the ICAB
v2 direction's explicit warning: "A failed KG connection must never
become a 'KG reasoning score.'").

Every rule below reads ONLY existing, already-persisted fields
(`ExperimentRecord.status`/`.error`, `EvaluationReport`'s existing
scores/fields) -- no new signal is invented, and classification is a
fixed priority order over those fields, not a heuristic score.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict

from icab.experiments.models import ExperimentRecord, ExperimentRunStatus

#: Exception-type/message substrings that indicate the run failed
#: because a BACKING SERVICE was unreachable/broken, not because of
#: anything the agent did -- matches the exact exception shapes
#: `icab.benchmark.runner._run_one`/`icab.architecture_health` already
#: surface for a genuinely broken component (connection errors,
#: operational errors, timeouts).
_INFRASTRUCTURE_ERROR_PATTERN = re.compile(
    r"ConnectError|OperationalError|TimeoutError|ConnectionRefusedError|ServiceUnavailable|OSError",
    re.IGNORECASE,
)


class FailureCategory:
    """The fixed ICAB v2 failure taxonomy -- string constants, not a StrEnum, so new categories can be added additively."""

    ARCHITECTURE_CONNECTIVITY_FAILURE = "architecture_connectivity_failure"
    CONTEXT_NOT_DISCOVERABLE = "context_not_discoverable"
    CONTEXT_NOT_RETRIEVED = "context_not_retrieved"
    CONTEXT_NOT_INTEGRATED = "context_not_integrated"
    REPRESENTATION_FAILURE = "representation_failure"
    REASONING_FAILURE = "reasoning_failure"
    GROUNDING_FAILURE = "grounding_failure"
    EFFICIENCY_FAILURE = "efficiency_failure"
    NONE = "none"  # the run succeeded by every available signal -- not a failure at all


class FailureClassification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    category: str
    reason: str


def _classify_one(record: ExperimentRecord) -> FailureClassification:
    if record.status == ExperimentRunStatus.FAILED:
        error = record.error or ""
        if _INFRASTRUCTURE_ERROR_PATTERN.search(error):
            return FailureClassification(
                run_id=record.run_id,
                category=FailureCategory.ARCHITECTURE_CONNECTIVITY_FAILURE,
                reason=f"Run failed with an infrastructure-shaped exception: {error}",
            )
        return FailureClassification(
            run_id=record.run_id,
            category=FailureCategory.ARCHITECTURE_CONNECTIVITY_FAILURE,
            reason=f"Run failed before producing a result (uncategorized failure, treated conservatively as infrastructure-related): {error}",
        )

    evaluation = record.evaluation
    if evaluation is None:
        return FailureClassification(
            run_id=record.run_id, category=FailureCategory.NONE, reason="Completed with no evaluation recorded."
        )

    if not evaluation.terminated_properly:
        return FailureClassification(
            run_id=record.run_id,
            category=FailureCategory.EFFICIENCY_FAILURE,
            reason="Investigation was cut off by a budget (step/tool-call/token/wall-time) rather than concluding on its own.",
        )

    if evaluation.required_evidence_score < 1.0 and not evaluation.context_acquired:
        return FailureClassification(
            run_id=record.run_id,
            category=FailureCategory.CONTEXT_NOT_DISCOVERABLE,
            reason="Required evidence missing and the trace shows NO context acquired at all -- the agent never even attempted discovery.",
        )

    if evaluation.required_evidence_score < 1.0:
        return FailureClassification(
            run_id=record.run_id,
            category=FailureCategory.CONTEXT_NOT_RETRIEVED,
            reason=f"required_evidence_score={evaluation.required_evidence_score:.2f} -- some required evidence was never retrieved, despite {len(evaluation.context_acquired)} item(s) acquired.",
        )

    if evaluation.canonical_id_score < 1.0:
        return FailureClassification(
            run_id=record.run_id,
            category=FailureCategory.REPRESENTATION_FAILURE,
            reason=f"canonical_id_score={evaluation.canonical_id_score:.2f} -- evidence was cited using an invalid/malformed canonical id.",
        )

    if evaluation.grounding_score < 1.0:
        return FailureClassification(
            run_id=record.run_id,
            category=FailureCategory.GROUNDING_FAILURE,
            reason=f"grounding_score={evaluation.grounding_score:.2f} -- the conclusion cites a number not actually observed in the trace.",
        )

    if evaluation.conclusion_correctness_score is not None and evaluation.conclusion_correctness_score < 1.0:
        # Evidence WAS available and grounded (checked above) -- a wrong
        # conclusion here is a reasoning failure, not a context failure.
        return FailureClassification(
            run_id=record.run_id,
            category=FailureCategory.REASONING_FAILURE,
            reason=f"conclusion_correctness_score={evaluation.conclusion_correctness_score:.2f} despite required evidence being retrieved and grounded -- the conclusion itself was wrong.",
        )

    if evaluation.relationship_score < 1.0:
        return FailureClassification(
            run_id=record.run_id,
            category=FailureCategory.CONTEXT_NOT_INTEGRATED,
            reason=f"relationship_score={evaluation.relationship_score:.2f} -- a required relationship was not confirmed/cited, despite other evidence being available.",
        )

    return FailureClassification(run_id=record.run_id, category=FailureCategory.NONE, reason="No failure signal found -- run succeeded by every available deterministic metric.")


def classify_failures(records: list[ExperimentRecord]) -> list[FailureClassification]:
    """Classify every record -- including successful ones (category NONE), so a caller can compute a full taxonomy breakdown, not just a filtered failure list."""

    return [_classify_one(record) for record in records]
