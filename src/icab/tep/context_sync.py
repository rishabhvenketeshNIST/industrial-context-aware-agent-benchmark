"""
Synchronizes a real TEPSimulator's current state into ICAB's industrial
context architectures, from one canonical CIMEnvironment snapshot -- so
every architecture agrees on the same canonical IDs, units, timestamps,
and provenance ("source") for the same underlying observation, per the
ICAB architectural principle:

    TEP simulator -> MQTT / Historian / (context) -> UNS / i3X / KG
    -> ICAB Agent Gateway -> agent

This module is the "connect the pipes" piece: it does not invent any new
per-architecture data, it just reuses `TEPAdapter.build_real_environment`
(the single source of truth for the real-simulator CIM projection),
`EnvironmentLoader` (historian + knowledge graph), and
`TEPMeasurementPublisher` (MQTT) together.

UNS is intentionally not resynced here: `icab.context.uns.tep_builder`
builds a static node tree (the hierarchy itself never changes as the
simulator steps -- only the values do, which historian/MQTT/KG already
carry), loaded once into the gateway's UNS repository at startup.
"""

from __future__ import annotations

from icab.cim import CIMEnvironment
from icab.context.environment_loader import EnvironmentLoader
from icab.context.mqtt.publisher import TEPMeasurementPublisher

from .adapter import TEPAdapter
from .simulator import TEPSimulator


class TEPContextSync:
    """Pushes one TEPSimulator snapshot into every configured context architecture."""

    def __init__(
        self,
        *,
        environment_loader: EnvironmentLoader,
        mqtt_publisher: TEPMeasurementPublisher | None = None,
        adapter: TEPAdapter | None = None,
    ) -> None:
        self.environment_loader = environment_loader
        self.mqtt_publisher = mqtt_publisher
        self.adapter = adapter or TEPAdapter()

    def sync(self, simulator: TEPSimulator) -> CIMEnvironment:
        """
        Build a CIM environment from the simulator's current state and load
        it into the historian and knowledge graph (and, if configured,
        publish it to MQTT). Returns the environment that was loaded.
        """

        state = simulator.get_state()
        environment = self.adapter.build_real_environment(state)

        self.environment_loader.load(environment)

        if self.mqtt_publisher is not None:
            self.mqtt_publisher.publish_state(simulator)

        return environment
