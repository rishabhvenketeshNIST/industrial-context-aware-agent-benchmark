from typing import Any

from icab.agent.client import AgentGatewayClient
from icab.agent.interface import Agent, EvidenceReference, InvestigationResult

REACTOR_ID = "urn:icab:equipment:reactor"
REACTOR_UNS_PATH = "site/tep/reaction/reactor"


class ContextAwareAgent(Agent):
    """Agent that discovers reactor measurements through the UNS."""

    def __init__(self, client: AgentGatewayClient) -> None:
        self.client = client

    def run(
        self,
        *,
        objective: str,
        initial_state: dict[str, Any],
    ) -> InvestigationResult:
        """Discover measurements through UNS and retrieve their current values."""

        uns_nodes = self.client.call_tool(
            "browse_uns",
            {"path": REACTOR_UNS_PATH},
            step=1,
            context_acquired=[REACTOR_UNS_PATH],
        )

        measurement_ids = [
            node["canonical_id"]
            for node in uns_nodes["nodes"]
            if node["node_type"] == "measurement" and node["canonical_id"] is not None
        ]

        measurements = {}

        for step, measurement_id in enumerate(measurement_ids, start=2):
            measurements[measurement_id] = self.client.call_tool(
                "get_current_value",
                {"measurement_id": measurement_id},
                step=step,
            )

        return InvestigationResult(
            objective=objective,
            conclusion=(
                f"Discovered {len(measurement_ids)} reactor "
                "measurements through the UNS."
            ),
            findings={
                "uns_nodes": uns_nodes,
                "measurements": measurements,
                "initial_state": initial_state,
            },
            evidence=[
                EvidenceReference(
                    source="uns",
                    identifier=REACTOR_UNS_PATH,
                ),
                *[
                    EvidenceReference(
                        source="historian",
                        identifier=measurement_id,
                    )
                    for measurement_id in measurement_ids
                ],
            ],
        )
