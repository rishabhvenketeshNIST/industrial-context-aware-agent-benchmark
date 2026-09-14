"""
The reusable ICAB question taxonomy -- a category label for a `Question`
(icab.questions.models), independent of which ISA-95 level it belongs
to, so questions can be compared ACROSS levels where meaningful (e.g.
"how do Equipment-level and Process-Cell-level diagnosis questions
differ?"). No level is required to use every category, and no category
is required to be used at every level -- this is a shared vocabulary,
not a per-level checklist.
"""

from __future__ import annotations

from enum import StrEnum


class QuestionCategory(StrEnum):
    """One reusable question-family label. See each value's own use in `configs/questions/*.yaml`."""

    IDENTIFICATION = "identification"
    STATE_INTERPRETATION = "state_interpretation"
    MEASUREMENT_INTERPRETATION = "measurement_interpretation"
    RELATIONSHIP_REASONING = "relationship_reasoning"
    TEMPORAL_REASONING = "temporal_reasoning"
    HISTORICAL_REASONING = "historical_reasoning"
    OPERATIONAL_REASONING = "operational_reasoning"
    PROCEDURAL_REASONING = "procedural_reasoning"
    DIAGNOSIS = "diagnosis"
    CONTEXTUALIZED_QA = "contextualized_qa"
    EVIDENCE_VERIFICATION = "evidence_verification"
    CROSS_SOURCE_REASONING = "cross_source_reasoning"


QUESTION_CATEGORY_LABELS: dict[QuestionCategory, str] = {
    QuestionCategory.IDENTIFICATION: "Identification (which entity/equipment/measurement is this?)",
    QuestionCategory.STATE_INTERPRETATION: "Current-state interpretation",
    QuestionCategory.MEASUREMENT_INTERPRETATION: "Measurement value interpretation",
    QuestionCategory.RELATIONSHIP_REASONING: "Structural relationship reasoning (hierarchy/association)",
    QuestionCategory.TEMPORAL_REASONING: "Bounded-window temporal reasoning",
    QuestionCategory.HISTORICAL_REASONING: "Wide-window historical/trend reasoning",
    QuestionCategory.OPERATIONAL_REASONING: "Live operational-value reasoning",
    QuestionCategory.PROCEDURAL_REASONING: "Control/procedural relationship reasoning",
    QuestionCategory.DIAGNOSIS: "Root-cause/diagnostic reasoning",
    QuestionCategory.CONTEXTUALIZED_QA: "Direct contextualized question-answering",
    QuestionCategory.EVIDENCE_VERIFICATION: "Verifying/confirming a specific piece of evidence",
    QuestionCategory.CROSS_SOURCE_REASONING: "Combining evidence from more than one architecture/source",
}
