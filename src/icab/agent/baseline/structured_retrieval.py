from typing import Any

from icab.agent.client import AgentGatewayClient
from icab.agent.interface import Agent, EvidenceReference, InvestigationResult

REACTOR_PRESSURE_ID = "urn:icab:measurement:tep_pv_reactor_pressure"
REACTOR_ID = "urn:icab:equipment:reactor"


class StructuredRetrievalAgent(Agent):
    """Minimal deterministic agent using structured industrial context."""

    def __init__(self, client: AgentGatewayClient) -> None:
        self.client = client

    def run(
        self,
        *,
        objective: str,
        initial_state: dict[str, Any],
    ) -> InvestigationResult:
        """Run a minimal context-aware investigation."""

        pressure = self.client.call_tool(
            "get_current_value",
            {"measurement_id": REACTOR_PRESSURE_ID},
            step=1,
        )

        relationships = self.client.call_tool(
            "get_entity_relationships",
            {"canonical_id": REACTOR_ID},
            step=2,
        )

        pressure_value = pressure["observation"]["value"]
        pressure_unit = pressure["observation"]["unit"]

        conclusion = f"Current reactor pressure is {pressure_value} {pressure_unit}."

        return InvestigationResult(
            objective=objective,
            conclusion=conclusion,
            findings={
                "reactor_pressure": pressure,
                "reactor_relationships": relationships,
                "initial_state": initial_state,
            },
            evidence=[
                EvidenceReference(
                    source="historian",
                    identifier=REACTOR_PRESSURE_ID,
                ),
                EvidenceReference(
                    source="knowledge_graph",
                    identifier=REACTOR_ID,
                ),
            ],
        )
