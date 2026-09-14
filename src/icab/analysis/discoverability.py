"""
ICAB v2: discoverability as a measurable, staged pipeline (Phase 12 of the
context-requirement experimentation direction) -- distinguishes:

    1. exists_in_architecture   -- the run itself completed (the backing
                                    architecture(s) were reachable at all)
    2. discovered_identifier    -- the agent acquired SOME context
                                    (EvaluationReport.context_acquired)
    3. retrieved_value          -- every piece of REQUIRED evidence was
                                    actually retrieved (required_evidence_score == 1.0)
    4. used_as_evidence         -- what was retrieved was cited with a
                                    valid canonical id (canonical_id_score == 1.0)
    5. grounded_in_conclusion   -- the conclusion made no unsupported
                                    numeric claims (grounding_score == 1.0)

Each stage's own definition uses ONLY the same existing, already-computed
`EvaluationReport`/`ExperimentRecord` fields `icab.analysis.failure_taxonomy`
already relies on -- this module is a complementary VIEW (how far did the
pipeline get, in order) rather than a competing signal. Together with
`classify_failures`, this is what lets a caller tell an
ARCHITECTURE failure apart from a DISCOVERY failure, a RETRIEVAL failure,
a REASONING failure, and a GROUNDING failure -- see the ICAB v2 direction's
explicit example: the real Area + knowledge_graph run that failed at
DISCOVERED (the agent never learned the Area's own canonical id) must
never be reported the same way as a run that failed later, at GROUNDED,
having retrieved everything correctly but cited an unsupported number.
"""

from __future__ import annotations

import re
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from icab.experiments.models import ExperimentRecord, ExperimentRunStatus

_INFRASTRUCTURE_ERROR_PATTERN = re.compile(
    r"ConnectError|OperationalError|TimeoutError|ConnectionRefusedError|ServiceUnavailable|OSError",
    re.IGNORECASE,
)


class DiscoverabilityStage(StrEnum):
    """The furthest stage a run's evidence pipeline reached -- an ORDERED ladder, not an unordered category."""

    NOT_REACHED = "not_reached"  # the run itself never completed (architecture/infra failure)
    EXISTS_IN_ARCHITECTURE = "exists_in_architecture"
    DISCOVERED_IDENTIFIER = "discovered_identifier"
    RETRIEVED_VALUE = "retrieved_value"
    USED_AS_EVIDENCE = "used_as_evidence"
    GROUNDED_IN_CONCLUSION = "grounded_in_conclusion"


#: The ladder's fixed order -- index is used to compute "how far did this run get" numerically.
STAGE_ORDER: tuple[DiscoverabilityStage, ...] = (
    DiscoverabilityStage.NOT_REACHED,
    DiscoverabilityStage.EXISTS_IN_ARCHITECTURE,
    DiscoverabilityStage.DISCOVERED_IDENTIFIER,
    DiscoverabilityStage.RETRIEVED_VALUE,
    DiscoverabilityStage.USED_AS_EVIDENCE,
    DiscoverabilityStage.GROUNDED_IN_CONCLUSION,
)


class DiscoverabilityClassification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    stage_reached: str
    reason: str


def _classify_one(record: ExperimentRecord) -> DiscoverabilityClassification:
    if record.status == ExperimentRunStatus.FAILED:
        error = record.error or ""
        shape = "an infrastructure-shaped exception" if _INFRASTRUCTURE_ERROR_PATTERN.search(error) else "an uncategorized failure"
        return DiscoverabilityClassification(
            run_id=record.run_id,
            stage_reached=DiscoverabilityStage.NOT_REACHED,
            reason=f"Run failed before producing a result ({shape}): {error}",
        )

    evaluation = record.evaluation
    if evaluation is None:
        return DiscoverabilityClassification(
            run_id=record.run_id, stage_reached=DiscoverabilityStage.NOT_REACHED, reason="Completed with no evaluation recorded."
        )

    # Stage 1: the run completed at all, so whatever architecture(s) this
    # config declared were, at minimum, reachable.
    if not evaluation.context_acquired:
        return DiscoverabilityClassification(
            run_id=record.run_id,
            stage_reached=DiscoverabilityStage.EXISTS_IN_ARCHITECTURE,
            reason="The run completed, but the trace shows NO context acquired at all -- the agent never discovered an identifier to retrieve.",
        )

    if evaluation.required_evidence_score < 1.0:
        return DiscoverabilityClassification(
            run_id=record.run_id,
            stage_reached=DiscoverabilityStage.DISCOVERED_IDENTIFIER,
            reason=f"context_acquired={evaluation.context_acquired} but required_evidence_score={evaluation.required_evidence_score:.2f} -- discovery happened, retrieval of all required evidence did not.",
        )

    if evaluation.canonical_id_score < 1.0:
        return DiscoverabilityClassification(
            run_id=record.run_id,
            stage_reached=DiscoverabilityStage.RETRIEVED_VALUE,
            reason=f"canonical_id_score={evaluation.canonical_id_score:.2f} -- required evidence was retrieved, but not cited with a valid canonical id.",
        )

    if evaluation.grounding_score < 1.0:
        return DiscoverabilityClassification(
            run_id=record.run_id,
            stage_reached=DiscoverabilityStage.USED_AS_EVIDENCE,
            reason=f"grounding_score={evaluation.grounding_score:.2f} -- evidence was cited with valid ids, but the conclusion also asserts a number not actually observed in the trace.",
        )

    return DiscoverabilityClassification(
        run_id=record.run_id,
        stage_reached=DiscoverabilityStage.GROUNDED_IN_CONCLUSION,
        reason="Every stage of the discoverability pipeline succeeded: acquired, retrieved, cited, and grounded.",
    )


def classify_discoverability(records: list[ExperimentRecord]) -> list[DiscoverabilityClassification]:
    """Classify every record's discoverability stage -- including fully successful ones."""

    return [_classify_one(record) for record in records]


def discoverability_breakdown(records: list[ExperimentRecord]) -> dict[str, int]:
    """Count of runs reaching each stage, keyed by `DiscoverabilityStage` value -- every stage present, even at 0."""

    counts = {stage.value: 0 for stage in STAGE_ORDER}
    for classification in classify_discoverability(records):
        counts[classification.stage_reached] += 1
    return counts
