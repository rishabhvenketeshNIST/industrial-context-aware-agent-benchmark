from typing import Any

from icab.agent.interface import EvidenceReference, NormalizedContext


class ContextNormalizer:
    """Convert architecture-specific observations into normalized ICAB context."""

    @staticmethod
    def _provenance(source: str, identifier: str) -> list[EvidenceReference]:
        """Build a single-entry provenance list for a normalized context."""
        return [EvidenceReference(source=source, identifier=identifier)]

    @staticmethod
    def from_uns(
        nodes: dict[str, Any],
        measurements: dict[str, dict[str, Any]],
    ) -> NormalizedContext:
        assets = [
            {
                "id": node["canonical_id"],
                "name": node["display_name"],
                "type": node["node_type"],
            }
            for node in nodes.get("nodes", [])
            if node.get("node_type") != "measurement" and node.get("canonical_id")
        ]

        normalized_measurements = [
            {
                "id": measurement_id,
                "name": next(
                    (
                        node.get("display_name", "")
                        for node in nodes.get("nodes", [])
                        if node.get("canonical_id") == measurement_id
                    ),
                    "",
                ),
                "value": value.get("value"),
            }
            for measurement_id, value in measurements.items()
        ]

        return NormalizedContext(
            assets=assets,
            measurements=normalized_measurements,
            provenance=ContextNormalizer._provenance(
                source="uns",
                identifier="site/tep/reaction/reactor",
            ),
        )

    @staticmethod
    def from_opcua(
        nodes: dict[str, Any],
        values: dict[str, dict[str, Any]],
    ) -> NormalizedContext:
        assets = [
            {
                "id": node["node_id"],
                "name": node["display_name"],
                "type": node["node_class"],
            }
            for node in nodes.get("nodes", [])
        ]

        measurements = [
            {
                "id": node_id,
                "name": next(
                    (
                        node.get("display_name", "")
                        for node in nodes.get("nodes", [])
                        if node["node_id"] == node_id
                    ),
                    node_id,
                ),
                "value": value.get("value"),
            }
            for node_id, value in values.items()
        ]

        return NormalizedContext(
            assets=[],
            measurements=measurements,
            provenance=ContextNormalizer._provenance(
                source="opcua",
                identifier="ns=2;i=1",
            ),
        )

    @staticmethod
    def from_i3x(
        reactor: dict[str, Any],
        related_objects: dict[str, Any],
        values: dict[str, dict[str, Any]],
    ) -> NormalizedContext:
        reactor_object = reactor.get("object", {})

        assets = [
            {
                "id": reactor_object.get("element_id"),
                "name": reactor_object.get("display_name"),
                "type": "object",
            }
        ]

        measurements = [
            {
                "id": item["element_id"],
                "name": item.get("display_name"),
                "value": values.get(item["element_id"], {}).get("value"),
            }
            for item in related_objects.get("related_objects", [])
            if item.get("element_id") in values
        ]

        relationships = [
            {
                "subject": reactor_object.get("element_id"),
                "object": item["element_id"],
                "predicate": "RELATED_TO",
            }
            for item in related_objects.get("related_objects", [])
            if item.get("element_id")
        ]

        return NormalizedContext(
            assets=assets,
            measurements=measurements,
            relationships=relationships,
            provenance=ContextNormalizer._provenance(
                source="i3x",
                identifier=reactor_object.get("element_id", ""),
            ),
        )

    @staticmethod
    def from_kg(
        relationships: dict[str, Any],
    ) -> NormalizedContext:
        normalized_relationships = [
            {
                "subject": item.get("subject"),
                "predicate": item.get("predicate"),
                "object": item.get("object"),
            }
            for item in relationships.get("relationships", [])
        ]

        return NormalizedContext(
            relationships=normalized_relationships,
            provenance=ContextNormalizer._provenance(
                source="kg",
                identifier="urn:icab:equipment:reactor",
            ),
        )
