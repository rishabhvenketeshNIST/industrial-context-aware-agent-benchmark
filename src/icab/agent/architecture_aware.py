from typing import Any

from icab.agent.client import AgentGatewayClient
from icab.agent.interface import Agent, EvidenceReference, InvestigationResult

from icab.context.normalizer import ContextNormalizer

REACTOR_UNS_PATH = "site/tep/reaction/reactor"
REACTOR_OPCUA_NODE = "ns=2;i=1"
REACTOR_I3X_ID = "reactor"


class ArchitectureAwareAgent(Agent):
    """Agent that acquires process context through a selected architecture."""

    def __init__(
        self,
        client: AgentGatewayClient,
        *,
        architecture: str,
    ) -> None:
        if architecture not in {"uns", "opcua", "i3x", "kg"}:
            raise ValueError(f"Unsupported architecture: {architecture}")

        self.client = client
        self.architecture = architecture

    def run(
        self,
        *,
        objective: str,
        initial_state: dict[str, Any],
    ) -> InvestigationResult:
        if self.architecture == "uns":
            return self._run_uns(objective, initial_state)

        if self.architecture == "opcua":
            return self._run_opcua(objective, initial_state)

        if self.architecture == "i3x":
            return self._run_i3x(objective, initial_state)

        return self._run_kg(objective, initial_state)

    def _run_uns(
        self,
        objective: str,
        initial_state: dict[str, Any],
    ) -> InvestigationResult:
        nodes = self.client.call_tool(
            "browse_uns",
            {"path": REACTOR_UNS_PATH},
            step=1,
            context_acquired=[REACTOR_UNS_PATH],
        )

        measurements = {}

        for step, node in enumerate(nodes["nodes"], start=2):
            measurement_id = node.get("canonical_id")

            if node.get("node_type") != "measurement" or not measurement_id:
                continue

            measurements[measurement_id] = self.client.call_tool(
                "get_current_value",
                {"measurement_id": measurement_id},
                step=step,
                context_consumed=[REACTOR_UNS_PATH],
            )

        normalized_context = ContextNormalizer.from_uns(
            nodes,
            measurements,
        )

        return InvestigationResult(
            objective=objective,
            conclusion="Acquired reactor context through the UNS.",
            findings={
                "architecture": "uns",
                "context": nodes,
                "measurements": measurements,
                "initial_state": initial_state,
            },
            
            context=normalized_context,
            evidence=[
                EvidenceReference(
                    source="uns",
                    identifier=REACTOR_UNS_PATH,
                )
            ],
        )

    def _run_opcua(
        self,
        objective: str,
        initial_state: dict[str, Any],
    ) -> InvestigationResult:
        nodes = self.client.call_tool(
            "opcua_browse",
            {"node_id": REACTOR_OPCUA_NODE},
            step=1,
            context_acquired=[REACTOR_OPCUA_NODE],
        )

        values = {}

        for step, node in enumerate(nodes["nodes"], start=2):
            node_id = node["node_id"]

            values[node_id] = self.client.call_tool(
                "opcua_read",
                {"node_id": node_id},
                step=step,
                context_consumed=[REACTOR_OPCUA_NODE],
            )

        normalized_context = ContextNormalizer.from_opcua(
            nodes,
            values,
        )

        return InvestigationResult(
            objective=objective,
            conclusion="Acquired reactor context through OPC UA.",
            findings={
                "architecture": "opcua",
                "context": nodes,
                "values": values,
                "initial_state": initial_state,
            },
            context=normalized_context,
            evidence=[
                EvidenceReference(
                    source="opcua",
                    identifier=REACTOR_OPCUA_NODE,
                )
            ],
        )

    def _run_i3x(
        self,
        objective: str,
        initial_state: dict[str, Any],
    ) -> InvestigationResult:
        discovered = self.client.call_tool(
            "i3x_get_objects",
            {},
            step=1,
            context_acquired=["i3x"],
        )

        objects = discovered.get("objects", [])

        reactor = next(
            (
                item
                for item in objects
                if item.get("display_name", "").lower() == "reactor"
            ),
            None,
        )

        if reactor is None:
            raise ValueError("i3X reactor object was not found")

        reactor_id = reactor["element_id"]

        object_info = self.client.call_tool(
            "i3x_get_object",
            {"element_id": reactor_id},
            step=2,
            context_acquired=[reactor_id],
            context_consumed=["i3x"],
        )

        related = self.client.call_tool(
            "i3x_get_related_objects",
            {"element_ids": [reactor_id]},
            step=3,
            context_acquired=[reactor_id],
            context_consumed=["i3x"],
        )

        values = {}

        for step, item in enumerate(
            related.get("related_objects", []),
            start=4,
        ):
            element_id = item["element_id"]

            values[element_id] = self.client.call_tool(
                "i3x_get_value",
                {"element_id": element_id},
                step=step,
                context_consumed=[reactor_id],
            )

        normalized_context = ContextNormalizer.from_i3x(
            object_info,
            related,
            values,
        )

        return InvestigationResult(
            objective=objective,
            conclusion="Acquired reactor context through i3X.",
            findings={
                "architecture": "i3x",
                "discovery": discovered,
                "context": object_info,
                "related_objects": related,
                "values": values,
                "initial_state": initial_state,
            },
            context=normalized_context,
            evidence=[
                EvidenceReference(
                    source="i3x",
                    identifier=reactor_id,
                )
            ],
        )

    def _run_kg(
        self,
        objective: str,
        initial_state: dict[str, Any],
    ) -> InvestigationResult:
        relationships = self.client.call_tool(
            "get_entity_relationships",
            {"entity_id": "urn:icab:equipment:reactor"},
            step=1,
            context_acquired=["urn:icab:equipment:reactor"],
        )
        normalized_context = ContextNormalizer.from_kg(
            relationships,
        )
        return InvestigationResult(
            objective=objective,
            conclusion="Acquired reactor context through the knowledge graph.",
            findings={
                "architecture": "kg",
                "relationships": relationships,
                "initial_state": initial_state,
            },
            context=normalized_context,
            evidence=[
                EvidenceReference(
                    source="kg",
                    identifier="urn:icab:equipment:reactor",
                )
            ],
        )
