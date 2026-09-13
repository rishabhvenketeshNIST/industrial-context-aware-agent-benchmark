"""
A real, self-hosted OPC UA server whose address space mirrors the real TEP
measurement registry (`icab.tep.measurements`), with variable values kept
in sync with a `TEPSimulator`.

This is deliberately separate from `scripts/run_opcua_demo_server.py`'s
small, static 3-variable demo server (kept as-is -- it backs the existing
`scripts/test_opcua_client.py` smoke test and `ArchitectureAwareAgent`'s
hard-coded demo node id). This server exposes the full real
41-measurement set, one Object per equipment item (mirroring the same
`REAL_TEP_EQUIPMENT` breakdown the MQTT/UNS bridges use) with one Variable
per measurement, and is meant to be driven by `sync_from_simulator` rather
than seeded with fixed demo values.
"""

from __future__ import annotations

from typing import Any

from asyncua import Server

from icab.tep.measurements import REAL_TEP_EQUIPMENT, build_real_tep_variables
from icab.tep.simulator import TEPSimulator

NAMESPACE_URI = "urn:icab:opcua:tep"


class TEPOPCUAServer:
    """Self-hosted OPC UA server backed by a real TEPSimulator."""

    def __init__(self, endpoint: str = "opc.tcp://127.0.0.1:4841/icab/tep/") -> None:
        self.endpoint = endpoint
        self.server: Server | None = None
        self._variable_nodes: dict[str, Any] = {}

    async def start(self) -> None:
        """Initialize the server, build its address space, and start listening."""

        server = Server()
        await server.init()
        server.set_endpoint(self.endpoint)

        namespace_index = await server.register_namespace(NAMESPACE_URI)
        objects = server.nodes.objects

        equipment_key_by_canonical_id = {
            canonical_id: key for key, (canonical_id, _) in REAL_TEP_EQUIPMENT.items()
        }

        equipment_object_nodes = {}
        for equipment_key, (_, display_name) in REAL_TEP_EQUIPMENT.items():
            equipment_object_nodes[equipment_key] = await objects.add_object(
                namespace_index,
                display_name,
            )

        for variable in build_real_tep_variables():
            equipment_key = equipment_key_by_canonical_id[variable.equipment_id]
            equipment_node = equipment_object_nodes[equipment_key]

            variable_node = await equipment_node.add_variable(
                namespace_index,
                variable.name,
                0.0,
            )
            await variable_node.set_writable()

            self._variable_nodes[variable.variable_id] = variable_node

        await server.start()
        self.server = server

    async def stop(self) -> None:
        """Stop the server. Safe to call even if `start()` was never called."""

        if self.server is not None:
            await self.server.stop()
            self.server = None

    async def sync_from_simulator(self, simulator: TEPSimulator) -> None:
        """Write the simulator's current measurements into the address space."""

        measurements = simulator.get_measurements()

        for variable_id, node in self._variable_nodes.items():
            value = measurements.get(variable_id)

            if value is not None:
                await node.write_value(float(value))

    def node_id_for(self, variable_id: str) -> str:
        """Return the OPC UA node id string for a real-measurement variable id."""

        return self._variable_nodes[variable_id].nodeid.to_string()
