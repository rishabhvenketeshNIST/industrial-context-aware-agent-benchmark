import pytest
from pydantic import TypeAdapter, ValidationError

from icab.cim import CanonicalId, make_canonical_id

canonical_id_adapter = TypeAdapter(CanonicalId)


def test_make_canonical_id():
    assert make_canonical_id("Equipment", "Reactor") == ("urn:icab:equipment:reactor")


@pytest.mark.parametrize(
    "value",
    [
        "urn:icab:enterprise:demo",
        "urn:icab:site:tep",
        "urn:icab:area:reaction",
        "urn:icab:workcenter:reaction",
        "urn:icab:processcell:reactor",
        "urn:icab:equipment:reactor",
        "urn:icab:sensor:reactor-pressure",
        "urn:icab:measurement:reactor-pressure",
    ],
)
def test_valid_canonical_ids(value):
    assert canonical_id_adapter.validate_python(value) == value


@pytest.mark.parametrize(
    "value",
    [
        "plant:tep",
        "http://example.com/reactor",
        "urn:ICAB:plant:tep",
        "urn:icab:",
        "",
    ],
)
def test_invalid_canonical_ids(value):
    with pytest.raises(ValidationError):
        canonical_id_adapter.validate_python(value)
