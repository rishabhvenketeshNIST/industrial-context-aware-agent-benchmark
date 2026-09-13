"""
Integration test for the M4 OPC UA data flow:

    TEP simulator -> TEPOPCUAServer (real, self-hosted asyncua server)
                  -> OPCUAClient (real OPC UA connection over TCP)

Confirms the server's address space is discoverable (browsable by
equipment) and that its values are actually the simulator's, not
fabricated/static demo values.
"""

import pytest

from icab.context.opcua import OPCUAClient, TEPOPCUAServer
from icab.tep.measurements import build_real_tep_variables
from icab.tep.simulator import TEPSimulator

ENDPOINT = "opc.tcp://127.0.0.1:4841/icab/tep/"


@pytest.mark.asyncio
async def test_tep_opcua_server_exposes_equipment_and_measurements():
    simulator = TEPSimulator()
    simulator.reset(seed=3)

    server = TEPOPCUAServer(ENDPOINT)
    await server.start()

    try:
        await server.sync_from_simulator(simulator)

        client = OPCUAClient(ENDPOINT)

        top_level = await client.browse("i=85")  # the standard Objects folder
        display_names = {node.display_name for node in top_level}

        assert "Reactor" in display_names
        assert "Separator" in display_names
        assert "Stripper" in display_names

        reactor_object_id = next(
            node.node_id for node in top_level if node.display_name == "Reactor"
        )
        reactor_children = await client.browse(reactor_object_id)
        reactor_variable_names = {node.display_name for node in reactor_children}

        expected_reactor_pressure_name = next(
            variable.name
            for variable in build_real_tep_variables()
            if variable.variable_id == "REACTOR_PRESSURE"
        )
        assert expected_reactor_pressure_name in reactor_variable_names

        reactor_pressure_node_id = server.node_id_for("REACTOR_PRESSURE")
        value = await client.read(reactor_pressure_node_id)

        assert value == pytest.approx(
            simulator.get_measurements()["REACTOR_PRESSURE"],
            rel=1e-9,
        )
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_tep_opcua_server_values_track_simulator_steps():
    simulator = TEPSimulator()
    simulator.reset(seed=4)

    server = TEPOPCUAServer(ENDPOINT)
    await server.start()

    try:
        await server.sync_from_simulator(simulator)

        client = OPCUAClient(ENDPOINT)
        node_id = server.node_id_for("REACTOR_TEMPERATURE")

        first_reading = await client.read(node_id)
        assert first_reading == pytest.approx(
            simulator.get_measurements()["REACTOR_TEMPERATURE"], rel=1e-9
        )

        simulator.inject_fault("idv_04")  # reactor cooling water inlet temperature
        for _ in range(20):
            simulator.step()

        await server.sync_from_simulator(simulator)

        second_reading = await client.read(node_id)
        assert second_reading == pytest.approx(
            simulator.get_measurements()["REACTOR_TEMPERATURE"], rel=1e-9
        )
        assert second_reading != first_reading
    finally:
        await server.stop()
