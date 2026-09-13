from unittest.mock import AsyncMock, Mock

import pytest

from icab.context.opcua.client import OPCUAClient


@pytest.mark.asyncio
async def test_opcua_client_browse():
    client = OPCUAClient.__new__(OPCUAClient)

    child = Mock()
    child.nodeid.to_string.return_value = "ns=2;s=Reactor.Pressure"

    display_name = Mock()
    display_name.Text = "Reactor Pressure"

    node_class = Mock()
    node_class.name = "Variable"

    child.read_display_name = AsyncMock(return_value=display_name)
    child.read_node_class = AsyncMock(return_value=node_class)

    root = Mock()
    root.get_children = AsyncMock(return_value=[child])

    client.client = Mock()
    client.client.connect = AsyncMock()
    client.client.disconnect = AsyncMock()
    client.client.get_node.return_value = root

    result = await client.browse("i=85")

    assert len(result) == 1
    assert result[0].node_id == "ns=2;s=Reactor.Pressure"
    assert result[0].display_name == "Reactor Pressure"
    assert result[0].node_class == "Variable"


@pytest.mark.asyncio
async def test_opcua_client_read():
    client = OPCUAClient.__new__(OPCUAClient)

    node = Mock()
    node.read_value = AsyncMock(return_value=2834.0)

    client.client = Mock()
    client.client.connect = AsyncMock()
    client.client.disconnect = AsyncMock()
    client.client.get_node.return_value = node

    result = await client.read("ns=2;s=Reactor.Pressure")

    assert result == 2834.0


@pytest.mark.asyncio
async def test_opcua_client_connect_and_disconnect():
    client = OPCUAClient.__new__(OPCUAClient)

    client.client = Mock()
    client.client.connect = AsyncMock()
    client.client.disconnect = AsyncMock()

    await client.connect()
    await client.disconnect()

    client.client.connect.assert_awaited_once()
    client.client.disconnect.assert_awaited_once()
