"""
ICAB MQTT topic namespace.

Topics are built as ``icab/<domain>/<equipment-key>/<measurement>``, e.g.
``icab/tep/reactor/reactor_pressure`` -- the same site/equipment/measurement
shape ICAB's UNS paths use (``site/tep/reaction/reactor/pressure``), anchored
to the actual ICAB canonical-equipment registry (``icab.tep.measurements``)
rather than an invented hierarchy.
"""

ROOT = "icab"


def build_topic(*segments: str) -> str:
    """Join segments into an ICAB-namespaced MQTT topic."""

    if not segments:
        raise ValueError("At least one topic segment is required.")

    if any(not segment for segment in segments):
        raise ValueError("Topic segments must be non-empty.")

    return "/".join([ROOT, *segments])


def equipment_key_from_canonical_id(canonical_id: str) -> str:
    """Extract the trailing equipment key from an ICAB equipment canonical id."""

    return canonical_id.rsplit(":", 1)[-1]


def parse_topic(topic: str) -> list[str] | None:
    """Split an ICAB MQTT topic into its segments, or None if not ICAB-namespaced."""

    if not topic.startswith(f"{ROOT}/"):
        return None

    return topic.split("/")[1:]
