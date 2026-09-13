import asyncio

from asyncua import Server


async def main() -> None:
    server = Server()
    await server.init()

    server.set_endpoint("opc.tcp://127.0.0.1:4840/icab/")

    uri = "urn:icab:opcua"
    idx = await server.register_namespace(uri)

    objects = server.nodes.objects

    reactor = await objects.add_object(idx, "Reactor")

    pressure = await reactor.add_variable(idx, "Pressure", 2834.0)
    temperature = await reactor.add_variable(idx, "Temperature", 120.0)
    level = await reactor.add_variable(idx, "Level", 50.0)

    print("ICAB OPC UA demo server starting...")
    print("Endpoint: opc.tcp://127.0.0.1:4840/icab/")
    print(f"Pressure:    {pressure.nodeid}")
    print(f"Temperature: {temperature.nodeid}")
    print(f"Level:       {level.nodeid}")

    await server.start()

    print("ICAB OPC UA demo server is running.")

    try:
        while True:
            await asyncio.sleep(1)
    finally:
        await server.stop()


if __name__ == "__main__":
    asyncio.run(main())
