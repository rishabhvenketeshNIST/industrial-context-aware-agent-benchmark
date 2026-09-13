from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from .identifiers import CanonicalId


class RelationshipType(StrEnum):
    PART_OF = "PART_OF"
    LOCATED_IN = "LOCATED_IN"
    MEASURES = "MEASURES"
    CONTROLS = "CONTROLS"
    ACTUATES = "ACTUATES"
    MONITORS = "MONITORS"
    CONNECTED_TO = "CONNECTED_TO"
    AFFECTS = "AFFECTS"
    DEPENDS_ON = "DEPENDS_ON"
    ASSOCIATED_WITH = "ASSOCIATED_WITH"
    HAS_STATE = "HAS_STATE"
    HAS_LIMIT = "HAS_LIMIT"
    GENERATES = "GENERATES"
    CAUSED_BY = "CAUSED_BY"
    DESCRIBED_BY = "DESCRIBED_BY"


class Relationship(BaseModel):
    """A first-class relationship between two CIM entities."""

    model_config = ConfigDict(extra="forbid")

    subject: CanonicalId
    predicate: RelationshipType
    object: CanonicalId

    source: str | None = Field(
        default=None,
        description="Information source providing this relationship.",
    )

    source_id: str | None = Field(
        default=None,
        description="Identifier of the relationship in the source system.",
    )

    generation_id: str | None = Field(
        default=None,
        description=(
            "Which scenario-preparation run wrote this relationship (see "
            "icab.scenarios.runner.ScenarioRunner) -- None for data written "
            "outside that path. A shared, persistent knowledge graph "
            "accumulates relationships across every run that has ever "
            "written to it; this field is what lets a benchmark run tell "
            "its own generation's relationships apart from an earlier run's."
        ),
    )
