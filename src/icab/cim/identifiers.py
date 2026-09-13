from typing import Annotated

from pydantic import StringConstraints

CanonicalId = Annotated[
    str,
    StringConstraints(
        pattern=r"^urn:icab:[a-z0-9][a-z0-9:_-]*$",
        min_length=10,
    ),
]


def make_canonical_id(entity_type: str, name: str) -> str:
    """Create a deterministic ICAB canonical identifier."""
    normalized_type = entity_type.strip().lower()
    normalized_name = name.strip().lower().replace(" ", "-")

    return f"urn:icab:{normalized_type}:{normalized_name}"
