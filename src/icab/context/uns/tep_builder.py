"""
Builds ICAB UNS nodes for the real, 41-measurement TEP kernel exposed by
:class:`icab.tep.simulator.TEPSimulator`.

Mirrors the explicit, prefix-based equipment mapping
``icab.context.mqtt.topics``/``icab.tep.measurements`` already use for MQTT
topics and CIM equipment assignment, so the UNS tree, MQTT namespace, and
knowledge-graph equipment nodes all agree on the same equipment breakdown
-- rather than re-deriving a (possibly inconsistent) hierarchy from a
generic graph walk.
"""

from icab.tep.adapter import TEPAdapter
from icab.tep.measurements import (
    REAL_TEP_EQUIPMENT,
    build_real_tep_manipulated_variables,
    build_real_tep_variables,
)

from .models import UNSNode

#: Root path for the real TEP equipment/measurement tree, consistent with
#: the site path the static prototype UNS tree already uses ("site/tep").
SITE_PATH = "site/tep"


def build_real_uns_nodes() -> list[UNSNode]:
    """Build the full site/equipment/measurement UNS tree for the real TEP kernel."""

    nodes = [
        UNSNode(
            path=SITE_PATH,
            display_name="Tennessee Eastman Process",
            node_type="site",
            canonical_id=TEPAdapter.SITE_ID,
        )
    ]

    equipment_key_by_canonical_id = {
        canonical_id: key for key, (canonical_id, _) in REAL_TEP_EQUIPMENT.items()
    }

    for equipment_key, (canonical_id, display_name) in REAL_TEP_EQUIPMENT.items():
        nodes.append(
            UNSNode(
                path=f"{SITE_PATH}/{equipment_key}",
                display_name=display_name,
                node_type="equipment",
                canonical_id=canonical_id,
            )
        )

    for variable in build_real_tep_variables():
        equipment_key = equipment_key_by_canonical_id[variable.equipment_id]

        nodes.append(
            UNSNode(
                path=f"{SITE_PATH}/{equipment_key}/{variable.variable_id.lower()}",
                display_name=variable.name,
                node_type="measurement",
                canonical_id=variable.canonical_id,
            )
        )

    # M13-A: manipulated variables (actuators) -- discoverable in the UNS
    # tree alongside the equipment/measurements they belong to, same as
    # the knowledge graph's ACTUATES relationships. Structural/identity
    # only: browse_uns never returns a live value, so this adds no
    # requirement for a current-value source (see
    # icab.tep.measurements.build_real_tep_manipulated_variables).
    for mv in build_real_tep_manipulated_variables():
        equipment_key = equipment_key_by_canonical_id[mv.equipment_id]

        nodes.append(
            UNSNode(
                path=f"{SITE_PATH}/{equipment_key}/{mv.variable_id.lower()}",
                display_name=mv.name,
                node_type="actuator",
                canonical_id=mv.canonical_id,
            )
        )

    return nodes
