"""
Long-running, TEP-backed OPC UA server for external consumers -- in
particular the private i3X wrapper (see services/i3x/).

Distinct from:
  * scripts/run_opcua_demo_server.py -- a small, static 3-variable demo
    server that ArchitectureAwareAgent's hard-coded OPC UA path and
    scripts/test_opcua_client.py depend on as-is.
  * tests/integration/test_opcua_tep_server.py -- spins up its own
    short-lived TEPOPCUAServer per test.

This script keeps a TEPOPCUAServer running indefinitely, stepping and
syncing a real TEPSimulator on a wall-clock interval, so external OPC UA
clients (including containers on the ICAB docker-compose network) see a
live, moving TEP-backed process rather than a fixed snapshot.
"""

from __future__ import annotations

import argparse
import asyncio

from icab.context.opcua.tep_server import TEPOPCUAServer
from icab.tep.simulator import TEPSimulator


async def main(endpoint: str, seed: int, step_seconds: float) -> None:
    simulator = TEPSimulator()
    simulator.reset(seed=seed)

    server = TEPOPCUAServer(endpoint)
    await server.start()
    await server.sync_from_simulator(simulator)

    print("ICAB TEP-backed OPC UA server running.")
    print(f"Endpoint:     {endpoint}")
    print(f"Seed:         {seed}")
    print(f"Step interval: {step_seconds}s wall-clock -> "
          f"{simulator.checkpoint_interval}h simulated")

    try:
        while True:
            await asyncio.sleep(step_seconds)
            simulator.step()
            await server.sync_from_simulator(simulator)

            if simulator.terminated:
                print(
                    f"Plant tripped at t={simulator.time:.2f}h "
                    f"({simulator.get_events()[-1]['message']}); resetting."
                )
                simulator.reset(seed=seed)
                await server.sync_from_simulator(simulator)
    finally:
        await server.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--endpoint",
        default="opc.tcp://0.0.0.0:4841/icab/tep/",
        help="OPC UA endpoint to bind (use 0.0.0.0 to accept external/container connections).",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--step-seconds",
        type=float,
        default=2.0,
        help="Wall-clock seconds between simulator steps.",
    )
    args = parser.parse_args()

    asyncio.run(main(args.endpoint, args.seed, args.step_seconds))
