from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from asyncua import Client


@dataclass(frozen=True)
class OPCUANode:
    node_id: str
    display_name: str
    node_class: str


class OPCUAClient:
    """Thin ICAB wrapper around an OPC UA client."""

    def __init__(
        self,
        endpoint_url: str,
        *,
        timeout: float = 30.0,
    ) -> None:
        self.endpoint_url = endpoint_url
        self.timeout = timeout
        self.client = Client(
            url=endpoint_url,
            timeout=timeout,
        )

    async def connect(self) -> None:
        await self.client.connect()

    async def disconnect(self) -> None:
        await self.client.disconnect()

    async def browse(self, node_id: str = "i=85") -> list[OPCUANode]:
        await self.connect()
        try:
            node = self.client.get_node(node_id)
            children = await node.get_children()

            result = []

            for child in children:
                display_name = await child.read_display_name()
                node_class = await child.read_node_class()

                result.append(
                    OPCUANode(
                        node_id=child.nodeid.to_string(),
                        display_name=display_name.Text,
                        node_class=node_class.name,
                    )
                )

            return sorted(result, key=lambda item: item.node_id)
        finally:
            await self.disconnect()

    async def read(self, node_id: str) -> Any:
        await self.connect()
        try:
            node = self.client.get_node(node_id)
            return await node.read_value()
        finally:
            await self.disconnect()
