import asyncio

from icab.context.opcua import OPCUAClient


async def main() -> None:
    client = OPCUAClient("opc.tcp://localhost:4840/icab/")

    nodes = await client.browse("i=85")

    print("Browsed nodes:")
    for node in nodes:
        print(f"  {node.node_id} | {node.display_name} | {node.node_class}")

    print()
    print("Values:")
    print("  Pressure:", await client.read("ns=2;i=2"))
    print("  Temperature:", await client.read("ns=2;i=3"))
    print("  Level:", await client.read("ns=2;i=4"))


if __name__ == "__main__":
    asyncio.run(main())
