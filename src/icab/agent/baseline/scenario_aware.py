"""
The M9 scenario-aware deterministic baseline.

Distinct from ``icab.agent.baseline.structured_retrieval.StructuredRetrievalAgent``
(and ``ContextAwareAgent``/``ArchitectureAwareAgent``): those three are the
*legacy* pre-M5 baselines, hard-coded to the static-prototype canonical
ids/paths, and are kept completely unchanged (see
``icab.experiments.models.DeterministicAgentKind`` and
``docs/research/experiment-plan.md`` for why: running one against a real
``BenchmarkScenario`` was found to silently investigate stale, unrelated
data). This agent is a *new*, separate implementation for exactly that
gap: a fixed, deterministic, non-LLM baseline that DOES see the real
scenario/environment.

Fixed, explicit behavior (no LLM, no randomness):

1. The target equipment's canonical id is resolved from
   ``icab.tep.measurements.REAL_TEP_EQUIPMENT`` -- the same real (not
   legacy) equipment registry ``TEPAdapter``/the UNS/MQTT bridges already
   use, not an invented id.
2. ``browse_uns("site/tep/<equipment_key>")`` -- discovers that
   equipment's real measurement canonical ids from the actual live UNS
   tree (``icab.context.uns.tep_builder``, M4), not a hard-coded list.
3. ``get_current_value`` for each discovered measurement, retrieving
   real, current values from the gateway, in the UNS tree's own
   (deterministic, sorted) order.
4. ``get_entity_relationships`` for that equipment's canonical id.
5. A deterministically-formatted conclusion summarizing the retrieved
   values.

Like the legacy baselines, this is a *fixed* (non-adaptive) strategy: it
always inspects the same equipment regardless of the objective, so it will
legitimately score poorly on a scenario like ``d4_plant_wide_investigation``
whose fault is NOT in the reactor -- by design, as a fixed-strategy control
distinct from an agent that actively discovers where to look.
"""

from __future__ import annotations

from typing import Any

from icab.agent.client import AgentGatewayClient
from icab.agent.interface import Agent, EvidenceReference, InvestigationResult
from icab.tep.measurements import REAL_TEP_EQUIPMENT

DEFAULT_EQUIPMENT_KEY = "reactor"


class ScenarioAwareBaselineAgent(Agent):
    """Fixed, deterministic investigation of one real equipment item's measurements."""

    def __init__(
        self,
        client: AgentGatewayClient,
        *,
        equipment_key: str = DEFAULT_EQUIPMENT_KEY,
    ) -> None:
        if equipment_key not in REAL_TEP_EQUIPMENT:
            raise ValueError(
                f"Unknown equipment key: {equipment_key!r}. "
                f"Valid keys: {sorted(REAL_TEP_EQUIPMENT)}"
            )

        self.client = client
        self.equipment_key = equipment_key
        self.equipment_id, self.equipment_name = REAL_TEP_EQUIPMENT[equipment_key]
        self.equipment_path = f"site/tep/{equipment_key}"

    def run(
        self,
        *,
        objective: str,
        initial_state: dict[str, Any],
    ) -> InvestigationResult:
        nodes_response = self.client.call_tool(
            "browse_uns",
            {"path": self.equipment_path},
            step=1,
            context_acquired=[self.equipment_path],
        )

        measurement_nodes = sorted(
            (
                node
                for node in nodes_response["nodes"]
                if node.get("node_type") == "measurement" and node.get("canonical_id")
            ),
            key=lambda node: node["canonical_id"],
        )

        values: dict[str, Any] = {}

        for step, node in enumerate(measurement_nodes, start=2):
            measurement_id = node["canonical_id"]
            values[measurement_id] = self.client.call_tool(
                "get_current_value",
                {"measurement_id": measurement_id},
                step=step,
                context_acquired=[measurement_id],
                context_consumed=[self.equipment_path],
            )

        relationships = self.client.call_tool(
            "get_entity_relationships",
            {"canonical_id": self.equipment_id},
            step=len(measurement_nodes) + 2,
            context_acquired=[self.equipment_id],
        )

        evidence = [
            EvidenceReference(source="browse_uns", identifier=self.equipment_path),
            EvidenceReference(source="get_entity_relationships", identifier=self.equipment_id),
            *(
                EvidenceReference(source="get_current_value", identifier=measurement_id)
                for measurement_id in values
            ),
        ]

        conclusion = self._build_conclusion(self.equipment_name, values)

        return InvestigationResult(
            objective=objective,
            conclusion=conclusion,
            findings={
                "equipment_key": self.equipment_key,
                "equipment_id": self.equipment_id,
                "uns_nodes": nodes_response,
                "values": values,
                "relationships": relationships,
                "initial_state": initial_state,
            },
            evidence=evidence,
        )

    @staticmethod
    def _build_conclusion(equipment_name: str, values: dict[str, Any]) -> str:
        if not values:
            return f"No measurements were found for {equipment_name}."

        parts = []
        for measurement_id, response in sorted(values.items()):
            observation = (response or {}).get("observation") or {}
            value = observation.get("value")
            unit = observation.get("unit") or ""
            parts.append(f"{measurement_id}={value} {unit}".strip())

        return f"{equipment_name}: " + "; ".join(parts)
