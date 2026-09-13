import pytest
from pydantic import ValidationError

from icab.cim import Relationship, RelationshipType


def test_part_of_relationship():
    relationship = Relationship(
        subject="urn:icab:equipment:reactor",
        predicate=RelationshipType.PART_OF,
        object="urn:icab:processcell:reactor",
        source="icab-cim",
    )

    assert relationship.subject == "urn:icab:equipment:reactor"
    assert relationship.predicate == RelationshipType.PART_OF
    assert relationship.object == "urn:icab:processcell:reactor"


def test_measurement_relationship():
    relationship = Relationship(
        subject="urn:icab:sensor:reactor-pressure",
        predicate=RelationshipType.MEASURES,
        object="urn:icab:measurement:reactor-pressure",
    )

    assert relationship.predicate == RelationshipType.MEASURES


@pytest.mark.parametrize(
    "predicate",
    [
        RelationshipType.PART_OF,
        RelationshipType.LOCATED_IN,
        RelationshipType.MEASURES,
        RelationshipType.CONTROLS,
        RelationshipType.ACTUATES,
        RelationshipType.MONITORS,
        RelationshipType.CONNECTED_TO,
        RelationshipType.AFFECTS,
        RelationshipType.DEPENDS_ON,
        RelationshipType.ASSOCIATED_WITH,
        RelationshipType.HAS_STATE,
        RelationshipType.HAS_LIMIT,
        RelationshipType.GENERATES,
        RelationshipType.CAUSED_BY,
        RelationshipType.DESCRIBED_BY,
    ],
)
def test_supported_relationship_types(predicate):
    relationship = Relationship(
        subject="urn:icab:equipment:reactor",
        predicate=predicate,
        object="urn:icab:equipment:separator",
    )

    assert relationship.predicate == predicate


def test_invalid_relationship_predicate():
    with pytest.raises(ValidationError):
        Relationship(
            subject="urn:icab:equipment:reactor",
            predicate="UNKNOWN_RELATIONSHIP",
            object="urn:icab:equipment:separator",
        )


def test_invalid_relationship_subject():
    with pytest.raises(ValidationError):
        Relationship(
            subject="not-a-canonical-id",
            predicate=RelationshipType.PART_OF,
            object="urn:icab:equipment:reactor",
        )
